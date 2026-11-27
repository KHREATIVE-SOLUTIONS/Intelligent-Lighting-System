"""
One Launcher
============

`python start.py` is the single way to start the system. These pin what it
promises: the flags, the exact commands, a preflight that names what to fix,
a health wait that gives up for the right reason, and a stop that lets the
backend shut itself down. Nothing here starts a service.
"""

import signal
import socket
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import launch_helpers as lh  # noqa: E402
import launcher  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tree(tmp_path, venv=True, node_modules=True, dist=False):
    """A checkout with only the files the launcher looks for."""
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("app = None\n")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "launch_audio.py").write_text("")
    if venv:
        python = launcher.venv_python(tmp_path)
        python.parent.mkdir(parents=True)
        python.write_text("")
    if node_modules:
        vite = launcher.vite_entry(tmp_path)
        vite.parent.mkdir(parents=True)
        vite.write_text("")
    if dist:
        (tmp_path / "frontend" / "dist").mkdir()
        (tmp_path / "frontend" / "dist" / "index.html").write_text("<html></html>")
    return tmp_path


def run_preflight(args, root, busy=(), python_ok=(True, ""), node="/usr/bin/node", environ=None):
    return launcher.preflight(
        args, root,
        environ={} if environ is None else environ,
        port_check=lambda port, host: port in busy,
        python_check=lambda python: python_ok,
        which=lambda name: node,
    )


def by_name(results):
    return {r.name: r for r in results}


class FakeProcess:
    """Stands in for subprocess.Popen: exits when told to, records what it was sent."""

    def __init__(self, exit_code=None, exits_after_polls=None, stops_on_wait=True):
        self.exit_code = exit_code
        self.exits_after_polls = exits_after_polls
        self.stops_on_wait = stops_on_wait
        self.polls = 0
        self.calls = []

    def poll(self):
        self.polls += 1
        if self.exits_after_polls is not None and self.polls > self.exits_after_polls:
            self.exit_code = 3
        return self.exit_code

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self.exit_code is None and not self.stops_on_wait:
            raise subprocess.TimeoutExpired("fake", timeout)
        if self.exit_code is None:
            self.exit_code = 0
        return self.exit_code

    def send_signal(self, sig):
        self.calls.append(("signal", sig))

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        self.exit_code = -9


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def test_defaults_are_the_documented_ports_and_loopback():
    args = launcher.parse_args([])
    assert (args.backend_port, args.ui_port, args.host) == (8000, 5173, "127.0.0.1")
    assert not (args.no_ui or args.check or args.dry_run or args.audio or args.open)


def test_every_flag_is_read():
    args = launcher.parse_args(["--backend-port", "8765", "--ui-port", "5199", "--no-ui",
                                "--check", "--dry-run", "--timeout", "5"])
    assert (args.backend_port, args.ui_port) == (8765, 5199)
    assert args.no_ui and args.check and args.dry_run
    assert args.timeout == 5


@pytest.mark.parametrize("argv,message", [
    (["--backend-port", "0"], "outside 1-65535"),
    (["--ui-port", "70000"], "outside 1-65535"),
    (["--backend-port", "http"], "not a port number"),
    (["--backend-port", "9000", "--ui-port", "9000"], "need different ports"),
    (["--timeout", "0"], "more than 0"),
])
def test_a_bad_argument_is_refused_with_the_reason(argv, message, capsys):
    with pytest.raises(SystemExit) as stop:
        launcher.parse_args(argv)
    assert stop.value.code == 2
    assert message in capsys.readouterr().err


def test_the_same_port_twice_is_fine_when_there_is_no_ui():
    args = launcher.parse_args(["--backend-port", "9000", "--ui-port", "9000", "--no-ui"])
    assert args.backend_port == 9000


