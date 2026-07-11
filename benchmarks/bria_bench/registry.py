"""Safe loading and atomic freezing of BRIA-Bench case registries."""

from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from .contracts import ContractError, validate_contract
from .hashing import HashingError, hash_file, hash_tree


MANIFEST_SCHEMA = "benchmark_manifest.schema.json"
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class RegistryError(ValueError):
    """Raised when a BRIA-Bench registry is invalid or unsafe to use."""


class ResolvedCasePaths(NamedTuple):
    package_path: Path
    annotation_path: Path


def _as_path(value: Path | str, *, label: str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise RegistryError(f"Invalid {label}: {value!r}") from exc


def _benchmark_root(root: Path | str) -> Path:
    candidate = _as_path(root, label="benchmark root")
    try:
        root_stat = candidate.lstat()
    except (OSError, ValueError) as exc:
        raise RegistryError(f"Benchmark root is unavailable: {candidate}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise RegistryError(f"Benchmark root must be an actual directory: {candidate}")
    try:
        return candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RegistryError(f"Could not resolve benchmark root: {candidate}") from exc


def _reject_symlink_components(root: Path, relative: Path) -> None:
    current = root
    for component in relative.parts:
        if component in ("", "."):
            continue
        current /= component
        try:
            component_stat = current.lstat()
        except FileNotFoundError:
            break
        except (OSError, ValueError) as exc:
            raise RegistryError(f"Could not inspect path component: {current}") from exc
        if stat.S_ISLNK(component_stat.st_mode):
            raise RegistryError(f"Path component is a symlink: {current}")


def resolve_inside(root: Path | str, value: Path | str) -> Path:
    """Resolve a lexical package-relative path below an actual benchmark root."""

    benchmark_root = _benchmark_root(root)
    candidate = _as_path(value, label="relative path")
    if isinstance(value, str) and not value:
        raise RegistryError("Path must not be empty")
    if candidate == Path("."):
        raise RegistryError("Path must not be empty or '.'")
    if candidate.is_absolute():
        raise RegistryError("Absolute paths are not allowed")
    if any(component == ".." for component in candidate.parts):
        raise RegistryError("Path with '..' escapes benchmark root")

    _reject_symlink_components(benchmark_root, candidate)
    try:
        resolved = (benchmark_root / candidate).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RegistryError(f"Could not resolve path: {value!r}") from exc

    try:
        inside = resolved.is_relative_to(benchmark_root)
    except (OSError, ValueError) as exc:
        raise RegistryError(f"Could not validate resolved path: {value!r}") from exc
    if not inside:
        raise RegistryError("Resolved path escapes benchmark root")
    _reject_symlink_components(benchmark_root, resolved.relative_to(benchmark_root))
    return resolved


def resolve_case_paths(root: Path | str, case: dict[str, Any]) -> ResolvedCasePaths:
    """Resolve and type-check a case's package and sealed annotation paths."""

    if not isinstance(case, dict):
        raise RegistryError("Case must be an object")
    case_id = case.get("case_id", "<unknown>")
    try:
        package = resolve_inside(root, case["package_path"])
        annotation = resolve_inside(root, case["annotation_path"])
    except KeyError as exc:
        raise RegistryError(f"Case {case_id!r} is missing {exc.args[0]}") from exc
    except RegistryError as exc:
        raise RegistryError(f"Case {case_id!r}: {exc}") from exc

    try:
        package_stat = package.lstat()
    except (OSError, ValueError) as exc:
        raise RegistryError(f"Case {case_id!r} package is unavailable: {package}") from exc
    if stat.S_ISLNK(package_stat.st_mode) or not stat.S_ISDIR(package_stat.st_mode):
        raise RegistryError(f"Case {case_id!r} package must be a directory: {package}")

    try:
        annotation_stat = annotation.lstat()
    except (OSError, ValueError) as exc:
        raise RegistryError(
            f"Case {case_id!r} annotation is unavailable: {annotation}"
        ) from exc
    if stat.S_ISLNK(annotation_stat.st_mode) or not stat.S_ISREG(annotation_stat.st_mode):
        raise RegistryError(f"Case {case_id!r} annotation must be a file: {annotation}")
    return ResolvedCasePaths(package, annotation)


def _validated_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"Could not read manifest: {path}") from exc
    try:
        validate_contract(MANIFEST_SCHEMA, payload)
    except ContractError as exc:
        raise RegistryError(f"Invalid BRIA-Bench manifest {path}: {exc}") from exc
    return payload


def load_manifest(path: Path | str, *, require_frozen: bool = False) -> dict[str, Any]:
    """Load, contract-validate, and path-check a manifest without reading annotations."""

    manifest_path = _as_path(path, label="manifest path")
    manifest = _validated_manifest(manifest_path)
    root = manifest_path.parent
    if require_frozen and "frozen_at" not in manifest:
        raise RegistryError("Frozen manifest requires frozen_at")

    for case in manifest["cases"]:
        resolve_case_paths(root, case)
        if require_frozen:
            for field in ("expected_sha256", "annotation_sha256"):
                if field not in case:
                    raise RegistryError(
                        f"Frozen case {case['case_id']!r} requires {field}"
                    )
    return manifest


def _fsync_directory(directory: Path) -> None:
    """Best-effort fsync of a containing directory where POSIX supports it."""

    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = -1
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(descriptor)
    except (OSError, ValueError):
        # Some POSIX filesystems expose directory open but reject fsync; the
        # file itself was already fsynced and publication remains atomic.
        return
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _publish_manifest(path: Path, manifest: dict[str, Any]) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(manifest, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(parent)
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def freeze_manifest(
    source_path: Path | str,
    output_path: Path | str,
    frozen_at: str,
) -> dict[str, Any]:
    """Freeze package hashes into a validated manifest and publish it atomically."""

    source = _as_path(source_path, label="source manifest path")
    output = _as_path(output_path, label="output manifest path")
    source_manifest = load_manifest(source, require_frozen=False)
    frozen = copy.deepcopy(source_manifest)
    frozen["frozen_at"] = frozen_at

    for case in frozen["cases"]:
        try:
            package, annotation = resolve_case_paths(source.parent, case)
            case["expected_sha256"] = hash_tree(package)
            case["annotation_sha256"] = hash_file(annotation)
        except (HashingError, RegistryError) as exc:
            raise RegistryError(
                f"Could not freeze case {case.get('case_id', '<unknown>')!r}: {exc}"
            ) from exc

    try:
        validate_contract(MANIFEST_SCHEMA, frozen)
    except ContractError as exc:
        raise RegistryError(f"Frozen manifest is invalid: {exc}") from exc
    _publish_manifest(output, frozen)
    return frozen


def verify_frozen_case(root: Path | str, case: dict[str, Any]) -> str:
    """Verify package and annotation hashes without parsing annotation content."""

    case_id = case.get("case_id", "<unknown>") if isinstance(case, dict) else "<unknown>"
    if not isinstance(case, dict):
        raise RegistryError(f"Case ID {case_id} must be an object")
    expected_package = case.get("expected_sha256")
    expected_annotation = case.get("annotation_sha256")
    for field, expected in (
        ("expected_sha256", expected_package),
        ("annotation_sha256", expected_annotation),
    ):
        if not isinstance(expected, str):
            raise RegistryError(f"Case ID {case_id} requires {field}")
        if SHA256_PATTERN.fullmatch(expected) is None:
            raise RegistryError(f"Case ID {case_id} has invalid {field}")

    try:
        package, annotation = resolve_case_paths(root, case)
        actual_package = hash_tree(package)
        actual_annotation = hash_file(annotation)
    except (HashingError, RegistryError) as exc:
        raise RegistryError(f"Could not verify case ID {case_id}: {exc}") from exc
    if actual_package != expected_package:
        raise RegistryError(
            f"Case ID {case_id} package hash mismatch: expected {expected_package}, "
            f"actual {actual_package}"
        )
    if actual_annotation != expected_annotation:
        raise RegistryError(
            f"Case ID {case_id} annotation hash mismatch: expected {expected_annotation}, "
            f"actual {actual_annotation}"
        )
    return actual_package
