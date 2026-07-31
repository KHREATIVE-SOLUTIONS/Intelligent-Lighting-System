"""
Operator Authentication Tests
=============================

Proves the gate described in the authentication contract actually holds: that
an unauthenticated caller on the venue's network cannot drive the lights, that
the WebSocket channels are closed rather than accepted, and - just as
importantly - that the operator is never locked out of their own box.

Every client here is built with an explicit source address. Login throttling is
per client IP and lives in module state shared by the whole process, so tests
that spend an address budget must not spend the one the rest of the suite logs
in from.
"""

import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.endpoints import auth as auth_endpoints
from app.core import security
from app.core.config import settings
from app.main import app

from tests.conftest import (
    AUTH_LOGIN_URL,
    AUTH_SETUP_URL,
    AUTH_STATUS_URL,
    OPERATOR_PASSWORD,
    WS_TOKEN_PARAM,
    bearer_headers,
    login_payload,
    read_setup_code,
    setup_payload,
    token_from_response,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Read endpoints, one per router. A gate applied centrally has to cover routers
# nobody remembered to look at.
PROTECTED_READS = [
    "/api/rigs/",
    "/api/shows/",
    "/api/fixtures/",
    "/api/dmx/config",
    "/api/audio/config",
    "/api/effects/status",
    "/api/lfo/status",
    "/api/training/status",
    "/api/wizard/venue-presets",
    "/api/templates/",
    "/api/demo/status",
]

# The endpoints that actually move light. These are the reason the box needs a
# lock at all.
PROTECTED_WRITES = [
    ("POST", "/api/dmx/blackout", None),
    ("POST", "/api/dmx/channel", {"channel": 1, "value": 255}),
    ("POST", "/api/dmx/test/pattern", {"pattern": "all_on"}),
    ("POST", "/api/effects/blackout", None),
]

WS_CHANNELS = ["/ws/audio", "/ws/dmx", "/ws/show"]


@asynccontextmanager
async def client_from(address: str, token: str = None):
    """A client whose requests arrive from a specific source address."""
    headers = bearer_headers(token) if token else None
    transport = ASGITransport(app=app, client=(address, 51234))
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=headers
    ) as ac:
        yield ac


def sync_client(token: str = None) -> TestClient:
    """TestClient for the WebSocket handshake, which httpx cannot drive."""
    client = TestClient(app)
    if token:
        client.headers.update(bearer_headers(token))
    return client


async def raw_asgi(
    path: str,
    method: str = "GET",
    headers=(),
    root_path: str = "",
    body: bytes = b"",
    address: str = "203.0.113.99",
):
    """Drive the ASGI app directly.

    Two things the suite cannot otherwise reach: a non-empty ``root_path``,
    which no test transport sets, and header bytes >= 0x80, which httpx refuses
    to send. Both are ordinary on the wire.
    """
    sent = []
    delivered = False
    finished = asyncio.Event()

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        # A real client stays connected until the response is complete; hanging
        # up here makes the middleware stack truncate the body it is streaming.
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            finished.set()

    request_headers = [(b"host", b"testserver")]
    if body:
        request_headers.append((b"content-length", str(len(body)).encode()))
    request_headers.extend(headers)

    await app({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": root_path,
        "query_string": b"",
        "headers": request_headers,
        "client": (address, 51234),
        "server": ("testserver", 80),
    }, receive, send)

    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    payload = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    return status, payload.decode("utf-8", "replace")


async def _ensure_password_is_set(ac, password=OPERATOR_PASSWORD) -> bool:
    """Set the operator password if the box has none. True when one is set."""
    status = await ac.get(AUTH_STATUS_URL)
    if status.status_code != 200:
        return False
    if status.json().get("configured"):
        return True
    code = read_setup_code()
    if not code:
        return False
    response = await ac.post(AUTH_SETUP_URL, json=setup_payload(code, password))
    return response.status_code in (200, 201)


@pytest.fixture(autouse=True)
async def a_configured_box(operator_token):
    """Give each test here a box that has an operator password.

    Other suites drop and recreate the schema, which takes the credential row
    with it, and tokens keep validating afterwards because they are signatures
    rather than sessions. Best effort on purpose: a box that cannot be put into
    this state has to surface as the failing assertion of whichever test cares,
    not as a setup error on all of them.
    """
    async with client_from("198.51.100.1") as ac:
        await _ensure_password_is_set(ac)


