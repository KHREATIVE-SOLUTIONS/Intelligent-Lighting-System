"""
Operator Authentication Endpoints
=================================

First-run setup, login, logout, password change and the offline recovery path
for the single operator credential.

The failure this module is written against is not "an intruder gets in", it is
"the venue is locked out of its own lights mid-set". Every lockout here is
per-client and bounded, and the recovery path in ``apply_pending_recovery``
needs nothing but access to the machine itself.
"""

import asyncio
import logging
import os
import threading
import time
import weakref
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.db.database import get_db
from app.models.auth import SINGLETON_ID, OperatorCredential

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Rate limiting (contract §6)
# ---------------------------------------------------------------------------

# Attempts allowed from one address before lockouts begin.
LOGIN_FAILURE_THRESHOLD = 5
LOCKOUT_BASE_SECONDS = 15
# Bounded on purpose. Behind a reverse proxy every request shares one peer
# address, so an attacker and the operator can land in the same bucket; a
# lockout that grows without limit would hand an attacker the show.
LOCKOUT_MAX_SECONDS = 300
# A locked-out bucket still gets its password checked this often, and a correct
# one always wins. Without it, one wrong guess sent whenever the lockout lifts
# pins the bucket at the cap and holds the venue out of its own lights.
LOCKED_PROBE_INTERVAL_SECONDS = 15
# A run of failures this old no longer counts against the next attempt.
FAILURE_WINDOW_SECONDS = 900
# Bounds memory when an attacker rotates source addresses.
MAX_TRACKED_CLIENTS = 2048
# The lockout doubles per failure; past this the cap has long since bitten and
# the shift is only a way to make an enormous integer.
MAX_LOCKOUT_DOUBLINGS = 16
# scrypt costs ~45ms of CPU and the DMX output loop shares this process, so the
# number of password checks running at once is capped rather than left to the
# thread pool.
MAX_CONCURRENT_VERIFICATIONS = 2
# Comma separated peer addresses whose X-Forwarded-For is believed. Empty by
# default: an unconfigured box must never take an attacker's word for where a
# request came from.
TRUSTED_PROXY_ENV_VAR = "TRUSTED_PROXIES"


@dataclass
class _ClientState:
    failures: int = 0
    last_failure: float = 0.0
    locked_until: float = 0.0
    next_probe: float = 0.0


@dataclass
class _Attempt:
    """The limiter's decision about one password check."""
    allowed: bool
    retry_after: float = 0.0
    lockout: float = 0.0


class _LoginRateLimiter:
    """Per-client failure tracking with a growing, capped lockout.

    In memory by design: one box, one operator, and a limiter that forgets
    everything on restart is a limiter the operator can always clear.
    """

    def __init__(self) -> None:
        self._clients: Dict[str, _ClientState] = {}
        self._lock = threading.Lock()

    def retry_after(self, client: str, now: Optional[float] = None) -> float:
        """Seconds until this client's next password check is allowed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._clients.get(client)
            if state is None or state.locked_until <= now:
                return 0.0
            remaining = state.next_probe - now
            return remaining if remaining > 0 else 0.0

    def begin_attempt(self, client: str, now: Optional[float] = None) -> _Attempt:
        """Count an attempt and say whether the password may be checked.

        Counted before the check, not after: verifying takes tens of
        milliseconds, so a limiter that only writes its state afterwards lets a
        simultaneous burst through the gate together and spends none of the
        budget.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._clients.get(client)
            if state is None or now - state.last_failure > FAILURE_WINDOW_SECONDS:
                state = _ClientState()
                self._clients[client] = state

            if state.locked_until > now and now < state.next_probe:
                return _Attempt(False, retry_after=state.next_probe - now)

            state.failures += 1
            state.last_failure = now

            lockout = 0.0
            if state.failures > LOGIN_FAILURE_THRESHOLD:
                steps = min(
                    state.failures - LOGIN_FAILURE_THRESHOLD - 1, MAX_LOCKOUT_DOUBLINGS
                )
                lockout = float(
                    min(LOCKOUT_BASE_SECONDS * (2 ** steps), LOCKOUT_MAX_SECONDS)
                )
                state.locked_until = now + lockout
                state.next_probe = now + min(LOCKED_PROBE_INTERVAL_SECONDS, lockout)

            self._evict(now)
            return _Attempt(True, lockout=lockout)

    def record_success(self, client: str) -> None:
        with self._lock:
            self._clients.pop(client, None)

    def clear(self) -> None:
        with self._lock:
            self._clients.clear()

    def _evict(self, now: float) -> None:
        """Drop tracked clients once the table is full. Caller holds the lock."""
        if len(self._clients) <= MAX_TRACKED_CLIENTS:
            return
        expired = [
            key for key, state in self._clients.items()
            if state.locked_until <= now and now - state.last_failure > FAILURE_WINDOW_SECONDS
        ]
        for key in expired:
            del self._clients[key]
        while len(self._clients) > MAX_TRACKED_CLIENTS:
            oldest = min(self._clients, key=lambda k: self._clients[k].last_failure)
            del self._clients[oldest]


