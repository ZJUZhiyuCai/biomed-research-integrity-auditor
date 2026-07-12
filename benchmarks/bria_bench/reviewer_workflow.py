"""Immutable two-reviewer comparison and adjudication for BRIA-Bench."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .contracts import ContractError, validate_contract
from .hashing import HashingError, hash_tree
from .matching import match_labels
from .registry import RegistryError, resolve_case_paths, verify_frozen_case
from .reviewer_packet import (
    INDEPENDENT_BLINDED_SCOPE,
    _canonical_absent_target,
    _clear_xattrs,
    _fsync_directory,
    _fsync_tree,
    _inventory_tree,
    _lexists,
    _load_frozen_manifest,
    _make_directory,
    _parent_identity,
    _publish_no_replace,
    _read_regular_bytes,
    _reject_symlink_components,
    _serialize_json,
    _verify_mapping_file,
    _write_bytes,
)


SCHEMA_VERSION = "1.0.0"
_REVIEWER_ID_RE = re.compile(r"^BRIA-REV-[A-Z0-9]{8,32}$")
_ADJUDICATOR_ID_RE = re.compile(r"^BRIA-ADJ-[A-Z0-9]{8,32}$")
_ACCUSATION_RE = re.compile(
    r"\b(?:fraud|misconduct|fabricat(?:e|ed|ion)|falsif(?:y|ied|ication)|fake|guilty)\b",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(
    r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])"
)
_LOCAL_PATH_RE = re.compile(
    r"(?i)(?:"
    r"(?<![A-Za-z0-9:/])/(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/[^\s\"'<>]+"
    r"|(?<![A-Za-z0-9])(?:[A-Z]:\\Users\\|\\\\[^\\\s]+\\)[^\s\"'<>]+"
    r"|file:///(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/[^\s\"'<>]+"
    r")"
)
_CREDENTIAL_RE = re.compile(
    r"(?im)^\s*(?:password|passwd|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|"
    r"auth[_-]?token|bearer[_-]?token)\s*[:=]\s*\S+"
)
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|"
    r"-----BEGIN OPENSSH PRIVATE KEY-----"
)
_PROHIBITED_KEYS = frozenset(
    {
        "source_case_id",
        "source_annotation_sha256",
        "expected_observations",
        "detector_name",
        "detector_output",
        "mapping_output",
        "seed_commitment_sha256",
    }
)
_RISK_LEVELS = {f"R{value}": value for value in range(5)}


class ReviewerWorkflowError(ValueError):
    """Raised when a blinded-review state transition is unsafe or invalid."""


@dataclass(frozen=True)
class _LockedSubmission:
    root: Path
    packet_manifest: dict[str, Any]
    submission: dict[str, Any]
    forms_by_package: dict[str, list[dict[str, Any]]]
    reviewer_case_by_package: dict[str, str]
    submission_sha256: str


def _walk_values(value: Any) -> Iterator[tuple[str | None, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if isinstance(key, str):
                yield key, key
            yield from _walk_values(child)
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for child in value:
            yield from _walk_values(child)
    elif isinstance(value, str):
        yield None, value


def _privacy_check(payload: Any, label: str) -> None:
    for key, text in _walk_values(payload):
        if key in _PROHIBITED_KEYS:
            raise ReviewerWorkflowError(f"{label} contains prohibited key {key!r}")
        if _EMAIL_RE.search(text):
            raise ReviewerWorkflowError(f"{label} contains an email address")
        if _LOCAL_PATH_RE.search(text):
            raise ReviewerWorkflowError(f"{label} contains an absolute local path")
        if _CREDENTIAL_RE.search(text) or _PRIVATE_KEY_RE.search(text):
            raise ReviewerWorkflowError(f"{label} contains credential-like material")
        if key is None and _ACCUSATION_RE.search(text):
            raise ReviewerWorkflowError(
                f"{label} contains conclusion language outside the review contract"
            )


def _strict_json(path: Path, label: str) -> tuple[Any, bytes]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ReviewerWorkflowError(
                    f"{label} contains duplicate JSON key {key!r}"
                )
            result[key] = value
        return result

    try:
        raw = _read_regular_bytes(path, label)
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=reject_duplicates
        ), raw
    except ReviewerWorkflowError:
        raise
    except Exception as exc:
        raise ReviewerWorkflowError(f"{label} is not strict UTF-8 JSON") from exc


def _input_directory(value: Path | str, label: str) -> Path:
    path = Path(value)
    if any(part == ".." for part in path.parts):
        raise ReviewerWorkflowError(f"{label} must not contain '..'")
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        _reject_symlink_components(absolute, label)
        resolved = absolute.resolve(strict=True)
        metadata = resolved.lstat()
    except Exception as exc:
        raise ReviewerWorkflowError(f"Could not inspect {label}: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ReviewerWorkflowError(f"{label} must be an actual directory")
    return resolved


def _private_identifier(path_value: Path | str, pattern: re.Pattern[str], label: str) -> str:
    path = Path(os.path.abspath(os.fspath(Path(path_value))))
    try:
        _reject_symlink_components(path, label)
        before = path.lstat()
        raw = _read_regular_bytes(path, label)
        after = path.lstat()
    except Exception as exc:
        raise ReviewerWorkflowError(f"Could not read {label}") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise ReviewerWorkflowError(
            f"{label} must be a single-link regular file with mode 0600"
        )
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ReviewerWorkflowError(f"{label} must contain ASCII") from exc
    identifier = text.rstrip("\n")
    if text not in {identifier, identifier + "\n"} or pattern.fullmatch(identifier) is None:
        raise ReviewerWorkflowError(f"{label} has an invalid pseudonymous identifier")
    return identifier


def _publish_private_directory(
    target: Path,
    parent_identity: tuple[int, int],
    build: Any,
) -> None:
    stage: Path | None = None
    try:
        parent_metadata = target.parent.stat()
        if stat.S_IMODE(parent_metadata.st_mode) & 0o077:
            raise ReviewerWorkflowError(
                "Private output parent must not grant group or other permissions"
            )
        if hasattr(os, "geteuid") and parent_metadata.st_uid != os.geteuid():
            raise ReviewerWorkflowError("Private output parent must be owned by this user")
        stage = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.stage-", dir=target.parent)
        )
        os.chmod(stage, 0o700, follow_symlinks=False)
        _clear_xattrs(stage)
        initial_stage = stage.lstat()
        stage_identity = (initial_stage.st_dev, initial_stage.st_ino)
        build(stage)
        _assert_private_tree(stage)
        _fsync_tree(stage)
        if _parent_identity(target, "private output") != parent_identity:
            raise ReviewerWorkflowError("Private output parent changed before publication")
        if _lexists(target):
            raise ReviewerWorkflowError("Private output target appeared before publication")
        final_stage = stage.lstat()
        if (
            stat.S_ISLNK(final_stage.st_mode)
            or not stat.S_ISDIR(final_stage.st_mode)
            or (final_stage.st_dev, final_stage.st_ino) != stage_identity
        ):
            raise ReviewerWorkflowError("Private output stage changed before publication")
        _publish_no_replace(stage, target)
        stage = None
        _fsync_directory(target.parent)
    except BaseException as exc:
        if stage is not None:
            try:
                shutil.rmtree(stage)
            except OSError:
                pass
        if isinstance(exc, ReviewerWorkflowError):
            raise
        if isinstance(exc, Exception):
            raise ReviewerWorkflowError(f"Could not publish private artifact: {exc}") from exc
        raise


def _validate_packet_inventory(
    packet: Path,
    packet_manifest: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    expected_ids = [case["reviewer_case_id"] for case in packet_manifest["cases"]]
    top_level = {entry.name for entry in packet.iterdir()}
    if top_level != {"REVIEWER_GUIDE.md", "packet_manifest.json", "cases", "forms"}:
        raise ReviewerWorkflowError("Independent packet has an unexpected inventory")
    expected_guide = _read_regular_bytes(
        Path(__file__).with_name("INDEPENDENT_REVIEWER_GUIDE.md"),
        "independent reviewer guide",
    )
    if _read_regular_bytes(packet / "REVIEWER_GUIDE.md", "packet guide") != expected_guide:
        raise ReviewerWorkflowError("Independent reviewer guide does not match this release")
    if {entry.name for entry in (packet / "cases").iterdir()} != set(expected_ids):
        raise ReviewerWorkflowError("Independent packet case inventory is incomplete")
    if {entry.name for entry in (packet / "forms").iterdir()} != {
        f"{case_id}.json" for case_id in expected_ids
    }:
        raise ReviewerWorkflowError("Independent packet form inventory is incomplete")

    forms: dict[str, list[dict[str, Any]]] = {}
    for case in packet_manifest["cases"]:
        reviewer_case_id = case["reviewer_case_id"]
        case_dir = packet / "cases" / reviewer_case_id
        if {entry.name for entry in case_dir.iterdir()} != {"materials"}:
            raise ReviewerWorkflowError(
                f"Independent packet case {reviewer_case_id} has extra content"
            )
        try:
            materials_sha = hash_tree(case_dir / "materials")
        except HashingError as exc:
            raise ReviewerWorkflowError(
                f"Could not verify materials for {reviewer_case_id}"
            ) from exc
        if materials_sha != case["source_package_sha256"]:
            raise ReviewerWorkflowError(
                f"Materials changed after packet export for {reviewer_case_id}"
            )
        form, _ = _strict_json(
            packet / "forms" / f"{reviewer_case_id}.json",
            f"completed form for {reviewer_case_id}",
        )
        try:
            validate_contract("reviewer_form_independent_completed.schema.json", form)
        except ContractError as exc:
            raise ReviewerWorkflowError(
                f"Completed form is invalid for {reviewer_case_id}: {exc}"
            ) from exc
        if any(row["reviewer_case_id"] != reviewer_case_id for row in form):
            raise ReviewerWorkflowError(
                f"Completed form is assigned to the wrong case: {reviewer_case_id}"
            )
        _privacy_check(form, f"completed form for {reviewer_case_id}")
        forms[reviewer_case_id] = form
    return forms


def lock_reviewer_submission(
    packet_dir: Path | str,
    reviewer_id_file: Path | str,
    output_dir: Path | str,
    *,
    locked_at: str,
) -> dict[str, Any]:
    """Validate and immutably lock one independent reviewer's completed packet."""

    packet = _input_directory(packet_dir, "reviewer packet")
    reviewer_id = _private_identifier(
        reviewer_id_file, _REVIEWER_ID_RE, "reviewer ID file"
    )
    target, parent_identity = _canonical_absent_target(output_dir, "locked submission")
    packet_manifest, packet_manifest_raw = _strict_json(
        packet / "packet_manifest.json", "packet manifest"
    )
    try:
        validate_contract("reviewer_packet_manifest.schema.json", packet_manifest)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"Packet manifest is invalid: {exc}") from exc
    if packet_manifest.get("packet_scope") != INDEPENDENT_BLINDED_SCOPE:
        raise ReviewerWorkflowError(
            "Only independent_blinded packets can enter the locked review workflow"
        )
    canonical_packet_manifest = _serialize_json(packet_manifest)
    if packet_manifest_raw != canonical_packet_manifest:
        raise ReviewerWorkflowError(
            "Packet manifest formatting changed after immutable packet export"
        )
    forms = _validate_packet_inventory(packet, packet_manifest)
    try:
        packet_tree_sha = hash_tree(packet)
    except HashingError as exc:
        raise ReviewerWorkflowError("Could not hash completed reviewer packet") from exc

    canonical_forms: dict[str, bytes] = {}
    cases: list[dict[str, Any]] = []
    packet_case_by_id = {
        item["reviewer_case_id"]: item for item in packet_manifest["cases"]
    }
    for reviewer_case_id in sorted(forms):
        form_bytes = _serialize_json(forms[reviewer_case_id])
        canonical_forms[reviewer_case_id] = form_bytes
        cases.append(
            {
                "reviewer_case_id": reviewer_case_id,
                "source_package_sha256": packet_case_by_id[reviewer_case_id][
                    "source_package_sha256"
                ],
                "form_path": f"forms/{reviewer_case_id}.json",
                "form_sha256": hashlib.sha256(form_bytes).hexdigest(),
                "row_count": len(forms[reviewer_case_id]),
            }
        )
    submission = {
        "schema_version": SCHEMA_VERSION,
        "packet_scope": INDEPENDENT_BLINDED_SCOPE,
        "review_round_id": packet_manifest["review_round_id"],
        "reviewer_id": reviewer_id,
        "locked_at": locked_at,
        "packet_manifest_sha256": hashlib.sha256(packet_manifest_raw).hexdigest(),
        "packet_tree_sha256": packet_tree_sha,
        "form_schema": "reviewer_form_independent_completed.schema.json",
        "cases": cases,
    }
    try:
        validate_contract("reviewer_submission.schema.json", submission)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"Locked submission contract is invalid: {exc}") from exc

    def build(stage: Path) -> None:
        _make_directory(stage / "forms", 0o700)
        _write_bytes(
            stage / "packet_manifest.json", canonical_packet_manifest, 0o600
        )
        for reviewer_case_id, form_bytes in canonical_forms.items():
            _write_bytes(stage / "forms" / f"{reviewer_case_id}.json", form_bytes, 0o600)
        _write_bytes(stage / "submission.json", _serialize_json(submission), 0o600)

    _publish_private_directory(target, parent_identity, build)
    return submission


