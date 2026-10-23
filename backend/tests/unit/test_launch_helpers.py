"""
Starting a Venue Box Unattended
===============================

start.py waited on a typed device number, drove rig 5 whatever the database
held, sent its audio feed without a token once login was on, waited out its
whole timeout on a degraded /health, and left the backend running when it gave
up. A fresh install with no .env pointed at a Postgres server that was not
there.
"""

import json
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import launch_helpers as lh  # noqa: E402

DEVICES = [
    {"index": 3, "name": "Speakers (Realtek)"},
    {"index": 7, "name": "Main Out 1/2 (Studio 24c)"},
]


@pytest.mark.parametrize("raw,expected", [("", None), ("12", 12), ("abc", None), ("0", None), ("-3", None)])
def test_rig_comes_from_the_environment_or_is_the_active_rig(raw, expected):
    assert lh.rig_id_from_env(raw) == expected


def test_no_rig_id_means_the_active_rig():
    assert json.loads(lh.reactive_on_message(None)) == {"type": "reactive_on"}
    assert json.loads(lh.reactive_on_message(4)) == {"type": "reactive_on", "rig_id": 4}


def test_the_audio_feed_carries_the_token():
    url = lh.backend_ws_url("http://localhost:8000", "/ws/audio", "a b.c")
    assert url == "ws://localhost:8000/ws/audio?token=a%20b.c"
    assert lh.backend_ws_url("https://box/", "/ws/audio", None) == "wss://box/ws/audio"


def test_a_degraded_backend_counts_as_up():
    def degraded(url, timeout):
        raise urllib.error.HTTPError(url, 503, "degraded", {}, None)

    def down(url, timeout):
        raise urllib.error.URLError("refused")

    assert lh.backend_answers("http://x/health", opener=degraded) is True
    assert lh.backend_answers("http://x/health", opener=down) is False


@pytest.mark.parametrize("choice,index", [("7", 7), ("studio 24c", 7), ("speakers", 3), ("99", 3)])
def test_a_named_device_is_used_without_asking(choice, index):
    def never(): raise AssertionError("asked a question on an unattended start")
    assert lh.pick_device(DEVICES, DEVICES[0], choice=choice, ask=never)["index"] == index


def test_an_unattended_start_takes_the_recommended_device():
    def never(): raise AssertionError("waited on a prompt nobody will answer")
    assert lh.pick_device(DEVICES, DEVICES[1], interactive=False, ask=never) is DEVICES[1]


def test_a_person_at_the_terminal_is_still_asked():
    assert lh.pick_device(DEVICES, DEVICES[0], interactive=True, ask=lambda: "7")["index"] == 7
    assert lh.pick_device(DEVICES, DEVICES[1], interactive=True, ask=lambda: "") is DEVICES[1]


def test_the_launcher_can_sign_its_own_feed_in(tmp_path):
    backend = REPO_ROOT / "backend"
    token = lh.mint_local_token(sys.executable, backend, lifetime_seconds=60)
    assert token and token.count(".") == 1


def test_with_no_env_the_database_is_a_local_file():
    from app.core import config

    assert config.DEFAULT_DATABASE_URL.startswith("sqlite:///")
    assert config.DEFAULT_DATABASE_PATH.is_absolute()
    assert config.Settings.model_fields["DATABASE_URL"].default == config.DEFAULT_DATABASE_URL


def test_the_linux_venue_file_gets_art_net_out_and_keeps_side_doors_local():
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!reset", lambda loader, node: [])
    venue = yaml.load((REPO_ROOT / "docker-compose.venue-linux.example.yml").read_text(), Loader=Loader)
    services = venue["services"]

    assert services["backend"]["network_mode"] == "host"
    assert "/dev/snd:/dev/snd" in services["backend"]["devices"]
    assert "--host 127.0.0.1" in services["backend"]["command"]
    for name in ("postgres", "redis"):
        assert all(str(p).startswith("127.0.0.1:") for p in services[name]["ports"])
    assert "VISUALIZER_HOST=127.0.0.1" in services["visualizer"]["environment"]