# ---------------------------------------------------------------------------
# The fixture itself must not be a no-op
# ---------------------------------------------------------------------------

async def test_the_suite_runs_against_a_real_session(client, operator_token):
    """Guards every other test in the suite.

    If the shared client fixture silently stopped authenticating, the rest of
    the suite would keep passing against an ungated app and prove nothing.
    """
    assert isinstance(operator_token, str) and operator_token, (
        "the suite is not holding an operator session token"
    )
    assert client.headers.get("Authorization") == f"Bearer {operator_token}"
    assert security.verify_token(operator_token) is not None, (
        "the token the suite carries is not one the box accepts"
    )

    response = await client.get("/api/rigs/")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# §3 - what is protected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", PROTECTED_READS)
async def test_unauthenticated_read_is_rejected(unauthenticated_client, path):
    response = await unauthenticated_client.get(path)
    assert response.status_code == 401, (
        f"{path} answered {response.status_code} to an anonymous caller"
    )


@pytest.mark.parametrize("method,path,body", PROTECTED_WRITES)
async def test_unauthenticated_write_is_rejected(
    unauthenticated_client, method, path, body
):
    response = await unauthenticated_client.request(method, path, json=body)
    assert response.status_code == 401, (
        f"{method} {path} answered {response.status_code} to an anonymous caller"
    )


@pytest.mark.parametrize("path", PROTECTED_READS)
async def test_the_operator_still_reaches_every_router(client, path):
    """The lock must not be a wall. A 401 here would be a lockout, not security.

    Only the gate is asserted: this client does not run the lifespan, so
    subsystem-backed routes legitimately answer 500/503 here.
    """
    response = await client.get(path)
    assert response.status_code != 401, (
        f"{path} rejected a signed-in operator"
    )


# The prefix a reverse proxy or `uvicorn --root-path` puts in front of the app.
MOUNT_PREFIX = "/lights"


@pytest.mark.parametrize("path", PROTECTED_READS)
async def test_the_gate_holds_when_the_app_is_mounted_under_a_prefix(
    unauthenticated_client, path
):
    """`uvicorn --root-path=/lights` must not switch the whole gate off.

    The router dispatches on the path with root_path stripped. A gate that
    classifies the unstripped path disagrees with it about every route at once,
    and disagreeing means "not under /api", which means "no token needed".
    """
    status, body = await raw_asgi(MOUNT_PREFIX + path, root_path=MOUNT_PREFIX)
    assert status == 401, (
        f"{path} answered {status} to an anonymous caller under "
        f"root_path={MOUNT_PREFIX!r}: {body[:200]}"
    )


async def test_a_mounted_app_still_serves_the_operator(unauthenticated_client, operator_token):
    """Non-vacuity: those 401s must be the gate, not a routing miss."""
    status, body = await raw_asgi(
        MOUNT_PREFIX + "/api/rigs/",
        headers=[(b"authorization", f"Bearer {operator_token}".encode())],
        root_path=MOUNT_PREFIX,
    )
    assert status == 200, f"a mounted app did not serve the operator: {status} {body[:200]}"


async def test_the_light_moving_routes_are_gated_under_a_prefix(unauthenticated_client):
    for method, path, _body in PROTECTED_WRITES:
        status, _ = await raw_asgi(
            MOUNT_PREFIX + path, method=method, root_path=MOUNT_PREFIX,
            body=b"{}", headers=[(b"content-type", b"application/json")],
        )
        assert status == 401, f"{method} {path} answered {status} under a mount prefix"


# ---------------------------------------------------------------------------
# §1 - a header the box cannot parse is a rejection, never a crash
# ---------------------------------------------------------------------------

# Header values arrive as latin-1, so any byte >= 0x80 becomes a non-ASCII
# character in the token string. hmac.compare_digest refuses to compare those
# as str.
NON_ASCII_BEARERS = [
    b"Bearer aaa.\xff",
    b"Bearer QUFB.\xe9\xe9\xe9",
    b"Bearer \xc3\xa9.\xc3\xa9",
]