def _assert_private_tree(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise ReviewerWorkflowError(f"Locked submission contains a symlink: {path.name}")
        expected_mode = 0o700 if stat.S_ISDIR(metadata.st_mode) else 0o600
        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise ReviewerWorkflowError(
                f"Locked submission entry has unsafe permissions: {path.name}"
            )
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
            raise ReviewerWorkflowError(
                f"Locked submission file must have one hard link: {path.name}"
            )


def _load_locked_submission(value: Path | str, label: str) -> _LockedSubmission:
    root = _input_directory(value, label)
    _assert_private_tree(root)
    packet_manifest, packet_raw = _strict_json(
        root / "packet_manifest.json", f"{label} packet manifest"
    )
    submission, submission_raw = _strict_json(
        root / "submission.json", f"{label} submission manifest"
    )
    try:
        validate_contract("reviewer_packet_manifest.schema.json", packet_manifest)
        validate_contract("reviewer_submission.schema.json", submission)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"{label} contract is invalid: {exc}") from exc
    if packet_manifest.get("packet_scope") != INDEPENDENT_BLINDED_SCOPE:
        raise ReviewerWorkflowError(f"{label} is not an independent blinded submission")
    if submission["packet_manifest_sha256"] != hashlib.sha256(packet_raw).hexdigest():
        raise ReviewerWorkflowError(f"{label} packet manifest hash does not match")
    if submission["review_round_id"] != packet_manifest["review_round_id"]:
        raise ReviewerWorkflowError(f"{label} review round does not match its packet")

    expected_inventory = {
        ("file", "packet_manifest.json"),
        ("file", "submission.json"),
        ("directory", "forms"),
    }
    expected_inventory.update(
        ("file", case["form_path"]) for case in submission["cases"]
    )
    if set(_inventory_tree(root, enforce_material_policy=False)) != expected_inventory:
        raise ReviewerWorkflowError(f"{label} locked inventory changed")

    packet_cases = {
        item["reviewer_case_id"]: item for item in packet_manifest["cases"]
    }
    forms_by_package: dict[str, list[dict[str, Any]]] = {}
    reviewer_case_by_package: dict[str, str] = {}
    for case in submission["cases"]:
        reviewer_case_id = case["reviewer_case_id"]
        packet_case = packet_cases.get(reviewer_case_id)
        if packet_case is None:
            raise ReviewerWorkflowError(f"{label} includes an unknown reviewer case")
        package_sha = case["source_package_sha256"]
        if packet_case["source_package_sha256"] != package_sha:
            raise ReviewerWorkflowError(f"{label} package hash binding changed")
        if package_sha in forms_by_package:
            raise ReviewerWorkflowError(f"{label} repeats a source package hash")
        form, form_raw = _strict_json(root / case["form_path"], f"{label} form")
        if hashlib.sha256(form_raw).hexdigest() != case["form_sha256"]:
            raise ReviewerWorkflowError(f"{label} form hash does not match")
        try:
            validate_contract("reviewer_form_independent_completed.schema.json", form)
        except ContractError as exc:
            raise ReviewerWorkflowError(f"{label} completed form is invalid: {exc}") from exc
        if any(row["reviewer_case_id"] != reviewer_case_id for row in form):
            raise ReviewerWorkflowError(f"{label} form case binding changed")
        _privacy_check(form, f"{label} form")
        forms_by_package[package_sha] = form
        reviewer_case_by_package[package_sha] = reviewer_case_id
    if set(packet_cases) != {
        case["reviewer_case_id"] for case in submission["cases"]
    }:
        raise ReviewerWorkflowError(f"{label} does not cover every packet case")
    return _LockedSubmission(
        root=root,
        packet_manifest=packet_manifest,
        submission=submission,
        forms_by_package=forms_by_package,
        reviewer_case_by_package=reviewer_case_by_package,
        submission_sha256=hashlib.sha256(submission_raw).hexdigest(),
    )


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _case_presence(rows: Sequence[Mapping[str, Any]]) -> str:
    values = {row["presence"] for row in rows}
    if "present" in values:
        return "present"
    if "insufficient_materials" in values:
        return "insufficient_materials"
    return "absent"


