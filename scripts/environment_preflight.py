#!/usr/bin/env python3
"""Local runtime preflight checks for the biomedical audit project."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
NODE_REQUIREMENT = "Node.js >=20.19.0 or >=22.12.0"
REQUIRED_MODULES = [
    "numpy",
    "cv2",
    "PIL",
    "yaml",
    "jsonschema",
    "openpyxl",
    "pypdf",
    "fitz",
    "requests",
    "fastapi",
    "uvicorn",
    "multipart",
    "detectors.image.global_near_duplicate",
    "detectors.image.channel_metadata_consistency",
    "detectors.image.keypoint_geometric_match",
    "detectors.image.local_patch_reuse",
    "detectors.image.splice_forensics_triage",
    "detectors.stats.pseudoreplication_screen",
    "detectors.text.external_literature_search",
    "detectors.text.text_overlap_screen",
    "webapp.__main__",
    "webapp.backend.app",
]


class PreflightError(RuntimeError):
    """Raised when a required local runtime dependency is unavailable."""


def parse_node_version(text: str) -> tuple[int, int, int] | None:
    token = text.strip().split()[0].lstrip("v")
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return major, minor, patch


def node_version_ok(version: tuple[int, int, int] | None) -> bool:
    if version is None:
        return False
    major, minor, patch = version
    if major == 20:
        return (minor, patch) >= (19, 0)
    if major == 22:
        return (minor, patch) >= (12, 0)
    return major > 22


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return (result.stdout or result.stderr or "").strip()


def frontend_dist_ready(frontend: Path) -> bool:
    return (frontend / "dist" / "index.html").is_file()


def ensure_node_runtime(frontend: Path, *, require_build: bool) -> str | None:
    npm = shutil.which("npm")
    dist_ready = frontend_dist_ready(frontend)
    if not npm:
        if dist_ready and not require_build:
            print("WARN: npm was not found; using existing webapp/frontend/dist build.", file=sys.stderr)
            return None
        raise PreflightError(
            "npm is required to build the local web UI from source. "
            "Install Node.js/npm or use a release build that already includes webapp/frontend/dist/."
        )

    node = shutil.which("node")
    if not node:
        raise PreflightError("node was not found even though npm is available. Install Node.js before building the web UI.")
    raw_version = command_output([node, "--version"])
    parsed = parse_node_version(raw_version)
    if not node_version_ok(parsed):
        if dist_ready and not require_build:
            print(
                f"WARN: found node {raw_version or 'unknown'}, but the frontend build requires {NODE_REQUIREMENT}; "
                "using existing webapp/frontend/dist build.",
                file=sys.stderr,
            )
            return None
        raise PreflightError(
            f"Frontend build requires {NODE_REQUIREMENT}; found {raw_version or 'unknown'}. "
            "Upgrade Node.js before running the local web app from source."
        )
    return npm


def check_python_runtime() -> list[str]:
    failures = []
    if sys.version_info < (3, 10):
        failures.append(f"Python 3.10+ is required; found {sys.version.split()[0]}.")
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - user-facing preflight surface.
            failures.append(f"Python module `{module}` is unavailable: {type(exc).__name__}: {exc}")
    return failures


def check_tesseract(required: bool) -> list[str]:
    if shutil.which("tesseract"):
        return []
    message = (
        "tesseract binary was not found. Scanned/image-only PDF OCR will be unavailable until "
        "Tesseract is installed and on PATH."
    )
    return [message] if required else [f"WARN: {message}"]


def run_preflight(root: Path, *, require_webapp: bool, require_ocr: bool) -> int:
    failures = check_python_runtime()
    notices = check_tesseract(require_ocr)
    if require_ocr:
        failures.extend(notices)
        notices = []

    frontend = root / "webapp" / "frontend"
    if frontend.exists():
        try:
            ensure_node_runtime(frontend, require_build=require_webapp or not frontend_dist_ready(frontend))
        except PreflightError as exc:
            if require_webapp:
                failures.append(str(exc))
            else:
                notices.append(f"WARN: {exc}")

    for notice in notices:
        print(notice)
    if failures:
        print("Environment preflight failed:")
        for failure in failures:
            print(f"- {failure}")
        print("")
        print("Recommended setup:")
        print("  python3 -m venv .venv")
        print("  .venv/bin/python -m pip install --upgrade pip")
        print("  .venv/bin/python -m pip install -r requirements.txt")
        if require_webapp:
            print(f"  Install {NODE_REQUIREMENT} for the local web UI.")
        return 1
    print("Environment preflight passed.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-webapp", action="store_true", help="Fail if Node/npm cannot build the web UI.")
    parser.add_argument("--require-ocr", action="store_true", help="Fail if the tesseract OCR binary is unavailable.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_preflight(args.root.expanduser().resolve(), require_webapp=args.require_webapp, require_ocr=args.require_ocr)


if __name__ == "__main__":
    raise SystemExit(main())