@pytest.mark.parametrize("header", NON_ASCII_BEARERS)
async def test_a_non_ascii_token_does_not_crash_the_public_status_route(
    unauthenticated_client, header
):
    """/api/auth/status is how the login screen decides what to show.

    A 500 here is unauthenticated and repeatable, and it takes the venue
    owner's way in with it.
    """
    status, body = await raw_asgi(
        "/api/auth/status", headers=[(b"authorization", header)]
    )
    assert status == 200, f"{header!r} on the public status route -> {status}: {body[:200]}"
    assert json.loads(body)["authenticated"] is False


@pytest.mark.parametrize("header", NON_ASCII_BEARERS)
async def test_a_non_ascii_token_is_rejected_not_crashed(unauthenticated_client, header):
    status, body = await raw_asgi("/api/rigs/", headers=[(b"authorization", header)])
    assert status == 401, f"{header!r} on a gated route -> {status}: {body[:200]}"


@pytest.mark.parametrize("token", ["aaa.\xff", "aaa.\ud800", "\xe9.\xe9"])
def test_verify_token_returns_none_for_anything_it_cannot_compare(token):
    """The primitive's own contract: None for an invalid token, never a raise."""
    assert security.verify_token(token) is None


# ---------------------------------------------------------------------------
# §3 - WebSockets close, never accept
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("channel", WS_CHANNELS)
def test_websocket_without_a_token_is_closed(channel):
    with sync_client() as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(channel):
                pytest.fail(f"{channel} accepted a socket with no token")
    assert excinfo.value.code == 1008, (
        f"{channel} closed with {excinfo.value.code}, expected 1008 policy violation"
    )


@pytest.mark.parametrize("channel", WS_CHANNELS)
def test_websocket_with_a_forged_token_is_closed(channel):
    forged = security.issue_token(secret="not-this-boxes-signing-key")
    with sync_client() as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(f"{channel}?{WS_TOKEN_PARAM}={forged}"):
                pytest.fail(f"{channel} accepted a forged token")
    assert excinfo.value.code == 1008


@pytest.mark.parametrize("channel", WS_CHANNELS)
def test_websocket_with_a_bearer_header_alone_is_closed(channel, operator_token):
    """A browser cannot set headers on a WebSocket, so the header must not count.

    If it did, the query parameter path would be dead code and the real browser
    connection would break.
    """
    with sync_client(operator_token) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect(channel):
                pytest.fail(f"{channel} accepted on an Authorization header")
    assert excinfo.value.code == 1008


def test_websocket_with_the_operators_token_is_accepted(operator_token):
    """Non-vacuity for the three tests above: 1008 has to mean something."""
    with sync_client() as client:
        with client.websocket_connect(
            f"/ws/show?{WS_TOKEN_PARAM}={operator_token}"
        ) as ws:
            ws.close()


# ---------------------------------------------------------------------------
# §3 - /health stays open and stays quiet
# ---------------------------------------------------------------------------

# Anything here in an anonymous /health body tells a stranger what the rig is
# and where its output goes.
LEAKED_HEALTH_KEYS = ("services", "dmx_detail")
LEAKED_HEALTH_SUBSTRINGS = (
    "target_ip", "artnet", "universe", "fixture", "rig", "broadcast",
    "audio_analyzer", "effects_engine", "pro_lighting",
)


async def test_health_answers_an_anonymous_watchdog(unauthenticated_client):
    response = await unauthenticated_client.get("/health")
    assert response.status_code != 401, "a watchdog cannot check a box it cannot reach"
    assert response.status_code in (200, 503)
    assert "status" in response.json()


async def test_health_leaks_no_configuration(unauthenticated_client):
    response = await unauthenticated_client.get("/health")
    body = response.json()

    for key in LEAKED_HEALTH_KEYS:
        assert key not in body, f"anonymous /health exposed '{key}': {body}"

    serialized = json.dumps(body).lower()
    for needle in LEAKED_HEALTH_SUBSTRINGS:
        assert needle not in serialized, (
            f"anonymous /health mentions '{needle}': {body}"
        )
    assert settings.ARTNET_IP.lower() not in serialized, (
        f"anonymous /health exposed the ArtNet target: {body}"
    )


