"""Anonymous browser sessions that own saved scenarios (no user accounts).

A session id is 128 bits from the operating system's CSPRNG (:func:`secrets.token_bytes`). The
cookie value is ``<id hex>.<HMAC-SHA256(secret, id)>``, so it cannot be forged or altered
without the server's secret; verification uses a constant-time comparison. Holding a valid
cookie is what authorises reading and changing that session's scenarios.

Cookie attributes: ``HttpOnly`` (not readable by scripts), ``SameSite=Lax`` (not sent with
cross-site POST/PATCH/DELETE), ``Secure`` in production, ``Path=/api/v1``, 30 days.

CSRF: in addition to ``SameSite=Lax``, every cookie-authenticated write must carry the custom
header ``X-Volterra-Client: web``. Browsers cannot attach a custom header to a cross-site request
without a CORS preflight, and the API's CORS allow-list rejects other origins. When an ``Origin``
header is present it must be the API's own origin, its forwarded origin, or an allowed origin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid

from fastapi import Request, Response

from app.core.config import Settings
from app.core.errors import ApiError

COOKIE_NAME = "volterra_session"
COOKIE_MAX_AGE = 30 * 24 * 3600
COOKIE_PATH = "/api/v1"
CSRF_HEADER = "x-volterra-client"
CSRF_VALUE = "web"
#: ``request.state`` key: the session issued by the request guard with the current response.
SESSION_STATE_KEY = "volterra_session_id"
_CONTEXT = b"volterra-scenario-session-v1:"


class SessionSigner:
    """Issues and verifies signed session cookies."""

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("session secret must be at least 32 bytes")
        self._secret = secret

    @classmethod
    def from_settings(cls, settings: Settings) -> SessionSigner:
        if settings.session_secret is not None:
            return cls(settings.session_secret.get_secret_value().encode("utf-8"))
        return cls(secrets.token_bytes(32))  # development/test: valid for this process only

    def _sign(self, session_id: uuid.UUID) -> str:
        mac = hmac.new(self._secret, _CONTEXT + session_id.bytes, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")

    def issue(self) -> tuple[uuid.UUID, str]:
        session_id = uuid.UUID(bytes=secrets.token_bytes(16), version=4)
        return session_id, f"{session_id.hex}.{self._sign(session_id)}"

    def verify(self, value: str | None) -> uuid.UUID | None:
        """The session id of a valid cookie value, else ``None`` (never raises)."""
        if not value or len(value) > 128 or value.count(".") != 1:
            return None
        id_hex, signature = value.split(".")
        try:
            session_id = uuid.UUID(hex=id_hex)
        except ValueError:
            return None
        if session_id.hex != id_hex:
            return None
        return session_id if hmac.compare_digest(signature, self._sign(session_id)) else None


def cookie_header(value: str, *, secure: bool) -> str:
    """The ``Set-Cookie`` value for a session (same attributes as :func:`set_session_cookie`)."""
    attributes = f"; HttpOnly; Max-Age={COOKIE_MAX_AGE}; Path={COOKIE_PATH}; SameSite=lax"
    return f"{COOKIE_NAME}={value}{attributes}{'; Secure' if secure else ''}"


def request_session(request: Request, signer: SessionSigner) -> uuid.UUID | None:
    """The request's session: a valid cookie, or the one the guard issued with this response."""
    session_id = signer.verify(request.cookies.get(COOKIE_NAME))
    if session_id is not None:
        return session_id
    issued = getattr(request.state, SESSION_STATE_KEY, None)
    return issued if isinstance(issued, uuid.UUID) else None


def set_session_cookie(response: Response, value: str, *, secure: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE,
        path=COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def check_csrf(request: Request, settings: Settings) -> None:
    """Reject writes that a cross-site page could have triggered (403 ``csrf_rejected``)."""
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise ApiError(403, "csrf_rejected", "Missing or invalid X-Volterra-Client header")
    origin = request.headers.get("origin")
    if origin is None:
        return
    allowed = set(settings.cors_origin_list)
    allowed.add(f"{request.url.scheme}://{request.url.netloc}")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        proto = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip()
        allowed.add(f"{proto}://{forwarded_host.split(',')[0].strip()}")
    if origin not in allowed:
        raise ApiError(403, "csrf_rejected", "Request origin is not allowed")