_rate_limiter = _LoginRateLimiter()


def trusted_proxies() -> frozenset:
    """Peer addresses whose X-Forwarded-For this box believes."""
    raw = os.environ.get(TRUSTED_PROXY_ENV_VAR, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def client_address(request: Request) -> str:
    """The address an attempt is charged to.

    X-Forwarded-For counts only when the connection itself arrives from a peer
    named in TRUSTED_PROXIES. Believing it unconditionally lets an attacker
    spend the operator's budget by naming them in a header; ignoring it
    entirely puts every client behind the venue's reverse proxy in one bucket,
    where a stranger's lockout is the operator's lockout too.
    """
    client = request.client
    peer = client.host if client is not None and client.host else "unknown"
    if peer in trusted_proxies():
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return peer


def _begin_attempt(client: str, what: str) -> _Attempt:
    """Reserve a password check for this client, or refuse it with a 429."""
    attempt = _rate_limiter.begin_attempt(client)
    if attempt.allowed:
        return attempt
    retry_after = max(1, int(attempt.retry_after + 0.999))
    logger.warning("Auth: %s from %s refused, locked out", what, client)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many failed attempts. Try again in {retry_after} seconds.",
        headers={"Retry-After": str(retry_after)},
    )


def _record_failure(client: str, what: str, attempt: _Attempt) -> None:
    if attempt.lockout:
        logger.warning(
            "Auth: %s from %s - locked out for %ds", what, client, int(attempt.lockout)
        )
    else:
        logger.warning("Auth: %s from %s", what, client)


def require_json_request(request: Request) -> None:
    """Refuse a credential POST that does not declare a JSON body.

    A body posted without a Content-Type is a CORS "simple request": the browser
    sends no preflight, so any page the operator happens to open can spend their
    attempt budget from their own address and lock them out of the room.
    Requiring JSON forces a preflight, which the origin allowlist answers.
    """
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Send this request with Content-Type: application/json.",
        )


# ---------------------------------------------------------------------------
# First-run setup code (contract §4)
# ---------------------------------------------------------------------------

_setup_code: Optional[str] = None
_setup_code_lock = threading.Lock()


def get_setup_code() -> Optional[str]:
    """The live setup code, or None once a password is configured."""
    with _setup_code_lock:
        return _setup_code


def clear_setup_code() -> None:
    global _setup_code
    with _setup_code_lock:
        _setup_code = None


def ensure_setup_code() -> str:
    """Return the live setup code, generating and announcing one if needed."""
    global _setup_code
    with _setup_code_lock:
        if _setup_code is not None:
            return _setup_code
        _setup_code = security.generate_setup_code()
        code = _setup_code

    _announce_setup_code(code)
    return code


def _announce_setup_code(code: str) -> None:
    """Put the code where the person standing at the box will see it."""
    banner = (
        "\n"
        "=================================================================\n"
        " LIGHTING BOX FIRST RUN - no operator password is set yet.\n"
        f" Setup code: {code}\n"
        " Open the lighting page and enter this code to choose a password.\n"
        " It is valid until this box restarts, and once a password is set\n"
        " it stops working.\n"
        "=================================================================\n"
    )
    print(banner, flush=True)
    logger.warning("First run: operator setup code is %s", code)


# ---------------------------------------------------------------------------
# Recovery (contract §5)
# ---------------------------------------------------------------------------

# Exactly what docs/README.md tells a venue owner to create. Matching is
# case-insensitive and tolerates the single ".txt" Windows Explorer's
# "New > Text Document" appends, and nothing looser: a match deletes the file
# and the operator's credential with it, so `reset_password.py` sitting in the
# data directory must not count.
RECOVERY_MARKER_NAMES = ("reset-password", "forgot-password")
RECOVERY_MARKER_SUFFIX = ".txt"
RECOVERY_ENV_VAR = "RESET_OPERATOR_PASSWORD"