async def test_health_gives_the_operator_the_detail(client):
    """Non-vacuity: the keys asserted absent above are keys /health can emit."""
    response = await client.get("/health")
    body = response.json()
    assert "services" in body and "dmx_detail" in body, (
        f"/health told a signed-in operator nothing useful: {body}"
    )


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/"])
async def test_the_documented_open_paths_stay_open(unauthenticated_client, path):
    """Contract §3 exempts the docs and static assets, so an installer can look."""
    response = await unauthenticated_client.get(path)
    assert response.status_code == 200, (
        f"{path} answered {response.status_code} unauthenticated"
    )


async def test_auth_status_is_public_and_hides_the_setup_code(unauthenticated_client):
    response = await unauthenticated_client.get(AUTH_STATUS_URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"configured", "authenticated"}, body
    assert body["configured"] is True
    assert body["authenticated"] is False

    code = auth_endpoints.get_setup_code()
    if code:
        assert code not in response.text


# ---------------------------------------------------------------------------
# §6 - brute force
# ---------------------------------------------------------------------------

async def test_wrong_password_is_rejected(operator_token):
    async with client_from("203.0.113.10") as ac:
        response = await ac.post(AUTH_LOGIN_URL, json=login_payload("not-the-password"))
    assert response.status_code == 401
    assert OPERATOR_PASSWORD not in response.text


async def test_repeated_wrong_passwords_are_throttled(operator_token):
    """A PIN is guessable, so guessing has to get expensive."""
    statuses = []
    async with client_from("203.0.113.20") as ac:
        for _ in range(12):
            response = await ac.post(
                AUTH_LOGIN_URL, json=login_payload("not-the-password")
            )
            statuses.append(response.status_code)
            if response.status_code == 429:
                break

    assert 429 in statuses, (
        f"twelve wrong passwords from one address were never throttled: {statuses}"
    )
    assert statuses.index(429) <= 10, (
        f"throttling started far too late: {statuses}"
    )
    assert int(response.headers["Retry-After"]) > 0

    correct = auth_endpoints.LOCKOUT_MAX_SECONDS
    assert int(response.headers["Retry-After"]) <= correct, (
        "an unbounded lockout is itself a lockout of the operator"
    )


async def test_a_locked_out_attacker_does_not_lock_out_the_operator(operator_token):
    """The 9pm-on-a-Friday failure: an attacker must not cost the venue its lights."""
    async with client_from("203.0.113.30") as attacker:
        for _ in range(12):
            response = await attacker.post(
                AUTH_LOGIN_URL, json=login_payload("not-the-password")
            )
            if response.status_code == 429:
                break
    assert response.status_code == 429, "the attacker was never locked out"

    async with client_from("198.51.100.7") as operator:
        response = await operator.post(AUTH_LOGIN_URL, json=login_payload())
    assert response.status_code == 200, (
        f"the operator was locked out by someone else's attempts: "
        f"{response.status_code} {response.text[:200]}"
    )
    assert token_from_response(response.json())


async def test_simultaneous_guesses_cannot_outrun_the_limiter(operator_token):
    """The budget has to be spent before the password is checked.

    Checking costs tens of milliseconds. A limiter that only writes its state
    afterwards lets a whole burst through the gate together, so "5 attempts
    then a lockout" becomes "unlimited attempts every lockout period".
    """
    async with client_from("203.0.113.60") as ac:
        responses = await asyncio.gather(*[
            ac.post(AUTH_LOGIN_URL, json=login_payload(f"not-the-password-{i}"))
            for i in range(60)
        ])

    checked = sum(1 for r in responses if r.status_code == 401)
    throttled = sum(1 for r in responses if r.status_code == 429)
    assert checked <= auth_endpoints.LOGIN_FAILURE_THRESHOLD + 1, (
        f"{checked} of 60 simultaneous guesses were evaluated; the limiter "
        f"allows {auth_endpoints.LOGIN_FAILURE_THRESHOLD}"
    )
    assert throttled + checked == 60, (
        f"unexpected statuses: {sorted({r.status_code for r in responses})}"
    )