def _reviewable_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["presence"] != "absent"]


def _location_text(row: Mapping[str, Any]) -> str:
    locations = row.get("locations")
    if isinstance(locations, list) and locations:
        return "; ".join(str(item) for item in locations)
    issue_family = row.get("issue_family")
    return f"materials completeness: {issue_family or 'unspecified'}"


def _as_label(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observation_id": row["reviewer_observation_id"],
        "role": (
            "coverage_gap"
            if row["presence"] == "insufficient_materials"
            else "recall_label"
        ),
        "issue_family": row["issue_family"],
        "location": {"text": _location_text(row)},
        "risk_range": row["risk_range"],
    }


def _as_observation(row: Mapping[str, Any]) -> dict[str, Any]:
    risk_range = row["risk_range"]
    return {
        "observation_id": row["reviewer_observation_id"],
        "issue_family": row["issue_family"],
        "location": {"text": _location_text(row)},
        "risk_level": risk_range[0],
    }


def _risk_ranges_overlap(left: Sequence[str], right: Sequence[str]) -> bool:
    left_low, left_high = (_RISK_LEVELS[item] for item in left)
    right_low, right_high = (_RISK_LEVELS[item] for item in right)
    return max(left_low, right_low) <= min(left_high, right_high)


def _fraction(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else round(numerator / denominator, 6),
    }


