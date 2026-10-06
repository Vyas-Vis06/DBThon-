"""Password hashing, opaque session tokens, and login throttling. No database access here."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

import bcrypt

MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_BYTES = 72  # bcrypt ignores (and bcrypt>=5 rejects) anything longer; refuse rather than truncate


def validate_password_strength(password: str) -> None:
    """Raise ValueError with a user-readable message when the password is unacceptable."""
    if len(password) < MIN_PASSWORD_CHARS:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_CHARS} characters long.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long.")
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        raise ValueError("Password must mix upper and lower case letters and include a digit.")


def hash_password(password: str, rounds: int = 12) -> str:
    validate_password_strength(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # malformed stored hash must never raise into the login path
        return False


# A real bcrypt hash of a random value, verified when the e-mail is unknown so that "no such user" and
# "wrong password" take the same time (no account enumeration by timing). Built lazily at the cost used.
_dummy: dict[int, str] = {}


def dummy_verify(password: str, rounds: int = 12) -> None:
    if rounds not in _dummy:
        _dummy[rounds] = bcrypt.hashpw(secrets.token_bytes(16), bcrypt.gensalt(rounds=rounds)).decode("ascii")
    verify_password(password, _dummy[rounds])


def new_token() -> str:
    """256-bit URL-safe random session token (goes into the cookie; never stored)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    """What the database stores. SHA-256 is enough because the input already has 256 bits of entropy."""
    return hashlib.sha256(token.encode("ascii")).digest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class SlidingWindowLimiter:
    """Per-key attempt limiter held in process memory (per-IP login throttle).

    Ceiling: one process only; behind several workers each keeps its own window. The per-account lockout stored
    in the database is the authoritative brake; this only slows a single address that probes many accounts.
    """

    def __init__(self, max_attempts: int, window_seconds: float) -> None:
        self.max_attempts, self.window = max_attempts, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.max_attempts:
            return False
        hits.append(now)
        return True