async def test_the_correct_password_gets_through_a_lockout(operator_token, monkeypatch):
    """The 9pm failure in its worst form: attacker and operator share a bucket.

    Behind the shipped reverse proxy every client is one peer address, so a
    lockout an attacker earns is a lockout the operator serves. A correct
    password has to keep working, or someone else's guessing takes the venue's
    lights away for as long as they care to keep going.
    """
    monkeypatch.setattr(auth_endpoints, "LOCKED_PROBE_INTERVAL_SECONDS", 0.5)
    address = "203.0.113.70"

    async with client_from(address) as shared:
        for _ in range(12):
            response = await shared.post(
                AUTH_LOGIN_URL, json=login_payload("not-the-password")
            )
            if response.status_code == 429:
                break
        assert response.status_code == 429, "the bucket was never locked"

        # Someone keeps guessing wrong at the same address, forever.
        deadline = asyncio.get_running_loop().time() + 20.0
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.2)
            await shared.post(AUTH_LOGIN_URL, json=login_payload("still-wrong"))
            response = await shared.post(AUTH_LOGIN_URL, json=login_payload())
            if response.status_code == 200:
                break

    assert response.status_code == 200, (
        "the operator's own password never got through a lockout someone else "
        f"earned: {response.status_code} {response.text[:200]}"
    )
    assert token_from_response(response.json())


def test_a_wrong_guess_each_time_the_lockout_lifts_cannot_pin_the_operator_out():
    """Driven on a synthetic clock; the real one would take half an hour.

    One request every lockout period used to walk the lockout to its 300s
    ceiling and hold it there, which is an indefinite lockout bought for a
    request every five minutes.
    """
    limiter = auth_endpoints._LoginRateLimiter()
    now = 0.0
    for _ in range(auth_endpoints.LOGIN_FAILURE_THRESHOLD + 1):
        limiter.begin_attempt("shared", now=now)
        now += 0.1

    worst_wait = 0.0
    for _ in range(40):
        wait = limiter.retry_after("shared", now=now)
        worst_wait = max(worst_wait, wait)
        now += wait + 0.01
        attacker = limiter.begin_attempt("shared", now=now)
        assert attacker.allowed

    assert worst_wait <= auth_endpoints.LOCKED_PROBE_INTERVAL_SECONDS + 1, (
        f"the operator would wait {worst_wait:.0f}s between password checks "
        "while someone else keeps guessing"
    )


# ---------------------------------------------------------------------------
# §6 - a page the operator opens must not be able to lock them out
# ---------------------------------------------------------------------------

async def test_a_login_without_a_content_type_is_refused(operator_token):
    """A body with no Content-Type is a CORS "simple request".

    No preflight is sent, so the origin allowlist never gets to answer, and any
    page the operator's laptop loads could spend their attempt budget from
    their own address.
    """
    address = "203.0.113.80"
    for _ in range(8):
        status, _ = await raw_asgi(
            AUTH_LOGIN_URL, method="POST", body=b'{"password":"wrong"}',
            headers=[(b"origin", b"http://evil.example")], address=address,
        )
        assert status == 415, f"a login with no Content-Type answered {status}"

    async with client_from(address) as operator:
        response = await operator.post(AUTH_LOGIN_URL, json=login_payload())
    assert response.status_code == 200, (
        "a page the operator opened locked them out of their own box: "
        f"{response.status_code} {response.text[:200]}"
    )


async def test_the_operators_own_client_still_logs_in(operator_token):
    """Non-vacuity: the declared-JSON path the frontend uses must work."""
    status, body = await raw_asgi(
        AUTH_LOGIN_URL, method="POST",
        body=json.dumps(login_payload()).encode(),
        headers=[(b"content-type", b"application/json")],
        address="203.0.113.85",
    )
    assert status == 200, f"{status}: {body[:200]}"
    assert token_from_response(json.loads(body))


# ---------------------------------------------------------------------------
# §2 - the persisted secret
# ---------------------------------------------------------------------------

RESTART_DRIVER = r'''
import json, os, sys

os.environ.pop("SECRET_KEY", None)
os.environ["DATABASE_URL"] = sys.argv[2]
sys.path.insert(0, sys.argv[1])

from app.core.config import settings
from app.core.security import verify_token

print("RESULT" + json.dumps({
    "secret": settings.SECRET_KEY,
    "operator_token_valid": verify_token(sys.argv[3]) is not None,
    "foreign_token_valid": verify_token(sys.argv[4]) is not None,
}))
'''