def _cohen_kappa(pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    if not pairs:
        return {
            "status": "undefined_no_units",
            "value": None,
            "observed_agreement": None,
            "expected_agreement": None,
        }
    total = len(pairs)
    observed = sum(left == right for left, right in pairs) / total
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    categories = set(left_counts) | set(right_counts)
    expected = sum(
        (left_counts[category] / total) * (right_counts[category] / total)
        for category in categories
    )
    if math.isclose(expected, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return {
            "status": "undefined_constant_marginals",
            "value": None,
            "observed_agreement": round(observed, 6),
            "expected_agreement": round(expected, 6),
        }
    value = (observed - expected) / (1.0 - expected)
    return {
        "status": "defined",
        "value": round(max(-1.0, min(1.0, value)), 6),
        "observed_agreement": round(observed, 6),
        "expected_agreement": round(expected, 6),
    }


def _stable_union(left: Sequence[str], right: Sequence[str]) -> list[str]:
    values: dict[str, str] = {}
    for item in [*left, *right]:
        normalized = _normalized_text(item)
        if normalized and normalized not in values:
            values[normalized] = item.strip()
    return [values[key] for key in sorted(values)]


def _merged_text(left: str, right: str) -> str:
    left_text = left.strip()
    right_text = right.strip()
    if _normalized_text(left_text) == _normalized_text(right_text):
        return left_text
    return f"{left_text}\n\nIndependent corroborating wording: {right_text}"


def _merge_rows(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    final_index: int,
) -> dict[str, Any]:
    lower = max(_RISK_LEVELS[left["risk_range"][0]], _RISK_LEVELS[right["risk_range"][0]])
    upper = min(_RISK_LEVELS[left["risk_range"][1]], _RISK_LEVELS[right["risk_range"][1]])
    return {
        "final_observation_id": f"FINAL-O{final_index:03d}",
        "source_reviewer_observation_ids": sorted(
            [
                left["reviewer_observation_id"],
                right["reviewer_observation_id"],
            ]
        ),
        "presence": left["presence"],
        "issue_family": left["issue_family"],
        "comment_class": left["comment_class"],
        "risk_range": [f"R{lower}", f"R{upper}"],
        "locations": _stable_union(left["locations"], right["locations"]),
        "expected_fact": _merged_text(left["observation"], right["observation"]),
        "minimum_review_comment": _merged_text(
            left["minimum_review_comment"], right["minimum_review_comment"]
        ),
        "scientific_relevance": _merged_text(
            left["scientific_relevance"], right["scientific_relevance"]
        ),
        "benign_explanations": _stable_union(
            left["benign_explanations"], right["benign_explanations"]
        ),
        "required_materials": _stable_union(
            left["required_materials"], right["required_materials"]
        ),
        "recommended_action": _merged_text(
            left["recommended_action"], right["recommended_action"]
        ),
    }


def _comparison_case_id(review_round_id: str, package_sha: str) -> str:
    digest = hashlib.sha256(
        review_round_id.encode("ascii") + bytes.fromhex(package_sha)
    ).hexdigest()[:32].upper()
    return f"BRIA-C-{digest}"


def _match_reviewer_rows(
    reviewer_a_rows: list[dict[str, Any]],
    reviewer_b_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str], bool]:
    left = _reviewable_rows(reviewer_a_rows)
    right = _reviewable_rows(reviewer_b_rows)
    if not left and not right:
        return [], [], [], False
    result = match_labels(
        [_as_label(row) for row in left],
        [_as_observation(row) for row in right],
        roles=("recall_label", "coverage_gap"),
        require_location=False,
    )
    left_by_id = {row["reviewer_observation_id"]: row for row in left}
    right_by_id = {row["reviewer_observation_id"]: row for row in right}
    matches: list[dict[str, Any]] = []
    for item in result.matches:
        left_row = left_by_id[item.label_id]
        right_row = right_by_id[item.observation_id]
        matches.append(
            {
                "reviewer_a_observation_id": item.label_id,
                "reviewer_b_observation_id": item.observation_id,
                "issue_family_agreement": (
                    _normalized_text(left_row["issue_family"])
                    == _normalized_text(right_row["issue_family"])
                ),
                "comment_class_agreement": (
                    left_row["comment_class"] == right_row["comment_class"]
                ),
                "location_agreement": bool(
                    item.compatibility.location_compatible
                ),
                "risk_range_agreement": _risk_ranges_overlap(
                    left_row["risk_range"], right_row["risk_range"]
                ),
            }
        )
    return (
        matches,
        list(result.unmatched_label_ids),
        list(result.unmatched_observation_ids),
        result.assignment_ambiguous,
    )


def compare_reviewer_submissions(
    submission_a_dir: Path | str,
    submission_b_dir: Path | str,
    output_dir: Path | str,
    *,
    compared_at: str,
) -> dict[str, Any]:
    """Compare two immutable submissions without loading mappings or labels."""

    reviewer_a = _load_locked_submission(submission_a_dir, "reviewer A submission")
    reviewer_b = _load_locked_submission(submission_b_dir, "reviewer B submission")
    target, parent_identity = _canonical_absent_target(output_dir, "comparison output")
    if reviewer_a.submission["reviewer_id"] == reviewer_b.submission["reviewer_id"]:
        raise ReviewerWorkflowError("Independent submissions require distinct reviewer IDs")
    if reviewer_a.submission["review_round_id"] != reviewer_b.submission["review_round_id"]:
        raise ReviewerWorkflowError("Independent submissions belong to different review rounds")
    package_hashes = set(reviewer_a.forms_by_package)
    if package_hashes != set(reviewer_b.forms_by_package):
        raise ReviewerWorkflowError("Independent submissions cover different package sets")

    presence_pairs: list[tuple[str, str]] = []
    comment_pairs: list[tuple[str, str]] = []
    comment_numerator = 0
    comment_denominator = 0
    location_numerator = 0
    location_denominator = 0
    risk_numerator = 0
    risk_denominator = 0
    cases: list[dict[str, Any]] = []
    round_id = reviewer_a.submission["review_round_id"]

    for package_sha in sorted(package_hashes):
        rows_a = reviewer_a.forms_by_package[package_sha]
        rows_b = reviewer_b.forms_by_package[package_sha]
        presence_a = _case_presence(rows_a)
        presence_b = _case_presence(rows_b)
        presence_pairs.append((presence_a, presence_b))
        matches, unmatched_a, unmatched_b, assignment_ambiguous = _match_reviewer_rows(
            rows_a, rows_b
        )
        rows_a_by_id = {
            row["reviewer_observation_id"]: row for row in _reviewable_rows(rows_a)
        }
        rows_b_by_id = {
            row["reviewer_observation_id"]: row for row in _reviewable_rows(rows_b)
        }
        for match in matches:
            left_row = rows_a_by_id[match["reviewer_a_observation_id"]]
            right_row = rows_b_by_id[match["reviewer_b_observation_id"]]
            comment_pairs.append(
                (left_row["comment_class"], right_row["comment_class"])
            )
            comment_denominator += 1
            comment_numerator += int(match["comment_class_agreement"])
            location_denominator += 1
            location_numerator += int(match["location_agreement"])
            risk_denominator += 1
            risk_numerator += int(match["risk_range_agreement"])
        for observation_id in unmatched_a:
            comment_pairs.append((rows_a_by_id[observation_id]["comment_class"], "not_mentioned"))
            comment_denominator += 1
            location_denominator += 1
            risk_denominator += 1
        for observation_id in unmatched_b:
            comment_pairs.append(("not_mentioned", rows_b_by_id[observation_id]["comment_class"]))
            comment_denominator += 1
            location_denominator += 1
            risk_denominator += 1

        reasons: list[str] = []
        if presence_a != presence_b:
            reasons.append("case_presence_disagreement")
        if assignment_ambiguous:
            reasons.append("comment_assignment_ambiguous")
        if unmatched_a or unmatched_b:
            reasons.append("unmatched_review_comment")
        if any(not item["issue_family_agreement"] for item in matches):
            reasons.append("issue_family_disagreement")
        if any(not item["comment_class_agreement"] for item in matches):
            reasons.append("comment_class_disagreement")
        if any(not item["location_agreement"] for item in matches):
            reasons.append("location_disagreement")
        if any(not item["risk_range_agreement"] for item in matches):
            reasons.append("risk_range_disagreement")

        consensus_rows: list[dict[str, Any]] = []
        if not reasons and presence_a != "absent":
            for index, match in enumerate(matches, start=1):
                left_row = rows_a_by_id[match["reviewer_a_observation_id"]]
                right_row = rows_b_by_id[match["reviewer_b_observation_id"]]
                if left_row["presence"] != right_row["presence"]:
                    reasons.append("observation_presence_disagreement")
                    consensus_rows = []
                    break
                consensus_rows.append(_merge_rows(left_row, right_row, index))

        case_status = "consensus" if not reasons else "disagreement"
        cases.append(
            {
                "comparison_case_id": _comparison_case_id(round_id, package_sha),
                "source_package_sha256": package_sha,
                "status": case_status,
                "reviewer_a_case_id": reviewer_a.reviewer_case_by_package[package_sha],
                "reviewer_b_case_id": reviewer_b.reviewer_case_by_package[package_sha],
                "reviewer_a_presence": presence_a,
                "reviewer_b_presence": presence_b,
                "reviewer_a_rows": rows_a,
                "reviewer_b_rows": rows_b,
                "matches": matches,
                "consensus_presence": presence_a if case_status == "consensus" else None,
                "consensus_rows": consensus_rows if case_status == "consensus" else [],
                "disagreement_reasons": sorted(set(reasons)),
            }
        )

    agreement = {
        "presence": _fraction(
            sum(left == right for left, right in presence_pairs), len(presence_pairs)
        ),
        "presence_kappa": _cohen_kappa(presence_pairs),
        "comment_class": _fraction(comment_numerator, comment_denominator),
        "comment_class_kappa": _cohen_kappa(comment_pairs),
        "location": _fraction(location_numerator, location_denominator),
        "risk_range": _fraction(risk_numerator, risk_denominator),
    }
    comparison = {
        "schema_version": SCHEMA_VERSION,
        "packet_scope": INDEPENDENT_BLINDED_SCOPE,
        "review_round_id": round_id,
        "compared_at": compared_at,
        "submissions": [
            {
                "slot": "a",
                "reviewer_id": reviewer_a.submission["reviewer_id"],
                "submission_manifest_sha256": reviewer_a.submission_sha256,
                "packet_manifest_sha256": reviewer_a.submission[
                    "packet_manifest_sha256"
                ],
            },
            {
                "slot": "b",
                "reviewer_id": reviewer_b.submission["reviewer_id"],
                "submission_manifest_sha256": reviewer_b.submission_sha256,
                "packet_manifest_sha256": reviewer_b.submission[
                    "packet_manifest_sha256"
                ],
            },
        ],
        "agreement": agreement,
        "cases": cases,
    }
    try:
        validate_contract("reviewer_comparison.schema.json", comparison)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"Reviewer comparison contract is invalid: {exc}") from exc
    comparison_bytes = _serialize_json(comparison)
    adjudication_template = {
        "schema_version": SCHEMA_VERSION,
        "status": "template",
        "review_round_id": round_id,
        "comparison_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "adjudicator_id": None,
        "adjudicated_at": None,
        "cases": [
            {
                "comparison_case_id": case["comparison_case_id"],
                "source_package_sha256": case["source_package_sha256"],
                "disagreement_reasons": case["disagreement_reasons"],
                "resolution": None,
                "final_presence": None,
                "final_rows": [],
                "rationale": "",
            }
            for case in cases
            if case["status"] == "disagreement"
        ],
    }
    try:
        validate_contract("reviewer_adjudication.schema.json", adjudication_template)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"Adjudication template contract is invalid: {exc}") from exc

    def build(stage: Path) -> None:
        _write_bytes(stage / "comparison.json", comparison_bytes, 0o600)
        _write_bytes(
            stage / "adjudication_template.json",
            _serialize_json(adjudication_template),
            0o600,
        )

    _publish_private_directory(target, parent_identity, build)
    return comparison


