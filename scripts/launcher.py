"""
One Launcher
============

`python start.py` starts the backend and the operator UI, waits until both
answer, prints the operator URL and stops everything on Ctrl+C.

Standard library only, and nothing runs at import, so it starts under any
Python and can be tested without spawning a service.

Three rules it keeps:

- It never chooses where the lights are sent. ARTNET_IP comes from the
  environment or backend/.env, exactly as when the backend is started by hand.
- It never installs anything. A missing dependency is a preflight failure with
  the command to run, because a venue box may have no internet.
- The command a dry run prints is the command a real start runs: both read
  the same plan.
"""

import argparse
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_helpers import backend_answers  # noqa: E402

DEFAULT_BACKEND_PORT = 8000
DEFAULT_UI_PORT = 5173
DEFAULT_HOST = "127.0.0.1"
DEFAULT_TIMEOUT = 120.0
# Health checks and the UI's proxy always use loopback, whatever --host binds.
LOOPBACK = "127.0.0.1"
BROADCAST_DEFAULT = "255.255.255.255"

ROOT_DIR = Path(__file__).resolve().parents[1]


class StopRequested(Exception):
    """Raised by the SIGTERM handler: stop, and the children have not been told."""


@dataclass
class Child:
    """One process the launcher starts."""

    name: str
    argv: List[str]
    cwd: Path
    env: Dict[str, str] = field(default_factory=dict)  # added to the inherited environment
    health_url: Optional[str] = None
    # A required child that exits takes the launcher down with it. The UI and
    # the audio feed are not required: losing a screen must not stop the lights.
    required: bool = True


@dataclass
class Plan:
    children: List[Child]
    urls: List[Tuple[str, str]]
    ui_mode: Optional[str]  # "dev", "preview" or None with --no-ui
    python: Optional[str]

    def child(self, name: str) -> Optional[Child]:
        return next((c for c in self.children if c.name == name), None)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    warning: bool = False  # ok is True; worth reading before a show


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a port number")
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"port {port} is outside 1-65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start.py",
        description="Start the Intelligent Lighting System: backend, operator UI, health check.",
    )
    parser.add_argument("--backend-port", type=_port, default=DEFAULT_BACKEND_PORT,
                        help=f"Backend port (default {DEFAULT_BACKEND_PORT})")
    parser.add_argument("--ui-port", type=_port, default=DEFAULT_UI_PORT,
                        help=f"Operator UI port (default {DEFAULT_UI_PORT})")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"Address to listen on (default {DEFAULT_HOST}; "
                             "0.0.0.0 lets a tablet on the same network reach the UI)")
    parser.add_argument("--no-ui", action="store_true", help="Start the backend only")
    parser.add_argument("--ui-mode", choices=("auto", "dev", "preview"), default="auto",
                        help="auto serves frontend/dist when it has been built, else the dev server")
    parser.add_argument("--check", action="store_true",
                        help="Preflight only: report what is missing or busy and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the exact commands a start would run and exit")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"Seconds to wait for each service to answer (default {DEFAULT_TIMEOUT:.0f})")
    parser.add_argument("--open", action="store_true", help="Open the operator screen in a browser")
    parser.add_argument("--audio", action="store_true",
                        help="Also feed this machine's audio to the backend (needs pyaudio in the backend venv)")
    parser.add_argument("--device", default=None,
                        help="With --audio: device index or part of its name (or set ILS_AUDIO_DEVICE)")
    parser.add_argument("--rig-id", default=None,
                        help="With --audio: rig to drive (or set ILS_RIG_ID); default is the active rig")
    # Accepted so the command in older notes still runs; a browser is no longer opened by default.
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    return parser


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.no_ui and args.backend_port == args.ui_port:
        parser.error(f"--backend-port and --ui-port are both {args.ui_port}; they need different ports")
    if args.timeout <= 0:
        parser.error("--timeout must be more than 0 seconds")
    # start.py used to capture audio on every start, so an old command line
    # (`--device "Main Out" --no-browser`) still parses but would feed nothing.
    args.audio_options_unused = not args.audio and (args.device is not None or args.rig_id is not None)
    if args.device is None:
        args.device = os.getenv("ILS_AUDIO_DEVICE")
    return args


