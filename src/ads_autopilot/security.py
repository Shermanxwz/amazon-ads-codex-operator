from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
import threading
from typing import Any

UTC = timezone.utc


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("control password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def constant_token_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(str(left), str(right))


@dataclass
class Session:
    sid: str
    csrf: str
    expires_at: datetime


class SessionStore:
    def __init__(self, ttl_seconds: int = 43200, max_sessions: int = 8):
        self.ttl_seconds = max(300, int(ttl_seconds))
        self.max_sessions = max(1, int(max_sessions))
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _cleanup(self) -> None:
        now = datetime.now(UTC)
        for sid in [k for k, v in self._sessions.items() if v.expires_at <= now]:
            self._sessions.pop(sid, None)

    def create(self) -> tuple[str, str]:
        with self._lock:
            self._cleanup()
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.values(), key=lambda x: x.expires_at)
                self._sessions.pop(oldest.sid, None)
            sid = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            self._sessions[sid] = Session(sid, csrf, datetime.now(UTC) + timedelta(seconds=self.ttl_seconds))
            return sid, csrf

    def validate(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        with self._lock:
            self._cleanup()
            return self._sessions.get(sid)

    def revoke(self, sid: str | None) -> None:
        if not sid:
            return
        with self._lock:
            self._sessions.pop(sid, None)

    def revoke_all(self) -> None:
        with self._lock:
            self._sessions.clear()


class LoginRateLimiter:
    def __init__(self, max_failures: int = 8, window_seconds: int = 300, block_seconds: int = 900):
        self.max_failures = max(1, int(max_failures))
        self.window_seconds = max(10, int(window_seconds))
        self.block_seconds = max(10, int(block_seconds))
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def allowed(self, key: str) -> tuple[bool, int]:
        now = datetime.now(UTC).timestamp()
        with self._lock:
            row = self._state.get(key)
            if not row:
                return True, 0
            blocked_until = float(row.get("blocked_until") or 0)
            if blocked_until > now:
                return False, max(1, int(blocked_until - now))
            if now - float(row.get("window_start") or now) > self.window_seconds:
                self._state.pop(key, None)
            return True, 0

    def failure(self, key: str) -> tuple[bool, int]:
        now = datetime.now(UTC).timestamp()
        with self._lock:
            row = self._state.setdefault(key, {"window_start": now, "failures": 0, "blocked_until": 0})
            if now - float(row["window_start"]) > self.window_seconds:
                row.update(window_start=now, failures=0, blocked_until=0)
            row["failures"] = int(row.get("failures") or 0) + 1
            if row["failures"] >= self.max_failures:
                row["blocked_until"] = now + self.block_seconds
                return False, self.block_seconds
            return True, 0

    def success(self, key: str) -> None:
        with self._lock:
            self._state.pop(key, None)