def test_the_old_command_line_still_parses_and_says_it_starts_no_audio(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ILS_AUDIO_DEVICE", "Speakers")
    old = launcher.parse_args(["--no-browser", "--device", "Main Out", "--dry-run"])
    assert old.audio_options_unused and old.device == "Main Out"
    assert launcher.run(old, make_tree(tmp_path)) == 0
    assert "No audio feed is started" in capsys.readouterr().out

    # The environment variable alone is a standing setting, not a request.
    assert not launcher.parse_args([]).audio_options_unused
    with_audio = launcher.parse_args(["--audio"])
    assert not with_audio.audio_options_unused and with_audio.device == "Speakers"


# ---------------------------------------------------------------------------
# The commands
# ---------------------------------------------------------------------------

def test_the_backend_command_is_uvicorn_under_the_backend_venv(tmp_path):
    root = make_tree(tmp_path)
    plan = launcher.build_plan(launcher.parse_args(["--backend-port", "8765", "--no-ui"]), root)

    backend = plan.child("backend")
    assert backend.argv == [str(launcher.venv_python(root)), "-m", "uvicorn", "app.main:app",
                            "--host", "127.0.0.1", "--port", "8765"]
    assert backend.cwd == root / "backend"
    assert backend.health_url == "http://127.0.0.1:8765/health"
    assert "--reload" not in backend.argv
    assert [c.name for c in plan.children] == ["backend"]


def test_the_ui_is_the_dev_server_pointed_at_this_backend(tmp_path):
    root = make_tree(tmp_path)
    args = launcher.parse_args(["--backend-port", "8765", "--ui-port", "5199"])
    plan = launcher.build_plan(args, root, node="node")

    ui = plan.child("ui")
    assert ui.argv == ["node", str(launcher.vite_entry(root)),
                       "--host", "127.0.0.1", "--port", "5199", "--strictPort"]
    assert ui.cwd == root / "frontend"
    # Without these the UI's proxy goes to port 8000: someone else's backend.
    assert ui.env == {"VITE_BACKEND_HTTP": "http://127.0.0.1:8765",
                      "VITE_BACKEND_WS": "ws://127.0.0.1:8765"}
    assert ui.health_url == "http://127.0.0.1:5199/"
    assert plan.ui_mode == "dev"
    assert plan.urls[0] == ("Operator screen", "http://127.0.0.1:5199/")


def test_a_built_ui_is_served_instead_of_the_dev_server(tmp_path):
    root = make_tree(tmp_path, dist=True)
    plan = launcher.build_plan(launcher.parse_args([]), root, node="node")
    assert plan.ui_mode == "preview"
    assert plan.child("ui").argv[:3] == ["node", str(launcher.vite_entry(root)), "preview"]

    forced = launcher.build_plan(launcher.parse_args(["--ui-mode", "dev"]), root, node="node")
    assert forced.ui_mode == "dev" and "preview" not in forced.child("ui").argv


def test_the_launcher_never_sets_the_output_target(tmp_path):
    root = make_tree(tmp_path, dist=True)
    args = launcher.parse_args(["--audio", "--host", "0.0.0.0"])
    plan = launcher.build_plan(args, root, node="node")
    for child in plan.children:
        assert not [key for key in child.env if key.startswith(("ARTNET", "DMX", "DEMO_RIG"))]
        assert "255.255.255.255" not in " ".join(child.argv)

    environments = []

    def popen(argv, cwd, env):
        environments.append(env)

    # The venue's own target reaches the backend untouched...
    launcher.spawn(plan.child("backend"), environ={"ARTNET_IP": "10.0.0.50"}, popen=popen)
    assert environments[-1]["ARTNET_IP"] == "10.0.0.50"
    # ...and with none set, the launcher does not invent one.
    launcher.spawn(plan.child("backend"), environ={"PATH": "x"}, popen=popen)
    assert set(environments[-1]) == {"PATH", "PYTHONUNBUFFERED"}


def test_listening_on_every_address_still_prints_a_url_that_opens(tmp_path):
    root = make_tree(tmp_path)
    plan = launcher.build_plan(launcher.parse_args(["--host", "0.0.0.0"]), root, node="node")
    assert "0.0.0.0" in plan.child("backend").argv
    assert all("0.0.0.0" not in url for _, url in plan.urls)
    assert plan.child("ui").env["VITE_BACKEND_HTTP"] == "http://127.0.0.1:8000"


def test_the_audio_feed_is_only_started_when_asked_for(tmp_path):
    root = make_tree(tmp_path)
    assert launcher.build_plan(launcher.parse_args([]), root, node="node").child("audio") is None

    args = launcher.parse_args(["--audio", "--device", "Main Out", "--rig-id", "4", "--backend-port", "8765"])
    audio = launcher.build_plan(args, root, node="node").child("audio")
    assert audio.argv == [str(launcher.venv_python(root)), str(root / "scripts" / "launch_audio.py"),
                          "--backend-url", "http://127.0.0.1:8765", "--device", "Main Out", "--rig-id", "4"]
    assert audio.required is False


def test_without_a_venv_the_running_python_is_used_if_it_has_the_packages(tmp_path):
    root = make_tree(tmp_path, venv=False)
    assert launcher.resolve_python(root, current="/opt/py", current_has_uvicorn=lambda: True) == "/opt/py"
    assert launcher.resolve_python(root, current="/opt/py", current_has_uvicorn=lambda: False) is None


def test_a_dry_run_prints_the_commands_and_starts_nothing(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path, venv=False, node_modules=False)

    def never(*a, **k):
        raise AssertionError("a dry run started or probed something")

    monkeypatch.setattr(launcher.subprocess, "Popen", never)
    monkeypatch.setattr(launcher, "port_in_use", never)
    monkeypatch.setattr(launcher, "resolve_python", lambda root: None)

    args = launcher.parse_args(["--dry-run", "--backend-port", "8765", "--ui-port", "5199"])
    assert launcher.run(args, root) == 0

    out = capsys.readouterr().out
    plan = launcher.build_plan(args, root, python=None)
    for child in plan.children:
        assert launcher.format_command(child.argv) in out
    assert "VITE_BACKEND_HTTP=http://127.0.0.1:8765" in out
    assert "http://127.0.0.1:8765/health" in out
    assert "http://127.0.0.1:5199/" in out
    assert "uvicorn app.main:app" in out and "--port 8765" in out
    assert "Output target: not set by the launcher" in out


def test_a_command_with_a_space_in_its_path_can_be_pasted():
    argv = ["E:\\Lighting System\\python.exe", "-m", "uvicorn"]
    assert launcher.format_command(argv, platform="win32") == '"E:\\Lighting System\\python.exe" -m uvicorn'
    assert launcher.format_command(["/opt/my app/python", "-m"], platform="linux") == "'/opt/my app/python' -m"


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

def test_a_listening_port_is_in_use_and_a_closed_one_is_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert launcher.port_in_use(port) is True
    assert launcher.port_in_use(port) is False


def test_a_port_that_is_held_but_not_listening_is_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        assert launcher.port_in_use(holder.getsockname()[1]) is True


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_a_complete_install_passes(tmp_path):
    root = make_tree(tmp_path)
    results = run_preflight(launcher.parse_args([]), root)
    assert all(r.ok for r in results), launcher.format_preflight(results)
    assert "Preflight passed." in launcher.format_preflight(results)


def test_a_missing_venv_says_how_to_make_one(tmp_path):
    root = make_tree(tmp_path, venv=False)
    args = launcher.parse_args([])
    plan = launcher.build_plan(args, root, python=None, node="node")
    plan.python = None
    results = launcher.preflight(args, root, plan, environ={}, port_check=lambda p, h: False,
                                 python_check=lambda p: (True, ""), which=lambda n: "node")
    failure = by_name(results)["backend python"]
    assert not failure.ok
    assert "python -m venv venv" in failure.detail and "requirements.txt" in failure.detail


def test_a_venv_without_the_packages_says_so(tmp_path):
    root = make_tree(tmp_path)
    results = run_preflight(launcher.parse_args([]), root,
                            python_ok=(False, "ModuleNotFoundError: No module named 'uvicorn'"))
    failure = by_name(results)["backend python"]
    assert not failure.ok
    assert "No module named 'uvicorn'" in failure.detail and "requirements.txt" in failure.detail


def test_missing_ui_packages_give_the_command_and_the_way_round(tmp_path):
    root = make_tree(tmp_path, node_modules=False)
    failure = by_name(run_preflight(launcher.parse_args([]), root))["ui packages"]
    assert not failure.ok
    assert "npm install" in failure.detail and "--no-ui" in failure.detail
    assert str(root / "frontend") in failure.detail

    without_ui = run_preflight(launcher.parse_args(["--no-ui"]), root, node=None)
    assert all(r.ok for r in without_ui), launcher.format_preflight(without_ui)
    assert "ui packages" not in by_name(without_ui)


def test_no_node_is_a_failure_with_a_way_forward(tmp_path):
    root = make_tree(tmp_path)
    failure = by_name(run_preflight(launcher.parse_args([]), root, node=None))["node"]
    assert not failure.ok and "Node.js" in failure.detail


def test_a_busy_port_names_the_port_and_the_flag(tmp_path):
    root = make_tree(tmp_path)
    results = by_name(run_preflight(launcher.parse_args([]), root, busy={8000, 5173}))
    assert not results["backend port"].ok and not results["ui port"].ok
    assert "port 8000 is already in use" in results["backend port"].detail
    assert "--backend-port" in results["backend port"].detail
    assert "port 5173" in results["ui port"].detail and "--ui-port" in results["ui port"].detail


def test_a_data_folder_that_cannot_be_written_fails(tmp_path):
    root = make_tree(tmp_path)
    # A file where the folder should be: unwritable on every platform, as any user.
    (root / "backend" / "data").write_text("not a folder")
    failure = by_name(run_preflight(launcher.parse_args([]), root))["data folder"]
    assert not failure.ok
    assert "DATABASE_URL" in failure.detail and "permissions" in failure.detail


def test_the_data_folder_follows_database_url_like_the_backend(tmp_path):
    root = make_tree(tmp_path)
    assert launcher.resolve_data_dir(root, {}) == root / "backend" / "data"

    elsewhere = tmp_path / "state" / "lighting.db"
    env = {"DATABASE_URL": f"sqlite:///{elsewhere.as_posix()}"}
    assert launcher.resolve_data_dir(root, env) == elsewhere.parent

    (root / "backend" / ".env").write_text('# venue\nDATABASE_URL="sqlite:///./venue/show.db"\n')
    assert launcher.resolve_data_dir(root, {}) == root / "backend" / "venue"
    # The environment wins over the file, as it does for the backend.
    assert launcher.resolve_data_dir(root, env) == elsewhere.parent


def test_checking_leaves_no_files_behind(tmp_path):
    root = make_tree(tmp_path)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    run_preflight(launcher.parse_args([]), root)
    assert sorted(p.relative_to(root) for p in root.rglob("*")) == before


def test_every_problem_is_listed_in_one_pass_and_the_exit_code_is_not_zero(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path, venv=False, node_modules=False)
    monkeypatch.setattr(launcher, "resolve_python", lambda root: None)
    monkeypatch.setattr(launcher, "port_in_use", lambda port, host: True)
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("started a service after a failed preflight"))

    assert launcher.run(launcher.parse_args(["--check"]), root) == 1
    out = capsys.readouterr().out
    for name in ("backend python", "ui packages", "backend port", "ui port"):
        assert f"[FAIL] {name}" in out
    assert "Preflight failed: " in out and "Nothing was started." in out