AUDIO_OPTIONS_UNUSED = ("NOTE: --device and --rig-id only apply with --audio. No audio feed is started: "
                        "add --audio, or pick the audio device in the UI.")


# ---------------------------------------------------------------------------
# What would run
# ---------------------------------------------------------------------------

def venv_python(root: Path, platform: str = sys.platform) -> Path:
    """Where the backend's own interpreter lives when the venv has been made."""
    if platform == "win32":
        return root / "backend" / "venv" / "Scripts" / "python.exe"
    return root / "backend" / "venv" / "bin" / "python"


def _current_has_uvicorn() -> bool:
    import importlib.util
    return importlib.util.find_spec("uvicorn") is not None


def resolve_python(root: Path, current: str = sys.executable,
                   current_has_uvicorn: Callable[[], bool] = _current_has_uvicorn,
                   platform: str = sys.platform) -> Optional[str]:
    """The interpreter the backend runs under, or None when there is none.

    backend/venv wins. Without it, the interpreter running the launcher is
    used if it has the backend's packages (a venv kept somewhere else).
    """
    candidate = venv_python(root, platform)
    if candidate.exists():
        return str(candidate)
    if current and current_has_uvicorn():
        return str(current)
    return None


def resolve_ui_mode(root: Path, requested: str = "auto") -> str:
    """"preview" serves the built app, "dev" the Vite dev server."""
    if requested in ("dev", "preview"):
        return requested
    return "preview" if (root / "frontend" / "dist" / "index.html").exists() else "dev"


def vite_entry(root: Path) -> Path:
    """Vite's own script. Run with node directly: npm is a .cmd on Windows,
    needs a shell, and leaves node running when it is stopped."""
    return root / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"


def _shown_host(host: str) -> str:
    return LOOPBACK if host in ("0.0.0.0", "::", "") else host


def build_plan(args: argparse.Namespace, root: Path = ROOT_DIR, python: Optional[str] = None,
               node: Optional[str] = None) -> Plan:
    """Every command a start would run, and the URLs it would print."""
    if python is None:
        python = resolve_python(root)
    # A dry run still prints a full command when nothing is installed yet.
    shown_python = python or str(venv_python(root))
    backend_dir = root / "backend"
    backend_base = f"http://{LOOPBACK}:{args.backend_port}"

    children = [Child(
        name="backend",
        # No --reload: the reloader is a second process that outlives a stop.
        argv=[shown_python, "-m", "uvicorn", "app.main:app",
              "--host", args.host, "--port", str(args.backend_port)],
        cwd=backend_dir,
        # So the first-run setup code reaches the console as it is printed.
        env={"PYTHONUNBUFFERED": "1"},
        health_url=f"{backend_base}/health",
    )]
    shown = _shown_host(args.host)
    urls: List[Tuple[str, str]] = []
    ui_mode = None

    if not args.no_ui:
        ui_mode = resolve_ui_mode(root, args.ui_mode)
        if node is None:
            node = shutil.which("node") or "node"
        argv = [node, str(vite_entry(root))]
        if ui_mode == "preview":
            argv.append("preview")
        # --strictPort: Vite otherwise moves to the next free port without
        # saying so, and the health check would then wait on the wrong one.
        argv += ["--host", args.host, "--port", str(args.ui_port), "--strictPort"]
        children.append(Child(
            name="ui",
            argv=argv,
            cwd=root / "frontend",
            # vite.config.ts proxies /api and /ws here, and defaults to 8000.
            env={"VITE_BACKEND_HTTP": backend_base,
                 "VITE_BACKEND_WS": f"ws://{LOOPBACK}:{args.backend_port}"},
            health_url=f"http://{LOOPBACK}:{args.ui_port}/",
            required=False,
        ))
        urls.append(("Operator screen", f"http://{shown}:{args.ui_port}/"))
        urls.append(("3D visualizer", f"http://{shown}:{args.ui_port}/visualizer"))

    if args.audio:
        argv = [shown_python, str(root / "scripts" / "launch_audio.py"), "--backend-url", backend_base]
        if args.device not in (None, ""):
            argv += ["--device", str(args.device)]
        if args.rig_id not in (None, ""):
            argv += ["--rig-id", str(args.rig_id)]
        children.append(Child(name="audio", argv=argv, cwd=root, required=False))

    urls.append(("Backend API", f"http://{shown}:{args.backend_port}"))
    urls.append(("Health", f"http://{shown}:{args.backend_port}/health"))
    return Plan(children=children, urls=urls, ui_mode=ui_mode, python=python)