def _reboot(tmp_path, operator_token, foreign_token):
    driver = tmp_path / "restart_driver.py"
    driver.write_text(RESTART_DRIVER, encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable, str(driver), str(BACKEND_DIR), settings.DATABASE_URL,
            operator_token, foreign_token,
        ],
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    if not marker:
        pytest.fail(
            "restart driver produced no result (exit %s)\nstdout:\n%s\nstderr:\n%s"
            % (proc.returncode, proc.stdout[-1500:], proc.stderr[-2000:])
        )
    return json.loads(marker[-1][len("RESULT"):])


def test_the_signing_secret_is_persisted(operator_token):
    path = settings.secret_key_path
    assert path.exists(), (
        f"no signing secret at {path}; a per-boot key signs the venue out on "
        "every restart"
    )
    assert path.read_text(encoding="utf-8").strip() == settings.SECRET_KEY


def test_a_token_survives_a_restart(tmp_path, operator_token):
    """A lighting appliance restarts. The show must not end when it does."""
    foreign = security.issue_token(secret="a-key-this-box-never-had")
    result = _reboot(tmp_path, operator_token, foreign)

    assert result["secret"] == settings.SECRET_KEY, (
        "a restarted box computed a different signing key"
    )
    assert result["operator_token_valid"] is True, (
        "the operator's session did not survive a restart"
    )
    assert result["foreign_token_valid"] is False, (
        "the restarted box accepts tokens it never issued"
    )


# ---------------------------------------------------------------------------
# §4 - first run is not a land grab
# ---------------------------------------------------------------------------

async def test_setup_cannot_be_rerun_once_a_password_is_set(operator_token):
    """Whoever reaches an open setup endpoint would own the lights."""
    async with client_from("203.0.113.40") as ac:
        status = await ac.get(AUTH_STATUS_URL)
        assert status.json()["configured"] is True

        for code in ("ABCD-EFGH-JKMN", security.generate_setup_code()):
            response = await ac.post(
                AUTH_SETUP_URL, json=setup_payload(code, "attacker-chosen-password")
            )
            assert response.status_code == 409, (
                f"setup answered {response.status_code} on a configured box: "
                f"{response.text[:200]}"
            )

        # The land grab only matters if it changed something.
        response = await ac.post(AUTH_LOGIN_URL, json=login_payload())
        assert response.status_code == 200, "the operator's password was overwritten"

        response = await ac.post(
            AUTH_LOGIN_URL, json=login_payload("attacker-chosen-password")
        )
        assert response.status_code == 401


FIRST_BOOT_DRIVER = r'''
import json, os, sys, tempfile, pathlib

data_dir = tempfile.mkdtemp(prefix="ils-firstboot-")
os.environ["DATABASE_URL"] = "sqlite:///" + (pathlib.Path(data_dir) / "boot.db").as_posix()
os.environ["ARTNET_IP"] = "127.0.0.1"
os.environ["AUDIO_CAPTURE_AUTO_START"] = "false"
os.environ.pop("SECRET_KEY", None)
sys.path.insert(0, sys.argv[1])

import io, contextlib
from starlette.testclient import TestClient
from app.main import app

console = io.StringIO()
with contextlib.redirect_stdout(console):
    with TestClient(app):
        pass

from app.api.endpoints.auth import get_setup_code

sys.stderr.write("RESULT" + json.dumps({
    "announced_on_stdout": "Setup code:" in console.getvalue(),
    "code_exists_after_boot": bool(get_setup_code()),
}))
'''


