"""Strict, portable import and scoring for the legacy synthetic eval collection."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .contracts import ContractError, validate_contract
from .hashing import HashingError, hash_tree
from .registry import RegistryError, freeze_manifest


FROZEN_AT = "2026-07-11T00:00:00Z"
CASE_IDS = tuple(f"case_{index:03d}" for index in range(1, 31))
NEGATIVE_CONTROLS = frozenset(
    {
        "case_001",
        "case_005",
        "case_012",
        "case_021",
        "case_022",
        "case_023",
        "case_029",
        "case_030",
    }
)
DEFAULT_FORBIDDEN = (
    "fraud confirmed",
    "misconduct confirmed",
    "fabricated",
    "falsified",
    "学术不端成立",
    "造假成立",
    "实锤",
    "作者造假",
    "故意造假",
)
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}

_EXPECTED_PACKAGE_HASHES = {
    "case_001": "8217134197e52d1dc6c270382f9ce413e0abbadbdd52b9c2c087a41dd379ed58",
    "case_002": "57bd63d0460251ef0c72f90e9f7b526d02da3639500c5bf942dd8d21c5da024f",
    "case_003": "0d740a9f028f362c5a5ab939895fec674125d456c0a19f4475e90a52759c54fe",
    "case_004": "76ac5afaca00ed530e70cc08ad3b59c949e4cce47dbd459f41e836b7539f6fcd",
    "case_005": "fb08b0966a976800fddb7741259eb0e355335512836c1a25f5c74815429afe20",
    "case_006": "4fa50e5312e9ebd55736aaa495416ec8b62797347e169cca1e1e418a387e503d",
    "case_007": "8afc8b33db361b8499fc6195a30b296f969ee9838e70f52d07e6c8671e96c8e2",
    "case_008": "8be79012e04d79df9bc6cbee5e82b601b11189ae3dba483ebdbe60dbb8200068",
    "case_009": "ddaf6f4e2ae37f36acd24cf042f91b0911772135d189b4d2eabca47296faea9e",
    "case_010": "a1c0a1560814201dd2dbe60366eb79129e92eaabe2c1730b1eda3095a0e0c5ba",
    "case_011": "a584432b190dd3a77f0e8572a82706938c2eae5f969d76bfc224fa92f90fef34",
    "case_012": "6da48646771f035302fa9d34812966fd5c0f43b31df248b1785f2fa662c81a95",
    "case_013": "10b8ad9fc07d8c0bb7dce2b967453aa67ef2e45f8ac54925317a2ad2b45d316e",
    "case_014": "8e117d4e68afda2ffa08cdb474f5b47112e103666643621ef97d493513cfe265",
    "case_015": "077bcbe5b4c91285b0b104523a54268141f5ac13498bbb5bfcc821be23a2ed7a",
    "case_016": "3f18e7ba2a583203ca9d8c2ac5e80e70774eb2a12ec34502f930806438f13179",
    "case_017": "159c445a6e87463a9d2d1b55ed75b35d4ef12739f2fb258130debdecbf570092",
    "case_018": "9eb1ace4fd3baefd6fb110096e44c597d391a9c975213befc9b0747224e008f5",
    "case_019": "96220236e8781b5cde57e79c81d262fde12869d4b75cce11c6003effc1094077",
    "case_020": "4caaabb6ac33fb6151a0026eddecafbae098619bd50753be5133b9cf5c5cca1b",
    "case_021": "a2b3456bed801c3375bb6ab7aafa3b7056162f33d4bc457b272ec8c45bb08d01",
    "case_022": "f279c1d1ac4ca339f379e2fdd7c00c61b429bd0167c0c3bc2d706e58b35b4554",
    "case_023": "482a9f0d0c2e9e8cd871b64f6e91f13dc17d2f4799a32436787e0284ba25ad1f",
    "case_024": "91840d0a86a0650e73412055d21d8acc981ef330e877ccb9a91a3697ca5d5e8e",
    "case_025": "9e3e86bdf93904eae27e218c1ac953200f1937387c51e2bfc8318f23b51e2614",
    "case_026": "19f519d65b97d9a0764c70a44d6436daa2fee086232d50cc518e17b0877e68eb",
    "case_027": "0416519db39bfeb724d1beaca9bde70cd77b3c314c70324c84501ce403d23829",
    "case_028": "66bdeb8a326a247902d815dad5f4b6d95d75b0c6aa8850588e1ef85a807df54c",
    "case_029": "ae2fcf023a14fb83543395866ca5365198ea5d2e77eb9d26b9cb04d80199447e",
    "case_030": "b3649b656142f1fdea2469a2a4c41f5357dc7be26ff4cb9e03863b8175008a12",
}

_ISSUE_FAMILY_BY_TYPE = {
    "image_reuse_cluster": "image_global_similarity",
    "local_patch_reuse": "image_local_reuse",
    "terminal_digit_anomaly": "statistics_or_numeric",
    "precision_mixing": "statistics_or_numeric",
    "cross_file_sequence_reuse": "statistics_or_numeric",
    "sd_sem_inconsistency": "statistics_or_numeric",
    "integer_count_inconsistency": "statistics_or_numeric",
    "linear_shift_pattern": "statistics_or_numeric",
    "affine_transform_pattern": "statistics_or_numeric",
    "rank_pattern_reuse": "statistics_or_numeric",
    "residual_pattern_reuse": "statistics_or_numeric",
    "methods_boilerplate_overlap": "text_overlap",
    "text_overlap_candidate": "text_overlap",
    "self_overlap_candidate": "text_overlap",
    # Exact aliases used by the committed JSON-compatible legacy labels.
    "SD is not consistent": "statistics_or_numeric",
    "weak triage signal": "statistics_or_numeric",
    "pseudoreplication_candidate": "statistics_or_numeric",
    "whole-column": "statistics_or_numeric",
    "longitudinal": "statistics_or_numeric",
    "Time-stratified": "statistics_or_numeric",
    "precision": "statistics_or_numeric",
    "Identical numeric sequence": "statistics_or_numeric",
    "Integer-count": "statistics_or_numeric",
}
_LABEL_KEYS = frozenset(
    {
        "case_id",
        "case_type_hidden",
        "audit_mode",
        "expected_behavior",
        "required_findings",
        "required_report_terms",
        "forbidden_outputs",
        "risk_caps",
    }
)
_REQUIRED_LABEL_KEYS = _LABEL_KEYS - {"required_report_terms"}
_BEHAVIOR_KEYS = frozenset(
    {"misconduct_verdict_allowed", "min_overall_risk", "max_overall_risk"}
)
_FINDING_KEYS = frozenset(
    {
        "finding_type",
        "expected_risk_range",
        "locations_should_include",
        "evidence_should_include",
        "required_materials_should_include",
        "benign_explanations_should_include_any",
    }
)
_RISK_CAP_KEYS = frozenset({"weak_statistics_only_max", "public_pdf_only_max"})
_SOURCE_NOTE = (
    "These are repository-authored procedural synthetic fixtures copied byte-for-byte from the legacy "
    "eval collection; redistributable under the repository MIT license."
)
_FIXTURE_README = """# Legacy Regression Fixtures

