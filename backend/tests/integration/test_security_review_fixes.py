"""
Security: Forwarded Addresses, Export Paths and the Shipped Compose File
========================================================================

The rate limiter believed the leftmost X-Forwarded-For entry, which the client
writes, so an attacker behind the venue proxy chose a fresh bucket per guess.
The training export wrote wherever a "../" filename pointed. And the shipped
compose file turned the operator login off and published an unauthenticated
database on the venue network.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.api.endpoints import auth as auth_endpoints
from app.services.ml.training_recorder import TrainingRecorder

REPO_ROOT = Path(__file__).resolve().parents[3]


def request_from(peer, forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv(auth_endpoints.TRUSTED_PROXY_ENV_VAR, "10.0.0.2")
    return "10.0.0.2"


def test_a_client_cannot_choose_its_own_bucket(proxy):
    # nginx appends the address it saw to whatever the client sent.
    spoofed = request_from(proxy, "1.1.1.1, 198.51.100.7")
    assert auth_endpoints.client_address(spoofed) == "198.51.100.7"


def test_the_real_client_behind_the_proxy_is_used(proxy):
    assert auth_endpoints.client_address(request_from(proxy, "198.51.100.7")) == "198.51.100.7"


def test_chained_trusted_proxies_are_skipped(monkeypatch):
    monkeypatch.setenv(auth_endpoints.TRUSTED_PROXY_ENV_VAR, "10.0.0.2,10.0.0.3")
    request = request_from("10.0.0.2", "6.6.6.6, 198.51.100.7, 10.0.0.3")
    assert auth_endpoints.client_address(request) == "198.51.100.7"


def test_an_untrusted_peer_is_charged_to_itself(proxy):
    assert auth_endpoints.client_address(request_from("203.0.113.9", "1.1.1.1")) == "203.0.113.9"


@pytest.mark.parametrize("name", ["../../escaped.jsonl", "/tmp/abs_escaped.jsonl", "..", "a/../../b"])
def test_training_export_stays_in_its_folder(tmp_path, name):
    out = tmp_path / "out"
    recorder = TrainingRecorder(output_dir=str(out))
    recorder.session_name = "s"
    recorder.frames = [SimpleNamespace(timestamp=1.0, audio=None, lighting=None)]

    safe = recorder._safe_name(name)
    assert "/" not in safe and not safe.startswith(".")
    assert (out / safe).resolve().parent == out.resolve()


def test_session_names_cannot_escape_either(tmp_path):
    recorder = TrainingRecorder(output_dir=str(tmp_path))
    assert recorder._safe_name("../../../etc/cron.d/x") == "x"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())


def env_of(service):
    env = service.get("environment", [])
    if isinstance(env, dict):
        return env
    return dict(item.split("=", 1) for item in env)


def test_compose_ships_with_login_on(compose):
    assert env_of(compose["services"]["backend"])["AUTH_ENABLED"] == "${AUTH_ENABLED:-true}"


@pytest.mark.parametrize("name", ["postgres", "redis"])
def test_compose_does_not_publish_the_datastores(compose, name):
    assert "ports" not in compose["services"][name]


@pytest.mark.parametrize("name", ["backend", "visualizer"])
def test_compose_keeps_unauthenticated_side_doors_on_this_machine(compose, name):
    for port in compose["services"][name].get("ports", []):
        assert str(port).startswith("127.0.0.1:")


def test_compose_restarts_the_show_after_a_crash(compose):
    for name in ("postgres", "backend", "frontend"):
        assert compose["services"][name].get("restart") == "unless-stopped"


def test_dev_override_is_an_example_and_ignored():
    assert (REPO_ROOT / "docker-compose.override.example.yml").exists()
    assert "docker-compose.override.yml" in (REPO_ROOT / ".gitignore").read_text()


def test_the_signing_key_stays_out_of_the_image():
    ignored = (REPO_ROOT / "backend" / ".dockerignore").read_text().split()
    assert "secret_key" in ignored and ".env" in ignored