def test_a_fresh_box_announces_its_setup_code_at_boot():
    """Contract §4: the installer reads the code off the console they are watching.

    Minting it lazily on the first HTTP call means a headless box that nobody
    has browsed to yet has no code, and nothing was ever printed at startup.
    """
    proc = subprocess.run(
        [sys.executable, "-c", FIRST_BOOT_DRIVER, str(BACKEND_DIR)],
        capture_output=True, text=True, timeout=300, cwd=str(BACKEND_DIR),
    )
    marker = [ln for ln in proc.stderr.splitlines() if ln.startswith("RESULT")]
    if not marker:
        pytest.fail(
            "first-boot driver produced no result (exit %s)\nstdout:\n%s\nstderr:\n%s"
            % (proc.returncode, proc.stdout[-1500:], proc.stderr[-2000:])
        )
    result = json.loads(marker[-1][len("RESULT"):])

    assert result["code_exists_after_boot"] is True, (
        "a fresh box finished booting with no setup code; nobody can claim it "
        "until something calls /api/auth/status"
    )
    assert result["announced_on_stdout"] is True, (
        "the setup code was never printed to the console the installer watches"
    )


async def test_the_setup_code_is_not_reachable_over_the_network(operator_token):
    """It is printed at the box on purpose: holding it proves physical presence."""
    live_code = auth_endpoints.ensure_setup_code()

    async with client_from("203.0.113.45") as ac:
        for path in (AUTH_STATUS_URL, "/health", "/"):
            response = await ac.get(path)
            assert live_code not in response.text, f"{path} handed out the setup code"
            assert "setup_code" not in response.text
            assert "setupCode" not in response.text


# ---------------------------------------------------------------------------
# §5 - recovery
# ---------------------------------------------------------------------------

# Exactly what docs/README.md tells a bar owner to create, including the .txt
# Windows silently appends and the claim that capitals do not matter.
DOCUMENTED_MARKER_NAMES = ["RESET-PASSWORD", "RESET-PASSWORD.txt", "reset-password"]


@pytest.mark.parametrize("marker_name", DOCUMENTED_MARKER_NAMES)
async def test_recovery_returns_the_box_to_first_run_state(operator_token, marker_name):
    """A venue owner who forgets the password must get back in without us."""
    data_dir = auth_endpoints.data_dir()
    marker = data_dir / marker_name

    async with client_from("198.51.100.20") as ac:
        try:
            marker.write_text("", encoding="utf-8")

            status = await ac.get(AUTH_STATUS_URL)
            assert status.status_code == 200
            assert status.json()["configured"] is False, (
                f"{marker.name} in {data_dir} did not clear the operator password"
            )

            assert not marker.exists(), (
                "the recovery marker was left behind; the box would reset its "
                "password on every boot from now on"
            )

            response = await ac.post(AUTH_LOGIN_URL, json=login_payload())
            assert response.status_code == 409, (
                f"the forgotten password still works after a reset: "
                f"{response.status_code}"
            )

            code = read_setup_code()
            assert code, "a reset box published no new setup code"
            response = await ac.post(
                AUTH_SETUP_URL, json=setup_payload(code, "second-chance-passphrase")
            )
            assert response.status_code in (200, 201), response.text[:200]
            assert token_from_response(response.json())

            response = await ac.post(
                AUTH_LOGIN_URL, json=login_payload("second-chance-passphrase")
            )
            assert response.status_code == 200
        finally:
            marker.unlink(missing_ok=True)
            marker.write_text("", encoding="utf-8")
            await ac.get(AUTH_STATUS_URL)
            marker.unlink(missing_ok=True)
            assert await _ensure_password_is_set(ac), (
                "could not put the operator password back after the reset"
            )


# Ordinary things to find in a directory that also holds the database. A match
# clears the operator credential and deletes the file, so a loose rule here
# destroys someone's script and returns a working box to first-run state.
INNOCENT_FILENAMES = [
    "reset_password.py",
    "forgot_password.txt",
    "ResetPassword",
    "reset password.doc.txt",
    "resetpassword.md",
    "reset-passwords",
    "lighting_dev.db",
    "secret_key",
    "reset-password-notes.txt",
]


@pytest.mark.parametrize("name", INNOCENT_FILENAMES)
def test_an_ordinary_filename_is_not_a_recovery_marker(name):
    assert auth_endpoints.is_recovery_marker(name) is False, (
        f"{name} would reset the operator password and be deleted"
    )


@pytest.mark.parametrize("name", DOCUMENTED_MARKER_NAMES)
def test_the_documented_filenames_are_recovery_markers(name):
    """Non-vacuity for the test above."""
    assert auth_endpoints.is_recovery_marker(name) is True