These repository-authored procedural synthetic fixtures preserve the legacy eval behavior.
Some files named `.pdf` are ASCII procedural fixtures rather than real PDF documents. These
cases test regression behavior, not real-PDF/manuscript accuracy.
"""


class LegacyRegressionError(ValueError):
    """Raised when legacy source data or deterministic materialization is invalid."""


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LegacyRegressionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_bytes(data: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                LegacyRegressionError(f"non-finite JSON value: {value}")
            ),
        )
    except LegacyRegressionError:
        raise
    except (UnicodeError, json.JSONDecodeError, OverflowError, RecursionError) as exc:
        raise LegacyRegressionError(
            f"invalid strict JSON label {label}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise LegacyRegressionError(f"legacy label {label} must be a JSON object")
    return payload


def _unknown_or_missing_keys(
    value: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    label: str,
) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise LegacyRegressionError(f"{label} has unknown fields: {sorted(unknown)!r}")
    if missing:
        raise LegacyRegressionError(f"{label} is missing fields: {sorted(missing)!r}")


def _require_nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LegacyRegressionError(f"{label} must be a non-empty string")
    return value


def _require_string_list(
    value: Any, *, label: str, allow_empty: bool = False
) -> list[str]:
    if not isinstance(value, list):
        raise LegacyRegressionError(f"{label} must be an array")
    if not allow_empty and not value:
        raise LegacyRegressionError(f"{label} must not be empty")
    for index, item in enumerate(value):
        _require_nonempty_string(item, label=f"{label}[{index}]")
    return value


def _require_risk(value: Any, *, label: str) -> str:
    risk = _require_nonempty_string(value, label=label)
    if risk not in RISK_ORDER:
        raise LegacyRegressionError(f"{label} has unknown risk level: {risk!r}")
    return risk


def _validate_label_payload(payload: dict[str, Any], *, expected_case_id: str) -> None:
    _unknown_or_missing_keys(
        payload,
        allowed=_LABEL_KEYS,
        required=_REQUIRED_LABEL_KEYS,
        label=f"legacy label {expected_case_id}",
    )
    case_id = _require_nonempty_string(payload["case_id"], label="case_id")
    if case_id != expected_case_id:
        raise LegacyRegressionError(
            f"legacy label ID mismatch: expected {expected_case_id!r}, found {case_id!r}"
        )
    _require_nonempty_string(payload["case_type_hidden"], label="case_type_hidden")
    audit_mode = _require_nonempty_string(payload["audit_mode"], label="audit_mode")
    expected_mode = (
        "external_literature_triage"
        if case_id == "case_009"
        else "internal_presubmission"
    )
    if audit_mode != expected_mode:
        raise LegacyRegressionError(
            f"{case_id} audit_mode must be {expected_mode!r}, found {audit_mode!r}"
        )

    behavior = payload["expected_behavior"]
    if not isinstance(behavior, dict):
        raise LegacyRegressionError("expected_behavior must be an object")
    _unknown_or_missing_keys(
        behavior,
        allowed=_BEHAVIOR_KEYS,
        required=_BEHAVIOR_KEYS,
        label="expected_behavior",
    )
    if not isinstance(behavior["misconduct_verdict_allowed"], bool):
        raise LegacyRegressionError("misconduct_verdict_allowed must be boolean")
    _require_risk(behavior["min_overall_risk"], label="min_overall_risk")
    _require_risk(behavior["max_overall_risk"], label="max_overall_risk")
    if (
        RISK_ORDER[behavior["min_overall_risk"]]
        > RISK_ORDER[behavior["max_overall_risk"]]
    ):
        raise LegacyRegressionError("expected_behavior risk range is reversed")

    findings = payload["required_findings"]
    if not isinstance(findings, list):
        raise LegacyRegressionError("required_findings must be an array")
    for index, finding in enumerate(findings):
        label = f"required_findings[{index}]"
        if not isinstance(finding, dict):
            raise LegacyRegressionError(f"{label} must be an object")
        _unknown_or_missing_keys(
            finding,
            allowed=_FINDING_KEYS,
            required=_FINDING_KEYS,
            label=label,
        )
        finding_type = _require_nonempty_string(
            finding["finding_type"], label=f"{label}.finding_type"
        )
        if finding_type not in _ISSUE_FAMILY_BY_TYPE:
            raise LegacyRegressionError(
                f"unknown legacy finding type: {finding_type!r}"
            )
        risk_range = finding["expected_risk_range"]
        if not isinstance(risk_range, list) or len(risk_range) != 2:
            raise LegacyRegressionError(
                f"{label}.expected_risk_range must have two items"
            )
        low = _require_risk(risk_range[0], label=f"{label}.expected_risk_range[0]")
        high = _require_risk(risk_range[1], label=f"{label}.expected_risk_range[1]")
        if RISK_ORDER[low] > RISK_ORDER[high]:
            raise LegacyRegressionError(f"{label}.expected_risk_range is reversed")
        for key in (
            "locations_should_include",
            "evidence_should_include",
            "required_materials_should_include",
            "benign_explanations_should_include_any",
        ):
            _require_string_list(finding[key], label=f"{label}.{key}")

    if "required_report_terms" in payload:
        _require_string_list(
            payload["required_report_terms"],
            label="required_report_terms",
            allow_empty=True,
        )
    _require_string_list(payload["forbidden_outputs"], label="forbidden_outputs")
    caps = payload["risk_caps"]
    if not isinstance(caps, dict):
        raise LegacyRegressionError("risk_caps must be an object")
    _unknown_or_missing_keys(
        caps,
        allowed=_RISK_CAP_KEYS,
        required=_RISK_CAP_KEYS,
        label="risk_caps",
    )
    for key in sorted(_RISK_CAP_KEYS):
        _require_risk(caps[key], label=f"risk_caps.{key}")


def _label_path(evals_root: Path, case_id: str) -> Path:
    return evals_root / "ground_truth" / f"{case_id}.expected.yaml"


def _source_label_path(case_id: str) -> str:
    return f"evals/ground_truth/{case_id}.expected.yaml"


def _load_label(evals_root: Path, case_id: str) -> tuple[dict[str, Any], str]:
    path = _label_path(evals_root, case_id)
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise LegacyRegressionError(f"legacy label must be an actual file: {path}")
        data = path.read_bytes()
    except LegacyRegressionError:
        raise
    except OSError as exc:
        raise LegacyRegressionError(f"could not read legacy label: {path}") from exc
    payload = _strict_json_bytes(data, label=path.name)
    _validate_label_payload(payload, expected_case_id=case_id)
    return payload, hashlib.sha256(data).hexdigest()


def _actual_child_names(path: Path, *, kind: str) -> set[str]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise LegacyRegressionError(f"{kind} must be an actual directory: {path}")
        return {item.name for item in path.iterdir()}
    except LegacyRegressionError:
        raise
    except OSError as exc:
        raise LegacyRegressionError(f"could not inspect {kind}: {path}") from exc


def _validate_source_inventory(evals_root: Path) -> None:
    expected_cases = set(CASE_IDS)
    actual_cases = _actual_child_names(evals_root / "cases", kind="legacy cases root")
    if actual_cases != expected_cases:
        raise LegacyRegressionError(
            "legacy case inventory mismatch: "
            f"missing={sorted(expected_cases - actual_cases)!r}, "
            f"extra={sorted(actual_cases - expected_cases)!r}"
        )
    expected_labels = {f"{case_id}.expected.yaml" for case_id in CASE_IDS}
    actual_labels = _actual_child_names(
        evals_root / "ground_truth", kind="legacy ground-truth root"
    )
    if actual_labels != expected_labels:
        raise LegacyRegressionError(
            "legacy label inventory mismatch: "
            f"missing={sorted(expected_labels - actual_labels)!r}, "
            f"extra={sorted(actual_labels - expected_labels)!r}"
        )

    file_count = 0
    for case_id in CASE_IDS:
        package = evals_root / "cases" / case_id
        try:
            actual_hash = hash_tree(package)
        except HashingError as exc:
            raise LegacyRegressionError(
                f"unsafe legacy package {case_id}: {exc}"
            ) from exc
        if actual_hash != _EXPECTED_PACKAGE_HASHES[case_id]:
            raise LegacyRegressionError(
                f"legacy package {case_id} does not match the tracked fixture bytes"
            )
        file_count += sum(path.is_file() for path in package.rglob("*"))
    if file_count != 148:
        raise LegacyRegressionError(
            f"legacy package inventory must contain 148 files, found {file_count}"
        )


def _embedded_contract(
    payload: dict[str, Any], *, case_id: str, source_sha256: str
) -> dict[str, Any]:
    contract = copy.deepcopy(payload)
    contract["source_label_path"] = _source_label_path(case_id)
    contract["source_label_sha256"] = source_sha256
    return contract


def _annotation(
    payload: dict[str, Any], *, case_id: str, source_sha256: str
) -> dict[str, Any]:
    source_path = _source_label_path(case_id)
    observations = []
    for index, finding in enumerate(payload["required_findings"], start=1):
        observations.append(
            {
                "observation_id": f"legacy_{case_id}_{index:03d}",
                "role": "recall_label",
                "issue_family": _ISSUE_FAMILY_BY_TYPE[finding["finding_type"]],
                "location": {
                    "terms": copy.deepcopy(finding["locations_should_include"])
                },
                "risk_range": copy.deepcopy(finding["expected_risk_range"]),
                "benign_explanations": copy.deepcopy(
                    finding["benign_explanations_should_include_any"]
                ),
                "required_materials": copy.deepcopy(
                    finding["required_materials_should_include"]
                ),
                "presence": "present",
                "evaluation_scope": "regression_only",
                "source_label_path": source_path,
            }
        )
    return {
        "schema_version": "1.0.0",
        "case_id": case_id,
        "negative_control": case_id in NEGATIVE_CONTROLS,
        "review_status": "controlled_ground_truth",
        "expected_observations": observations,
        "source_annotation_path": source_path,
        "legacy_regression_contract": _embedded_contract(
            payload, case_id=case_id, source_sha256=source_sha256
        ),
        "notes": (
            "Converted from a repository-authored procedural synthetic legacy label; "
            "regression-only and excluded from headline accuracy."
        ),
    }


def _manifest_case(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "track": "regression",
        "split": "reference",
        "package_path": f"cases/regression/{case_id}",
        "annotation_path": f"annotations/regression/{case_id}.json",
        "mode": (
            "external_public_material"
            if case_id == "case_009"
            else "internal_presubmission"
        ),
        "scan_profile": "standard",
        "redistributable": True,
        "license": "MIT",
        "headline_eligible": False,
        "source": f"evals/cases/{case_id}",
        "notes": _SOURCE_NOTE,
    }


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _write_canonical_json(path: Path, payload: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(payload))


def _inspect_expected_output_path(
    destination: Path, relative: Path, *, directory: bool
) -> None:
    current = destination
    for index, component in enumerate(relative.parts):
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise LegacyRegressionError(
                f"could not inspect generated output path: {current}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise LegacyRegressionError(
                f"generated output path must not contain a symlink: {current}"
            )
        expected_directory = index < len(relative.parts) - 1 or directory
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise LegacyRegressionError(
                f"generated output path component must be a directory: {current}"
            )
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise LegacyRegressionError(
                f"generated output path must be a regular file: {current}"
            )


def _inspect_replaced_tree(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LegacyRegressionError(
            f"could not inspect generated tree: {path}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise LegacyRegressionError(
            f"generated tree must be an actual directory: {path}"
        )
    stack = [path]
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                children = list(entries)
        except OSError as exc:
            raise LegacyRegressionError(
                f"could not inspect generated tree: {directory}"
            ) from exc
        for entry in children:
            child = Path(entry.path)
            try:
                child_metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise LegacyRegressionError(
                    f"could not inspect generated tree entry: {child}"
                ) from exc
            if stat.S_ISLNK(child_metadata.st_mode):
                raise LegacyRegressionError(
                    f"generated tree must not contain a symlink: {child}"
                )
            if stat.S_ISDIR(child_metadata.st_mode):
                stack.append(child)
            elif not stat.S_ISREG(child_metadata.st_mode):
                raise LegacyRegressionError(
                    f"generated tree contains an unsupported entry: {child}"
                )


def _preflight_output(destination: Path, source: Path) -> None:
    directory_paths = {
        Path("cases"),
        Path("cases/regression"),
        Path("annotations"),
        Path("annotations/regression"),
        Path("annotations/dev"),
        Path("results"),
    }
    file_paths = {
        Path("cases/regression/README.md"),
        Path("annotations/dev/.gitkeep"),
        Path("results/.gitkeep"),
        Path("benchmark_manifest.source.json"),
        Path("benchmark_manifest.json"),
    }
    for case_id in CASE_IDS:
        source_package = source / "cases" / case_id
        destination_package = Path("cases/regression") / case_id
        directory_paths.add(destination_package)
        for entry in source_package.rglob("*"):
            relative = destination_package / entry.relative_to(source_package)
            metadata = entry.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                directory_paths.add(relative)
            elif stat.S_ISREG(metadata.st_mode):
                file_paths.add(relative)
        file_paths.add(Path("annotations/regression") / f"{case_id}.json")

    for relative in sorted(
        directory_paths, key=lambda item: (len(item.parts), item.as_posix())
    ):
        _inspect_expected_output_path(destination, relative, directory=True)
    for relative in sorted(
        file_paths, key=lambda item: (len(item.parts), item.as_posix())
    ):
        _inspect_expected_output_path(destination, relative, directory=False)
    _inspect_replaced_tree(destination / "cases" / "regression")
    _inspect_replaced_tree(destination / "annotations" / "regression")


def _ensure_output_directory(destination: Path, relative: Path) -> Path:
    current = destination
    for component in relative.parts:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            try:
                current.mkdir()
                metadata = current.lstat()
            except OSError as exc:
                raise LegacyRegressionError(
                    f"could not create generated output directory: {current}"
                ) from exc
        except OSError as exc:
            raise LegacyRegressionError(
                f"could not inspect generated output directory: {current}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise LegacyRegressionError(
                f"generated output directory must be an actual directory: {current}"
            )
    return current


def _owned_output_file(destination: Path, relative: Path) -> Path:
    parent = _ensure_output_directory(destination, relative.parent)
    path = parent / relative.name
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as exc:
        raise LegacyRegressionError(
            f"could not inspect generated output file: {path}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise LegacyRegressionError(
            f"generated output file must be an actual regular file: {path}"
        )
    return path


def _replace_generated_directory(destination: Path, relative: Path) -> Path:
    parent = _ensure_output_directory(destination, relative.parent)
    path = parent / relative.name
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as exc:
        raise LegacyRegressionError(
            f"could not inspect generated directory: {path}"
        ) from exc
    if metadata is not None:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise LegacyRegressionError(
                f"generated path must be an actual directory: {path}"
            )
        _inspect_replaced_tree(path)
        shutil.rmtree(path)
    try:
        path.mkdir()
        metadata = path.lstat()
    except OSError as exc:
        raise LegacyRegressionError(
            f"could not create generated directory: {path}"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise LegacyRegressionError(
            f"generated path must be an actual directory: {path}"
        )
    return path


def _copy_package(source: Path, destination: Path, *, expected_sha256: str) -> None:
    destination.mkdir()
    entries = sorted(
        source.rglob("*"), key=lambda path: (len(path.parts), path.as_posix())
    )
    for entry in entries:
        relative = entry.relative_to(source)
        target = destination / relative
        metadata = entry.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise LegacyRegressionError(f"legacy package contains a symlink: {entry}")
        if stat.S_ISDIR(metadata.st_mode):
            target.mkdir()
        elif stat.S_ISREG(metadata.st_mode):
            target.write_bytes(entry.read_bytes())
        else:
            raise LegacyRegressionError(
                f"legacy package has an unsupported entry: {entry}"
            )
    try:
        actual = hash_tree(destination)
    except HashingError as exc:
        raise LegacyRegressionError(
            f"could not verify copied package: {destination}"
        ) from exc
    if actual != expected_sha256:
        raise LegacyRegressionError(f"copied package hash mismatch: {destination.name}")


def _validated_root(value: Path | str, *, label: str, create: bool = False) -> Path:
    try:
        path = Path(value)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if not create:
                raise
            parent = _validated_root(path.parent, label=f"{label} parent", create=True)
            path = parent / path.name
            path.mkdir()
            metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise LegacyRegressionError(f"{label} must be an actual directory: {path}")
        return path.resolve(strict=True)
    except LegacyRegressionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise LegacyRegressionError(f"invalid {label}: {value!r}") from exc


def _prospective_output_root(value: Path | str) -> Path:
    try:
        path = Path(os.path.abspath(value))
        current = path
        missing_components: list[str] = []
        while True:
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                missing_components.append(current.name)
                current = current.parent
                continue
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise LegacyRegressionError(
                    "benchmark output root components must be actual directories: "
                    f"{current}"
                )
            resolved = current.resolve(strict=True)
            return resolved.joinpath(*reversed(missing_components))
    except LegacyRegressionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise LegacyRegressionError(
            f"invalid benchmark output root: {value!r}"
        ) from exc


def expand_legacy_regression(
    evals_root: Path | str,
    output_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Copy and convert the sealed 30-case legacy collection into a benchmark root."""

    source = _validated_root(evals_root, label="legacy eval root")
    destination_candidate = _prospective_output_root(
        output_root if output_root is not None else Path(__file__).resolve().parent
    )
    if (
        destination_candidate == source
        or destination_candidate.is_relative_to(source)
        or source.is_relative_to(destination_candidate)
    ):
        raise LegacyRegressionError(
            "benchmark output root and legacy eval root must not overlap"
        )
    destination = _validated_root(
        destination_candidate,
        label="benchmark output root",
        create=True,
    )
    _validate_source_inventory(source)

    loaded = {case_id: _load_label(source, case_id) for case_id in CASE_IDS}
    _preflight_output(destination, source)
    cases_root = _replace_generated_directory(destination, Path("cases/regression"))
    annotations_root = _replace_generated_directory(
        destination, Path("annotations/regression")
    )

    manifest_cases = []
    for case_id in CASE_IDS:
        _copy_package(
            source / "cases" / case_id,
            cases_root / case_id,
            expected_sha256=_EXPECTED_PACKAGE_HASHES[case_id],
        )
        label, source_sha256 = loaded[case_id]
        annotation = _annotation(label, case_id=case_id, source_sha256=source_sha256)
        try:
            validate_contract("annotation.schema.json", annotation)
        except ContractError as exc:
            raise LegacyRegressionError(
                f"converted annotation is invalid: {case_id}: {exc}"
            ) from exc
        _write_canonical_json(annotations_root / f"{case_id}.json", annotation)
        manifest_cases.append(_manifest_case(case_id))

    _write_bytes_atomic(
        _owned_output_file(destination, Path("cases/regression/README.md")),
        _FIXTURE_README.encode("utf-8"),
    )
    _write_bytes_atomic(
        _owned_output_file(destination, Path("annotations/dev/.gitkeep")), b""
    )
    _write_bytes_atomic(_owned_output_file(destination, Path("results/.gitkeep")), b"")

    source_manifest = {
        "schema_version": "1.0.0",
        "benchmark_id": "bria-bench",
        "benchmark_version": "0.1.0",
        "cases": manifest_cases,
    }
    source_path = _owned_output_file(
        destination, Path("benchmark_manifest.source.json")
    )
    frozen_path = _owned_output_file(destination, Path("benchmark_manifest.json"))
    _write_canonical_json(source_path, source_manifest)
    try:
        freeze_manifest(source_path, frozen_path, FROZEN_AT)
    except RegistryError as exc:
        raise LegacyRegressionError(f"could not freeze legacy manifest: {exc}") from exc
    return copy.deepcopy(manifest_cases)


