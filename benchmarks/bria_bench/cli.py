"""Resumable and integrity-checked orchestration for BRIA-Bench."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ADAPTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_ADAPTER_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_PLACEHOLDERS = frozenset({"package", "mode", "profile", "case_id", "output"})
_REQUIRED_PRODUCER_FILES = (
    "AUDIT_JSON_SUMMARY.json",
    "coverage.json",
    "pipeline_summary.json",
    "audit-report.md",
)
_HARNESS_ARTIFACTS = frozenset({"normalized_observation.json", "stdout.log", "stderr.log"})
_CASE_OUTPUT_ARTIFACTS = {
    "audit_summary": "AUDIT_JSON_SUMMARY.json",
    "coverage": "coverage.json",
    "pipeline_summary": "pipeline_summary.json",
    "report": "audit-report.md",
    "normalized_observation": "normalized_observation.json",
    "stdout_log": "stdout.log",
    "stderr_log": "stderr.log",
}
_RUNNER_SUFFIXES = frozenset({".json", ".md", ".py", ".toml", ".yaml", ".yml"})
_DEPENDENCIES = {
    "numpy": ("numpy",),
    "Pillow": ("Pillow",),
    "OpenCV": ("opencv-python-headless", "opencv-python"),
    "PyMuPDF": ("PyMuPDF",),
    "PyYAML": ("PyYAML",),
    "openpyxl": ("openpyxl",),
    "pypdf": ("pypdf",),
    "requests": ("requests",),
    "pytesseract": ("pytesseract",),
    "jsonschema": ("jsonschema",),
    "psutil": ("psutil",),
}


class CliError(ValueError):
    """Raised for an actionable orchestration or evaluation failure."""


class _CaseFailure(CliError):
    def __init__(self, status: str, message: str, runtime: Any | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.runtime = runtime


class AdapterProtocol(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def build_command(
        self, *, package: Path | str, case: Mapping[str, Any], output: Path | str
    ) -> list[str]: ...


AssertionProvider = Callable[
    [Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Sequence[bool]
]


@dataclass(frozen=True, slots=True)
class CommandAdapter:
    """An explicit argv template; shell strings and partial placeholders are forbidden."""

    name: str
    version: str
    argv_template: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _ADAPTER_ID.fullmatch(self.name) is None:
            raise ValueError("adapter name must be a safe non-empty identifier")
        if not isinstance(self.version, str) or _ADAPTER_VERSION.fullmatch(self.version) is None:
            raise ValueError("adapter version must be a safe non-empty identifier")
        if not isinstance(self.argv_template, tuple):
            raise ValueError("adapter argv_template must be an actual tuple of strings")
        if not self.argv_template or any(not isinstance(arg, str) or not arg for arg in self.argv_template):
            raise ValueError("adapter argv_template must be a non-empty string array")
        placeholder = re.compile(r"^\{([^{}]+)\}$")
        for argument in self.argv_template:
            match = placeholder.fullmatch(argument)
            if match is not None:
                if match.group(1) not in _PLACEHOLDERS:
                    raise ValueError(f"unknown adapter placeholder: {match.group(1)!r}")
                continue
            has_known_placeholder = any(f"{{{name}}}" in argument for name in _PLACEHOLDERS)
            if argument.startswith("{") or argument.endswith("}") or has_known_placeholder:
                raise ValueError("adapter placeholders must occupy a complete argv item")

    def build_command(
        self, *, package: Path | str, case: Mapping[str, Any], output: Path | str
    ) -> list[str]:
        values = {
            "package": str(package),
            "mode": str(case["mode"]),
            "profile": str(case["scan_profile"]),
            "case_id": str(case["case_id"]),
            "output": str(output),
        }
        return [values[arg[1:-1]] if arg.startswith("{") else arg for arg in self.argv_template]


def _module_origin(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise CliError(f"Installed runtime module is unavailable: {name}")
    path = Path(spec.origin)
    if not path.is_file() or path.is_symlink():
        raise CliError(f"Installed runtime module is unsafe or unavailable: {name}: {path}")
    return path.resolve()


def repository_root() -> Path:
    """Return the source or installed package root without requiring pyproject.toml."""

    return Path(__file__).resolve().parents[2]


def _full_adapter() -> CommandAdapter:
    return CommandAdapter(
        "full",
        "2",
        (
            sys.executable,
            str(_module_origin("scripts.audit_package")),
            "{package}",
            "--mode",
            "{mode}",
            "--scan-profile",
            "{profile}",
            "--external-literature-provider",
            "none",
            "--case-id",
            "{case_id}",
            "--output-dir",
            "{output}",
        ),
    )


def default_adapters() -> dict[str, AdapterProtocol]:
    return {"full": _full_adapter()}


def _adapter_registry(adapters: Mapping[str, AdapterProtocol] | None) -> dict[str, AdapterProtocol]:
    registry = default_adapters()
    if adapters is not None:
        registry.update(adapters)
    for key, adapter in registry.items():
        if key != adapter.name:
            raise CliError(f"Adapter registry key {key!r} does not match adapter name {adapter.name!r}")
    return registry


def _canonical_sha(payload: Any) -> str:
    data = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CliError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                CliError(f"non-finite JSON value: {value}")
            ),
        )
    except CliError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CliError(f"Could not read strict JSON {label}: {path}: {exc}") from exc


def _write_json_atomic(path: Path, payload: Any) -> None:
    serialized = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _project_version() -> str:
    try:
        return importlib.metadata.version("biomed-research-integrity-auditor")
    except importlib.metadata.PackageNotFoundError:
        from . import __version__

        return __version__


def _dependency_version(names: Sequence[str]) -> str:
    for name in names:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "missing"


def _environment_payload() -> dict[str, str]:
    result = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "project_version": _project_version(),
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_machine": platform.machine(),
        "platform_architecture": platform.architecture()[0],
    }
    result.update({key: _dependency_version(names) for key, names in _DEPENDENCIES.items()})
    return result


def _package_directory(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise CliError(f"Runner package is unavailable: {name}")
    locations = spec.submodule_search_locations
    if locations:
        return Path(next(iter(locations))).resolve()
    if spec.origin:
        return Path(spec.origin).resolve().parent
    raise CliError(f"Runner package has no filesystem location: {name}")


def _walk_runner_tree(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise CliError(f"Runner input directory is unsafe or unavailable: {root}")
    paths: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if entry.is_symlink():
                    raise CliError(f"Symlinked runner input is forbidden: {path}")
                if entry.is_dir(follow_symlinks=False):
                    if entry.name != "__pycache__":
                        stack.append(path)
                elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in _RUNNER_SUFFIXES:
                    paths.append(path.resolve())
    return paths


def _runner_inputs(adapter: AdapterProtocol, actual_command: Sequence[str]) -> list[Path]:
    paths = _walk_runner_tree(Path(__file__).resolve().parent)
    if adapter.name == "full":
        for package in ("detectors", "calibrators", "provenance", "scripts", "schemas", "skill"):
            paths.extend(_walk_runner_tree(_package_directory(package)))
        root = repository_root()
        for name in ("pyproject.toml", "requirements.txt", "requirements-lock.txt"):
            candidate = root / name
            if candidate.exists():
                if candidate.is_symlink() or not candidate.is_file():
                    raise CliError(f"Runner metadata input is unsafe: {candidate}")
                paths.append(candidate.resolve())
    execution_cwd = _execution_cwd(adapter)
    for argument in actual_command:
        raw_candidate = Path(argument)
        is_relative = not raw_candidate.is_absolute()
        candidate = execution_cwd / raw_candidate if is_relative else raw_candidate
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if candidate.resolve() == Path(sys.executable).resolve():
            continue
        if candidate.is_symlink():
            raise CliError(f"Symlinked command input is forbidden: {raw_candidate}")
        if candidate.is_file():
            paths.append(candidate.resolve())
        elif is_relative and candidate.is_dir():
            paths.extend(_walk_runner_tree(candidate.resolve()))
    return sorted(set(paths), key=lambda item: item.as_posix())


def _hash_files(paths: Sequence[Path]) -> str:
    root = repository_root().resolve()
    records: list[tuple[str, str]] = []
    for path in sorted(set(paths), key=lambda item: item.as_posix()):
        if path.is_symlink() or not path.is_file():
            raise CliError(f"Runner input is unsafe or unavailable: {path}")
        try:
            name = path.relative_to(root).as_posix()
        except ValueError:
            name = f"external:{path.name}"
        records.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return _canonical_sha(records)


def _logical_command(adapter: AdapterProtocol, case: Mapping[str, Any]) -> list[str]:
    command = adapter.build_command(
        package=str(case["package_path"]), case=case, output="{staging_output}"
    )
    root = repository_root().resolve()
    logical: list[str] = []
    for argument in command:
        if Path(argument) == Path(sys.executable):
            logical.append("{python_executable}")
            continue
        candidate = Path(argument)
        if candidate.is_absolute():
            try:
                logical.append(candidate.resolve().relative_to(root).as_posix())
            except ValueError:
                logical.append(f"{{external_runner:{candidate.name}}}")
        else:
            logical.append(argument)
    return logical


def _normalized_timeout(value: float) -> float:
    if isinstance(value, bool):
        raise CliError("timeout_seconds must be finite and positive")
    try:
        timeout = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CliError("timeout_seconds must be finite and positive") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise CliError("timeout_seconds must be finite and positive")
    return timeout


def _policy_marker(timeout_seconds: float) -> str:
    return f"bria-bench-policy:timeout_seconds={format(timeout_seconds, '.17g')}"


def _timeout_from_command(command: object) -> float:
    if not isinstance(command, list) or any(not isinstance(item, str) for item in command):
        raise CliError("run result command must be a string array")
    markers = [item for item in command if item.startswith("bria-bench-policy:timeout_seconds=")]
    if len(markers) != 1 or command[-1] != markers[0]:
        raise CliError("run result lacks one canonical timeout execution policy")
    return _normalized_timeout(markers[0].split("=", 1)[1])


def _cache_material(
    manifest: Mapping[str, Any],
    case: Mapping[str, Any],
    adapter: AdapterProtocol,
    actual_command: Sequence[str],
    manifest_sha256: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, str], list[str]]:
    timeout = _normalized_timeout(timeout_seconds)
    logical = _logical_command(adapter, case) + [_policy_marker(timeout)]
    environment = _environment_payload()
    runner_inputs = _runner_inputs(adapter, actual_command)
    runner_sha = _hash_files(runner_inputs)
    hashes = {
        "package_sha256": str(case["expected_sha256"]),
        "annotation_sha256": str(case["annotation_sha256"]),
        "runner_sha256": runner_sha,
        "command_sha256": _canonical_sha(logical),
        "environment_sha256": _canonical_sha(environment),
        "manifest_sha256": manifest_sha256,
    }
    key = _canonical_sha(
        {
            "benchmark_id": manifest["benchmark_id"],
            "benchmark_version": manifest["benchmark_version"],
            "package_sha256": case["expected_sha256"],
            "annotation_sha256": case["annotation_sha256"],
            "adapter": {"name": adapter.name, "version": adapter.version},
            "logical_command": logical,
            "environment": environment,
            "runner_sha256": runner_sha,
            "execution_policy": {"timeout_seconds": timeout},
        }
    )
    return key, hashes, logical


def _select_cases(
    manifest: Mapping[str, Any], case_ids: Sequence[str] | None
) -> list[Mapping[str, Any]]:
    cases = list(manifest["cases"])
    by_id = {case["case_id"]: case for case in cases}
    for case_id in by_id:
        if _CASE_ID.fullmatch(case_id) is None or case_id in {".", ".."}:
            raise CliError(f"Unsafe case ID in manifest: {case_id!r}")
    if case_ids is None:
        selected = cases
    else:
        values = list(case_ids)
        duplicates = sorted({item for item in values if values.count(item) > 1})
        if duplicates:
            raise CliError(f"duplicate case IDs requested: {duplicates!r}")
        unknown = sorted(set(values) - set(by_id))
        if unknown:
            raise CliError(f"unknown case IDs requested: {unknown!r}")
        selected = [by_id[item] for item in values]
    if not selected:
        raise CliError("case selection is empty")
    return selected


def _canonical_runs_dir(value: Path | str) -> Path:
    path = Path(value).absolute()
    anchors = [Path.cwd().absolute(), Path.home().absolute(), Path(tempfile.gettempdir()).absolute()]
    eligible = [anchor for anchor in anchors if path == anchor or path.is_relative_to(anchor)]
    anchor = max(eligible, key=lambda item: len(item.parts), default=Path(path.anchor))
    current = anchor
    for part in path.relative_to(anchor).parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise CliError(f"runs_dir contains a symlinked component: {current}")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise CliError(f"runs_dir must be an actual directory: {path}")
    return path.resolve()


def _safe_relative(value: str | Path) -> Path:
    relative = Path(value)
    if relative.is_absolute() or relative in {Path(""), Path(".")} or any(
        part in {"", ".."} for part in relative.parts
    ):
        raise CliError(f"Unsafe runs-dir relative path: {value!r}")
    return relative


def _inside_runs(runs: Path, value: str | Path, *, require_exists: bool = True) -> Path:
    relative = _safe_relative(value)
    current = runs
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if require_exists:
                raise CliError(f"Run artifact is missing: {relative.as_posix()}")
            break
        if stat.S_ISLNK(metadata.st_mode):
            raise CliError(f"Symlinked runs-dir component is forbidden: {relative.as_posix()}")
    resolved = (runs / relative).resolve(strict=False)
    if not resolved.is_relative_to(runs):
        raise CliError(f"Run artifact escapes runs_dir: {relative.as_posix()}")
    return resolved


def _ensure_real_directory(runs: Path, relative: str | Path) -> Path:
    relative_path = _safe_relative(relative)
    current = runs
    for part in relative_path.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current.mkdir()
            metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise CliError(f"Unsafe runs-dir directory component: {relative_path.as_posix()}")
    return current


def _reject_symlink_tree(root: Path, *, label: str) -> None:
    metadata = root.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise CliError(f"{label} must be an actual directory: {root}")
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                if entry.is_symlink():
                    raise CliError(f"{label} contains forbidden symlink: {path.name}")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)


def _empty_normalized(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "observations": [],
        "technical_failures": [],
        "reported_technical_failures": [],
        "boundary_violations": [],
        "contract_errors": [],
    }


def _redact(text: str, *, staging: Path | None = None, package: Path | None = None) -> str:
    replacements = [(str(Path.home()), "<HOME>")]
    temporary = Path(tempfile.gettempdir())
    replacements.extend(
        [(str(temporary.resolve()), "<TEMP>"), (str(temporary), "<TEMP>")]
    )
    if staging is not None:
        replacements.insert(0, (str(staging), "<STAGING_OUTPUT>"))
    if package is not None:
        replacements.insert(0, (str(package), "<PACKAGE_ROOT>"))
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def _failure(
    category: str,
    message: str,
    *,
    runtime: Any | None = None,
    staging: Path | None = None,
    package: Path | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "category": category,
        "message": _redact(message, staging=staging, package=package),
        "module": "bria_bench.runner",
    }
    if runtime is not None:
        result.update(
            {
                "returncode": runtime.returncode,
                "timed_out": runtime.timed_out,
                "stdout_tail": _redact(runtime.stdout_tail, staging=staging, package=package),
                "stderr_tail": _redact(runtime.stderr_tail, staging=staging, package=package),
            }
        )
    return result


def _telemetry(runtime: Any | None, output_size: int = 0) -> dict[str, Any]:
    if runtime is None:
        return {
            "elapsed_seconds": 0.0,
            "cpu_seconds": 0.0,
            "peak_rss_bytes": 0,
            "output_size_bytes": output_size,
            "returncode": None,
            "timed_out": False,
        }
    return {
        "elapsed_seconds": runtime.elapsed_seconds,
        "cpu_seconds": runtime.cpu_seconds,
        "peak_rss_bytes": runtime.peak_rss_bytes,
        "output_size_bytes": output_size,
        "returncode": runtime.returncode,
        "timed_out": runtime.timed_out,
    }


def _tree_size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise CliError(f"Cannot size symlinked producer artifact: {entry.name}")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
    return total


def _producer_artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    stack = [(path, Path("."))]
    while stack:
        directory, relative = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                child_relative = relative / entry.name
                if child_relative.parts[0] in _HARNESS_ARTIFACTS:
                    continue
                if entry.is_symlink():
                    raise CliError(f"Producer artifact tree contains a symlink: {entry.name}")
                digest.update(child_relative.as_posix().encode("utf-8"))
                digest.update(b"\0")
                if entry.is_dir(follow_symlinks=False):
                    digest.update(b"D")
                    stack.append((Path(entry.path), child_relative))
                elif entry.is_file(follow_symlinks=False):
                    digest.update(b"F")
                    digest.update(Path(entry.path).read_bytes())
                digest.update(b"\xff")
    return digest.hexdigest()


def _load_run_monitored() -> Callable[..., Any]:
    try:
        from .runtime import run_monitored
    except ModuleNotFoundError as exc:
        if exc.name == "psutil":
            raise CliError(
                "BRIA-Bench process monitoring requires psutil; install the benchmark dependencies with `pip install '.[benchmark]'`"
            ) from exc
        raise
    return run_monitored


def _execution_cwd(adapter: AdapterProtocol) -> Path:
    if adapter.name == "full":
        return _module_origin("scripts.audit_package").parents[1]
    return repository_root()


def _result_compare(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("cache_status", None)
    return result


def _validate_attempt(
    path: Path,
    *,
    runs: Path,
    case_id: str,
    expected_key: str | None = None,
    expected_hashes: Mapping[str, str] | None = None,
    expected_adapter: AdapterProtocol | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    from .normalize import normalize_audit_output

    payload = _load_attempt_contract(path, runs=runs, case_id=case_id)
    if expected_key is not None and payload["cache_key"] != expected_key:
        raise CliError(f"Attempt cache key mismatch for case {case_id!r}")
    if expected_hashes is not None and payload["hashes"] != dict(expected_hashes):
        raise CliError(f"Attempt hash mismatch for case {case_id!r}")
    if expected_adapter is not None and (
        payload["adapter"] != expected_adapter.name
        or payload.get("adapter_version") != expected_adapter.version
    ):
        raise CliError(f"Attempt adapter mismatch for case {case_id!r}")

    paths = payload["output_paths"]
    for value in paths.values():
        _inside_runs(runs, value, require_exists=False)
    output_value = paths.get("case_output")
    if output_value is None:
        if payload["status"] == "success":
            raise CliError(f"Successful attempt lacks producer output for case {case_id!r}")
        if set(paths) != {"run_result"}:
            raise CliError(
                f"Artifact-free attempt has noncanonical output paths for case {case_id!r}"
            )
        return payload

    output_relative = _safe_relative(output_value)
    attempt_relative = path.relative_to(runs)
    expected_paths = {
        "case_output": output_relative.as_posix(),
        "run_result": attempt_relative.as_posix(),
        **{
            key: (output_relative / filename).as_posix()
            for key, filename in _CASE_OUTPUT_ARTIFACTS.items()
        },
    }
    if output_relative.parent != attempt_relative.parent:
        raise CliError(
            f"case_output is not in the canonical attempt directory for case {case_id!r}"
        )
    if set(paths) != set(expected_paths):
        raise CliError(f"Attempt has noncanonical artifact path keys for case {case_id!r}")
    for key, expected in expected_paths.items():
        if paths[key] != expected:
            raise CliError(
                f"Attempt artifact {key!r} is not the canonical child of case_output "
                f"for case {case_id!r}"
            )

    output = _inside_runs(runs, output_relative)
    normalized_path = _inside_runs(runs, paths["normalized_observation"])
    if normalized_path.is_symlink() or not normalized_path.is_file():
        raise CliError(f"Normalized artifact is unsafe for case {case_id!r}")
    normalized = _strict_json(normalized_path, label=f"normalized observation for {case_id}")
    if normalized != payload["normalized_observation"]:
        raise CliError(f"Normalized artifact differs from run result for case {case_id!r}")

    _reject_symlink_tree(output, label="published producer output")
    digest_match = re.fullmatch(r"output-([a-f0-9]{64})", output.name)
    if digest_match is None or _producer_artifact_digest(output) != digest_match.group(1):
        raise CliError(f"Producer artifact digest mismatch for case {case_id!r}")
    if payload["status"] == "success":
        for key in ("audit_summary", "coverage", "pipeline_summary", "report"):
            artifact = _inside_runs(runs, paths[key])
            if artifact.is_symlink() or not artifact.is_file():
                raise CliError(f"Successful producer artifact is missing for case {case_id!r}: {key}")
    renormalized = normalize_audit_output(
        case_id, output, package_root=package_root, staging_roots=(output,)
    )
    if renormalized != payload["normalized_observation"]:
        raise CliError(f"Producer artifacts do not match normalized result for case {case_id!r}")
    return payload


def _load_attempt_contract(path: Path, *, runs: Path, case_id: str) -> dict[str, Any]:
    from .contracts import validate_contract

    if path.is_symlink() or not path.is_file():
        raise CliError(f"Attempt result is unsafe or missing for case {case_id!r}")
    relative = path.relative_to(runs).as_posix()
    payload = _strict_json(path, label=f"attempt result for {case_id}")
    validate_contract("run_result.schema.json", payload)
    if payload["case_id"] != case_id or payload["output_paths"].get("run_result") != relative:
        raise CliError(f"Attempt identity mismatch for case {case_id!r}")
    return payload


def _verified_annotation(manifest_file: Path, case: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    from .contracts import validate_contract
    from .hashing import HashingError, hash_file
    from .registry import RegistryError, resolve_inside

    case_id = str(case["case_id"])
    try:
        path = resolve_inside(manifest_file.parent, str(case["annotation_path"]))
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CliError(f"Annotation must be an actual file for case {case_id!r}")
        actual = hash_file(path)
    except (HashingError, OSError, RegistryError) as exc:
        raise CliError(f"Could not verify sealed annotation for case {case_id!r}: {exc}") from exc
    if actual != case["annotation_sha256"]:
        raise CliError(f"Sealed annotation hash mismatch for case {case_id!r}")
    annotation = _strict_json(path, label=f"annotation for {case_id}")
    validate_contract("annotation.schema.json", annotation)
    if annotation["case_id"] != case_id:
        raise CliError(f"Annotation case_id mismatch for case {case_id!r}")
    return path, annotation


def _valid_prior_current(
    current: Path, *, runs: Path, case_id: str, package_root: Path
) -> dict[str, Any] | None:
    from .contracts import ContractError, validate_contract

    try:
        if current.is_symlink() or not current.is_file():
            return None
        payload = _strict_json(current, label=f"current result for {case_id}")
        validate_contract("run_result.schema.json", payload)
        attempt_path = _inside_runs(runs, payload["output_paths"]["run_result"])
        attempt = _validate_attempt(
            attempt_path, runs=runs, case_id=case_id, package_root=package_root
        )
        if _result_compare(payload) != _result_compare(attempt) or attempt["status"] != "success":
            return None
        return attempt
    except (CliError, ContractError, KeyError, TypeError, ValueError):
        return None


def _directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    stack = [(path, Path("."))]
    while stack:
        directory, relative = stack.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                child_relative = relative / entry.name
                digest.update(child_relative.as_posix().encode("utf-8"))
                if entry.is_symlink():
                    digest.update(b"L")
                    digest.update(os.readlink(entry.path).encode("utf-8", errors="replace"))
                elif entry.is_dir(follow_symlinks=False):
                    digest.update(b"D")
                    stack.append((Path(entry.path), child_relative))
                elif entry.is_file(follow_symlinks=False):
                    digest.update(b"F")
                    digest.update(Path(entry.path).read_bytes())
    return digest.hexdigest()


def _archive_attempt(path: Path, *, kind: str) -> Path:
    digest = _directory_digest(path)[:12]
    base = path.with_name(f".{kind}-{path.name}-{digest}")
    destination = base
    index = 2
    while destination.exists() or destination.is_symlink():
        destination = base.with_name(f"{base.name}-{index}")
        index += 1
    os.replace(path, destination)
    return destination


def _publish_attempt(prepared: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise CliError(f"Immutable attempt destination already exists: {destination.name}")
    os.replace(prepared, destination)


def _attempt_directory_name(cache_key: str, version: int) -> str:
    if version < 1:
        raise CliError("attempt version must be positive")
    return cache_key if version == 1 else f"{cache_key}.attempt-{version:04d}"


def _attempt_paths(case_id: str, cache_key: str, version: int = 1) -> tuple[Path, Path]:
    attempt = Path("cases") / case_id / "attempts" / _attempt_directory_name(
        cache_key, version
    )
    return attempt, attempt / "run_result.json"


def _attempt_candidates(attempts_dir: Path, cache_key: str) -> list[tuple[int, Path]]:
    pattern = re.compile(rf"^{re.escape(cache_key)}(?:\.attempt-([0-9]{{4}}))?$")
    candidates: list[tuple[int, Path]] = []
    with os.scandir(attempts_dir) as entries:
        for entry in entries:
            match = pattern.fullmatch(entry.name)
            if match is None:
                continue
            version = 1 if match.group(1) is None else int(match.group(1))
            candidates.append((version, Path(entry.path)))
    return sorted(candidates)


def _formal_failure(
    *,
    runs: Path,
    case_id: str,
    adapter: AdapterProtocol,
    cache_key: str,
    hashes: Mapping[str, str],
    logical: Sequence[str],
    cache_status: str,
    message: str,
    status: str = "environment_failure",
    runtime: Any | None = None,
) -> tuple[dict[str, Any], str]:
    from .contracts import validate_contract

    directory = _ensure_real_directory(runs, Path("failures") / case_id)
    safe_message = _redact(message)
    digest = _canonical_sha({"cache_key": cache_key, "message": safe_message})[:12]
    relative = Path("failures") / case_id / f"{cache_key}-{digest}.json"
    path = directory / relative.name
    index = 2
    while path.exists() or path.is_symlink():
        relative = Path("failures") / case_id / f"{cache_key}-{digest}-{index}.json"
        path = directory / relative.name
        index += 1
    payload = {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "adapter": adapter.name,
        "adapter_version": adapter.version,
        "status": status,
        "hashes": dict(hashes),
        "cache_key": cache_key,
        "cache_status": cache_status,
        "command": list(logical),
        "telemetry": _telemetry(runtime),
        "output_paths": {"run_result": relative.as_posix()},
        "normalized_observation": _empty_normalized(case_id),
        "failure": _failure(status, safe_message, runtime=runtime),
    }
    validate_contract("run_result.schema.json", payload)
    _write_json_atomic(path, payload)
    return payload, relative.as_posix()


def _fallback_material(
    manifest: Mapping[str, Any],
    case: Mapping[str, Any],
    adapter: AdapterProtocol,
    manifest_sha: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, str], list[str]]:
    zero = "0" * 64
    timeout = _normalized_timeout(timeout_seconds)
    logical = ["<unavailable>", _policy_marker(timeout)]
    hashes = {
        "package_sha256": str(case.get("expected_sha256", zero)),
        "annotation_sha256": str(case.get("annotation_sha256", zero)),
        "runner_sha256": zero,
        "command_sha256": _canonical_sha(logical),
        "environment_sha256": zero,
        "manifest_sha256": manifest_sha,
    }
    key = _canonical_sha(
        {
            "benchmark": manifest.get("benchmark_id"),
            "case": case.get("case_id"),
            "failure": hashes,
            "execution_policy": {"timeout_seconds": timeout},
        }
    )
    return key, hashes, logical


def run_benchmark(
    manifest_path: Path | str,
    runs_dir: Path | str,
    *,
    case_ids: Sequence[str] | None = None,
    adapter_name: str = "full",
    timeout_seconds: float = 900,
    adapters: Mapping[str, AdapterProtocol] | None = None,
) -> dict[str, Any]:
    """Execute selected cases while preserving immutable attempts and latest-attempt truth."""

    from .contracts import validate_contract
    from .normalize import normalize_audit_output
    from .registry import load_manifest, resolve_case_paths, verify_frozen_case

    manifest_file = Path(manifest_path)
    manifest = load_manifest(manifest_file, require_frozen=True, resolve_paths=False)
    selected = _select_cases(manifest, case_ids)
    timeout = _normalized_timeout(timeout_seconds)
    registry = _adapter_registry(adapters)
    if adapter_name not in registry:
        raise CliError(f"Unknown adapter {adapter_name!r}; available: {sorted(registry)!r}")
    adapter = registry[adapter_name]
    runs = _canonical_runs_dir(runs_dir)
    _ensure_real_directory(runs, "failures")
    manifest_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    summary_cases: list[dict[str, Any]] = []

    for case in selected:
        case_id = str(case["case_id"])
        cache_key, hashes, logical = _fallback_material(
            manifest, case, adapter, manifest_sha, timeout
        )
        cache_status = "fresh"
        staging: Path | None = None
        latest_path: str | None = None
        latest_status = "environment_failure"
        try:
            verify_frozen_case(manifest_file.parent, dict(case))
            package, _ = resolve_case_paths(manifest_file.parent, dict(case))
            probe = adapter.build_command(package=package, case=case, output="{staging_output}")
            cache_key, hashes, logical = _cache_material(
                manifest,
                case,
                adapter,
                probe,
                manifest_sha,
                timeout,
            )

            case_dir = _ensure_real_directory(runs, Path("cases") / case_id)
            attempts_dir = _ensure_real_directory(runs, Path("cases") / case_id / "attempts")
            current = case_dir / "run_result.json"
            if current.is_symlink():
                raise CliError(f"Current result path is a symlink for case {case_id!r}")
            prior_success = _valid_prior_current(
                current, runs=runs, case_id=case_id, package_root=package
            )
            candidates = _attempt_candidates(attempts_dir, cache_key)
            cache_status = "invalidated" if current.exists() or candidates else "fresh"
            valid_successes: list[tuple[int, Path, dict[str, Any]]] = []
            for version, candidate in candidates:
                if candidate.is_symlink():
                    raise CliError(f"Immutable attempt path is a symlink for case {case_id!r}")
                try:
                    cached = _validate_attempt(
                        candidate / "run_result.json",
                        runs=runs,
                        case_id=case_id,
                        expected_key=cache_key,
                        expected_hashes=hashes,
                        expected_adapter=adapter,
                        package_root=package,
                    )
                except Exception:
                    _archive_attempt(candidate, kind="quarantine")
                    cache_status = "invalidated"
                else:
                    if cached["status"] == "success":
                        valid_successes.append((version, candidate, cached))

            if valid_successes:
                _, successful_dir, cached = max(valid_successes, key=lambda item: item[0])
                repaired = dict(cached)
                repaired["cache_status"] = "reused"
                _write_json_atomic(current, repaired)
                latest_path = (successful_dir / "run_result.json").relative_to(runs).as_posix()
                latest_status = "success"
                cache_status = "reused"
                summary_cases.append(
                    {
                        "case_id": case_id,
                        "cache_status": cache_status,
                        "status": latest_status,
                        "run_result": latest_path,
                    }
                )
                continue

            next_version = max((version for version, _ in candidates), default=0) + 1
            attempt_rel, result_rel = _attempt_paths(case_id, cache_key, next_version)
            attempt_dir = runs / attempt_rel

            run_monitored = _load_run_monitored()
            staging = Path(tempfile.mkdtemp(prefix=f".staging-{case_id}-", dir=runs))
            command = adapter.build_command(package=package, case=case, output=staging)
            runtime = run_monitored(command, _execution_cwd(adapter), timeout)

            normalized = _empty_normalized(case_id)
            staging_error: Exception | None = None
            normalization_error: Exception | None = None
            try:
                _reject_symlink_tree(staging, label="fresh producer staging")
            except Exception as exc:
                staging_error = exc
            if staging_error is None:
                try:
                    normalized = normalize_audit_output(
                        case_id, staging, package_root=package, staging_roots=(staging,)
                    )
                except Exception as exc:
                    normalization_error = exc

            missing = [
                name
                for name in _REQUIRED_PRODUCER_FILES
                if staging_error is None and not (staging / name).is_file()
            ]
            if runtime.status == "timeout":
                status = "timeout"
                failure = _failure(
                    "timeout", "Producer exceeded timeout.", runtime=runtime, staging=staging, package=package
                )
            elif runtime.status != "success":
                status = "process_error"
                failure = _failure(
                    "process_error", "Producer exited unsuccessfully.", runtime=runtime, staging=staging, package=package
                )
            elif not runtime.cleanup_complete:
                status = "environment_failure"
                failure = _failure(
                    "cleanup_failure",
                    "; ".join(runtime.cleanup_errors) or "Process-tree cleanup was incomplete.",
                    runtime=runtime,
                    staging=staging,
                    package=package,
                )
            elif staging_error is not None:
                status = "invalid_output"
                failure = _failure(
                    "invalid_output", str(staging_error), runtime=runtime, staging=staging, package=package
                )
            elif normalization_error is not None:
                status = "normalization_error"
                failure = _failure(
                    "normalization_error",
                    f"Could not normalize producer output: {type(normalization_error).__name__}: {normalization_error}",
                    runtime=runtime,
                    staging=staging,
                    package=package,
                )
            elif missing:
                status = "missing_output"
                failure = _failure(
                    "missing_output",
                    f"Missing required producer artifacts: {', '.join(missing)}",
                    runtime=runtime,
                    staging=staging,
                    package=package,
                )
            elif normalized["contract_errors"]:
                status = "invalid_output"
                failure = _failure(
                    "invalid_output",
                    "Producer artifacts failed normalization contract checks.",
                    runtime=runtime,
                    staging=staging,
                    package=package,
                )
            else:
                status = "success"
                failure = None

            if staging_error is not None or normalization_error is not None:
                if runtime.status == "timeout":
                    formal_status = "timeout"
                elif runtime.status != "success":
                    formal_status = "process_error"
                elif not runtime.cleanup_complete:
                    formal_status = "environment_failure"
                elif staging_error is not None:
                    formal_status = "invalid_output"
                else:
                    formal_status = "normalization_error"
                detail = staging_error if staging_error is not None else normalization_error
                raise _CaseFailure(
                    formal_status,
                    f"Producer output could not be safely normalized: {type(detail).__name__}: {detail}",
                    runtime,
                )
            _write_json_atomic(staging / "normalized_observation.json", normalized)
            (staging / "stdout.log").write_text(
                _redact(runtime.stdout_tail, staging=staging, package=package), encoding="utf-8"
            )
            (staging / "stderr.log").write_text(
                _redact(runtime.stderr_tail, staging=staging, package=package), encoding="utf-8"
            )
            output_size = _tree_size(staging)
            artifact_digest = _producer_artifact_digest(staging)
            output_rel = attempt_rel / f"output-{artifact_digest}"
            result = {
                "schema_version": "1.0.0",
                "case_id": case_id,
                "adapter": adapter.name,
                "adapter_version": adapter.version,
                "status": status,
                "hashes": hashes,
                "cache_key": cache_key,
                "cache_status": cache_status,
                "command": logical,
                "telemetry": _telemetry(runtime, output_size),
                "output_paths": {
                    "case_output": output_rel.as_posix(),
                    "run_result": result_rel.as_posix(),
                    "audit_summary": (output_rel / "AUDIT_JSON_SUMMARY.json").as_posix(),
                    "coverage": (output_rel / "coverage.json").as_posix(),
                    "pipeline_summary": (output_rel / "pipeline_summary.json").as_posix(),
                    "report": (output_rel / "audit-report.md").as_posix(),
                    "normalized_observation": (output_rel / "normalized_observation.json").as_posix(),
                    "stdout_log": (output_rel / "stdout.log").as_posix(),
                    "stderr_log": (output_rel / "stderr.log").as_posix(),
                },
                "normalized_observation": normalized,
                "failure": failure,
            }
            validate_contract("run_result.schema.json", result)

            prepared = Path(tempfile.mkdtemp(prefix=f".prepared-{cache_key[:12]}-", dir=attempts_dir))
            try:
                os.replace(staging, prepared / output_rel.name)
                staging = None
                _write_json_atomic(prepared / "run_result.json", result)
                _publish_attempt(prepared, attempt_dir)
            finally:
                if prepared.exists():
                    shutil.rmtree(prepared, ignore_errors=True)

            latest_path = result_rel.as_posix()
            latest_status = status
            if status == "success" or prior_success is None:
                _write_json_atomic(current, result)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            formal_status = exc.status if isinstance(exc, _CaseFailure) else "environment_failure"
            formal_runtime = exc.runtime if isinstance(exc, _CaseFailure) else None
            failure_result, latest_path = _formal_failure(
                runs=runs,
                case_id=case_id,
                adapter=adapter,
                cache_key=cache_key,
                hashes=hashes,
                logical=logical,
                cache_status=cache_status,
                message=f"{type(exc).__name__}: {exc}",
                status=formal_status,
                runtime=formal_runtime,
            )
            latest_status = failure_result["status"]
        finally:
            if staging is not None and (staging.exists() or staging.is_symlink()):
                if staging.is_symlink():
                    staging.unlink(missing_ok=True)
                else:
                    shutil.rmtree(staging, ignore_errors=True)

        assert latest_path is not None
        summary_cases.append(
            {
                "case_id": case_id,
                "cache_status": cache_status,
                "status": latest_status,
                "run_result": latest_path,
            }
        )

    summary = {
        "schema_version": "1.0.0",
        "benchmark_id": manifest["benchmark_id"],
        "benchmark_version": manifest["benchmark_version"],
        "manifest_sha256": manifest_sha,
        "adapter": adapter.name,
        "adapter_version": adapter.version,
        "cases": summary_cases,
    }
    _write_json_atomic(runs / "run_summary.json", summary)
    return summary


def _load_summary(runs: Path, manifest: Mapping[str, Any], manifest_sha: str) -> dict[str, Any]:
    summary_path = _inside_runs(runs, "run_summary.json")
    if summary_path.is_symlink() or not summary_path.is_file():
        raise CliError("Run summary is unsafe or missing")
    summary = _strict_json(summary_path, label="run summary")
    expected_keys = {
        "schema_version",
        "benchmark_id",
        "benchmark_version",
        "manifest_sha256",
        "adapter",
        "adapter_version",
        "cases",
    }
    if not isinstance(summary, dict) or set(summary) != expected_keys:
        raise CliError("Run summary has an invalid structure")
    if (
        summary["benchmark_id"] != manifest["benchmark_id"]
        or summary["benchmark_version"] != manifest["benchmark_version"]
        or summary["manifest_sha256"] != manifest_sha
        or not isinstance(summary["cases"], list)
    ):
        raise CliError("Run summary does not match the frozen manifest")
    seen: set[str] = set()
    for item in summary["cases"]:
        if not isinstance(item, dict) or set(item) != {
            "case_id",
            "cache_status",
            "status",
            "run_result",
        }:
            raise CliError("Run summary case entry is invalid")
        if item["case_id"] in seen:
            raise CliError(f"Run summary has duplicate case ID: {item['case_id']}")
        seen.add(item["case_id"])
    return summary


def _default_legacy_assertions(
    runs: Path,
    case: Mapping[str, Any],
    annotation: Mapping[str, Any],
    run: Mapping[str, Any],
) -> Sequence[bool]:
    contract = annotation.get("legacy_regression_contract")
    if contract is None:
        return []
    if run["status"] != "success":
        return [False]

    output_paths = run["output_paths"]
    try:
        summary_path = _inside_runs(runs, output_paths["audit_summary"])
        report_path = _inside_runs(runs, output_paths["report"])
    except KeyError as exc:
        raise CliError(
            f"Successful legacy run lacks {exc.args[0]} for case {case['case_id']!r}"
        ) from exc
    for label, path in (("audit summary", summary_path), ("report", report_path)):
        if path.is_symlink() or not path.is_file():
            raise CliError(f"Legacy {label} is unsafe for case {case['case_id']!r}")
    summary = _strict_json(summary_path, label=f"legacy audit summary for {case['case_id']}")
    if not isinstance(summary, dict):
        raise CliError(f"Legacy audit summary must be an object for case {case['case_id']!r}")
    try:
        report_text = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CliError(f"Could not read legacy report for case {case['case_id']!r}") from exc

    from .legacy_regression import LegacyRegressionError, evaluate_legacy_contract

    try:
        return [evaluate_legacy_contract(contract, summary, report_text)]
    except LegacyRegressionError as exc:
        raise CliError(
            f"Invalid sealed legacy contract for case {case['case_id']!r}: {exc}"
        ) from exc


def evaluate_benchmark(
    manifest_path: Path | str,
    runs_dir: Path | str,
    output_path: Path | str,
    *,
    case_ids: Sequence[str] | None = None,
    adapters: Mapping[str, AdapterProtocol] | None = None,
    assertion_providers: Mapping[str, AssertionProvider] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate the latest requested attempts referenced by run_summary.json."""

    from .matching import match_labels
    from .metrics import aggregate_metrics, select_evaluation_labels
    from .registry import load_manifest, resolve_case_paths, verify_frozen_case

    manifest_file = Path(manifest_path)
    manifest = load_manifest(manifest_file, require_frozen=True, resolve_paths=False)
    selected = _select_cases(manifest, case_ids)
    registry = _adapter_registry(adapters)
    providers = dict(assertion_providers or {})
    manifest_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    runs = _canonical_runs_dir(runs_dir)
    summary = _load_summary(runs, manifest, manifest_sha)
    summary_by_id = {item["case_id"]: item for item in summary["cases"]}
    missing = [case["case_id"] for case in selected if case["case_id"] not in summary_by_id]
    if missing:
        raise CliError(f"Run summary lacks requested cases: {missing!r}")

    bundles: list[dict[str, Any]] = []
    for case in selected:
        case_id = str(case["case_id"])
        _, annotation = _verified_annotation(manifest_file, case)
        summary_case = summary_by_id[case_id]
        result_path = _inside_runs(runs, summary_case["run_result"])
        raw_run = _load_attempt_contract(result_path, runs=runs, case_id=case_id)
        adapter_name = raw_run["adapter"]
        if adapter_name not in registry:
            raise CliError(f"No registered adapter can verify run {case_id!r}: {adapter_name!r}")
        adapter = registry[adapter_name]
        fallback_key, fallback_hashes, fallback_logical = _fallback_material(
            manifest,
            case,
            adapter,
            manifest_sha,
            _timeout_from_command(raw_run["command"]),
        )
        is_preflight_failure = (
            raw_run["status"] == "environment_failure"
            and raw_run["cache_key"] == fallback_key
            and raw_run["hashes"] == fallback_hashes
            and raw_run.get("command") == fallback_logical
        )
        if is_preflight_failure:
            run = _validate_attempt(result_path, runs=runs, case_id=case_id)
        else:
            verify_frozen_case(manifest_file.parent, dict(case))
            package, _ = resolve_case_paths(manifest_file.parent, dict(case))
            run = _validate_attempt(
                result_path, runs=runs, case_id=case_id, package_root=package
            )
            probe = adapter.build_command(package=package, case=case, output="{staging_output}")
            expected_key, expected_hashes, _ = _cache_material(
                manifest,
                case,
                adapter,
                probe,
                manifest_sha,
                _timeout_from_command(run["command"]),
            )
            if run["cache_key"] != expected_key or run["hashes"] != expected_hashes:
                raise CliError(f"Run result cache/hash mismatch for case {case_id!r}; rerun the case")

        if run["status"] != summary_case["status"]:
            raise CliError(f"Run summary status mismatch for case {case_id!r}")
        labels = select_evaluation_labels(case, annotation)
        match = match_labels(
            labels,
            run["normalized_observation"]["observations"],
            roles=("recall_label", "coverage_gap"),
        )
        assertions: Sequence[bool] = ()
        if case["track"] == "regression" and adapter_name in providers:
            assertions = providers[adapter_name](case, annotation, run)
        elif case["track"] == "regression" and "legacy_regression_contract" in annotation:
            assertions = _default_legacy_assertions(runs, case, annotation, run)
        if case["track"] == "regression":
            if any(not isinstance(value, bool) for value in assertions):
                raise CliError("Regression assertion provider must return booleans")
        bundles.append(
            {
                "manifest_case": case,
                "annotation": annotation,
                "run_result": run,
                "match_result": match,
                "regression_assertions": list(assertions),
            }
        )

    metrics = aggregate_metrics(
        cases=bundles,
        benchmark_id=manifest["benchmark_id"],
        benchmark_version=manifest["benchmark_version"],
        manifest_sha256=manifest_sha,
        generated_at=generated_at,
    )
    _write_json_atomic(Path(output_path), metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bria-bench", description="Run and evaluate frozen BRIA-Bench registries."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="Freeze package and annotation hashes.")
    freeze.add_argument("--source", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--frozen-at", required=True)
    run = commands.add_parser("run", help="Run or resume frozen benchmark cases.")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--runs-dir", required=True, type=Path)
    run.add_argument("--case", action="append", dest="case_ids")
    run.add_argument("--adapter", default="full")
    run.add_argument("--timeout-seconds", type=float, default=900)
    evaluate = commands.add_parser("evaluate", help="Validate runs and aggregate metrics.")
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--runs-dir", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    evaluate.add_argument("--case", action="append", dest="case_ids")
    report = commands.add_parser("report", help="Render Task 8 metrics report (when installed).")
    report.add_argument("--metrics", required=True, type=Path)
    report.add_argument("--output", required=True, type=Path)
    packet = commands.add_parser(
        "reviewer-packet", help="Export Task 11 reviewer packet (when installed)."
    )
    packet.add_argument("--manifest", required=True, type=Path)
    packet.add_argument("--output-dir", required=True, type=Path)
    packet.add_argument("--mapping-output", required=True, type=Path)
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "freeze":
        from .registry import freeze_manifest

        freeze_manifest(args.source, args.output, args.frozen_at)
        return 0
    if args.command == "run":
        summary = run_benchmark(
            args.manifest,
            args.runs_dir,
            case_ids=args.case_ids,
            adapter_name=args.adapter,
            timeout_seconds=args.timeout_seconds,
        )
        failed = [case for case in summary["cases"] if case["status"] != "success"]
        for case in failed:
            try:
                result = _strict_json(
                    _canonical_runs_dir(args.runs_dir) / case["run_result"],
                    label=f"failed result for {case['case_id']}",
                )
                message = result["failure"]["message"]
            except Exception:
                message = "see the formal run result for details"
            print(
                f"bria-bench: {case['case_id']}: {case['status']}: {message}",
                file=sys.stderr,
            )
        return 1 if failed else 0
    if args.command == "evaluate":
        evaluate_benchmark(args.manifest, args.runs_dir, args.output, case_ids=args.case_ids)
        return 0
    if args.command == "report":
        try:
            from .report import render_metrics_report
        except ModuleNotFoundError as exc:
            if exc.name == "benchmarks.bria_bench.report":
                raise CliError(
                    "The report command requires BRIA-Bench Task 8; report.py is not implemented yet"
                ) from exc
            raise
        metrics = _strict_json(args.metrics, label="metrics")
        args.output.write_text(render_metrics_report(metrics), encoding="utf-8")
        return 0
    if args.command == "reviewer-packet":
        try:
            from .reviewer_packet import export_reviewer_packet
        except ModuleNotFoundError as exc:
            if exc.name == "benchmarks.bria_bench.reviewer_packet":
                raise CliError(
                    "The reviewer-packet command requires BRIA-Bench Task 11; reviewer_packet.py is not implemented yet"
                ) from exc
            raise
        export_reviewer_packet(args.manifest, args.output_dir, args.mapping_output)
        return 0
    raise CliError(f"Unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _dispatch(build_parser().parse_args(argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(f"bria-bench: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