async def test_a_helper_script_in_the_data_directory_does_not_reset_the_box(operator_token):
    """The data directory is the source tree on a dev box, and a checkout."""
    script = auth_endpoints.data_dir() / "reset_password.py"
    async with client_from("198.51.100.30") as ac:
        try:
            script.write_text("# a helper someone added\n", encoding="utf-8")
            status = await ac.get(AUTH_STATUS_URL)
            assert status.json()["configured"] is True, (
                f"{script.name} cleared the operator password"
            )
            assert script.exists(), f"{script.name} was deleted from {script.parent}"
        finally:
            script.unlink(missing_ok=True)


async def test_the_documented_environment_variable_also_resets(operator_token):
    """The command-line half of the documented recovery path."""
    previous = os.environ.get(auth_endpoints.RECOVERY_ENV_VAR)
    already_consumed = auth_endpoints._env_recovery_consumed

    async with client_from("198.51.100.25") as ac:
        try:
            os.environ[auth_endpoints.RECOVERY_ENV_VAR] = "1"
            # The flag is what makes the variable fire once per boot; clearing it
            # is how a test gets a fresh boot without one.
            auth_endpoints._env_recovery_consumed = False

            status = await ac.get(AUTH_STATUS_URL)
            assert status.json()["configured"] is False, (
                f"{auth_endpoints.RECOVERY_ENV_VAR}=1 did not clear the password"
            )
        finally:
            if previous is None:
                os.environ.pop(auth_endpoints.RECOVERY_ENV_VAR, None)
            else:
                os.environ[auth_endpoints.RECOVERY_ENV_VAR] = previous
            auth_endpoints._env_recovery_consumed = already_consumed
            assert await _ensure_password_is_set(ac), (
                "could not put the operator password back after the reset"
            )


async def test_recovery_needs_local_access_not_a_request(operator_token):
    """Nothing reachable over the network may trigger the reset."""
    async with client_from("203.0.113.50") as ac:
        for path in ("/api/auth/recover", "/api/auth/reset", "/api/auth/forgot"):
            for method in ("GET", "POST"):
                response = await ac.request(method, path)
                assert response.status_code >= 400, (
                    f"{method} {path} answered {response.status_code}; a reset "
                    "must need the machine, not a request"
                )

        status = await ac.get(AUTH_STATUS_URL)
        assert status.json()["configured"] is True, (
            "the password was cleared without local access"
        )


# ---------------------------------------------------------------------------
# §1 - token validation
# ---------------------------------------------------------------------------

async def test_a_tampered_token_is_rejected(unauthenticated_client, operator_token):
    body, signature = operator_token.split(".", 1)

    forgeries = {
        "flipped signature byte": (
            f"{body}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
        ),
        "signature stripped": body,
        "empty signature": f"{body}.",
        "claims swapped": (
            security.issue_token(secret="attacker-key").split(".", 1)[0]
            + "." + signature
        ),
    }

    for description, token in forgeries.items():
        response = await unauthenticated_client.get(
            "/api/rigs/", headers=bearer_headers(token)
        )
        assert response.status_code == 401, (
            f"a token with its {description} was accepted"
        )


async def test_an_expired_token_is_rejected(unauthenticated_client):
    expired = security.issue_token(lifetime_seconds=-1)
    response = await unauthenticated_client.get(
        "/api/rigs/", headers=bearer_headers(expired)
    )
    assert response.status_code == 401, "an expired token still opened the box"


async def test_a_token_signed_by_another_key_is_rejected(unauthenticated_client):
    foreign = security.issue_token(secret="a-key-this-box-never-had")
    response = await unauthenticated_client.get(
        "/api/rigs/", headers=bearer_headers(foreign)
    )
    assert response.status_code == 401


@pytest.mark.parametrize("header", [
    "",
    "Bearer",
    "Bearer ",
    "Basic ZGVtbzpkZW1v",
    "Bearer null",
    "Bearer undefined",
])
async def test_malformed_authorization_headers_are_rejected(
    unauthenticated_client, header
):
    response = await unauthenticated_client.get(
        "/api/rigs/", headers={"Authorization": header}
    )
    assert response.status_code == 401, (
        f"Authorization: {header!r} was accepted"
    )
