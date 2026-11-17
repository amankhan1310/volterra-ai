"""Request guard (pure ASGI middleware): body-size limit, rate limits and security headers.

**Rate limits are process-local and in memory.** Counters live in this process only: they reset
when the process restarts, and with several instances or workers each one counts separately (a
client could make N times the requests across N instances). They protect a small single-instance
deployment against bursts and accidental loops; they are not durable or distributed. The durable
protection for stored data is the scenario limits, which the database enforces (see
``SqlRepository.create_scenario``).

**Request classes** (fixed one-minute windows):

* ``read`` - GET/HEAD/OPTIONS: per client;
* ``calc`` - ``POST /batteries/{id}/simulate``, a pure calculation that stores nothing: per client
  and for all clients together (protects CPU), and it never uses the write budgets;
* ``write`` - every other POST/PUT/PATCH/DELETE (scenario create, rename, delete): per client and
  for all clients together.

The all-clients limits ignore client identity, so rotating identities cannot bypass them. Health
endpoints are exempt, so the hosting platform's health checks are never throttled.

**Client identity** (who a per-client limit belongs to):

1. A request with a valid signed session cookie (:mod:`app.core.sessions`) is identified by its
   session. Cookies cannot be forged (HMAC), so each browser has its own allowance even when many
   visitors reach the API through the same proxy address (e.g. a shared Vercel edge).
2. Any other request (no cookie, or a forged/expired one: scripts, a browser's very first
   request) is identified by its network address: an entry of ``X-Forwarded-For`` counted from the
   right (``trusted_proxy_hops``; 0 = the right-most entry, which the hosting provider's proxy
   appends and a client cannot forge), or the socket peer when the header is absent.

So that browsers have a session from their first response, the guard issues the session cookie on
API responses to requests without a valid one (when rate limiting or session scenarios are on).
Minting new sessions requires cookie-less requests, which count against the network address, so
discarding cookies does not escape the per-client limits.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Literal

from app.core.config import API_PREFIX, Settings
from app.core.sessions import COOKIE_NAME, SESSION_STATE_KEY, SessionSigner, cookie_header

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
RequestClass = Literal["read", "calc", "write"]

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
#: Pure calculations: POST only because the parameters are a JSON body; nothing is stored.
CALC_PATHS = (re.compile(rf"^{re.escape(API_PREFIX)}/batteries/[^/]+/simulate$"),)
WINDOW_SECONDS = 60
MAX_TRACKED_KEYS = 10_000
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
]


def request_class(method: str, path: str) -> RequestClass:
    if method not in WRITE_METHODS:
        return "read"
    if method == "POST" and any(p.match(path) for p in CALC_PATHS):
        return "calc"
    return "write"


def network_key(scope: Scope, trusted_proxy_hops: int) -> str:
    """The network address used for requests without a session (see the module docstring)."""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            raw: str = bytes(value).decode("latin-1")
            entries = [e.strip() for e in raw.split(",") if e.strip()]
            if entries:
                return entries[max(0, len(entries) - 1 - trusted_proxy_hops)]
    client = scope.get("client")
    return str(client[0]) if client else "unknown"


# Backwards-compatible name used by earlier tests and documentation.
client_key = network_key


def session_cookie(scope: Scope) -> str | None:
    """The raw ``volterra_session`` cookie value of a request, if any."""
    for name, value in scope.get("headers", []):
        if name == b"cookie":
            for part in bytes(value).decode("latin-1").split(";"):
                key, _, val = part.strip().partition("=")
                if key == COOKIE_NAME:
                    return val
    return None


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
        self,
        app: ASGIApp,
        settings: Settings,
        signer: SessionSigner,
        clock: Callable[[], float] = _monotonic,
    ) -> None:
        self.app = app
        self.signer = signer
        self.max_body = settings.max_body_bytes
        self.hops = settings.trusted_proxy_hops
        self.enabled = settings.effective_rate_limit
        self.issue_sessions = self.enabled or settings.effective_scenario_access == "session"
        self.secure_cookie = settings.environment == "production"
        self.per_client: dict[RequestClass, FixedWindowCounter] = {
            "read": FixedWindowCounter(settings.rate_limit_reads_per_minute, clock),
            "calc": FixedWindowCounter(settings.rate_limit_calc_per_minute, clock),
            "write": FixedWindowCounter(settings.rate_limit_writes_per_minute, clock),
        }
        self.all_clients: dict[RequestClass, FixedWindowCounter] = {
            "calc": FixedWindowCounter(settings.rate_limit_global_calc_per_minute, clock),
            "write": FixedWindowCounter(settings.rate_limit_global_writes_per_minute, clock),
        }

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
        kind = request_class(method, path)
        is_api = path.startswith(f"{API_PREFIX}/")
        exempt = path.startswith(f"{API_PREFIX}/health")

        session_id = self.signer.verify(session_cookie(scope))
        issued: str | None = None
        if session_id is None and is_api and not exempt and self.issue_sessions:
            session_id, issued = self.signer.issue()
            # The route sees the session issued with this response (scenario ownership).
            scope.setdefault("state", {})[SESSION_STATE_KEY] = session_id
            identity = f"net:{network_key(scope, self.hops)}"
        elif session_id is not None:
            identity = f"session:{session_id.hex}"
        else:
            identity = f"net:{network_key(scope, self.hops)}"

        if self.enabled and not exempt:
            wait = self.per_client[kind].hit(identity)
            if wait is None and kind in self.all_clients:
                wait = self.all_clients[kind].hit("*")
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

        if kind != "read":
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

        no_store = "/scenarios" in path or issued is not None
        set_cookie = (
            cookie_header(issued, secure=self.secure_cookie).encode("latin-1") if issued else None
        )

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", [])) + SECURITY_HEADERS
                if no_store:
                    headers.append((b"cache-control", b"no-store"))
                if set_cookie is not None:
                    headers.append((b"set-cookie", set_cookie))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