def test_a_start_stops_at_a_failed_preflight(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path)
    monkeypatch.setattr(launcher, "port_in_use", lambda port, host: port == 8000)
    monkeypatch.setattr(launcher, "python_can_run_backend", lambda python: (True, ""))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "node")
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("started a service on a busy port"))

    assert launcher.run(launcher.parse_args([]), root) == 1
    assert "port 8000 is already in use" in capsys.readouterr().out


def test_a_passing_check_exits_zero_and_starts_nothing(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path)
    monkeypatch.setattr(launcher, "port_in_use", lambda port, host: False)
    monkeypatch.setattr(launcher, "python_can_run_backend", lambda python: (True, ""))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "node")
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("--check started a service"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ARTNET_IP", raising=False)

    assert launcher.run(launcher.parse_args(["--check"]), root) == 0
    assert "Preflight passed." in capsys.readouterr().out


def test_the_output_target_is_reported_and_broadcast_is_flagged(tmp_path):
    root = make_tree(tmp_path)
    unset = launcher.describe_output_target(root, {})
    assert unset.ok and unset.warning and "255.255.255.255" in unset.detail

    node = launcher.describe_output_target(root, {"ARTNET_IP": "10.0.0.50"})
    assert node.ok and not node.warning and "10.0.0.50" in node.detail

    (root / "backend" / ".env").write_text("ARTNET_IP=127.0.0.1\n")
    assert "127.0.0.1" in launcher.describe_output_target(root, {}).detail
    assert not launcher.describe_output_target(root, {}).warning


def test_a_database_server_is_named_without_its_password(tmp_path):
    root = make_tree(tmp_path)
    env = {"DATABASE_URL": "postgresql://lighting:hunter2@db.venue.lan:5432/lighting"}
    offline = by_name(run_preflight(launcher.parse_args([]), root, environ=env))["offline"]
    assert offline.warning and "db.venue.lan:5432" in offline.detail
    assert "hunter2" not in offline.detail


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_the_wait_ends_as_soon_as_the_service_answers():
    clock = FakeClock()
    replies = iter([False, False, True])
    asked = []

    def answers(url):
        asked.append(url)
        return next(replies)

    ok, message = launcher.wait_until_up("backend", "http://127.0.0.1:8765/health", FakeProcess(),
                                         timeout=30, answers=answers, sleep=clock.sleep, clock=clock)
    assert ok and "backend is up" in message
    assert asked == ["http://127.0.0.1:8765/health"] * 3
    assert clock.sleeps == [0.5, 0.5]


def test_a_degraded_backend_ends_the_wait_too():
    def degraded(url, timeout):
        raise urllib.error.HTTPError(url, 503, "degraded", {}, None)

    clock = FakeClock()
    ok, _ = launcher.wait_until_up(
        "backend", "http://127.0.0.1:8765/health", FakeProcess(), timeout=30,
        answers=lambda url: lh.backend_answers(url, opener=degraded), sleep=clock.sleep, clock=clock)
    assert ok and clock.sleeps == []


def test_the_wait_gives_up_at_the_timeout():
    clock = FakeClock()
    ok, message = launcher.wait_until_up("ui", "http://127.0.0.1:5199/", FakeProcess(), timeout=3,
                                         answers=lambda url: False, sleep=clock.sleep, clock=clock)
    assert not ok
    assert message == "ui did not answer at http://127.0.0.1:5199/ within 3s"
    assert sum(clock.sleeps) == pytest.approx(3.0)


def test_a_service_that_dies_is_reported_without_waiting_out_the_timeout():
    clock = FakeClock()
    ok, message = launcher.wait_until_up("backend", "http://x/health", FakeProcess(exits_after_polls=2),
                                         timeout=120, answers=lambda url: False,
                                         sleep=clock.sleep, clock=clock)
    assert not ok and "backend exited with code 3" in message
    assert clock.now < 2


def test_an_answer_from_a_port_whose_process_has_died_is_not_believed():
    def answers(url):
        raise AssertionError("asked a port whose process is gone: something else owns it")

    ok, message = launcher.wait_until_up("backend", "http://x/health", FakeProcess(exit_code=1),
                                         timeout=10, answers=answers, sleep=lambda s: None,
                                         clock=FakeClock())
    assert not ok and "exited with code 1" in message


# ---------------------------------------------------------------------------
# Stopping
# ---------------------------------------------------------------------------

def test_after_ctrl_c_the_children_are_waited_for_not_signalled_again():
    backend, ui = FakeProcess(), FakeProcess()
    launcher.stop_children([("backend", backend), ("ui", ui)], already_signalled=True,
                           log=lambda line: None)
    assert backend.calls == ["wait"] and ui.calls == ["wait"]


def test_a_stop_that_was_not_ctrl_c_asks_each_child_to_stop():
    proc = FakeProcess()
    launcher.stop_children([("backend", proc)], already_signalled=False, platform="linux",
                           log=lambda line: None)
    assert proc.calls == [("signal", signal.SIGINT), "wait"]

    proc = FakeProcess()
    launcher.stop_children([("backend", proc)], already_signalled=False, platform="win32",
                           log=lambda line: None)
    assert proc.calls == ["terminate", "wait"]


def test_a_child_that_will_not_stop_is_ended():
    stuck = FakeProcess(stops_on_wait=False)
    launcher.stop_children([("ui", stuck)], already_signalled=True, grace=0.01, log=lambda line: None)
    assert stuck.calls == ["wait", "terminate", "wait", "kill"]


def test_a_child_that_already_exited_is_left_alone():
    gone = FakeProcess(exit_code=0)
    launcher.stop_children([("ui", gone)], already_signalled=False, log=lambda line: None)
    assert gone.calls == []


def test_losing_the_ui_does_not_stop_the_lights_but_losing_the_backend_stops_the_run(tmp_path):
    root = make_tree(tmp_path)
    plan = launcher.build_plan(launcher.parse_args([]), root, node="node")
    backend, ui = FakeProcess(exits_after_polls=4), FakeProcess(exit_code=1)
    lines = []

    code = launcher.supervise([(plan.child("backend"), backend), (plan.child("ui"), ui)],
                              sleep=lambda s: None, log=lines.append)
    assert code == 1
    said = "\n".join(lines)
    assert said.count("ui exited with code 1") == 1 and "backend is still running" in said
    assert "backend exited with code 3; stopping everything" in said


def _fake_start(monkeypatch, root, answers):
    """Wire run() to fake processes; returns the list of (name, process) it started."""
    started = []

    def fake_spawn(child):
        proc = FakeProcess()
        started.append((child.name, proc))
        return proc

    monkeypatch.setattr(launcher, "spawn", fake_spawn)
    monkeypatch.setattr(launcher, "backend_answers", answers)
    monkeypatch.setattr(launcher, "port_in_use", lambda port, host: False)
    monkeypatch.setattr(launcher, "python_can_run_backend", lambda python: (True, ""))
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "node")
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(launcher.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("a test started a real process"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return started


def test_a_start_waits_for_both_prints_the_operator_url_and_ctrl_c_stops_both(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path)
    started = _fake_start(monkeypatch, root, answers=lambda url: True)

    def ctrl_c(running):
        raise KeyboardInterrupt

    monkeypatch.setattr(launcher, "supervise", ctrl_c)
    args = launcher.parse_args(["--backend-port", "8765", "--ui-port", "5199", "--audio"])
    assert launcher.run(args, root) == 0

    # The audio feed signs in to the backend, so it starts after the health checks.
    assert [name for name, _ in started] == ["backend", "ui", "audio"]
    out = capsys.readouterr().out
    assert out.index("backend is up") < out.index("ui is up") < out.index("Starting audio")
    assert "Operator screen: http://127.0.0.1:5199/" in out
    assert "All stopped." in out
    # The console already interrupted them: wait, do not signal again.
    assert all(proc.calls == ["wait"] for _, proc in started)


def test_a_service_that_never_answers_fails_the_start_and_leaves_nothing_running(tmp_path, capsys, monkeypatch):
    root = make_tree(tmp_path)
    started = _fake_start(monkeypatch, root, answers=lambda url: False)
    ticks = iter(range(0, 10_000, 5))
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(launcher, "supervise", lambda running: pytest.fail("reported ready"))

    assert launcher.run(launcher.parse_args(["--timeout", "10"]), root) == 1

    out = capsys.readouterr().out
    assert "backend did not answer at http://127.0.0.1:8000/health within 10s" in out
    assert "Ready." not in out
    assert [name for name, _ in started] == ["backend", "ui"]
    assert all(proc.exit_code is not None for _, proc in started)


# ---------------------------------------------------------------------------
# The entry points
# ---------------------------------------------------------------------------

def test_start_py_is_a_thin_way_in_that_needs_no_audio_packages():
    source = (REPO_ROOT / "start.py").read_text(encoding="utf-8")
    assert "from launcher import main" in source
    for heavy in ("pyaudio", "numpy", "websockets", "subprocess"):
        assert heavy not in source


def test_the_wrappers_hand_every_argument_to_start_py():
    bat = (REPO_ROOT / "start.bat").read_text(encoding="utf-8")
    assert '"%ROOT%start.py" %*' in bat
    sh = (REPO_ROOT / "start.sh").read_bytes()
    assert b'"$ROOT/start.py" "$@"' in sh
    assert b"\r" not in sh, "start.sh needs LF line endings to run"


def test_the_old_scripts_lead_to_the_one_launcher():
    for name in ("start_all.bat", "run_backend.bat", "run_dev.bat"):
        text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "start.bat" in text, name
        assert "uvicorn" not in text, f"{name} starts the backend its own way"
