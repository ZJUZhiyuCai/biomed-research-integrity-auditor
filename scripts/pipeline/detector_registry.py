"""YAML-backed extension detector registry.

The core pipeline keeps its curated built-in detector stages explicit. This
registry is for local or contributed extension detectors that already emit the
standard detector-output contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.pipeline.common import PYTHON, ROOT, has_files
from scripts.pipeline.detectors import run_detector


DEFAULT_REGISTRY = ROOT / "schemas" / "detector_registry.yaml"
ALLOWED_KEYS = {
    "name",
    "output",
    "command",
    "profiles",
    "modes",
    "run_if_any_suffix",
}


def load_detector_registry(path: Path) -> list[dict[str, Any]]:
    registry_path = path
    if not registry_path.exists():
        return []
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    detectors = payload.get("detectors", [])
    if not isinstance(detectors, list):
        raise ValueError(f"Detector registry {registry_path} must define detectors as a list")
    normalized = []
    for idx, item in enumerate(detectors, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Detector registry item {idx} must be a mapping")
        unknown = sorted(set(item) - ALLOWED_KEYS)
        if unknown:
            raise ValueError(f"Detector registry item {idx} has unsupported keys: {', '.join(unknown)}")
        name = str(item.get("name", "")).strip()
        output = str(item.get("output", "")).strip()
        command = item.get("command")
        if not name:
            raise ValueError(f"Detector registry item {idx} must define name")
        if not output:
            raise ValueError(f"Detector registry item {idx} must define output")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
            raise ValueError(f"Detector registry item {idx} must define command as a non-empty list of strings")
        normalized.append(item)
    return normalized


def normalized_output_path(output_dir: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Registered detector output must stay inside output_dir: {value}")
    return output_dir / candidate


def detector_enabled(detector: dict[str, Any], package: Path, mode: str, scan_profile: str) -> bool:
    modes = detector.get("modes")
    if modes and mode not in {str(item) for item in modes}:
        return False
    profiles = detector.get("profiles")
    if profiles and scan_profile not in {str(item) for item in profiles}:
        return False
    suffixes = detector.get("run_if_any_suffix")
    if suffixes:
        suffix_set = {str(item).lower() for item in suffixes}
        if not has_files(package, suffix_set):
            return False
    return True


def expand_command(
    command: list[str],
    *,
    package: Path,
    output_dir: Path,
    output: Path,
    mode: str,
    scan_profile: str,
    provenance_graph: Path | None,
) -> list[str]:
    mapping = {
        "python": PYTHON,
        "root": str(ROOT),
        "package": str(package),
        "output_dir": str(output_dir),
        "output": str(output),
        "mode": mode,
        "scan_profile": scan_profile,
        "provenance_graph": str(provenance_graph or ""),
    }
    return [part.format(**mapping) for part in command]


def run_registered_detectors(
    package: Path,
    output_dir: Path,
    *,
    mode: str,
    scan_profile: str,
    registry_path: Path | None = None,
    provenance_graph: Path | None = None,
) -> list[Path]:
    if registry_path is None:
        return []
    outputs: list[Path] = []
    for detector in load_detector_registry(registry_path):
        if not detector_enabled(detector, package, mode, scan_profile):
            continue
        name = str(detector["name"])
        output = normalized_output_path(output_dir, str(detector["output"]))
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = expand_command(
            list(detector["command"]),
            package=package,
            output_dir=output_dir,
            output=output,
            mode=mode,
            scan_profile=scan_profile,
            provenance_graph=provenance_graph,
        )
        result = run_detector(f"registered_{name}", package, output_dir, cmd, output)
        outputs.append(result.output)
    return outputs
