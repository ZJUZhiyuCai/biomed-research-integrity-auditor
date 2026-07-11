"""Resumable command-line orchestration for BRIA-Bench."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PLACEHOLDERS = frozenset({"package", "mode", "profile", "case_id", "output"})
_REQUIRED_PRODUCER_FILES = (
    "AUDIT_JSON_SUMMARY.json",
    "coverage.json",
    "pipeline_summary.json",
    "audit-report.md",
)


class CliError(ValueError):
    """Raised for an actionable orchestration or evaluation failure."""


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
    """Explicit argv-template adapter, primarily for local tests and integrations.

    Templates are argument arrays, never shell strings. Only ``package``, ``mode``,
    ``profile``, ``case_id``, and ``output`` placeholders are accepted, and each
    placeholder must occupy the complete argument.
    """

    name: str
    version: str
    argv_template: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("adapter name and version must be non-empty")
        if not self.argv_template or any(not isinstance(arg, str) for arg in self.argv_template):
            raise ValueError("adapter argv_template must be a non-empty string array")
        placeholder = re.compile(r"\{([^{}]+)\}")
        for argument in self.argv_template:
            found = placeholder.findall(argument)
            if found and (argument != "{" + found[0] + "}" or len(found) != 1):
                raise ValueError("adapter placeholders must occupy a complete argv item")
            unknown = set(found) - _PLACEHOLDERS
            if unknown:
                raise ValueError(f"unknown adapter placeholders: {sorted(unknown)!r}")

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


def repository_root() -> Path:
    """Resolve the repository containing this installed/source module."""

    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file():
        raise CliError(f"Could not resolve BRIA-Bench repository root from {__file__}")
    return root


def _full_adapter() -> CommandAdapter:
    return CommandAdapter(
        name="full",
        version="1",
        argv_template=(
            sys.executable,
            "scripts/audit_package.py",
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


def _adapter_registry(
    adapters: Mapping[str, AdapterProtocol] | None,
) -> dict[str, AdapterProtocol]:
    registry = default_adapters()
    if adapters is not None:
        registry.update(adapters)
    for key, adapter in registry.items():
        if key != adapter.name:
            raise CliError(f"Adapter registry key {key!r} does not match adapter name {adapter.name!r}")
    return registry


def _canonical_sha(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
            parse_constant=lambda value: (_ for _ in ()).throw(CliError(f"non-finite JSON value: {value}")),
        )
    except CliError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CliError(f"Could not read strict JSON {label}: {path}: {exc}") from exc


def _project_version() -> str:
    text = (repository_root() / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise CliError("Could not determine project version")
    return match.group(1)


def _hash_files(paths: Sequence[Path], *, root: Path) -> str:
    records = []
    for path in sorted(set(paths), key=lambda item: str(item)):
        if not path.is_file() or path.is_symlink():
            raise CliError(f"Runner input is unavailable or unsafe: {path}")
        try:
            name = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            name = f"external:{path.name}"
        records.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return _canonical_sha(records)


def _runner_inputs(adapter: AdapterProtocol, actual_command: Sequence[str]) -> list[Path]:
    root = repository_root()
    paths = [
        Path(__file__),
        root / "benchmarks/bria_bench/contracts.py",
        root / "benchmarks/bria_bench/normalize.py",
        root / "benchmarks/bria_bench/runtime.py",
        root / "schemas/risk_rules.yaml",
        root / "schemas/detector_registry.yaml",
    ]
    paths.extend(sorted((root / "benchmarks/bria_bench/schemas").glob("*.json")))
    if adapter.name == "full":
        paths.append(root / "scripts/audit_package.py")
        paths.extend(sorted((root / "scripts/pipeline").glob("*.py")))
    for argument in actual_command:
        candidate = Path(argument)
        if candidate.is_absolute() and candidate.is_file() and not candidate.is_symlink():
            paths.append(candidate)
    return paths


def _environment_payload() -> dict[str, str]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "project_version": _project_version(),
    }


def _logical_command(adapter: AdapterProtocol, case: Mapping[str, Any]) -> list[str]:
    command = adapter.build_command(
        package=str(case["package_path"]), case=case, output="{staging_output}"
    )
    root = repository_root().resolve()
    logical: list[str] = []
    for argument in command:
        if argument == sys.executable:
            logical.append("{python_executable}")
            continue
        candidate = Path(argument)
        if candidate.is_absolute():
            try:
                logical.append(candidate.resolve().relative_to(root).as_posix())
            except ValueError:
                logical.append(f"{{external_runner:{candidate.name}}}")
            continue
        logical.append(argument)
    return logical


def _cache_material(
    manifest: Mapping[str, Any],
    case: Mapping[str, Any],
    adapter: AdapterProtocol,
    actual_command: Sequence[str],
    manifest_sha256: str,
) -> tuple[str, dict[str, str], list[str]]:
    logical = _logical_command(adapter, case)
    command_sha = _canonical_sha(logical)
    environment_sha = _canonical_sha(_environment_payload())
    runner_sha = _hash_files(_runner_inputs(adapter, actual_command), root=repository_root())
    hashes = {
        "package_sha256": str(case["expected_sha256"]),
        "annotation_sha256": str(case["annotation_sha256"]),
        "runner_sha256": runner_sha,
        "command_sha256": command_sha,
        "environment_sha256": environment_sha,
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
            "environment": _environment_payload(),
            "runner_sha256": runner_sha,
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


def _empty_normalized(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "observations": [],
        "technical_failures": [],
        "reported_technical_failures": [],
        "boundary_violations": [],
        "contract_errors": [],
    }


def _redact(text: str, *, staging: Path, package: Path) -> str:
    temporary = Path(tempfile.gettempdir())
    replacements = (
        (str(staging), "<STAGING_OUTPUT>"),
        (str(package), "<PACKAGE_ROOT>"),
        (str(Path.home()), "<HOME>"),
        (str(temporary.resolve()), "<TEMP>"),
        (str(temporary), "<TEMP>"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def _failure(
    category: str,
    message: str,
    *,
    runtime: Any | None = None,
    staging: Path,
    package: Path,
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
    for item in path.rglob("*"):
        if item.is_symlink():
            continue
        if item.is_file():
            total += item.stat().st_size
    return total


def _valid_current(
    path: Path,
    *,
    runs: Path,
    case_id: str,
    cache_key: str,
    hashes: Mapping[str, str],
    adapter: AdapterProtocol,
) -> dict[str, Any] | None:
    from .contracts import ContractError, validate_contract

    try:
        payload = _strict_json(path, label="current run result")
        validate_contract("run_result.schema.json", payload)
        _validate_run_artifacts(payload, runs=runs, case_id=case_id)
    except (CliError, ContractError, TypeError, ValueError):
        return None
    if (
        payload.get("cache_key") != cache_key
        or payload.get("hashes") != dict(hashes)
        or payload.get("adapter") != adapter.name
        or payload.get("adapter_version") != adapter.version
        or payload.get("status") != "success"
    ):
        return None
    return payload


def _inside_runs(runs: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not value or any(part == ".." for part in relative.parts):
        raise CliError(f"Unsafe run artifact path: {value!r}")
    root = runs.resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise CliError(f"Run artifact escapes runs_dir: {value!r}")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise CliError(f"Run artifact path contains a symlink: {value!r}")
    return resolved


def _validate_run_artifacts(payload: Mapping[str, Any], *, runs: Path, case_id: str) -> None:
    paths = payload["output_paths"]
    expected_result = f"cases/{case_id}/attempts/{payload['cache_key']}/run_result.json"
    if paths.get("run_result") != expected_result:
        raise CliError(f"Run result points to an unexpected attempt for case {case_id!r}")
    required = ["run_result", "normalized_observation"]
    if payload["status"] == "success":
        required.extend(("audit_summary", "coverage", "pipeline_summary", "report"))
    resolved = {name: _inside_runs(runs, paths[name]) for name in required}
    if any(not path.is_file() for path in resolved.values()):
        raise CliError(f"Run artifacts are incomplete for case {case_id!r}")
    attempt = _strict_json(resolved["run_result"], label=f"attempt result for {case_id}")
    current_compare = dict(payload)
    attempt_compare = dict(attempt)
    current_compare.pop("cache_status", None)
    attempt_compare.pop("cache_status", None)
    if current_compare != attempt_compare:
        raise CliError(f"Current and immutable attempt results differ for case {case_id!r}")
    normalized = _strict_json(
        resolved["normalized_observation"], label=f"normalized observation for {case_id}"
    )
    if normalized != payload["normalized_observation"]:
        raise CliError(f"Normalized artifact differs from run result for case {case_id!r}")


def _publish_directory(staging: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.bak")
    had_previous = destination.exists()
    try:
        if had_previous:
            os.replace(destination, backup)
        os.replace(staging, destination)
    except OSError:
        if had_previous and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def run_benchmark(
    manifest_path: Path | str,
    runs_dir: Path | str,
    *,
    case_ids: Sequence[str] | None = None,
    adapter_name: str = "full",
    timeout_seconds: float = 900,
    adapters: Mapping[str, AdapterProtocol] | None = None,
) -> dict[str, Any]:
    """Run selected frozen cases, reusing only fully validated successful results."""

    from .contracts import ContractError, validate_contract
    from .normalize import normalize_audit_output
    from .registry import load_manifest, resolve_case_paths, verify_frozen_case
    from .runtime import run_monitored, write_json_atomic

    manifest_file = Path(manifest_path)
    manifest = load_manifest(manifest_file, require_frozen=True)
    selected = _select_cases(manifest, case_ids)
    registry = _adapter_registry(adapters)
    if adapter_name not in registry:
        raise CliError(f"Unknown adapter {adapter_name!r}; available: {sorted(registry)!r}")
    adapter = registry[adapter_name]
    runs = Path(runs_dir)
    runs.mkdir(parents=True, exist_ok=True)
    if runs.is_symlink():
        raise CliError(f"runs_dir must not be a symlink: {runs}")
    manifest_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    summary_cases: list[dict[str, Any]] = []

    for case in selected:
        case_id = str(case["case_id"])
        verify_frozen_case(manifest_file.parent, dict(case))
        package, _ = resolve_case_paths(manifest_file.parent, dict(case))
        case_dir = runs / "cases" / case_id
        current_path = case_dir / "run_result.json"
        logical_probe = adapter.build_command(package=package, case=case, output="{staging_output}")
        cache_key, hashes, logical = _cache_material(
            manifest, case, adapter, logical_probe, manifest_sha
        )
        cached = _valid_current(
            current_path,
            runs=runs,
            case_id=case_id,
            cache_key=cache_key,
            hashes=hashes,
            adapter=adapter,
        )
        if cached is not None:
            cached = dict(cached)
            cached["cache_status"] = "reused"
            write_json_atomic(current_path, cached)
            summary_cases.append(
                {
                    "case_id": case_id,
                    "cache_status": "reused",
                    "status": "success",
                    "run_result": f"cases/{case_id}/run_result.json",
                }
            )
            continue

        cache_status = "invalidated" if current_path.exists() else "fresh"
        prior_success = None
        if current_path.exists():
            try:
                candidate = _strict_json(current_path, label="prior run result")
                validate_contract("run_result.schema.json", candidate)
                if candidate["status"] == "success":
                    prior_success = candidate
            except (CliError, ContractError, TypeError, ValueError):
                pass

        staging = Path(tempfile.mkdtemp(prefix=f".staging-{case_id}-", dir=runs))
        runtime = None
        normalized = _empty_normalized(case_id)
        status = "environment_failure"
        failure: dict[str, Any] | None = None
        try:
            actual_command = adapter.build_command(package=package, case=case, output=staging)
            runtime = run_monitored(actual_command, repository_root(), timeout_seconds)
            try:
                normalized = normalize_audit_output(
                    case_id, staging, package_root=package, staging_roots=(staging,)
                )
            except Exception as exc:
                status = "normalization_error"
                failure = _failure(
                    "normalization_error",
                    f"Could not normalize producer output: {type(exc).__name__}: {exc}",
                    runtime=runtime,
                    staging=staging,
                    package=package,
                )
            else:
                missing = [name for name in _REQUIRED_PRODUCER_FILES if not (staging / name).is_file()]
                if runtime.status == "timeout":
                    status = "timeout"
                    failure = _failure("timeout", "Producer exceeded timeout.", runtime=runtime, staging=staging, package=package)
                elif runtime.status != "success":
                    status = "process_error"
                    failure = _failure("process_error", "Producer exited unsuccessfully.", runtime=runtime, staging=staging, package=package)
                elif not runtime.cleanup_complete:
                    status = "environment_failure"
                    failure = _failure("cleanup_failure", "; ".join(runtime.cleanup_errors) or "Process-tree cleanup was incomplete.", runtime=runtime, staging=staging, package=package)
                elif missing:
                    status = "missing_output"
                    failure = _failure("missing_output", f"Missing required producer artifacts: {', '.join(missing)}", runtime=runtime, staging=staging, package=package)
                elif normalized["contract_errors"]:
                    status = "invalid_output"
                    failure = _failure("invalid_output", "Producer artifacts failed normalization contract checks.", runtime=runtime, staging=staging, package=package)
                else:
                    status = "success"
                    failure = None

            write_json_atomic(staging / "normalized_observation.json", normalized)
            if runtime is not None:
                (staging / "stdout.log").write_text(_redact(runtime.stdout_tail, staging=staging, package=package), encoding="utf-8")
                (staging / "stderr.log").write_text(_redact(runtime.stderr_tail, staging=staging, package=package), encoding="utf-8")
            output_size = _tree_size(staging)
            attempt_rel = Path("cases") / case_id / "attempts" / cache_key
            output_rel = attempt_rel / "output"
            result_rel = attempt_rel / "run_result.json"
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
            attempt_dir = runs / attempt_rel
            _publish_directory(staging, attempt_dir / "output")
            write_json_atomic(attempt_dir / "run_result.json", result)
            if status == "success" or prior_success is None:
                write_json_atomic(current_path, result)
        except Exception as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            status = "environment_failure"
            failure_telemetry = _telemetry(runtime)
            failure_telemetry["timed_out"] = False
            publication_failure = _failure(
                "environment_failure",
                f"Attempt publication failed: {type(exc).__name__}: {exc}",
                runtime=runtime,
                staging=staging,
                package=package,
            )
            publication_failure["timed_out"] = False
            failure_result = {
                "schema_version": "1.0.0",
                "case_id": case_id,
                "adapter": adapter.name,
                "adapter_version": adapter.version,
                "status": status,
                "hashes": hashes,
                "cache_key": cache_key,
                "cache_status": cache_status,
                "command": logical,
                "telemetry": failure_telemetry,
                "output_paths": {"run_result": f"cases/{case_id}/attempts/{cache_key}/run_result.json"},
                "normalized_observation": normalized,
                "failure": publication_failure,
            }
            validate_contract("run_result.schema.json", failure_result)
            attempt_result = case_dir / "attempts" / cache_key / "run_result.json"
            try:
                write_json_atomic(attempt_result, failure_result)
                if prior_success is None:
                    write_json_atomic(current_path, failure_result)
            except OSError:
                pass
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)

        summary_cases.append(
            {
                "case_id": case_id,
                "cache_status": cache_status,
                "status": status,
                "run_result": f"cases/{case_id}/attempts/{cache_key}/run_result.json",
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
    write_json_atomic(runs / "run_summary.json", summary)
    return summary


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
    """Strictly validate current runs, recompute matches, and write metrics."""

    from .contracts import validate_contract
    from .matching import match_labels
    from .metrics import aggregate_metrics, select_evaluation_labels
    from .registry import load_manifest, resolve_case_paths, verify_frozen_case
    from .runtime import write_json_atomic

    manifest_file = Path(manifest_path)
    manifest = load_manifest(manifest_file, require_frozen=True)
    selected = _select_cases(manifest, case_ids)
    registry = _adapter_registry(adapters)
    providers = dict(assertion_providers or {})
    manifest_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    runs = Path(runs_dir)
    bundles: list[dict[str, Any]] = []
    for case in selected:
        case_id = str(case["case_id"])
        verify_frozen_case(manifest_file.parent, dict(case))
        package, annotation_path = resolve_case_paths(manifest_file.parent, dict(case))
        result_path = runs / "cases" / case_id / "run_result.json"
        run = _strict_json(result_path, label=f"run result for {case_id}")
        validate_contract("run_result.schema.json", run)
        _validate_run_artifacts(run, runs=runs, case_id=case_id)
        adapter_name = run["adapter"]
        if adapter_name not in registry:
            raise CliError(f"No registered adapter can verify run {case_id!r}: {adapter_name!r}")
        adapter = registry[adapter_name]
        probe = adapter.build_command(package=package, case=case, output="{staging_output}")
        expected_key, expected_hashes, _ = _cache_material(manifest, case, adapter, probe, manifest_sha)
        if run["cache_key"] != expected_key or run["hashes"] != expected_hashes:
            raise CliError(f"Run result cache/hash mismatch for case {case_id!r}; rerun the case")
        annotation = _strict_json(annotation_path, label=f"annotation for {case_id}")
        validate_contract("annotation.schema.json", annotation)
        if annotation["case_id"] != case_id:
            raise CliError(f"Annotation case_id mismatch for case {case_id!r}")
        labels = select_evaluation_labels(case, annotation)
        match = match_labels(
            labels,
            run["normalized_observation"]["observations"],
            roles=("recall_label", "coverage_gap"),
        )
        assertions: Sequence[bool] = ()
        if case["track"] == "regression" and adapter_name in providers:
            assertions = providers[adapter_name](case, annotation, run)
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
    write_json_atomic(output_path, metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bria-bench", description="Run and evaluate frozen BRIA-Bench registries.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    freeze = subcommands.add_parser("freeze", help="Freeze package and annotation hashes.")
    freeze.add_argument("--source", required=True, type=Path)
    freeze.add_argument("--output", required=True, type=Path)
    freeze.add_argument("--frozen-at", required=True)

    run = subcommands.add_parser("run", help="Run or resume frozen benchmark cases.")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--runs-dir", required=True, type=Path)
    run.add_argument("--case", action="append", dest="case_ids")
    run.add_argument("--adapter", default="full")
    run.add_argument("--timeout-seconds", type=float, default=900)

    evaluate = subcommands.add_parser("evaluate", help="Validate runs and aggregate metrics.")
    evaluate.add_argument("--manifest", required=True, type=Path)
    evaluate.add_argument("--runs-dir", required=True, type=Path)
    evaluate.add_argument("--output", required=True, type=Path)
    evaluate.add_argument("--case", action="append", dest="case_ids")

    report = subcommands.add_parser("report", help="Render Task 8 metrics report (when installed).")
    report.add_argument("--metrics", required=True, type=Path)
    report.add_argument("--output", required=True, type=Path)

    packet = subcommands.add_parser("reviewer-packet", help="Export Task 11 reviewer packet (when installed).")
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
        return 0 if all(case["status"] == "success" for case in summary["cases"]) else 1
    if args.command == "evaluate":
        evaluate_benchmark(args.manifest, args.runs_dir, args.output, case_ids=args.case_ids)
        return 0
    if args.command == "report":
        try:
            from .report import render_metrics_report
        except ModuleNotFoundError as exc:
            if exc.name == "benchmarks.bria_bench.report":
                raise CliError("The report command requires BRIA-Bench Task 8; report.py is not implemented yet") from exc
            raise
        metrics = _strict_json(args.metrics, label="metrics")
        rendered = render_metrics_report(metrics)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        return 0
    if args.command == "reviewer-packet":
        try:
            from .reviewer_packet import export_reviewer_packet
        except ModuleNotFoundError as exc:
            if exc.name == "benchmarks.bria_bench.reviewer_packet":
                raise CliError("The reviewer-packet command requires BRIA-Bench Task 11; reviewer_packet.py is not implemented yet") from exc
            raise
        export_reviewer_packet(args.manifest, args.output_dir, args.mapping_output)
        return 0
    raise CliError(f"Unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return _dispatch(args)
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(f"bria-bench: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