_FINAL_ROW_KEYS = frozenset(
    {
        "final_observation_id",
        "source_reviewer_observation_ids",
        "presence",
        "issue_family",
        "comment_class",
        "risk_range",
        "locations",
        "expected_fact",
        "minimum_review_comment",
        "scientific_relevance",
        "benign_explanations",
        "required_materials",
        "recommended_action",
    }
)


def _validate_final_rows(rows: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ReviewerWorkflowError(f"{label} final_rows must be a list")
    identifiers: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != _FINAL_ROW_KEYS:
            raise ReviewerWorkflowError(f"{label} final row {index + 1} has invalid fields")
        identifier = row["final_observation_id"]
        if not isinstance(identifier, str) or re.fullmatch(r"FINAL-O[0-9]{3,}", identifier) is None:
            raise ReviewerWorkflowError(f"{label} final observation ID is invalid")
        if identifier in identifiers:
            raise ReviewerWorkflowError(f"{label} repeats a final observation ID")
        identifiers.add(identifier)
        source_ids = row["source_reviewer_observation_ids"]
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or len(set(source_ids)) != len(source_ids)
            or any(
                not isinstance(item, str)
                or re.fullmatch(r"BRIA-R[0-9]{3,}-O[0-9]{3,}", item) is None
                for item in source_ids
            )
        ):
            raise ReviewerWorkflowError(
                f"{label} final source observation references are invalid"
            )
        presence = row["presence"]
        if presence not in {"present", "insufficient_materials"}:
            raise ReviewerWorkflowError(f"{label} final row presence is invalid")
        if row["comment_class"] not in (
            {"major", "minor"} if presence == "present" else {"materials_request"}
        ):
            raise ReviewerWorkflowError(f"{label} final comment class is inconsistent")
        risk_range = row["risk_range"]
        if (
            not isinstance(risk_range, list)
            or len(risk_range) != 2
            or any(item not in _RISK_LEVELS for item in risk_range)
            or _RISK_LEVELS[risk_range[0]] > _RISK_LEVELS[risk_range[1]]
        ):
            raise ReviewerWorkflowError(f"{label} final risk range is invalid")
        for field in (
            "issue_family",
            "expected_fact",
            "minimum_review_comment",
            "scientific_relevance",
            "recommended_action",
        ):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ReviewerWorkflowError(f"{label} final {field} is required")
        for field in ("locations", "benign_explanations", "required_materials"):
            values = row[field]
            minimum = 1
            if (
                not isinstance(values, list)
                or len(values) < minimum
                or any(not isinstance(item, str) or not item.strip() for item in values)
                or len({_normalized_text(item) for item in values}) != len(values)
            ):
                raise ReviewerWorkflowError(f"{label} final {field} is invalid")
        _privacy_check(row, f"{label} final row")
        validated.append(row)
    return validated


