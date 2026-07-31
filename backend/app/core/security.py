"""
Security Primitives
===================

Password hashing, session tokens and first-run setup codes for the single
operator credential.

Standard library only. The appliance ships without a crypto dependency and the
box it runs on has no outbound network, so nothing can be added at install time.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional

# scrypt work factors. They are written into every stored hash, so raising them
# later leaves existing passwords verifiable.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SCRYPT_SALT_BYTES = 32
# scrypt allocates 128 * N * r * p bytes; passed explicitly so raising N later
# does not silently hit OpenSSL's implicit 32 MiB ceiling.
SCRYPT_MAXMEM = 128 * 1024 * 1024

PASSWORD_SCHEME = "scrypt"

# A session must never expire mid-show: 30 days, refreshed whenever the operator
# is active.
TOKEN_LIFETIME_SECONDS = 30 * 24 * 60 * 60
TOKEN_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60
TOKEN_SUBJECT = "operator"

# Unambiguous when read off a console and typed on a phone: no 0/O, 1/I/L.
SETUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SETUP_CODE_GROUPS = 3
SETUP_CODE_GROUP_LENGTH = 4


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def constant_time_compare(left: str, right: str) -> bool:
    """Compare two strings without leaking their contents through timing."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash an operator password into a self-describing string.

    Format: ``scrypt$n$r$p$salt_b64$hash_b64`` - the parameters travel with the
    hash so they can be raised without invalidating existing credentials.
    """
    if not isinstance(password, str):
        raise TypeError("password must be a string")

    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=SCRYPT_DKLEN,
    )
    return "$".join(
        (
            PASSWORD_SCHEME,
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _b64encode(salt),
            _b64encode(derived),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash. Never raises on malformed input."""
    if not isinstance(password, str) or not isinstance(stored, str):
        return False

    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != PASSWORD_SCHEME:
        return False

    _, n_text, r_text, p_text, salt_text, hash_text = parts
    try:
        n, r, p = int(n_text), int(r_text), int(p_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(hash_text)
    except (ValueError, TypeError, binascii.Error):
        return False

    if n < 2 or n & (n - 1) or r < 1 or p < 1 or not salt or not expected:
        return False

    try:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=SCRYPT_MAXMEM,
            dklen=len(expected),
        )
    except ValueError:
        return False

    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str) -> bool:
    """True when a stored hash predates the current work factors."""
    parts = stored.split("$") if isinstance(stored, str) else []
    if len(parts) != 6 or parts[0] != PASSWORD_SCHEME:
        return True
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return True
    return (n, r, p) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

def _secret_bytes(secret: Optional[str] = None) -> bytes:
    if secret is None:
        # Imported lazily so app.core.config stays importable on its own.
        from app.core.config import settings

        secret = settings.SECRET_KEY
    if isinstance(secret, bytes):
        return secret
    return str(secret).encode("utf-8")


def _sign(body: str, secret: Optional[str] = None) -> str:
    signature = hmac.new(_secret_bytes(secret), body.encode("ascii"), hashlib.sha256)
    return _b64encode(signature.digest())


def issue_token(
    subject: str = TOKEN_SUBJECT,
    *,
    lifetime_seconds: int = TOKEN_LIFETIME_SECONDS,
    secret: Optional[str] = None,
    issued_at: Optional[int] = None,
) -> str:
    """Mint an HMAC-SHA256 signed session token carrying issue and expiry times."""
    iat = int(issued_at if issued_at is not None else time.time())
    claims = {"sub": subject, "iat": iat, "exp": iat + int(lifetime_seconds)}
    body = _b64encode(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{body}.{_sign(body, secret)}"


def verify_token(
    token: str,
    *,
    secret: Optional[str] = None,
    now: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Return the claims of a valid token, or None if it is invalid or expired.

    A bad signature and an expired token are deliberately indistinguishable to
    the caller; both mean "log in again".
    """
    if not isinstance(token, str) or token.count(".") != 1:
        return None

    body, signature = token.split(".", 1)
    if not body or not signature:
        return None

    try:
        # Compared as bytes: hmac.compare_digest raises TypeError on str inputs
        # holding a non-ASCII character, and an Authorization header is decoded
        # latin-1, so any byte >= 0x80 reaches here.
        matches = constant_time_compare(signature, _sign(body, secret))
    except (UnicodeEncodeError, ValueError):
        return None
    if not matches:
        return None

    try:
        claims = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        return None
    if not isinstance(claims, dict):
        return None

    expiry = claims.get("exp")
    issued = claims.get("iat")
    if not isinstance(expiry, int) or not isinstance(issued, int):
        return None

    current = time.time() if now is None else now
    if current >= expiry:
        return None

    return claims


def should_refresh(
    claims: Dict[str, Any],
    *,
    now: Optional[float] = None,
    interval_seconds: int = TOKEN_REFRESH_INTERVAL_SECONDS,
) -> bool:
    """True when an active session's token is old enough to be reissued."""
    issued = claims.get("iat")
    if not isinstance(issued, int):
        return True
    current = time.time() if now is None else now
    return (current - issued) >= interval_seconds


def refresh_token(
    token: str,
    *,
    secret: Optional[str] = None,
    now: Optional[float] = None,
    lifetime_seconds: int = TOKEN_LIFETIME_SECONDS,
) -> Optional[str]:
    """Reissue a still-valid token with a full lifetime. None if it is not valid."""
    claims = verify_token(token, secret=secret, now=now)
    if claims is None:
        return None
    issued_at = int(time.time() if now is None else now)
    return issue_token(
        str(claims.get("sub", TOKEN_SUBJECT)),
        lifetime_seconds=lifetime_seconds,
        secret=secret,
        issued_at=issued_at,
    )


# ---------------------------------------------------------------------------
# First-run setup code
# ---------------------------------------------------------------------------

def generate_setup_code() -> str:
    """Generate the one-time code that authorises setting the first password."""
    groups = [
        "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(SETUP_CODE_GROUP_LENGTH))
        for _ in range(SETUP_CODE_GROUPS)
    ]
    return "-".join(groups)


def normalize_setup_code(code: str) -> str:
    """Fold a typed setup code to its comparable form (case and spacing free)."""
    if not isinstance(code, str):
        return ""
    return "".join(ch for ch in code.upper() if ch.isalnum())


def verify_setup_code(supplied: str, expected: str) -> bool:
    """Constant-time comparison of a typed setup code against the issued one."""
    if not isinstance(expected, str) or not expected:
        return False
    return constant_time_compare(
        normalize_setup_code(supplied), normalize_setup_code(expected)
    )