def format_command(argv: Sequence[str], platform: str = sys.platform) -> str:
    """The command as it could be pasted into this platform's shell."""
    if platform == "win32":
        return subprocess.list2cmdline(list(argv))
    return shlex.join(argv)


def format_plan(plan: Plan, platform: str = sys.platform) -> str:
    setter = "set" if platform == "win32" else "export"
    lines = ["Dry run: nothing is started. A start would run:", ""]
    for child in plan.children:
        note = ""
        if child.name == "ui":
            note = "  (built app from frontend/dist)" if plan.ui_mode == "preview" else "  (Vite dev server)"
        lines.append(f"[{child.name}]{note}")
        lines.append(f"  cd {format_command([str(child.cwd)], platform)}")
        for key, value in child.env.items():
            lines.append(f"  {setter} {key}={value}")
        lines.append(f"  {format_command(child.argv, platform)}")
        if child.health_url:
            lines.append(f"  health check: {child.health_url}")
        lines.append("")
    lines.append("Output target: not set by the launcher (ARTNET_IP from the environment or backend/.env).")
    lines.append("")
    lines.append("Then print:")
    lines += [f"  {label + ':':17s}{url}" for label, url in plan.urls]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def port_in_use(port: int, host: str = DEFAULT_HOST, connect_timeout: float = 0.3) -> bool:
    """True when something already holds the port.

    Two probes, because either alone misses a case: a connect finds a listener
    on any local address (a Vite bound to ::1 only, say), and a bind finds a
    port that is held but not yet listening. SO_REUSEADDR is left off: on
    Windows it lets a bind succeed on a port another process is using.
    """
    for family, address in ((socket.AF_INET, LOOPBACK), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(connect_timeout)
                if probe.connect_ex((address, port)) == 0:
                    return True
        except OSError:
            pass  # no IPv6 on this machine, for one
    try:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
    except OSError:
        return True
    return False


def read_env_file(path: Path) -> Dict[str, str]:
    """KEY=VALUE pairs from a .env file; a missing file is an empty one."""
    values: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def backend_setting(key: str, root: Path, environ: Optional[Dict[str, str]] = None) -> Optional[str]:
    """A backend setting as the backend will see it: environment, then backend/.env."""
    environ = os.environ if environ is None else environ
    if key in environ:
        return environ[key]
    return read_env_file(root / "backend" / ".env").get(key)


def resolve_data_dir(root: Path, environ: Optional[Dict[str, str]] = None) -> Path:
    """The directory the backend keeps its database and signing key in.

    Worked out the way app.core.config does, without importing it: importing
    the settings writes a signing key, and a check should change nothing.
    """
    backend_dir = root / "backend"
    url = backend_setting("DATABASE_URL", root, environ)
    if not url:
        return backend_dir / "data"
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and db_path != ":memory:":
            path = Path(db_path)
            if not path.is_absolute():
                path = backend_dir / path
            return path.parent
    return backend_dir


def dir_writable(path: Path) -> Tuple[bool, str]:
    """Whether a file can be made in `path`, or in its nearest existing parent
    when the backend has not created it yet. Leaves nothing behind."""
    target = path
    while not target.exists():
        if target.parent == target:
            return False, f"{path} does not exist and has no existing parent"
        target = target.parent
    if not target.is_dir():
        return False, f"{target} is a file, not a folder"
    try:
        with tempfile.TemporaryFile(dir=str(target)):
            pass
    except OSError as exc:
        return False, f"cannot write in {target} ({exc.strerror or exc})"
    if target != path:
        return True, f"{path} (will be created on first start)"
    return True, str(path)


def python_can_run_backend(python: str, run: Optional[Callable] = None) -> Tuple[bool, str]:
    """Ask the backend's interpreter whether it has the server packages."""
    try:
        result = (run or subprocess.run)([python, "-c", "import uvicorn, fastapi"],
                     capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return False, str(exc)
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()
        return False, tail[-1] if tail else f"exit code {result.returncode}"
    return True, ""


def _install_backend_hint(root: Path, platform: str = sys.platform) -> str:
    pip = "venv\\Scripts\\pip" if platform == "win32" else "venv/bin/pip"
    return (f"in {root / 'backend'} run: python -m venv venv   then   "
            f"{pip} install -r requirements.txt   (needs internet once)")


def describe_output_target(root: Path, environ: Optional[Dict[str, str]] = None) -> CheckResult:
    """Where the backend will send Art-Net. Reported, never changed."""
    target = backend_setting("ARTNET_IP", root, environ)
    source = "ARTNET_IP"
    if target is None:
        target, source = BROADCAST_DEFAULT, "the backend's default; ARTNET_IP is not set"
    detail = f"{target} ({source}); the launcher does not change it"
    if target.endswith(".255"):
        return CheckResult("output target", True,
                           detail + ". This is a broadcast address: every Art-Net device on the network "
                           "receives a patched rig's output. Set ARTNET_IP in backend/.env to one node "
                           "(or 127.0.0.1 for the bench).", warning=True)
    return CheckResult("output target", True, detail)


def preflight(args: argparse.Namespace, root: Path = ROOT_DIR, plan: Optional[Plan] = None,
              environ: Optional[Dict[str, str]] = None,
              port_check: Optional[Callable[[int, str], bool]] = None,
              python_check: Optional[Callable[[str], Tuple[bool, str]]] = None,
              which: Optional[Callable[[str], Optional[str]]] = None,
              platform: str = sys.platform) -> List[CheckResult]:
    """Everything that would stop a start, found before anything is started.

    Every check runs, so one pass lists all there is to fix.
    """
    if plan is None:
        plan = build_plan(args, root)
    port_check = port_check or port_in_use
    python_check = python_check or python_can_run_backend
    which = which or shutil.which
    results: List[CheckResult] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append(CheckResult(name, ok, detail))

    # Backend
    if not (root / "backend" / "app" / "main.py").exists():
        add("backend code", False, f"{root / 'backend' / 'app' / 'main.py'} is missing; "
                                   "run the launcher from a full checkout")
    if plan.python is None:
        add("backend python", False,
            f"no Python with the backend's packages. Expected {venv_python(root, platform)}; "
            + _install_backend_hint(root, platform))
    else:
        ok, why = python_check(plan.python)
        if ok:
            add("backend python", True, plan.python)
        else:
            add("backend python", False,
                f"{plan.python} cannot import the server packages ({why}); "
                + _install_backend_hint(root, platform))

    # UI
    if not args.no_ui:
        frontend = root / "frontend"
        if which("node") is None:
            add("node", False, "node is not on PATH; install Node.js 18 or newer, or start with --no-ui")
        else:
            add("node", True, str(which("node")))
        if vite_entry(root).exists():
            add("ui packages", True, str(frontend / "node_modules"))
        else:
            add("ui packages", False,
                f"{frontend / 'node_modules'} is missing or incomplete; in {frontend} run: "
                "npm install   (needs internet once), or start with --no-ui")
        if plan.ui_mode == "preview":
            if (frontend / "dist" / "index.html").exists():
                add("ui build", True, f"serving the built app in {frontend / 'dist'}; "
                                      "rebuild with `npm run build` after UI changes, or use --ui-mode dev")
            else:
                add("ui build", False, f"--ui-mode preview needs {frontend / 'dist'}; "
                                       f"in {frontend} run: npm run build")
        else:
            add("ui build", True, "no built app in frontend/dist; using the Vite dev server")

    # Ports
    ports = [("backend port", args.backend_port, "--backend-port")]
    if not args.no_ui:
        ports.append(("ui port", args.ui_port, "--ui-port"))
    for name, port, flag in ports:
        if port_check(port, args.host):
            add(name, False, f"port {port} is already in use; stop what is using it "
                             f"(the system may already be running) or pass {flag} with a free port")
        else:
            add(name, True, f"{port} is free")

    # Data
    data_dir = resolve_data_dir(root, environ)
    ok, detail = dir_writable(data_dir)
    add("data folder", ok, detail if ok else
        f"{detail}; the database and the login key are kept there, so fix its permissions "
        "or point DATABASE_URL somewhere writable")

    # Offline
    url = backend_setting("DATABASE_URL", root, environ) or ""
    if url and not url.startswith("sqlite"):
        # Host only: the URL carries the database password.
        host = url.rsplit("@", 1)[-1].split("/", 1)[0] or "?"
        results.append(CheckResult(
            "offline", True,
            f"DATABASE_URL points at a database server ({host}); it has to be reachable "
            "without internet. Remove DATABASE_URL to use the local file database.", warning=True))
    else:
        add("offline", True, "nothing is downloaded or installed at start; "
                             "database is a local file; health checks use 127.0.0.1")

    if args.audio and not (root / "scripts" / "launch_audio.py").exists():
        add("audio feed", False, f"{root / 'scripts' / 'launch_audio.py'} is missing")

    results.append(describe_output_target(root, environ))
    return results


def format_preflight(results: Sequence[CheckResult]) -> str:
    lines = []
    for r in results:
        tag = "FAIL" if not r.ok else ("WARN" if r.warning else " ok ")
        lines.append(f"  [{tag}] {r.name}: {r.detail}")
    failed = [r for r in results if not r.ok]
    lines.append("")
    if failed:
        lines.append(f"Preflight failed: {len(failed)} problem(s) to fix "
                     f"({', '.join(r.name for r in failed)}). Nothing was started.")
    else:
        lines.append("Preflight passed.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Starting, waiting, stopping
# ---------------------------------------------------------------------------

def wait_until_up(name: str, url: str, proc, timeout: float,
                  answers: Optional[Callable[[str], bool]] = None,
                  sleep: Optional[Callable[[float], None]] = None,
                  clock: Optional[Callable[[], float]] = None,
                  interval: float = 0.5) -> Tuple[bool, str]:
    """Poll `url` until it answers. Gives up when the process exits or time runs out.

    The process is looked at first each round: once it has exited, an answer
    on its port would be some other program's.
    """
    answers = answers or backend_answers
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    started = clock()
    while True:
        code = proc.poll()
        if code is not None:
            return False, f"{name} exited with code {code} before it answered; its output is above"
        if answers(url):
            return True, f"{name} is up ({clock() - started:.0f}s)"
        if clock() - started >= timeout:
            return False, f"{name} did not answer at {url} within {timeout:.0f}s"
        sleep(interval)


def spawn(child: Child, environ: Optional[Dict[str, str]] = None, popen: Optional[Callable] = None):
    """Start one child in this console.

    Its output is inherited, not piped: a pipe nobody reads fills and blocks
    the child. No new process group: the child must receive the console's
    Ctrl+C itself so that it shuts down on its own terms.
    """
    env = dict(os.environ if environ is None else environ)
    env.update(child.env)
    return (popen or subprocess.Popen)(child.argv, cwd=str(child.cwd), env=env)


def stop_children(running: Sequence[Tuple[str, object]], already_signalled: bool,
                  grace: float = 10.0, platform: str = sys.platform,
                  log: Callable[[str], None] = print) -> None:
    """Stop every child, gently first.

    After Ctrl+C the console has already interrupted each child, so they are
    only waited for; a second signal would cut uvicorn's shutdown short. On
    any other stop they are asked here: SIGINT where there is one, terminate
    on Windows, which has no gentler request for a process sharing a console.
    """
    alive = [(name, proc) for name, proc in running if proc.poll() is None]
    if not already_signalled:
        for name, proc in alive:
            try:
                if platform == "win32":
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGINT)
            except Exception:
                pass
    for name, proc in reversed(alive):
        log(f"  Stopping {name}...")
        try:
            proc.wait(timeout=grace)
            continue
        except subprocess.TimeoutExpired:
            log(f"  {name} did not stop within {grace:.0f}s; ending it")
        except KeyboardInterrupt:
            log(f"  Not waiting for {name}; ending it")
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _raise_stop(signum, frame):
    raise StopRequested()


def supervise(running: Sequence[Tuple[Child, object]], sleep: Optional[Callable[[float], None]] = None,
              log: Callable[[str], None] = print) -> int:
    """Wait until a required child exits. Returns the launcher's exit code."""
    sleep = sleep or time.sleep
    reported = set()
    while True:
        for child, proc in running:
            code = proc.poll()
            if code is None or child.name in reported:
                continue
            if child.required:
                log(f"\n{child.name} exited with code {code}; stopping everything")
                return 1
            reported.add(child.name)
            log(f"\n{child.name} exited with code {code}. The backend is still running; "
                "restart the launcher to bring it back.")
        sleep(0.5)


def run(args: argparse.Namespace, root: Path = ROOT_DIR) -> int:
    plan = build_plan(args, root)

    if args.dry_run:
        print(format_plan(plan))
        if args.audio_options_unused:
            print("\n" + AUDIO_OPTIONS_UNUSED)
        return 0

    print("Intelligent Lighting System")
    if args.audio_options_unused:
        print(AUDIO_OPTIONS_UNUSED)
    print("Preflight:")
    results = preflight(args, root, plan)
    print(format_preflight(results))
    if any(not r.ok for r in results):
        return 1
    if args.check:
        return 0

    running: List[Tuple[Child, object]] = []
    signalled = False
    previous_term = signal.signal(signal.SIGTERM, _raise_stop)
    try:
        print()
        later = []
        for child in plan.children:
            if child.name == "audio":
                later.append(child)  # it signs in to the backend, so the backend goes first
                continue
            print(f"Starting {child.name}...")
            running.append((child, spawn(child)))

        for child, proc in list(running):
            ok, message = wait_until_up(child.name, child.health_url, proc, args.timeout)
            print(f"  {message}")
            if not ok:
                return 1

        for child in later:
            print(f"Starting {child.name}...")
            running.append((child, spawn(child)))

        print()
        print("=" * 60)
        print("  Ready.")
        for label, url in plan.urls:
            print(f"  {label + ':':17s}{url}")
        if plan.ui_mode == "preview":
            print("  (UI is the built app in frontend/dist)")
        print("  Press Ctrl+C to stop everything.")
        print("=" * 60, flush=True)

        if args.open and plan.urls and not args.no_ui:
            webbrowser.open(plan.urls[0][1])

        return supervise(running)
    except KeyboardInterrupt:
        signalled = True
        print("\nStopping...")
        return 0
    except StopRequested:
        print("\nStop requested...")
        return 0
    finally:
        try:
            stop_children([(c.name, p) for c, p in running], already_signalled=signalled)
        finally:
            signal.signal(signal.SIGTERM, previous_term)
        if running:
            print("All stopped.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
