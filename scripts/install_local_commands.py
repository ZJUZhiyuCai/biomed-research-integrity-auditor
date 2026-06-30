#!/usr/bin/env python3
"""Install local console commands for the biomedical audit project."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    "biomed-audit",
    "biomed-audit-diff",
    "biomed-audit-web",
    "biomed-self-audit-webapp",
)


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


def python_bin(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def command_bin(venv: Path, command: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return venv / ("Scripts" if os.name == "nt" else "bin") / f"{command}{suffix}"


def ensure_python_version() -> None:
    if sys.version_info >= (3, 10):
        return
    for name in ("python3.11", "python3.10"):
        candidate = shutil.which(name)
        if candidate and candidate_python_ok(candidate):
            print(f"Current Python is {sys.version.split()[0]}; re-running with {candidate}.")
            os.execv(candidate, [candidate, *sys.argv])
    raise SystemExit("Python 3.10+ is required. Re-run with python3.10 or python3.11.")


def build_frontend(skip: bool) -> None:
    if skip:
        return
    frontend = ROOT / "webapp" / "frontend"
    if not frontend.exists():
        return
    npm = shutil.which("npm")
    if not npm:
        print("npm was not found; skipping frontend build. Install Node/npm to build the web UI.", file=sys.stderr)
        return
    if not (frontend / "node_modules").exists():
        run([npm, "install"], frontend)
    run([npm, "run", "build"], frontend)


def link_command(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        target.unlink()
    if os.name == "nt":
        shutil.copy2(source, target)
    else:
        target.symlink_to(source)


def install_commands(venv: Path, bin_dir: Path) -> None:
    for command in COMMANDS:
        source = command_bin(venv, command)
        if not source.exists():
            raise SystemExit(f"Expected console script was not installed: {source}")
        target = bin_dir / command
        link_command(source, target)
        print(f"linked {target} -> {source}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=ROOT / ".venv", help="Virtual environment path.")
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=Path.home() / ".local" / "bin",
        help="Directory where stable command links are written.",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="Install Python commands without rebuilding the React frontend.",
    )
    return parser.parse_args()


def main() -> int:
    ensure_python_version()
    args = parse_args()
    venv = args.venv.expanduser().resolve()
    bin_dir = args.bin_dir.expanduser().resolve()

    if not python_bin(venv).exists():
        run([sys.executable, "-m", "venv", str(venv)])

    py = str(python_bin(venv))
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-r", "requirements.txt"])
    run([py, "-m", "pip", "install", "-e", "."])
    build_frontend(args.skip_frontend_build)
    install_commands(venv, bin_dir)

    print("")
    print("Installed commands:")
    for command in COMMANDS:
        print(f"  {bin_dir / command}")
    print("")
    print(f"Make sure {bin_dir} is on PATH before launching the commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