def _load_private_contract(
    path_value: Path | str,
    schema_name: str,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    path = Path(os.path.abspath(os.fspath(Path(path_value))))
    try:
        _reject_symlink_components(path, label)
        metadata = path.lstat()
    except OSError as exc:
        raise ReviewerWorkflowError(f"Could not inspect {label}") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        raise ReviewerWorkflowError(
            f"{label} must be a single-link regular file with mode 0600"
        )
    payload, raw = _strict_json(path, label)
    if not isinstance(payload, dict):
        raise ReviewerWorkflowError(f"{label} must contain a JSON object")
    try:
        validate_contract(schema_name, payload)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"{label} contract is invalid: {exc}") from exc
    return payload, raw


def _load_mapping(path_value: Path | str, label: str) -> tuple[dict[str, Any], bytes]:
    path = Path(os.path.abspath(os.fspath(Path(path_value))))
    try:
        _reject_symlink_components(path, label)
    except Exception as exc:
        raise ReviewerWorkflowError(f"Could not inspect {label}") from exc
    payload, raw = _strict_json(path, label)
    try:
        validate_contract("reviewer_mapping.schema.json", payload)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"{label} contract is invalid: {exc}") from exc
    try:
        _verify_mapping_file(path, raw, label)
    except Exception as exc:
        raise ReviewerWorkflowError(f"{label} is not an intact private mapping") from exc
    return payload, raw


def _mapping_by_package(
    mapping: dict[str, Any],
    submission: _LockedSubmission,
    label: str,
) -> dict[str, str]:
    if mapping["packet_manifest_sha256"] != submission.submission[
        "packet_manifest_sha256"
    ]:
        raise ReviewerWorkflowError(f"{label} does not bind the selected submission")
    packet_by_id = {
        item["reviewer_case_id"]: item
        for item in submission.packet_manifest["cases"]
    }
    result: dict[str, str] = {}
    for item in mapping["cases"]:
        packet_case = packet_by_id.get(item["reviewer_case_id"])
        if packet_case is None:
            raise ReviewerWorkflowError(f"{label} contains an unknown reviewer case")
        package_sha = item["source_package_sha256"]
        if packet_case["source_package_sha256"] != package_sha:
            raise ReviewerWorkflowError(f"{label} package binding changed")
        if package_sha in result:
            raise ReviewerWorkflowError(f"{label} repeats a package hash")
        result[package_sha] = item["source_case_id"]
    if set(result) != set(submission.forms_by_package):
        raise ReviewerWorkflowError(f"{label} does not cover the locked submission")
    return result


def _validate_adjudication(
    payload: dict[str, Any],
    comparison: dict[str, Any],
    comparison_sha256: str,
) -> tuple[str, dict[str, dict[str, Any]]]:
    _privacy_check(payload, "completed adjudication")
    if payload["status"] != "completed":
        raise ReviewerWorkflowError("Adjudication must be completed before finalization")
    if payload["review_round_id"] != comparison["review_round_id"]:
        raise ReviewerWorkflowError("Adjudication belongs to another review round")
    if payload["comparison_sha256"] != comparison_sha256:
        raise ReviewerWorkflowError("Adjudication does not bind this comparison")
    adjudicator_id = payload["adjudicator_id"]
    reviewer_ids = {item["reviewer_id"] for item in comparison["submissions"]}
    if adjudicator_id in reviewer_ids:
        raise ReviewerWorkflowError("Adjudicator must be distinct from both reviewers")
    disagreement_cases = {
        item["comparison_case_id"]: item
        for item in comparison["cases"]
        if item["status"] == "disagreement"
    }
    supplied = {item["comparison_case_id"]: item for item in payload["cases"]}
    if len(supplied) != len(payload["cases"]) or set(supplied) != set(disagreement_cases):
        raise ReviewerWorkflowError("Adjudication must cover every disagreement exactly once")
    for case_id, item in supplied.items():
        expected = disagreement_cases[case_id]
        if item["source_package_sha256"] != expected["source_package_sha256"]:
            raise ReviewerWorkflowError("Adjudication package binding changed")
        if item["disagreement_reasons"] != expected["disagreement_reasons"]:
            raise ReviewerWorkflowError("Adjudication disagreement reasons changed")
        if not item["rationale"].strip():
            raise ReviewerWorkflowError("Every adjudication requires a rationale")
        if item["resolution"] == "ambiguous":
            if item["final_presence"] is not None or item["final_rows"]:
                raise ReviewerWorkflowError("Ambiguous adjudication must not invent final rows")
            continue
        if item["resolution"] != "resolved":
            raise ReviewerWorkflowError("Each adjudication must resolve or remain ambiguous")
        presence = item["final_presence"]
        rows = _validate_final_rows(item["final_rows"], f"adjudication {case_id}")
        if presence == "absent":
            if rows:
                raise ReviewerWorkflowError("Absent adjudication must have no final rows")
        elif presence in {"present", "insufficient_materials"}:
            if not rows or _case_presence(rows) != presence:
                raise ReviewerWorkflowError("Adjudicated rows do not match final presence")
        else:
            raise ReviewerWorkflowError("Resolved adjudication requires final presence")
        available_rows = {
            row["reviewer_observation_id"]: row
            for row in [
                *expected["reviewer_a_rows"],
                *expected["reviewer_b_rows"],
            ]
        }
        for row in rows:
            source_ids = row["source_reviewer_observation_ids"]
            if any(source_id not in available_rows for source_id in source_ids):
                raise ReviewerWorkflowError(
                    "Adjudicated final row references an observation outside the locked submissions"
                )
            sources = [available_rows[source_id] for source_id in source_ids]
            reviewable_sources = [
                source for source in sources if source["presence"] != "absent"
            ]
            if not reviewable_sources:
                raise ReviewerWorkflowError(
                    "Adjudicated final row must derive from a reviewable locked observation"
                )
            if not any(
                _normalized_text(source["issue_family"])
                == _normalized_text(row["issue_family"])
                and source["presence"] == row["presence"]
                and source["comment_class"] == row["comment_class"]
                and _risk_ranges_overlap(source["risk_range"], row["risk_range"])
                for source in reviewable_sources
            ):
                raise ReviewerWorkflowError(
                    "Adjudicated final row is not category-compatible with its locked sources"
                )
            final_label = {
                "observation_id": row["final_observation_id"],
                "role": "recall_label",
                "issue_family": row["issue_family"],
                "location": {"text": "; ".join(row["locations"])},
                "risk_range": row["risk_range"],
            }
            source_observations = [
                _as_observation(source) for source in reviewable_sources
            ]
            if not match_labels(
                [final_label],
                source_observations,
                require_location=True,
            ).matches:
                raise ReviewerWorkflowError(
                    "Adjudicated final row location is not supported by its locked sources"
                )
    return adjudicator_id, supplied


