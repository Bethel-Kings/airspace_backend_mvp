"""Minimal in-memory sliding-window rate limiter.

Per-process only: fine for a single Render instance. If you scale to several
instances, move this to Redis (or put limits at a gateway/CDN).
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._calls += 1
            if self._calls % 1000 == 0:  # occasional sweep so idle keys don't pile up
                for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - 3600]:
                    del self._hits[k]
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry_after = int(window_seconds - (now - q[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            q.append(now)


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def ip_limit(scope: str, limit: int, window_seconds: int):
    def dependency(request: Request) -> None:
        limiter.check(f"{scope}:ip:{client_ip(request)}", limit, window_seconds)

    return dependency