_env_recovery_consumed = False


def data_dir() -> Path:
    """The directory holding the database, the log folder and the signing secret."""
    return settings.data_dir


def is_recovery_marker(name: str) -> bool:
    """True for the documented reset filenames, and only those."""
    folded = name.strip().lower()
    if folded.endswith(RECOVERY_MARKER_SUFFIX):
        folded = folded[: -len(RECOVERY_MARKER_SUFFIX)]
    return folded in RECOVERY_MARKER_NAMES


def find_recovery_markers() -> Tuple[Path, ...]:
    """Recovery files present in the data directory."""
    directory = data_dir()
    try:
        entries = list(directory.iterdir())
    except OSError:
        return ()
    return tuple(
        path for path in entries
        if path.is_file() and is_recovery_marker(path.name)
    )


def _consume_env_recovery() -> bool:
    """True once per process when the reset environment variable is set."""
    global _env_recovery_consumed
    if _env_recovery_consumed:
        return False
    value = os.environ.get(RECOVERY_ENV_VAR, "").strip().lower()
    if value in ("", "0", "false", "no"):
        return False
    _env_recovery_consumed = True
    return True


async def apply_pending_recovery(db: AsyncSession) -> bool:
    """Return the box to first-run state when a local reset was requested.

    Requires access to the machine - a file in the data directory or an
    environment variable set before boot. Nothing reachable over the network
    can trigger this.
    """
    markers = find_recovery_markers()
    by_env = _consume_env_recovery()
    if not markers and not by_env:
        return False

    if by_env:
        logger.warning("Recovery: %s was set - resetting the operator password", RECOVERY_ENV_VAR)
    for marker in markers:
        logger.warning("Recovery: found %s - resetting the operator password", marker)

    result = await db.execute(select(OperatorCredential))
    credentials = result.scalars().all()
    for credential in credentials:
        await db.delete(credential)
    await db.commit()

    for marker in markers:
        try:
            marker.unlink()
        except OSError as e:
            logger.error(
                "Recovery: could not remove %s (%s) - delete it by hand or the box "
                "will keep resetting its password", marker, e
            )

    _rate_limiter.clear()
    clear_setup_code()
    ensure_setup_code()
    logger.warning(
        "Recovery complete: the operator password was cleared (%d credential(s) removed)",
        len(credentials),
    )
    return True


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------

# One semaphore per event loop: the app runs on one, but the test suite builds a
# fresh loop per test and an asyncio primitive cannot wait across loops.
_verification_slots: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _verification_slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slot = _verification_slots.get(loop)
    if slot is None:
        slot = asyncio.Semaphore(MAX_CONCURRENT_VERIFICATIONS)
        _verification_slots[loop] = slot
    return slot


# scrypt costs ~45ms per call and the DMX output loop is a task on this same
# event loop, so hashing inline drops nearly two frames per attempt. Off the
# loop and capped: unbounded concurrency puts the same stall back through the
# thread pool.
async def hash_password(password: str) -> str:
    async with _verification_slot():
        return await asyncio.to_thread(security.hash_password, password)


async def check_password(password: str, stored: str) -> bool:
    async with _verification_slot():
        return await asyncio.to_thread(security.verify_password, password, stored)


async def load_credential(db: AsyncSession) -> Optional[OperatorCredential]:
    result = await db.execute(
        select(OperatorCredential).order_by(OperatorCredential.id).limit(1)
    )
    return result.scalars().first()


async def is_configured(db: AsyncSession) -> bool:
    return await load_credential(db) is not None


async def prepare_first_run(db: AsyncSession) -> Optional[str]:
    """Boot hook: apply any pending recovery, then publish a setup code if needed.

    Returns the live setup code, or None when a password is already configured.
    """
    await apply_pending_recovery(db)
    if await is_configured(db):
        clear_setup_code()
        return None
    return ensure_setup_code()


def bearer_token(request: Request) -> Optional[str]:
    """Pull a session token off the Authorization header."""
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    if len(parts) == 1:
        return parts[0].strip() or None
    return None


def _require_token(request: Request) -> dict:
    token = bearer_token(request)
    claims = security.verify_token(token) if token else None
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims


def _token_response(token: str) -> dict:
    claims = security.verify_token(token) or {}
    return {
        "token": token,
        "token_type": "bearer",
        "expires_at": claims.get("exp"),
    }


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=256)


class SetupRequest(BaseModel):
    setup_code: str = Field(..., min_length=1, max_length=64)
    # Short enough for a PIN on purpose; the per-client lockout is what makes a
    # PIN survivable.
    password: str = Field(..., min_length=4, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=4, max_length=256)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/status")
async def auth_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Report whether a password exists and whether this caller is signed in."""
    # Dev mode: auth disabled -> nothing to configure, everyone is "in".
    if not settings.AUTH_ENABLED:
        return {"configured": True, "authenticated": True, "enabled": False}

    await apply_pending_recovery(db)
    configured = await is_configured(db)

    if configured:
        clear_setup_code()
    else:
        # Covers a box whose password was reset without a restart.
        ensure_setup_code()

    token = bearer_token(request)
    authenticated = bool(token and security.verify_token(token))
    return {"configured": configured, "authenticated": authenticated, "enabled": True}


@router.post("/setup")
async def setup_operator(
    payload: SetupRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Set the first operator password, using the code printed at first run."""
    require_json_request(request)
    await apply_pending_recovery(db)
    client = client_address(request)

    if await is_configured(db):
        clear_setup_code()
        logger.warning("Auth: setup attempted from %s but a password is already set", client)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A password is already set. Sign in, or reset the box locally.",
        )

    attempt = _begin_attempt(client, "setup")
    expected = ensure_setup_code()
    if not security.verify_setup_code(payload.setup_code, expected):
        _record_failure(client, "wrong setup code", attempt)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That setup code is not right. It is printed in the box's console.",
        )
    _rate_limiter.record_success(client)

    now = datetime.utcnow()
    db.add(OperatorCredential(
        id=SINGLETON_ID,
        password_hash=await hash_password(payload.password),
        created_at=now,
        updated_at=now,
        last_login_at=now,
    ))
    try:
        await db.commit()
    except IntegrityError:
        # Two clients raced through setup with the same code; the first one won.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A password is already set. Sign in, or reset the box locally.",
        )

    clear_setup_code()
    logger.warning("Auth: operator password set from %s", client)
    return _token_response(security.issue_token())


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Exchange the operator password for a session token."""
    require_json_request(request)
    await apply_pending_recovery(db)
    client = client_address(request)

    credential = await load_credential(db)
    if credential is None:
        ensure_setup_code()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No password is set on this box yet. Use the setup code to choose one.",
        )

    # The password is checked even while this client is locked out, once per
    # probe interval: the operator holding the right password must never be shut
    # out of their own lights by someone else spending the attempt budget.
    attempt = _begin_attempt(client, "login")
    if not await check_password(payload.password, credential.password_hash):
        _record_failure(client, "failed login", attempt)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wrong password.",
        )
    _rate_limiter.record_success(client)

    if security.needs_rehash(credential.password_hash):
        credential.password_hash = await hash_password(payload.password)
    credential.last_login_at = datetime.utcnow()
    await db.commit()

    logger.info("Auth: operator signed in from %s", client)
    return _token_response(security.issue_token())


@router.post("/logout")
async def logout(request: Request):
    """End this client's session.

    Tokens are stateless signatures, so the client discarding the token is what
    ends the session. To evict a token the operator no longer holds, rotate the
    box's session key (see docs/README.md).
    """
    token = bearer_token(request)
    if token and security.verify_token(token):
        logger.info("Auth: operator signed out from %s", client_address(request))
    return {"status": "logged_out"}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Replace the operator password. The current one is required."""
    require_json_request(request)
    _require_token(request)
    client = client_address(request)

    credential = await load_credential(db)
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No password is set on this box yet.",
        )

    attempt = _begin_attempt(client, "password change")
    if not await check_password(payload.current_password, credential.password_hash):
        _record_failure(client, "failed password change", attempt)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The current password is not right.",
        )
    _rate_limiter.record_success(client)

    credential.password_hash = await hash_password(payload.new_password)
    credential.updated_at = datetime.utcnow()
    await db.commit()

    logger.warning("Auth: operator password changed from %s", client)
    # Reissued so the operator who just changed it is not signed out.
    return _token_response(security.issue_token())
