"""Package intake guardrails for local audit runs.

These checks are intentionally about audit scope and runtime safety, not about
the scientific content of the supplied materials.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.pipeline.common import IMAGE_EXTS, write_json
from scripts.pipeline.detectors import validate_detector


DEFAULT_MAX_PACKAGE_SIZE_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_IMAGE_FILES = 1000
DEFAULT_MAX_TOTAL_FILES = 10000
DEFAULT_SAMPLE_LIMIT = 25


@dataclass(frozen=True)
class PackageGuardrailLimits:
    max_package_size_bytes: int = DEFAULT_MAX_PACKAGE_SIZE_BYTES
    max_single_file_bytes: int = DEFAULT_MAX_SINGLE_FILE_BYTES
    max_image_files: int = DEFAULT_MAX_IMAGE_FILES
    max_total_files: int = DEFAULT_MAX_TOTAL_FILES
    sample_limit: int = DEFAULT_SAMPLE_LIMIT


def relpath(package: Path, path: Path) -> str:
    try:
        return path.relative_to(package).as_posix()
    except ValueError:
        return path.name


def scan_package_guardrails(
    package: Path,
    limits: PackageGuardrailLimits = PackageGuardrailLimits(),
) -> dict[str, Any]:
    """Scan package shape without following symlinks or reading file contents."""

    total_size = 0
    file_count = 0
    image_file_count = 0
    oversized_files: list[dict[str, Any]] = []
    symlink_entries: list[str] = []
    unreadable_entries: list[dict[str, str]] = []

    pending = [package]
    while pending:
        directory = pending.pop(0)
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            unreadable_entries.append({
                "path": relpath(package, directory),
                "error": exc.__class__.__name__,
            })
            continue

        for entry in entries:
            rel = relpath(package, entry)
            if entry.is_symlink():
                if len(symlink_entries) < limits.sample_limit:
                    symlink_entries.append(rel)
                continue
            if entry.is_dir():
                pending.append(entry)
                continue
            if not entry.is_file():
                continue
            try:
                size = entry.stat().st_size
            except OSError as exc:
                unreadable_entries.append({
                    "path": rel,
                    "error": exc.__class__.__name__,
                })
                continue

            file_count += 1
            total_size += size
            if entry.suffix.lower() in IMAGE_EXTS:
                image_file_count += 1
            if size > limits.max_single_file_bytes and len(oversized_files) < limits.sample_limit:
                oversized_files.append({
                    "path": rel,
                    "size_bytes": size,
                    "limit_bytes": limits.max_single_file_bytes,
                })

    limit_records: list[dict[str, Any]] = []
    if total_size > limits.max_package_size_bytes:
        limit_records.append({
            "limit_type": "max_package_size_bytes",
            "observed": total_size,
            "limit": limits.max_package_size_bytes,
        })
    if file_count > limits.max_total_files:
        limit_records.append({
            "limit_type": "max_total_files",
            "observed": file_count,
            "limit": limits.max_total_files,
        })
    if image_file_count > limits.max_image_files:
        limit_records.append({
            "limit_type": "max_image_files",
            "observed": image_file_count,
            "limit": limits.max_image_files,
        })
    if oversized_files:
        limit_records.append({
            "limit_type": "max_single_file_bytes",
            "observed": len(oversized_files),
            "limit": limits.max_single_file_bytes,
            "sample_files": oversized_files,
        })

    image_screening_blocked = any(
        record["limit_type"] in {
            "max_package_size_bytes",
            "max_image_files",
            "max_total_files",
            "max_single_file_bytes",
        }
        for record in limit_records
    )
    has_findings = bool(symlink_entries or unreadable_entries or limit_records)
    return {
        "schema_version": "0.1.0",
        "package": str(package),
        "limits": asdict(limits),
        "file_count": file_count,
        "total_size_bytes": total_size,
        "image_file_count": image_file_count,
        "symlink_entries": symlink_entries,
        "symlink_count_reported": len(symlink_entries),
        "unreadable_entries": unreadable_entries,
        "limit_records": limit_records,
        "has_findings": has_findings,
        "image_screening_blocked": image_screening_blocked,
    }


def write_package_guardrail_candidates(package: Path, output_dir: Path, guardrails: dict[str, Any]) -> Path | None:
    if not guardrails.get("has_findings"):
        return None

    records: list[dict[str, Any]] = []
    for path in guardrails.get("symlink_entries", []) or []:
        records.append({
            "guardrail_type": "symlink_skipped",
            "path": path,
            "message": "Symlink entries are not followed or hashed by the audit pipeline.",
        })
    for item in guardrails.get("unreadable_entries", []) or []:
        records.append({
            "guardrail_type": "unreadable_package_entry",
            **item,
        })
    for item in guardrails.get("limit_records", []) or []:
        records.append({
            "guardrail_type": "resource_limit_exceeded",
            **item,
        })

    locations = [str(package), *[str(path) for path in guardrails.get("symlink_entries", []) or []]]
    payload = {
        "detector_name": "audit.package_guardrail",
        "detector_version": "0.1.0",
        "input": {
            "package": str(package),
            "file_count": guardrails.get("file_count", 0),
            "total_size_bytes": guardrails.get("total_size_bytes", 0),
            "image_file_count": guardrails.get("image_file_count", 0),
            "limits": guardrails.get("limits", {}),
            "image_screening_blocked": bool(guardrails.get("image_screening_blocked")),
        },
        "candidates": [
            {
                "candidate_id": "AUDIT-GUARDRAIL-0001",
                "detector": "audit.package_guardrail",
                "candidate_type": "audit_coverage_gap",
                "finding_type": "package_intake_guardrail",
                "locations": locations[: DEFAULT_SAMPLE_LIMIT + 1],
                "evidence": {
                    "message": (
                        "Package intake guardrails found entries that were skipped or resource limits that affect "
                        "automated screening scope. This is an audit completeness issue, not a content finding."
                    ),
                    "records": records,
                    "symlink_entries": guardrails.get("symlink_entries", []),
                    "unreadable_entries": guardrails.get("unreadable_entries", []),
                    "limit_records": guardrails.get("limit_records", []),
                    "image_screening_blocked": bool(guardrails.get("image_screening_blocked")),
                },
                "evidence_strength": "weak_signal",
                "risk_suggestion": "R1_max",
                "risk_cap_tags": ["audit_coverage_gap", "completeness_gap"],
                "benign_explanations": [
                    "The package may include local convenience symlinks or oversized files that are valid records but unsuitable for automatic intake.",
                    "A smaller exported audit package may contain the same materials without symlinks or runtime-heavy files.",
                ],
                "required_materials": [
                    "regular copied files rather than symlinks",
                    "a narrower package or supported exports for oversized/runtime-heavy materials",
                    "manual confirmation of any skipped entries",
                ],
                "recommended_action": (
                    "Replace symlinks with copied files and split or export very large packages before treating automated coverage as complete."
                ),
                "requires_contextual_calibration": True,
            }
        ],
        "errors": [],
    }
    output = output_dir / "package_guardrail_candidates.json"
    write_json(output, payload)
    validate_detector(output)
    return output