def _annotation_from_final(
    source_case_id: str,
    presence: str | None,
    rows: list[dict[str, Any]],
    *,
    reviewer_ids: list[str],
    adjudicator_id: str | None,
    frozen_at: str,
    ambiguous: bool,
) -> dict[str, Any]:
    expected_observations: list[dict[str, Any]] = []
    if not ambiguous:
        for index, row in enumerate(rows, start=1):
            locations = row["locations"]
            expected_observations.append(
                {
                    "observation_id": f"{source_case_id}-independent-{index:03d}",
                    "role": (
                        "coverage_gap"
                        if row["presence"] == "insufficient_materials"
                        else "recall_label"
                    ),
                    "issue_family": row["issue_family"],
                    "location": {"text": "; ".join(locations)},
                    "risk_range": row["risk_range"],
                    "benign_explanations": row["benign_explanations"],
                    "required_materials": row["required_materials"],
                    "presence": row["presence"],
                    "expected_fact": row["expected_fact"],
                    "minimum_review_comment": row["minimum_review_comment"],
                    "comment_priority": row["comment_class"],
                    "evaluation_scope": "headline_detection",
                    "notes": row["scientific_relevance"],
                }
            )
    annotation: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "case_id": source_case_id,
        "negative_control": bool(not ambiguous and presence == "absent"),
        "review_status": "ambiguous" if ambiguous else "independent_adjudicated",
        "expected_observations": expected_observations,
        "reviewer_ids": reviewer_ids,
        "frozen_at": frozen_at,
        "notes": (
            "Independent reviewer disagreement remained unresolved."
            if ambiguous
            else "Finalized from two locked independent reviews; original forms were not modified."
        ),
    }
    if adjudicator_id is not None:
        annotation["adjudicator_id"] = adjudicator_id
    try:
        validate_contract("annotation.schema.json", annotation)
    except ContractError as exc:
        raise ReviewerWorkflowError(
            f"Final annotation for {source_case_id!r} is invalid: {exc}"
        ) from exc
    return annotation


