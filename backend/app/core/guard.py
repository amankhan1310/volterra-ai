"""Request guard (pure ASGI middleware): body-size limit, rate limits and security headers.

**Rate limits are process-local and in memory.** Counters live in this process only: they reset
when the process restarts, and with several instances or workers each one counts separately (a
client could make N times the requests across N instances). They protect a small single-instance
deployment against bursts and accidental loops; they are not durable or distributed. The durable
protection for stored data is the scenario limits, which the database enforces (see
``SqlRepository.create_scenario``).

Limits (fixed one-minute windows):

* per client key: reads (GET/HEAD/OPTIONS) and writes (POST/PATCH/PUT/DELETE) separately;
* all clients together: writes only, so rotating client keys cannot bypass it;
* health endpoints are exempt, so the hosting platform's health checks are never throttled.

The client key is an entry of ``X-Forwarded-For`` counted from the right (``trusted_proxy_hops``;
0 = the right-most entry, which the hosting provider's proxy appends and a client cannot forge),
or the socket peer when the header is absent.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from app.core.config import API_PREFIX, Settings

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WINDOW_SECONDS = 60
MAX_TRACKED_KEYS = 10_000
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
]


def client_key(scope: Scope, trusted_proxy_hops: int) -> str:
    """The rate-limit key of a request (see the module docstring)."""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            raw: str = bytes(value).decode("latin-1")
            entries = [e.strip() for e in raw.split(",") if e.strip()]
            if entries:
                return entries[max(0, len(entries) - 1 - trusted_proxy_hops)]
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


def _monotonic() -> float:
    """Looked up at call time, so tests can patch time.monotonic."""
    return time.monotonic()


class FixedWindowCounter:
    """Counts events per key in fixed windows; bounded memory (oldest windows are dropped)."""

    def __init__(self, limit: int, clock: Callable[[], float] = _monotonic) -> None:
        self.limit = limit
        self._clock = clock
        self._counts: dict[str, tuple[int, int]] = {}

    def hit(self, key: str) -> float | None:
        """Record one event; ``None`` if allowed, else seconds until the window resets."""
        now = self._clock()
        window = int(now // WINDOW_SECONDS)
        start, count = self._counts.get(key, (window, 0))
        if start != window:
            start, count = window, 0
        if count >= self.limit:
            return (start + 1) * WINDOW_SECONDS - now
        if key not in self._counts and len(self._counts) >= MAX_TRACKED_KEYS:
            self._counts = {k: v for k, v in self._counts.items() if v[0] == window}
        self._counts[key] = (start, count + 1)
        return None


def _error(
    status: int, code: str, message: str, extra: list[tuple[bytes, bytes]]
) -> tuple[Message, Message]:
    body = json.dumps({"error": {"code": code, "message": message}}).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    return (
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers + extra + SECURITY_HEADERS,
        },
        {"type": "http.response.body", "body": body},
    )


class RequestGuard:
    def __init__(
        self, app: ASGIApp, settings: Settings, clock: Callable[[], float] = _monotonic
    ) -> None:
        self.app = app
        self.max_body = settings.max_body_bytes
        self.hops = settings.trusted_proxy_hops
        self.enabled = settings.effective_rate_limit
        self.reads = FixedWindowCounter(settings.rate_limit_reads_per_minute, clock)
        self.writes = FixedWindowCounter(settings.rate_limit_writes_per_minute, clock)
        self.global_writes = FixedWindowCounter(settings.rate_limit_global_writes_per_minute, clock)

    async def _reject(
        self,
        send: Send,
        status: int,
        code: str,
        message: str,
        extra: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        start, body = _error(status, code, message, extra or [])
        await send(start)
        await send(body)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        write = method in WRITE_METHODS

        if self.enabled and not path.startswith(f"{API_PREFIX}/health"):
            wait = (
                self.writes.hit(client_key(scope, self.hops))
                if write
                else self.reads.hit(client_key(scope, self.hops))
            )
            if wait is None and write:
                wait = self.global_writes.hit("*")
            if wait is not None:
                retry = str(max(1, math.ceil(wait))).encode()
                await self._reject(
                    send,
                    429,
                    "rate_limited",
                    "Too many requests; please retry later",
                    [(b"retry-after", retry)],
                )
                return

        if write:
            # Read the whole body (bounded) before the app sees it; works with chunked bodies too.
            for name, value in scope.get("headers", []):
                if name == b"content-length" and value.isdigit() and int(value) > self.max_body:
                    await self._reject(send, 413, "payload_too_large", "Request body is too large")
                    return
            chunks: list[bytes] = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_body:
                    await self._reject(send, 413, "payload_too_large", "Request body is too large")
                    return
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            replayed = False

            async def replay() -> Message:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            receive = replay

        no_store = "/scenarios" in path

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", [])) + SECURITY_HEADERS
                if no_store:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