def _risk_value(value: Any) -> int:
    return RISK_ORDER.get(str(value or "R0").strip().upper(), -1)


def _fields_text(finding: Mapping[str, Any], fields: Sequence[str]) -> str:
    values: list[str] = []
    for field in fields:
        value = finding.get(field, "")
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.append(json.dumps(value, ensure_ascii=False))
        else:
            values.append(str(value))
    return " ".join(values).lower()


def _contains_any(text: str, needles: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(str(needle).lower() in lowered for needle in needles)


def _risk_in_range(risk: Any, expected_range: Sequence[str]) -> bool:
    if len(expected_range) != 2:
        return True
    value = _risk_value(risk)
    return _risk_value(expected_range[0]) <= value <= _risk_value(expected_range[1])


def _finding_matches(
    finding: Mapping[str, Any], requirement: Mapping[str, Any], report_text: str
) -> bool:
    expected = str(requirement.get("finding_type", "")).lower()
    if expected:
        actual = _fields_text(
            finding,
            (
                "finding_type",
                "evidence_type",
                "location",
                "required_materials_to_resolve",
                "benign_explanations_considered",
                "recommended_action",
            ),
        )
        if expected not in actual:
            return False
    risk_range = requirement.get("expected_risk_range")
    if isinstance(risk_range, list) and not _risk_in_range(
        finding.get("risk_level", "R0"), risk_range
    ):
        return False
    for key, fields in (
        ("locations_should_include", ("location",)),
        (
            "evidence_should_include",
            (
                "finding_type",
                "evidence_type",
                "location",
                "evidence",
                "recommended_action",
            ),
        ),
        ("required_materials_should_include", ("required_materials_to_resolve",)),
    ):
        text = _fields_text(finding, fields)
        if key == "evidence_should_include":
            text = f"{text} {report_text.lower()}"
        if any(str(needle).lower() not in text for needle in requirement.get(key, [])):
            return False
    benign = requirement.get("benign_explanations_should_include_any", [])
    return not benign or _contains_any(
        _fields_text(finding, ("benign_explanations_considered",)), benign
    )


def _embedded_label(contract: Mapping[str, Any]) -> dict[str, Any]:
    allowed = _LABEL_KEYS | {"source_label_path", "source_label_sha256"}
    required = _REQUIRED_LABEL_KEYS | {"source_label_path", "source_label_sha256"}
    _unknown_or_missing_keys(
        contract,
        allowed=allowed,
        required=required,
        label="legacy_regression_contract",
    )
    case_id = _require_nonempty_string(contract["case_id"], label="case_id")
    source_path = _require_nonempty_string(
        contract["source_label_path"], label="source_label_path"
    )
    if source_path != _source_label_path(case_id):
        raise LegacyRegressionError(
            "legacy contract source_label_path does not match case_id"
        )
    source_sha = _require_nonempty_string(
        contract["source_label_sha256"], label="source_label_sha256"
    )
    if len(source_sha) != 64 or any(
        character not in "0123456789abcdef" for character in source_sha
    ):
        raise LegacyRegressionError("source_label_sha256 must be lowercase SHA-256")
    label = {
        key: copy.deepcopy(value)
        for key, value in contract.items()
        if key in _LABEL_KEYS
    }
    _validate_label_payload(label, expected_case_id=case_id)
    return label


def evaluate_legacy_contract(
    contract: Mapping[str, Any], summary: Mapping[str, Any], report_text: str
) -> bool:
    """Evaluate one sealed legacy label using the historical scorer's semantics."""

    if not isinstance(contract, Mapping):
        raise LegacyRegressionError("legacy contract must be an object")
    label = _embedded_label(contract)
    if not isinstance(summary, Mapping) or not isinstance(report_text, str):
        return False
    findings = summary.get("findings", []) or []
    if not isinstance(findings, list) or any(
        not isinstance(item, Mapping) for item in findings
    ):
        return False
    scoring_text = (
        report_text
        + "\n"
        + json.dumps(summary, ensure_ascii=False, sort_keys=True, allow_nan=False)
    )
    forbidden = list(label.get("forbidden_outputs", [])) + list(DEFAULT_FORBIDDEN)
    if bool(summary.get("misconduct_verdict_present")) or _contains_any(
        scoring_text, forbidden
    ):
        return False

    risks = [summary.get("overall_risk", "R0")]
    risks.extend(finding.get("risk_level", "R0") for finding in findings)
    observed_max = max(risks, key=_risk_value)
    behavior = label.get("expected_behavior", {})
    minimum = behavior.get("min_overall_risk")
    maximum = behavior.get("max_overall_risk")
    if minimum and _risk_value(observed_max) < _risk_value(minimum):
        return False
    if maximum and _risk_value(observed_max) > _risk_value(maximum):
        return False

    for requirement in label.get("required_findings", []) or []:
        if not any(
            _finding_matches(finding, requirement, scoring_text) for finding in findings
        ):
            return False
    if any(
        str(term).lower() not in scoring_text.lower()
        for term in label.get("required_report_terms", []) or []
    ):
        return False

    for finding in findings:
        if _risk_value(finding.get("risk_level")) >= _risk_value("R3"):
            if not finding.get("benign_explanations_considered"):
                return False
            if not finding.get("required_materials_to_resolve"):
                return False
            if not finding.get("recommended_action"):
                return False

    caps = label.get("risk_caps", {})
    case_type = str(label.get("case_type_hidden", "")).lower()
    weak_cap = caps.get("weak_statistics_only_max")
    if (
        weak_cap
        and "weak" in case_type
        and _risk_value(observed_max) > _risk_value(weak_cap)
    ):
        return False
    public_cap = caps.get("public_pdf_only_max")
    if (
        public_cap
        and "external" in case_type
        and _risk_value(observed_max) > _risk_value(public_cap)
    ):
        return False
    return True


__all__ = [
    "CASE_IDS",
    "LegacyRegressionError",
    "evaluate_legacy_contract",
    "expand_legacy_regression",
]