def finalize_reviewer_labels(
    comparison_path: Path | str,
    submission_a_dir: Path | str,
    mapping_a_path: Path | str,
    submission_b_dir: Path | str,
    mapping_b_path: Path | str,
    manifest_path: Path | str,
    output_dir: Path | str,
    *,
    frozen_at: str,
    benchmark_version: str,
    adjudication_path: Path | str | None = None,
) -> dict[str, Any]:
    """Finalize private labels after two locks and any required adjudication."""

    comparison, comparison_raw = _load_private_contract(
        comparison_path,
        "reviewer_comparison.schema.json",
        "reviewer comparison",
    )
    comparison_sha = hashlib.sha256(comparison_raw).hexdigest()
    reviewer_a = _load_locked_submission(submission_a_dir, "reviewer A submission")
    reviewer_b = _load_locked_submission(submission_b_dir, "reviewer B submission")
    expected_submissions = {
        item["slot"]: item for item in comparison["submissions"]
    }
    for slot, submission in (("a", reviewer_a), ("b", reviewer_b)):
        expected = expected_submissions[slot]
        if (
            expected["reviewer_id"] != submission.submission["reviewer_id"]
            or expected["submission_manifest_sha256"] != submission.submission_sha256
            or expected["packet_manifest_sha256"]
            != submission.submission["packet_manifest_sha256"]
        ):
            raise ReviewerWorkflowError(
                f"Reviewer {slot.upper()} submission changed after comparison"
            )
    with tempfile.TemporaryDirectory(prefix="bria-review-comparison-recheck-") as temporary:
        temporary_root = Path(temporary)
        os.chmod(temporary_root, 0o700)
        recomputed = compare_reviewer_submissions(
            reviewer_a.root,
            reviewer_b.root,
            temporary_root / "comparison",
            compared_at=comparison["compared_at"],
        )
    if recomputed != comparison:
        raise ReviewerWorkflowError(
            "Reviewer comparison does not match the two locked submissions"
        )
    mapping_a, _ = _load_mapping(mapping_a_path, "reviewer A mapping")
    mapping_b, _ = _load_mapping(mapping_b_path, "reviewer B mapping")
    source_by_package_a = _mapping_by_package(mapping_a, reviewer_a, "reviewer A mapping")
    source_by_package_b = _mapping_by_package(mapping_b, reviewer_b, "reviewer B mapping")
    if source_by_package_a != source_by_package_b:
        raise ReviewerWorkflowError("Reviewer mappings do not resolve to the same source cases")
    if mapping_a["source_manifest_sha256"] != mapping_b["source_manifest_sha256"]:
        raise ReviewerWorkflowError("Reviewer mappings bind different source manifests")
    if mapping_a["selection_sha256"] != mapping_b["selection_sha256"]:
        raise ReviewerWorkflowError("Reviewer mappings bind different case selections")
    if (
        mapping_a["anonymization"]["seed_commitment_sha256"]
        == mapping_b["anonymization"]["seed_commitment_sha256"]
    ):
        raise ReviewerWorkflowError(
            "Independent reviewer packets require distinct anonymization seeds"
        )

    manifest_file = Path(manifest_path)
    manifest, manifest_raw = _load_frozen_manifest(manifest_file)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    if manifest_sha != mapping_a["source_manifest_sha256"]:
        raise ReviewerWorkflowError("Frozen source manifest does not match reviewer mappings")
    manifest_cases = {case["case_id"]: case for case in manifest["cases"]}
    for package_sha, source_case_id in source_by_package_a.items():
        case = manifest_cases.get(source_case_id)
        if case is None or case.get("expected_sha256") != package_sha:
            raise ReviewerWorkflowError("Frozen source case binding changed")
        try:
            verify_frozen_case(manifest_file.parent, case)
            _, annotation_path = resolve_case_paths(manifest_file.parent, case)
            pending, _ = _strict_json(annotation_path, "pending source annotation")
            validate_contract("annotation.schema.json", pending)
        except (RegistryError, ContractError) as exc:
            raise ReviewerWorkflowError("Frozen source case is no longer valid") from exc
        if (
            case.get("track") != "blinded_challenge"
            or case.get("split") != "test"
            or case.get("headline_eligible") is not False
            or pending.get("review_status") != "independent_pending"
            or pending.get("expected_observations") != []
        ):
            raise ReviewerWorkflowError("Source case no longer satisfies blinded eligibility")
        for mapping, label in ((mapping_a, "reviewer A"), (mapping_b, "reviewer B")):
            mapping_case = next(
                item
                for item in mapping["cases"]
                if item["source_package_sha256"] == package_sha
            )
            if mapping_case["source_annotation_sha256"] != case["annotation_sha256"]:
                raise ReviewerWorkflowError(
                    f"{label} mapping annotation hash no longer matches the source manifest"
                )

    disagreement_cases = [
        item for item in comparison["cases"] if item["status"] == "disagreement"
    ]
    adjudicator_id: str | None = None
    adjudication_sha: str | None = None
    adjudicated: dict[str, dict[str, Any]] = {}
    if disagreement_cases:
        if adjudication_path is None:
            raise ReviewerWorkflowError("Disagreements require completed adjudication")
        adjudication, adjudication_raw = _load_private_contract(
            adjudication_path,
            "reviewer_adjudication.schema.json",
            "completed adjudication",
        )
        adjudicator_id, adjudicated = _validate_adjudication(
            adjudication, comparison, comparison_sha
        )
        adjudication_sha = hashlib.sha256(adjudication_raw).hexdigest()
    elif adjudication_path is not None:
        raise ReviewerWorkflowError("Adjudication was supplied but no cases disagree")

    reviewer_ids = sorted(
        [reviewer_a.submission["reviewer_id"], reviewer_b.submission["reviewer_id"]]
    )
    annotations: dict[str, bytes] = {}
    case_records: list[dict[str, Any]] = []
    for case in comparison["cases"]:
        source_case_id = source_by_package_a[case["source_package_sha256"]]
        ambiguous = False
        if case["status"] == "consensus":
            presence = case["consensus_presence"]
            rows = _validate_final_rows(
                case["consensus_rows"], f"consensus {case['comparison_case_id']}"
            )
        else:
            resolution = adjudicated[case["comparison_case_id"]]
            ambiguous = resolution["resolution"] == "ambiguous"
            presence = resolution["final_presence"]
            rows = (
                []
                if ambiguous
                else _validate_final_rows(
                    resolution["final_rows"],
                    f"adjudication {case['comparison_case_id']}",
                )
            )
        annotation = _annotation_from_final(
            source_case_id,
            presence,
            rows,
            reviewer_ids=reviewer_ids,
            adjudicator_id=(
                adjudicator_id if case["status"] == "disagreement" else None
            ),
            frozen_at=frozen_at,
            ambiguous=ambiguous,
        )
        annotation_bytes = _serialize_json(annotation)
        filename = (
            "annotation-"
            + hashlib.sha256(source_case_id.encode("utf-8")).hexdigest()[:20]
            + ".json"
        )
        relative = f"annotations/{filename}"
        annotations[relative] = annotation_bytes
        case_records.append(
            {
                "source_case_id": source_case_id,
                "source_package_sha256": case["source_package_sha256"],
                "review_status": annotation["review_status"],
                "resolution_source": (
                    "consensus"
                    if case["status"] == "consensus"
                    else ("ambiguous" if ambiguous else "third_party_resolved")
                ),
                "annotation_path": relative,
                "annotation_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
                "eligible_for_manifest_promotion": (
                    annotation["review_status"] == "independent_adjudicated"
                ),
            }
        )

    finalization = {
        "schema_version": SCHEMA_VERSION,
        "review_round_id": comparison["review_round_id"],
        "benchmark_version": benchmark_version,
        "frozen_at": frozen_at,
        "source_manifest_sha256": manifest_sha,
        "comparison_sha256": comparison_sha,
        "submissions": [
            {
                "slot": slot,
                "submission_manifest_sha256": submission.submission_sha256,
                "packet_manifest_sha256": submission.submission[
                    "packet_manifest_sha256"
                ],
            }
            for slot, submission in (("a", reviewer_a), ("b", reviewer_b))
        ],
        "adjudication_sha256": adjudication_sha,
        "reviewer_ids": reviewer_ids,
        "adjudicator_id": adjudicator_id,
        "agreement": comparison["agreement"],
        "cases": sorted(case_records, key=lambda item: item["source_case_id"]),
    }
    try:
        validate_contract("reviewer_finalization.schema.json", finalization)
    except ContractError as exc:
        raise ReviewerWorkflowError(f"Finalization contract is invalid: {exc}") from exc
    summary = {
        "schema_version": SCHEMA_VERSION,
        "review_round_id": comparison["review_round_id"],
        "case_count": len(case_records),
        "independent_adjudicated_count": sum(
            item["review_status"] == "independent_adjudicated" for item in case_records
        ),
        "ambiguous_count": sum(
            item["review_status"] == "ambiguous" for item in case_records
        ),
        "agreement": comparison["agreement"],
        "reviewer_ids": reviewer_ids,
        "adjudicator_used": adjudicator_id is not None,
    }
    target, parent_identity = _canonical_absent_target(output_dir, "finalization output")

    def build(stage: Path) -> None:
        _make_directory(stage / "annotations", 0o700)
        for relative, data in annotations.items():
            _write_bytes(stage / relative, data, 0o600)
        _write_bytes(stage / "finalization.json", _serialize_json(finalization), 0o600)
        _write_bytes(stage / "agreement-summary.json", _serialize_json(summary), 0o600)

    _publish_private_directory(target, parent_identity, build)
    return finalization


__all__ = [
    "ReviewerWorkflowError",
    "compare_reviewer_submissions",
    "finalize_reviewer_labels",
    "lock_reviewer_submission",
]
