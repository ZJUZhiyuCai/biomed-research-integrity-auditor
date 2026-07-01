#!/usr/bin/env python3
"""Prepare and launch the local self-audit web app from a source checkout."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VENV = ROOT / ".venv"


def run(cmd: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def candidate_python_ok(candidate: str) -> bool:
    try:
        result = subprocess.run(
            [
                candidate,
                "-c",
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def ensure_python_version() -> None:
    if sys.version_info >= (3, 10):
        return
    for name in ("python3.12", "python3.11", "python3.10"):
        candidate = shutil.which(name)
        if candidate and candidate_python_ok(candidate):
            print(f"Current Python is {sys.version.split()[0]}; re-running with {candidate}.")
            os.execv(candidate, [candidate, *sys.argv])
    raise SystemExit("Python 3.10+ is required. Install Python 3.10+ or run with PYTHON=python3.11 make run.")


def python_bin(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv(venv: Path) -> Path:
    py = python_bin(venv)
    if not py.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    return py


def install_python_dependencies(py: Path, skip_install: bool) -> None:
    if skip_install:
        return
    run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(py), "-m", "pip", "install", "-r", "requirements.txt"])
    run([str(py), "-m", "pip", "install", "-e", "."])


def build_frontend(skip_frontend: bool) -> None:
    if skip_frontend:
        return
    frontend = ROOT / "webapp" / "frontend"
    dist_index = frontend / "dist" / "index.html"
    if not frontend.exists():
        raise SystemExit("Missing webapp/frontend directory.")
    npm = shutil.which("npm")
    if not npm:
        if dist_index.exists():
            print("npm not found; using existing webapp/frontend/dist build.", file=sys.stderr)
            return
        raise SystemExit("npm is required to build the browser UI. Install Node/npm or use a release build with dist/.")
    if not (frontend / "node_modules").exists():
        run([npm, "install"], frontend)
    run([npm, "run", "build"], frontend)


def port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=DEFAULT_VENV, help="Virtual environment path.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--skip-install", action="store_true", help="Skip pip install steps.")
    parser.add_argument("--skip-frontend-build", action="store_true", help="Skip npm install/build steps.")
    return parser.parse_args()


def main() -> int:
    ensure_python_version()
    args = parse_args()
    url = f"http://{args.host}:{args.port}"
    if port_is_open(args.host, args.port):
        print(f"Local self-audit web app already appears to be running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    venv = args.venv.expanduser().resolve()
    py = ensure_venv(venv)
    install_python_dependencies(py, args.skip_install)
    build_frontend(args.skip_frontend_build)

    print("")
    print(f"Starting local self-audit web app at {url}")
    print("Press Ctrl+C in this terminal to stop it.")
    cmd = [str(py), "-m", "webapp", "--host", args.host, "--port", str(args.port)]
    if args.no_browser:
        cmd.append("--no-browser")
    run(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
