"""Request dependencies: owner identity cookie, mutation guard, rate limits."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import Request, Response

from app.sessions.service import ApiProblem
from app.state import AppState

OWNER_COOKIE = "cc_owner"
MUTATION_HEADER = "x-clipcart-request"


def state_of(request: Request) -> AppState:
    return request.app.state.clipcart


def owner_from_token(token: str) -> str:
    return "own_" + hashlib.sha256(token.encode()).hexdigest()[:32]


def current_owner(request: Request) -> str:
    tok = request.cookies.get(OWNER_COOKIE)
    if not tok or len(tok) < 20:
        raise ApiProblem(401, "no_session", "No shopping session; reload the page")
    return owner_from_token(tok)


def ensure_owner(request: Request, response: Response) -> str:
    tok = request.cookies.get(OWNER_COOKIE)
    if not tok or len(tok) < 20:
        tok = secrets.token_urlsafe(32)
        st = state_of(request)
        response.set_cookie(
            OWNER_COOKIE, tok, httponly=True, samesite="lax", secure=st.settings.cookie_secure, max_age=60 * 60 * 24 * 30
        )
    return owner_from_token(tok)


def require_mutation_header(request: Request) -> None:
    """A custom header cannot be sent cross-site without a CORS preflight, which we never allow."""
    if request.headers.get(MUTATION_HEADER) != "1":
        raise ApiProblem(403, "missing_request_header", "Mutating requests must come from the ClipCart app")


class RateLimiter:
    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, owner: str, action: str, limit: int, window_s: float = 600) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[(owner, action)]
            while q and now - q[0] > window_s:
                q.popleft()
            if len(q) >= limit:
                raise ApiProblem(429, "rate_limited", f"Too many {action} requests; try again shortly", retryable=True)
            q.append(now)


limiter = RateLimiter()
