"""Deterministic, leakage-checked BRIA-Bench reviewer packet export."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from PIL import ExifTags, Image

from .contracts import ContractError, validate_contract
from .hashing import HashingError, hash_tree
from .registry import (
    RegistryError,
    load_manifest,
    resolve_case_paths,
    verify_frozen_case,
)


SCHEMA_VERSION = "1.0.0"
PACKET_SCOPE = "workflow_demo_only"
ANONYMIZATION_ALGORITHM = "hmac-sha256-ranked-permutation-v1"
_HMAC_CONTEXT = b"BRIA-BENCH/REVIEWER-PACKET/1\0"
_LICENSE_ALLOWLIST = frozenset({"MIT", "CC0-1.0"})
_SEED_PATTERN = re.compile(rb"^[a-f0-9]{64}$")
_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_TOKEN_CHARS = rb"A-Za-z0-9._-"
_TOKEN_TEXT_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)
_ENCODED_TEXT_ENCODINGS = (
    ("utf-8", 1),
    ("utf-16-le", 2),
    ("utf-16-be", 2),
    ("utf-32-le", 4),
    ("utf-32-be", 4),
)
_ENCODED_LOCAL_PATH_MARKERS = frozenset(
    {
        "/Users/",
        "/home/",
        "/private/",
        "/root/",
        "/tmp/",
        "/var/folders/",
        "/Volumes/",
        "/mnt/",
        "C:\\Users\\",
        "file:///Users/",
        "file:///home/",
        "file:///private/",
        "file:///root/",
        "file:///tmp/",
        "file:///var/folders/",
        "file:///Volumes/",
        "file:///mnt/",
    }
)
_CHUNK_SIZE = 1024 * 1024
_MAX_ARCHIVE_DEPTH = 4
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_MAX_EMBEDDED_TEXT_BYTES = 16 * 1024 * 1024
_MAX_PDF_PAGES = 10_000
_MAX_PDF_PREAMBLE_BYTES = 1024
_MAX_PDF_TRAILER_SCAN_BYTES = 4096
_PDF_HEADER_PATTERN = re.compile(
    rb"%PDF-(?:1\.[0-9]|2\.0)(?=[\x00\x09\x0a\x0c\x0d\x20])"
)
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(
    {
        errno.EINVAL,
        errno.ENOSYS,
        errno.ENOTSUP,
        getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
    }
)

_SENSITIVE_MARKERS = frozenset(
    {
        "adjudicator_id",
        "audit.coverage",
        "audit.detector_failure",
        "audit.format_coverage",
        "audit.intake_coverage",
        "audit.package_guardrail",
        "audit_json_summary",
        "case_type_hidden",
        "channel_metadata_consistency",
        "default_max",
        "detector_caps",
        "detector_name",
        "detector_output",
        "detector_registry",
        "detector_version",
        "evaluation_scope",
        "evidence_should_include",
        "expected_behavior",
        "expected_observations",
        "expected_risk_range",
        "external_literature_search",
        "finding_type",
        "forbidden_outputs",
        "global_near_duplicate",
        "headline_detection",
        "issue_family",
        "keypoint_geometric_match",
        "legacy_regression_contract",
        "local_patch_reuse",
        "locations_should_include",
        "mandatory_fields_for_r3_plus",
        "manifest_conflict",
        "max_overall_risk",
        "min_overall_risk",
        "misconduct_verdict_allowed",
        "missing_source_data_max",
        "mode_caps",
        "negative_control",
        "normalized_observation",
        "overall_risk",
        "pseudoreplication_screen",
        "required_findings",
        "required_materials_should_include",
        "reviewer_ids",
        "r4_requirements",
        "review_status",
        "risk_cap_tags",
        "risk_caps",
        "risk_range",
        "risk_rules",
        "source_annotation_path",
        "source_label_path",
        "source_label_sha256",
        "splice_forensics_triage",
        "text_overlap_screen",
        "unless_r4_requirement",
    }
)
_MAPPING_ONLY_MARKERS = frozenset(
    {
        "packet_manifest_sha256",
        "seed_commitment_sha256",
        "selection_sha256",
        "source_annotation_sha256",
        "source_case_id",
        "source_manifest_sha256",
    }
)
_EXPECTED_LABEL_MARKERS = frozenset({"expected_label", "expected_labels"})
_MAPPING_ARTIFACT_MARKERS = frozenset({"mapping_output", "reviewer_mapping"})
_PROTECTED_TOKEN_MARKERS = (
    _SENSITIVE_MARKERS
    | _MAPPING_ONLY_MARKERS
    | _EXPECTED_LABEL_MARKERS
    | _MAPPING_ARTIFACT_MARKERS
)
_PROHIBITED_FILE_NAMES = frozenset(
    {
        "annotation.json",
        "annotations.json",
        "audit_json_summary.json",
        "benchmark_manifest.json",
        "benchmark_manifest.source.json",
        "coverage.json",
        "detector_registry.yaml",
        "manifest.json",
        "mapping.json",
        "metrics.json",
        "normalized_observation.json",
        "packet_manifest.json",
        "pipeline_summary.json",
        "reviewer_mapping.json",
        "risk_rules.yaml",
        "run_result.json",
        "seed",
        "seed.txt",
        "source_manifest.json",
    }
)
_PROHIBITED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".git",
        "__pycache__",
        "annotations",
        "cache",
        "detector_output",
        "detector_outputs",
        "ground_truth",
        "logs",
        "mappings",
        "previous_answers",
        "rules",
    }
)
_IDENTITY_METADATA_KEYS = frozenset(
    {
        "artist",
        "author",
        "cameraownername",
        "company",
        "copyright",
        "creator",
        "lastmodifiedby",
        "manager",
        "owner",
        "username",
        "xpauthor",
    }
)
_IMAGE_IDENTITY_KEYS = _IDENTITY_METADATA_KEYS | frozenset(
    {"email", "gpsinfo", "hostcomputer"}
)

_EMAIL_PATTERN = re.compile(
    r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])"
)
_LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:"
    r"(?<![A-Za-z0-9:/])/(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/[^\s\"'<>]+"
    r"|(?<![A-Za-z0-9])(?:[A-Z]:\\Users\\|\\\\[^\\\s]+\\)[^\s\"'<>]+"
    r"|file:///(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/[^\s\"'<>]+"
    r")"
)
_IDENTITY_FIELD_PATTERN = re.compile(
    r"(?i)(?:[\"']?(?:author|creator|lastmodifiedby|reviewer_id|reviewer_identity|"
    r"username|user_name|login|account)[\"']?)\s*[:=]\s*[\"']?([^\s\"'<>,}]+)"
)
_IDENTITY_XML_PATTERN = re.compile(
    r"(?is)<(?:[A-Za-z0-9_.-]+:)?(?:creator|lastModifiedBy|company|manager|author)>"
    r"\s*[^<\s][^<]*</"
)
_CREDENTIAL_PATTERN = re.compile(
    r"(?im)^\s*(?:password|passwd|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|"
    r"auth[_-]?token|bearer[_-]?token)\s*[:=]\s*\S+"
)
_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|"
    r"-----BEGIN OPENSSH PRIVATE KEY-----"
)
_CLOUD_CREDENTIAL_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"
)


class ReviewerPacketError(ValueError):
    """Raised when a reviewer packet cannot be exported without leakage or ambiguity."""


@dataclass(frozen=True)
class _Placement:
    output: Path
    mapping: Path
    output_parent_identity: tuple[int, int]
    mapping_parent_identity: tuple[int, int]


@dataclass(frozen=True)
class _SourceCase:
    reviewer_case_id: str
    normalized_case_id: str
    case: dict[str, Any]
    package: Path
    annotation: Path
    annotation_schema_version: str
    inventory: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _EncodedTokenPattern:
    encoding: str
    unit_width: int
    pattern: re.Pattern[bytes]


@dataclass(frozen=True)
class _ScanPolicy:
    identifiers: tuple[str, ...]
    paths: tuple[str, ...]
    forbidden_bytes: tuple[bytes, ...]
    encoded_identifier_patterns: tuple[_EncodedTokenPattern, ...]
    encoded_sensitive_patterns: tuple[_EncodedTokenPattern, ...]
    encoded_forbidden_patterns: tuple[re.Pattern[bytes], ...]


def _as_path(value: Path | str, label: str) -> Path:
    try:
        return Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise ReviewerPacketError(f"Invalid {label}: {value!r}") from exc


def _lexists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not inspect output target: {path}") from exc
    return True


def _is_standard_macos_alias(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    aliases = {
        Path("/etc"): Path("/private/etc"),
        Path("/tmp"): Path("/private/tmp"),
        Path("/var"): Path("/private/var"),
    }
    expected = aliases.get(path)
    if expected is None:
        return False
    try:
        return path.resolve(strict=True) == expected
    except (OSError, RuntimeError, ValueError):
        return False


def _reject_symlink_components(path: Path, label: str) -> None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            entry = current.lstat()
        except FileNotFoundError:
            break
        except (OSError, ValueError) as exc:
            raise ReviewerPacketError(
                f"Could not inspect {label} component: {current}"
            ) from exc
        if stat.S_ISLNK(entry.st_mode) and not _is_standard_macos_alias(current):
            raise ReviewerPacketError(
                f"{label} must not use a symlinked component: {current}"
            )


def _canonical_absent_target(
    value: Path | str, label: str
) -> tuple[Path, tuple[int, int]]:
    lexical = _as_path(value, label)
    if not lexical.name or lexical.name in {".", ".."}:
        raise ReviewerPacketError(f"{label} must name a new target")
    if any(part == ".." for part in lexical.parts):
        raise ReviewerPacketError(f"{label} must not contain '..'")
    absolute = Path(os.path.abspath(os.fspath(lexical)))
    _reject_symlink_components(absolute, label)
    try:
        parent = absolute.parent.resolve(strict=True)
        parent_stat = parent.stat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReviewerPacketError(
            f"{label} parent must be an existing directory"
        ) from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise ReviewerPacketError(f"{label} parent must be an existing directory")
    target = parent / absolute.name
    if _lexists(target):
        raise ReviewerPacketError(
            f"{label} already exists and will not be overwritten: {target}"
        )
    return target, (parent_stat.st_dev, parent_stat.st_ino)


def _resolve_placement(
    output_dir: Path | str, mapping_output: Path | str
) -> _Placement:
    output, output_parent_identity = _canonical_absent_target(
        output_dir, "packet output"
    )
    mapping, mapping_parent_identity = _canonical_absent_target(
        mapping_output, "mapping output"
    )
    try:
        overlaps = (
            output == mapping
            or mapping.is_relative_to(output)
            or output.is_relative_to(mapping)
        )
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(
            "Could not compare packet and mapping placement"
        ) from exc
    if overlaps:
        raise ReviewerPacketError(
            "Mapping output must be outside and must not be an ancestor of packet output"
        )
    return _Placement(
        output,
        mapping,
        output_parent_identity,
        mapping_parent_identity,
    )


def _parent_identity(path: Path, label: str) -> tuple[int, int]:
    _reject_symlink_components(path.parent, label)
    try:
        resolved = path.parent.resolve(strict=True)
        value = resolved.stat()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not recheck {label} parent") from exc
    if resolved != path.parent:
        raise ReviewerPacketError(f"{label} parent changed after canonical resolution")
    return value.st_dev, value.st_ino


def _recheck_before_mapping_publish(placement: _Placement) -> None:
    if (
        _parent_identity(placement.output, "packet output")
        != placement.output_parent_identity
    ):
        raise ReviewerPacketError("Packet output parent changed before publication")
    if (
        _parent_identity(placement.mapping, "mapping output")
        != placement.mapping_parent_identity
    ):
        raise ReviewerPacketError("Mapping output parent changed before publication")
    if _lexists(placement.output) or _lexists(placement.mapping):
        raise ReviewerPacketError(
            "Packet or mapping target appeared before publication"
        )


def _recheck_before_packet_publish(
    placement: _Placement,
    mapping_identity: tuple[int, int],
) -> None:
    if (
        _parent_identity(placement.output, "packet output")
        != placement.output_parent_identity
    ):
        raise ReviewerPacketError("Packet output parent changed before commit")
    if (
        _parent_identity(placement.mapping, "mapping output")
        != placement.mapping_parent_identity
    ):
        raise ReviewerPacketError("Mapping output parent changed before packet commit")
    if _lexists(placement.output):
        raise ReviewerPacketError("Packet target appeared before commit")
    try:
        mapping_stat = placement.mapping.lstat()
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(
            "Published mapping disappeared before packet commit"
        ) from exc
    if (
        stat.S_ISLNK(mapping_stat.st_mode)
        or not stat.S_ISREG(mapping_stat.st_mode)
        or (mapping_stat.st_dev, mapping_stat.st_ino) != mapping_identity
        or stat.S_IMODE(mapping_stat.st_mode) != 0o600
        or mapping_stat.st_nlink != 1
    ):
        raise ReviewerPacketError("Published mapping changed before packet commit")


def _stable_metadata(value: os.stat_result) -> tuple[object, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        getattr(value, "st_mtime_ns", None),
        getattr(value, "st_ctime_ns", None),
    )


def _read_regular_bytes(path: Path, label: str) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ReviewerPacketError(f"{label} must be an actual regular file: {path}")
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _stable_metadata(
            before
        ) != _stable_metadata(opened):
            raise ReviewerPacketError(f"{label} changed while it was opened: {path}")
        chunks: list[bytes] = []
        count = 0
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
            count += len(chunk)
        after_read = os.fstat(descriptor)
        if (
            _stable_metadata(opened) != _stable_metadata(after_read)
            or count != opened.st_size
        ):
            raise ReviewerPacketError(f"{label} changed while it was read: {path}")
        after_path = path.lstat()
        if _stable_metadata(opened) != _stable_metadata(after_path):
            raise ReviewerPacketError(f"{label} path changed while it was read: {path}")
        return b"".join(chunks)
    except ReviewerPacketError:
        raise
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not read {label}: {path}") from exc
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _load_frozen_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    raw_before = _read_regular_bytes(path, "frozen manifest")
    try:
        manifest = load_manifest(path, require_frozen=True, resolve_paths=False)
    except RegistryError as exc:
        raise ReviewerPacketError(f"Frozen manifest is invalid: {exc}") from exc
    raw_after = _read_regular_bytes(path, "frozen manifest")
    if raw_before != raw_after:
        raise ReviewerPacketError("Frozen manifest changed while it was loaded")
    try:
        parsed = json.loads(raw_before.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewerPacketError(
            "Frozen manifest bytes are not strict UTF-8 JSON"
        ) from exc
    if parsed != manifest:
        raise ReviewerPacketError(
            "Frozen manifest bytes do not match the validated manifest"
        )
    return manifest, raw_before


def _read_seed(path: Path) -> tuple[bytes, bytes]:
    raw = _read_regular_bytes(path, "seed file")
    if _SEED_PATTERN.fullmatch(raw) is None:
        raise ReviewerPacketError(
            "Seed file must contain exactly 64 lowercase hexadecimal characters"
        )
    return bytes.fromhex(raw.decode("ascii")), raw


def _length_prefixed(value: str) -> bytes:
    encoded = unicodedata.normalize("NFC", value).encode("utf-8")
    if len(encoded) > 0xFFFFFFFF:
        raise ReviewerPacketError(
            "Selected case ID is too long for the packet algorithm"
        )
    return len(encoded).to_bytes(4, "big") + encoded


def _select_cases(
    manifest: dict[str, Any], case_ids: Sequence[str]
) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(case_ids, (str, bytes, bytearray)) or not isinstance(
        case_ids, Sequence
    ):
        raise ReviewerPacketError("case_ids must be an explicit nonempty sequence")
    if not case_ids:
        raise ReviewerPacketError("At least one --case selection is required")

    by_normalized_id: dict[str, dict[str, Any]] = {}
    for case in manifest["cases"]:
        source_id = case["case_id"]
        normalized = unicodedata.normalize("NFC", source_id)
        if normalized in by_normalized_id:
            raise ReviewerPacketError(
                "Frozen manifest case IDs collide after NFC normalization"
            )
        by_normalized_id[normalized] = case

    selected: dict[str, dict[str, Any]] = {}
    for value in case_ids:
        if not isinstance(value, str) or not value:
            raise ReviewerPacketError("Selected case IDs must be nonempty strings")
        normalized = unicodedata.normalize("NFC", value)
        if normalized in selected:
            raise ReviewerPacketError(f"Duplicate selected case ID: {value!r}")
        case = by_normalized_id.get(normalized)
        if case is None:
            raise ReviewerPacketError(f"Unknown selected case ID: {value!r}")
        selected[normalized] = case
    return [(case_id, selected[case_id]) for case_id in sorted(selected)]


def _rank_cases(
    selected: list[tuple[str, dict[str, Any]]],
    seed: bytes,
    manifest_digest: bytes,
) -> tuple[list[tuple[str, dict[str, Any]]], bytes]:
    selection_material = b"".join(_length_prefixed(case_id) for case_id, _ in selected)
    selection_digest = hashlib.sha256(selection_material).digest()
    ranked = sorted(
        (
            hmac.new(
                seed,
                _HMAC_CONTEXT
                + manifest_digest
                + selection_digest
                + _length_prefixed(case_id),
                hashlib.sha256,
            ).digest(),
            case_id,
            case,
        )
        for case_id, case in selected
    )
    return [(case_id, case) for _, case_id, case in ranked], selection_digest


def _safe_component(name: str, relative: str) -> None:
    if unicodedata.normalize("NFC", name) != name:
        raise ReviewerPacketError(f"Material path is not NFC-normalized: {relative}")
    if (
        not name
        or name in {".", ".."}
        or name.endswith((" ", "."))
        or ":" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ReviewerPacketError(
            f"Material path is not portable or may encode ADS: {relative}"
        )


def _check_material_path(relative: str, kind: str) -> None:
    pure = PurePosixPath(relative)
    parts = pure.parts
    for part in parts:
        _safe_component(part, relative)
    lowered = [part.casefold() for part in parts]
    if any(part in _PROHIBITED_DIRECTORY_NAMES for part in lowered[:-1]):
        raise ReviewerPacketError(
            f"Administrative material path is prohibited: {relative}"
        )
    basename = lowered[-1]
    if kind == "file":
        if (
            basename in _PROHIBITED_FILE_NAMES
            or basename.endswith(".log")
            or ".expected." in basename
            or ".label." in basename
            or "annotation" in basename
            or "audit_output" in basename
            or "detector_output" in basename
            or "expected_label" in basename
            or "expected_output" in basename
            or "ground_truth" in basename
            or "mapping" in basename
            or "previous_answer" in basename
            or "reviewer_identity" in basename
            or "reviewer_mapping" in basename
            or (
                "manifest" in basename and not basename.startswith("assembly_manifest.")
            )
            or basename.startswith("seed.")
        ):
            raise ReviewerPacketError(
                f"Administrative material file is prohibited: {relative}"
            )


def _inventory_tree(
    root: Path,
    *,
    enforce_material_policy: bool = True,
) -> tuple[tuple[str, str], ...]:
    try:
        root_stat = root.lstat()
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not inspect material root: {root}") from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ReviewerPacketError(f"Material root must be an actual directory: {root}")

    inventory: list[tuple[str, str]] = []

    def visit(directory: Path, parent: str) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except (OSError, ValueError) as exc:
            raise ReviewerPacketError(
                f"Could not enumerate material directory: {directory}"
            ) from exc
        folded: dict[str, str] = {}
        for entry in entries:
            relative = f"{parent}/{entry.name}" if parent else entry.name
            previous = folded.get(entry.name.casefold())
            if previous is not None and previous != entry.name:
                raise ReviewerPacketError(
                    f"Material names casefold-collide: {previous!r} and {entry.name!r}"
                )
            folded[entry.name.casefold()] = entry.name
            _safe_component(entry.name, relative)
            try:
                value = entry.stat(follow_symlinks=False)
            except (OSError, ValueError) as exc:
                raise ReviewerPacketError(
                    f"Could not inspect material entry: {relative}"
                ) from exc
            if stat.S_ISLNK(value.st_mode):
                raise ReviewerPacketError(
                    f"Symlink is prohibited in packet materials: {relative}"
                )
            if stat.S_ISDIR(value.st_mode):
                if enforce_material_policy:
                    _check_material_path(relative, "directory")
                inventory.append(("directory", relative))
                visit(Path(entry.path), relative)
            elif stat.S_ISREG(value.st_mode):
                if enforce_material_policy:
                    _check_material_path(relative, "file")
                inventory.append(("file", relative))
            else:
                raise ReviewerPacketError(f"Unsupported material entry: {relative}")

    visit(root, "")
    return tuple(inventory)


def _clear_xattrs(path: Path) -> None:
    if not hasattr(os, "listxattr") or not hasattr(os, "removexattr"):
        return
    try:
        attributes = os.listxattr(path, follow_symlinks=False)
        for attribute in attributes:
            os.removexattr(path, attribute, follow_symlinks=False)
    except TypeError:
        try:
            attributes = os.listxattr(path)
            for attribute in attributes:
                os.removexattr(path, attribute)
        except OSError as exc:
            raise ReviewerPacketError(
                f"Could not remove packet xattrs: {path}"
            ) from exc
    except OSError as exc:
        raise ReviewerPacketError(f"Could not remove packet xattrs: {path}") from exc


def _assert_no_xattrs(path: Path) -> None:
    if not hasattr(os, "listxattr"):
        return
    try:
        try:
            attributes = os.listxattr(path, follow_symlinks=False)
        except TypeError:
            attributes = os.listxattr(path)
    except OSError as exc:
        raise ReviewerPacketError(f"Could not inspect packet xattrs: {path}") from exc
    if attributes:
        raise ReviewerPacketError(f"Packet entry contains filesystem xattrs: {path}")


def _make_directory(path: Path, mode: int = 0o755) -> None:
    try:
        os.mkdir(path, mode)
        os.chmod(path, mode, follow_symlinks=False)
        _clear_xattrs(path)
    except ReviewerPacketError:
        raise
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not create packet directory: {path}") from exc


def _write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    descriptor = -1
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, mode)
        os.fchmod(descriptor, mode)
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short packet write")
            written += count
        os.fsync(descriptor)
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"Could not write packet file: {path}") from exc
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass
    _clear_xattrs(path)


def _copy_regular_bytes(source: Path, destination: Path, relative: str) -> None:
    data = _read_regular_bytes(source, f"material file {relative}")
    _write_bytes(destination, data)


def _copy_materials(
    source: Path,
    destination: Path,
    inventory: tuple[tuple[str, str], ...],
) -> None:
    _make_directory(destination)
    for kind, relative in inventory:
        target = destination / PurePosixPath(relative)
        if kind == "directory":
            _make_directory(target)
        else:
            _copy_regular_bytes(source / PurePosixPath(relative), target, relative)


def _serialize_json(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _blank_form(reviewer_case_id: str) -> list[dict[str, Any]]:
    return [
        {
            "reviewer_case_id": reviewer_case_id,
            "presence": None,
            "comment_class": None,
            "locations": [],
            "observation": "",
            "scientific_relevance": "",
            "benign_explanations": [],
            "required_materials": [],
            "recommended_action": "",
        }
    ]


def _annotation_version(
    annotation_path: Path,
    source_case_id: str,
    expected_sha256: str,
) -> str:
    raw = _read_regular_bytes(annotation_path, f"annotation for {source_case_id}")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ReviewerPacketError(
            f"Selected case {source_case_id!r} annotation hash mismatch: "
            f"expected {expected_sha256}, actual {actual_sha256}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
        validate_contract("annotation.schema.json", payload)
    except (UnicodeError, json.JSONDecodeError, ContractError) as exc:
        raise ReviewerPacketError(
            f"Selected case {source_case_id!r} has an invalid annotation contract"
        ) from exc
    if payload.get("case_id") != source_case_id:
        raise ReviewerPacketError(
            f"Selected case {source_case_id!r} annotation case ID does not match"
        )
    version = payload.get("schema_version")
    if not isinstance(version, str) or _SEMANTIC_VERSION.fullmatch(version) is None:
        raise ReviewerPacketError(
            f"Selected case {source_case_id!r} annotation requires a schema_version"
        )
    return version


def _prepare_source_cases(
    manifest_root: Path,
    ranked: list[tuple[str, dict[str, Any]]],
) -> list[_SourceCase]:
    prepared: list[_SourceCase] = []
    for index, (normalized_case_id, case) in enumerate(ranked, start=1):
        source_case_id = case["case_id"]
        if case.get("redistributable") is not True:
            raise ReviewerPacketError(
                f"Selected case {source_case_id!r} is not redistributable"
            )
        if case.get("license") not in _LICENSE_ALLOWLIST:
            raise ReviewerPacketError(
                f"Selected case {source_case_id!r} has unsupported license: "
                f"{case.get('license')!r}"
            )
        try:
            verify_frozen_case(manifest_root, case)
            package, annotation = resolve_case_paths(manifest_root, case)
        except RegistryError as exc:
            raise ReviewerPacketError(
                f"Selected case {source_case_id!r} frozen hash verification failed: {exc}"
            ) from exc
        annotation_version = _annotation_version(
            annotation,
            source_case_id,
            case["annotation_sha256"],
        )
        inventory = _inventory_tree(package)
        prepared.append(
            _SourceCase(
                reviewer_case_id=f"BRIA-R{index:03d}",
                normalized_case_id=normalized_case_id,
                case=case,
                package=package,
                annotation=annotation,
                annotation_schema_version=annotation_version,
                inventory=inventory,
            )
        )
    return prepared


def _token_pattern(value: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9._-]){re.escape(value)}(?![A-Za-z0-9._-])",
        re.IGNORECASE,
    )


def _token_bytes_pattern(value: str) -> re.Pattern[bytes]:
    encoded = re.escape(value.encode("utf-8"))
    return re.compile(
        rb"(?<!["
        + _TOKEN_CHARS
        + rb"])(?:"
        + encoded
        + rb")(?!["
        + _TOKEN_CHARS
        + rb"])",
        re.IGNORECASE,
    )


def _text_marker_variants(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", value)
    bases = {value, normalized, unicodedata.normalize("NFD", normalized)}
    return tuple(
        sorted(
            {
                variant
                for base in bases
                for variant in (base, base.casefold(), base.lower(), base.upper())
            }
            - {""}
        )
    )


def _compile_literal_pattern(payloads: set[bytes]) -> re.Pattern[bytes] | None:
    if not payloads:
        return None
    alternatives = sorted(payloads, key=lambda value: (-len(value), value))
    return re.compile(b"|".join(re.escape(value) for value in alternatives))


def _compile_encoded_token_patterns(
    tokens: tuple[str, ...],
) -> tuple[_EncodedTokenPattern, ...]:
    compiled: list[_EncodedTokenPattern] = []
    for encoding, unit_width in _ENCODED_TEXT_ENCODINGS:
        payloads = {
            variant.encode(encoding, errors="strict")
            for token in tokens
            for variant in _text_marker_variants(token)
        }
        pattern = _compile_literal_pattern(payloads)
        if pattern is not None:
            compiled.append(_EncodedTokenPattern(encoding, unit_width, pattern))
    return tuple(compiled)


def _compile_encoded_forbidden_patterns(
    values: tuple[str, ...],
    *,
    include_case_variants: bool = True,
) -> tuple[re.Pattern[bytes], ...]:
    compiled: list[re.Pattern[bytes]] = []
    for encoding, _ in _ENCODED_TEXT_ENCODINGS:
        payloads: set[bytes] = set()
        for value in values:
            variants = (
                _text_marker_variants(value) if include_case_variants else (value,)
            )
            payloads.update(
                variant.encode(encoding, errors="strict")
                for variant in variants
                if variant
            )
        pattern = _compile_literal_pattern(payloads)
        if pattern is not None:
            compiled.append(pattern)
    return tuple(compiled)


def _encoded_unit_is_token_character(
    unit: bytes,
    encoding: str,
    unit_width: int,
) -> bool:
    if len(unit) != unit_width:
        return False
    try:
        character = unit.decode(encoding, errors="strict")
    except UnicodeError:
        return False
    return len(character) == 1 and character in _TOKEN_TEXT_CHARS


def _encoded_token_present(
    data: bytes,
    compiled: _EncodedTokenPattern,
) -> bool:
    position = 0
    while True:
        match = compiled.pattern.search(data, position)
        if match is None:
            return False
        before = data[match.start() - compiled.unit_width : match.start()]
        after = data[match.end() : match.end() + compiled.unit_width]
        if not _encoded_unit_is_token_character(
            before,
            compiled.encoding,
            compiled.unit_width,
        ) and not _encoded_unit_is_token_character(
            after,
            compiled.encoding,
            compiled.unit_width,
        ):
            return True
        position = match.start() + 1


def _raise_leak(label: str, category: str) -> None:
    raise ReviewerPacketError(f"Packet leakage scan found {category} in {label}")


def _scan_text(text: str, label: str, policy: _ScanPolicy) -> None:
    normalized = unicodedata.normalize("NFC", text)
    lowered = normalized.casefold()
    for identifier in policy.identifiers:
        if _token_pattern(identifier).search(normalized):
            _raise_leak(label, "an exact source identifier")
    for path in policy.paths:
        if path and path.casefold() in lowered:
            _raise_leak(label, "an exact source or private path")
    for marker in _PROTECTED_TOKEN_MARKERS:
        if _token_pattern(marker).search(normalized):
            _raise_leak(label, "a sensitive annotation, rule, or analysis identifier")
    if _EMAIL_PATTERN.search(normalized):
        _raise_leak(label, "an email address")
    if _LOCAL_PATH_PATTERN.search(normalized):
        _raise_leak(label, "a local absolute path")
    if _IDENTITY_FIELD_PATTERN.search(normalized) or _IDENTITY_XML_PATTERN.search(
        normalized
    ):
        _raise_leak(label, "reportable identity metadata")
    if (
        _CREDENTIAL_PATTERN.search(normalized)
        or _PRIVATE_KEY_PATTERN.search(normalized)
        or _CLOUD_CREDENTIAL_PATTERN.search(normalized)
    ):
        _raise_leak(label, "a private-key or credential form")


def _scan_raw_bytes(data: bytes, label: str, policy: _ScanPolicy) -> None:
    lowered = data.lower()
    for identifier in policy.identifiers:
        if _token_bytes_pattern(identifier).search(data):
            _raise_leak(label, "an exact source identifier")
    for compiled in policy.encoded_identifier_patterns:
        if _encoded_token_present(data, compiled):
            _raise_leak(label, "an exact source identifier")
    for path in policy.paths:
        encoded = path.encode("utf-8", errors="strict")
        if encoded and encoded.lower() in lowered:
            _raise_leak(label, "an exact source or private path")
    for marker in _PROTECTED_TOKEN_MARKERS:
        if _token_bytes_pattern(marker).search(data):
            _raise_leak(label, "a sensitive annotation, rule, or analysis identifier")
    for compiled in policy.encoded_sensitive_patterns:
        if _encoded_token_present(data, compiled):
            _raise_leak(label, "a sensitive encoded marker")
    for forbidden in policy.forbidden_bytes:
        if forbidden and forbidden in data:
            _raise_leak(label, "seed or external mapping bytes")
    for pattern in policy.encoded_forbidden_patterns:
        if pattern.search(data):
            _raise_leak(label, "a sensitive encoded marker")
    if b"-----begin " in lowered and b"private key-----" in lowered:
        _raise_leak(label, "a private-key or credential form")
    if re.search(
        rb"(?i)(?<![A-Z0-9_])(?:password|passwd|api[_-]?key|access[_-]?key|"
        rb"secret(?:[_-]?key)?|auth[_-]?token|bearer[_-]?token)\s*[:=]\s*\S+",
        data,
    ) or re.search(
        rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])",
        data,
    ):
        _raise_leak(label, "a private-key or credential form")
    if re.search(
        rb"(?i)(?<![A-Z0-9_])(?:author|creator|lastmodifiedby|reviewer_id|"
        rb"reviewer_identity|username|user_name|login|account)\s*[:=]\s*\S+",
        data,
    ):
        _raise_leak(label, "reportable identity metadata")
    if re.search(rb"(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", data):
        _raise_leak(label, "an email address")
    if re.search(
        rb"(?i)(?:/(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/|"
        rb"[A-Z]:\\Users\\|file:///(?:Users|home|private|root|tmp|var/folders|Volumes|mnt)/)",
        data,
    ):
        _raise_leak(label, "a local absolute path")


def _plausible_unicode_text(text: str) -> bool:
    candidate = text.rstrip("\x00")
    if not candidate:
        return False
    readable = sum(
        character.isprintable() or character in "\t\r\n" for character in candidate
    )
    if readable * 20 < len(candidate) * 19:
        return False
    return any(
        unicodedata.category(character)[0] in {"L", "M", "N", "P", "S"}
        for character in candidate
    )


def _plausible_bomless_utf16(data: bytes, encoding: str) -> str | None:
    if len(data) < 8 or len(data) % 2:
        return None
    units = len(data) // 2
    even = data[0::2]
    odd = data[1::2]
    zero_lane, text_lane = (odd, even) if encoding == "utf-16-le" else (even, odd)
    zero_count = zero_lane.count(0)
    text_zero_count = text_lane.count(0)
    has_local_zero_run = b"\x00" * 8 in zero_lane
    has_asymmetric_zero_lane = (
        zero_count >= 4
        and zero_count * 8 >= units
        and zero_count >= (text_zero_count + 1) * 4
    )
    if not has_local_zero_run and not has_asymmetric_zero_lane:
        return None
    try:
        text = data.decode(encoding, errors="strict")
    except UnicodeError:
        return None
    if not _plausible_unicode_text(text):
        return None
    return text


def _plausible_bomless_utf32(data: bytes, encoding: str) -> str | None:
    if len(data) < 16 or len(data) % 4:
        return None
    if encoding == "utf-32-le":
        upper_lane = data[2::4]
        high_lane = data[3::4]
    else:
        high_lane = data[0::4]
        upper_lane = data[1::4]
    if high_lane.count(0) != len(high_lane) or max(upper_lane, default=0) > 0x10:
        return None
    try:
        text = data.decode(encoding, errors="strict")
    except UnicodeError:
        return None
    if not _plausible_unicode_text(text):
        return None
    return text


def _decoded_text_candidates(data: bytes, label: str) -> tuple[str, ...]:
    bom_encodings = (
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xef\xbb\xbf", "utf-8"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
    )
    for bom, encoding in bom_encodings:
        if not data.startswith(bom):
            continue
        try:
            return (data[len(bom) :].decode(encoding, errors="strict"),)
        except UnicodeError as exc:
            raise ReviewerPacketError(
                f"Could not inspect BOM-tagged text in {label}"
            ) from exc

    candidates: list[str] = []
    try:
        candidates.append(data.decode("utf-8", errors="strict"))
    except UnicodeError:
        pass
    for encoding in ("utf-16-le", "utf-16-be"):
        decoded = _plausible_bomless_utf16(data, encoding)
        if decoded is not None and decoded not in candidates:
            candidates.append(decoded)
    for encoding in ("utf-32-le", "utf-32-be"):
        decoded = _plausible_bomless_utf32(data, encoding)
        if decoded is not None and decoded not in candidates:
            candidates.append(decoded)
    return tuple(candidates)


def _scan_decoded_value(text: str, label: str, policy: _ScanPolicy) -> None:
    _scan_text(text, label, policy)
    encoded = text.encode("utf-8", errors="strict")
    for forbidden in policy.forbidden_bytes:
        if forbidden and forbidden in encoded:
            _raise_leak(label, "seed or external mapping bytes")


def _scan_decoded_text(data: bytes, label: str, policy: _ScanPolicy) -> None:
    for text in _decoded_text_candidates(data, label):
        _scan_decoded_value(text, label, policy)


def _scan_exif_user_comment(
    value: bytes,
    label: str,
    policy: _ScanPolicy,
) -> None:
    prefix, body = value[:8], value[8:]
    if prefix == b"ASCII\x00\x00\x00":
        try:
            text = body.decode("ascii", errors="strict")
        except UnicodeError as exc:
            raise ReviewerPacketError(
                f"Could not inspect EXIF UserComment text in {label}"
            ) from exc
        _scan_decoded_value(text, label, policy)
        return
    if prefix == b"UNICODE\x00":
        if body.startswith((b"\xff\xfe", b"\xfe\xff")):
            _scan_decoded_text(body, label, policy)
            return
        decoded: list[str] = []
        for encoding in ("utf-16-be", "utf-16-le"):
            try:
                text = body.decode(encoding, errors="strict")
            except UnicodeError:
                continue
            if text not in decoded:
                decoded.append(text)
        if not decoded:
            raise ReviewerPacketError(
                f"Could not inspect EXIF UserComment text in {label}"
            )
        for text in decoded:
            _scan_decoded_value(text, label, policy)
        return
    if prefix == b"JIS\x00\x00\x00\x00\x00":
        for encoding in ("shift_jis", "iso2022_jp"):
            try:
                text = body.decode(encoding, errors="strict")
            except UnicodeError:
                continue
            _scan_decoded_value(text, label, policy)
            return
        raise ReviewerPacketError(f"Could not inspect EXIF UserComment text in {label}")
    if prefix == b"\x00" * 8:
        _scan_decoded_text(body, label, policy)
        return
    _scan_decoded_text(value, label, policy)


def _scan_metadata_value(
    key: str, value: object, label: str, policy: _ScanPolicy
) -> None:
    if value in (None, "", b""):
        return
    normalized_key = key.replace(" ", "").casefold()
    if normalized_key in _IMAGE_IDENTITY_KEYS:
        _raise_leak(label, "reportable identity metadata")
    if isinstance(value, bytes):
        _scan_raw_bytes(value, label, policy)
        if normalized_key == "usercomment":
            _scan_exif_user_comment(value, label, policy)
        else:
            _scan_decoded_text(value, label, policy)
    else:
        _scan_decoded_value(str(value), label, policy)


def _scan_exif(data: bytes, label: str, policy: _ScanPolicy) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            exif = image.getexif()
            for tag, value in exif.items():
                key = ExifTags.TAGS.get(tag, str(tag))
                _scan_metadata_value(key, value, f"{label} EXIF {key}", policy)
            try:
                gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            except (AttributeError, KeyError, TypeError, ValueError):
                gps = {}
            if gps:
                _raise_leak(label, "reportable location metadata")
    except ReviewerPacketError:
        raise
    except Exception as exc:
        raise ReviewerPacketError(
            f"Could not inspect image metadata in {label}"
        ) from exc


def _decompress_embedded_text(data: bytes, label: str) -> bytes:
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(data, _MAX_EMBEDDED_TEXT_BYTES + 1)
        if len(decoded) > _MAX_EMBEDDED_TEXT_BYTES or decompressor.unconsumed_tail:
            raise ReviewerPacketError(
                f"Embedded text exceeds the inspection limit in {label}"
            )
        decoded += decompressor.flush(_MAX_EMBEDDED_TEXT_BYTES + 1 - len(decoded))
    except zlib.error as exc:
        raise ReviewerPacketError(
            f"Could not inspect compressed metadata in {label}"
        ) from exc
    if len(decoded) > _MAX_EMBEDDED_TEXT_BYTES or not decompressor.eof:
        raise ReviewerPacketError(
            f"Embedded text exceeds the inspection limit in {label}"
        )
    return decoded


def _scan_png(data: bytes, label: str, policy: _ScanPolicy) -> None:
    offset = 8
    saw_exif = False
    metadata_types = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(data):
            if chunk_type in metadata_types:
                raise ReviewerPacketError(
                    f"Could not inspect truncated PNG metadata in {label}"
                )
            break
        payload = data[offset + 8 : offset + 8 + length]
        if chunk_type == b"tIME":
            _raise_leak(label, "embedded timestamp metadata")
        if chunk_type == b"tEXt":
            key, separator, value = payload.partition(b"\0")
            if not separator:
                raise ReviewerPacketError(
                    f"Could not inspect PNG text metadata in {label}"
                )
            decoded_key = key.decode("latin-1", errors="replace")
            decoded_value = value.decode("latin-1", errors="replace")
            _scan_metadata_value(decoded_key, value, f"{label} PNG text", policy)
            _scan_metadata_value(
                decoded_key, decoded_value, f"{label} PNG text", policy
            )
        elif chunk_type == b"zTXt":
            key, separator, remainder = payload.partition(b"\0")
            if not separator or len(remainder) < 2 or remainder[0] != 0:
                raise ReviewerPacketError(
                    f"Could not inspect PNG compressed text in {label}"
                )
            raw_value = _decompress_embedded_text(remainder[1:], label)
            decoded_key = key.decode("latin-1", errors="replace")
            _scan_metadata_value(decoded_key, raw_value, f"{label} PNG text", policy)
            decoded_value = raw_value.decode("latin-1", errors="replace")
            _scan_metadata_value(
                decoded_key,
                decoded_value,
                f"{label} PNG text",
                policy,
            )
        elif chunk_type == b"iTXt":
            key, separator, remainder = payload.partition(b"\0")
            if not separator or len(remainder) < 2:
                raise ReviewerPacketError(
                    f"Could not inspect PNG international text in {label}"
                )
            compression_flag = remainder[0]
            compression_method = remainder[1]
            language, separator, remainder = remainder[2:].partition(b"\0")
            if not separator:
                raise ReviewerPacketError(
                    f"Could not inspect PNG international text in {label}"
                )
            translated, separator, text_data = remainder.partition(b"\0")
            if not separator or compression_method != 0:
                raise ReviewerPacketError(
                    f"Could not inspect PNG international text in {label}"
                )
            if compression_flag == 1:
                text_data = _decompress_embedded_text(text_data, label)
            elif compression_flag != 0:
                raise ReviewerPacketError(
                    f"Could not inspect PNG international text in {label}"
                )
            combined = b"\n".join((language, translated, text_data)).decode(
                "utf-8", errors="strict"
            )
            _scan_metadata_value(
                key.decode("latin-1", errors="replace"),
                combined,
                f"{label} PNG text",
                policy,
            )
        elif chunk_type == b"eXIf":
            saw_exif = True
        if chunk_type == b"IEND":
            break
        offset = end
    if saw_exif:
        _scan_exif(data, label, policy)


def _scan_jpeg(data: bytes, label: str, policy: _ScanPolicy) -> None:
    offset = 2
    saw_exif = False
    while offset + 1 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA:
            break
        if marker in set(range(0xD0, 0xD8)) | {0x01}:
            continue
        if offset + 2 > len(data):
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            break
        payload = data[offset + 2 : offset + length]
        if marker in {0xE1, 0xED, 0xFE}:
            _scan_raw_bytes(payload, f"{label} JPEG metadata", policy)
            _scan_decoded_text(payload, f"{label} JPEG metadata", policy)
        if marker == 0xE1 and payload.startswith(b"Exif\0\0"):
            saw_exif = True
        offset += length
    if saw_exif:
        _scan_exif(data, label, policy)


def _validate_archive_name(name: str, label: str) -> None:
    if unicodedata.normalize("NFC", name) != name:
        raise ReviewerPacketError(
            f"Archive member name is not NFC-normalized in {label}"
        )
    if "\\" in name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        raise ReviewerPacketError(f"Archive member path is unsafe in {label}: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ReviewerPacketError(
            f"Archive traversal entry is prohibited in {label}: {name!r}"
        )
    for part in parts:
        _safe_component(part, f"{label}:{name}")


def _scan_zip(data: bytes, label: str, policy: _ScanPolicy, depth: int) -> None:
    if depth >= _MAX_ARCHIVE_DEPTH:
        raise ReviewerPacketError(
            f"Nested archive depth exceeds the inspection limit in {label}"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReviewerPacketError(
            f"Could not inspect ZIP/Office content in {label}"
        ) from exc
    with archive:
        infos = sorted(archive.infolist(), key=lambda item: item.filename)
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            raise ReviewerPacketError(
                f"Archive member count exceeds the inspection limit in {label}"
            )
        total = sum(item.file_size for item in infos)
        if total > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ReviewerPacketError(
                f"Archive expands beyond the inspection limit in {label}"
            )
        if archive.comment:
            _scan_blob(archive.comment, f"{label} archive comment", policy, depth + 1)
        seen: set[str] = set()
        for info in infos:
            _validate_archive_name(info.filename, label)
            folded = info.filename.casefold()
            if folded in seen:
                raise ReviewerPacketError(
                    f"Archive has duplicate member names in {label}"
                )
            seen.add(folded)
            if info.flag_bits & 0x1:
                raise ReviewerPacketError(
                    f"Encrypted archive member cannot be inspected in {label}"
                )
            embedded_mode = info.external_attr >> 16
            embedded_type = stat.S_IFMT(embedded_mode)
            if embedded_type and embedded_type not in {stat.S_IFREG, stat.S_IFDIR}:
                raise ReviewerPacketError(f"Unsupported archive member type in {label}")
            _scan_text(info.filename, f"{label} archive member name", policy)
            if info.comment:
                _scan_blob(
                    info.comment, f"{label}:{info.filename} comment", policy, depth + 1
                )
            if info.extra:
                _scan_raw_bytes(
                    info.extra, f"{label}:{info.filename} extra metadata", policy
                )
                _scan_decoded_text(
                    info.extra,
                    f"{label}:{info.filename} extra metadata",
                    policy,
                )
            if info.is_dir():
                continue
            try:
                member = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ReviewerPacketError(
                    f"Could not inspect archive member {info.filename!r} in {label}"
                ) from exc
            _scan_blob(member, f"{label}:{info.filename}", policy, depth + 1)


def _scan_pdf(data: bytes, label: str, policy: _ScanPolicy, depth: int) -> None:
    try:
        import fitz
    except ImportError as exc:
        raise ReviewerPacketError(
            "PyMuPDF is required to inspect real PDF materials"
        ) from exc
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ReviewerPacketError(
            f"Could not inspect real PDF content in {label}"
        ) from exc
    try:
        if document.needs_pass:
            raise ReviewerPacketError(f"Encrypted PDF cannot be inspected in {label}")
        if document.page_count > _MAX_PDF_PAGES:
            raise ReviewerPacketError(
                f"PDF page count exceeds the inspection limit in {label}"
            )
        for key, value in (document.metadata or {}).items():
            if not value:
                continue
            if key.replace(" ", "").casefold() in _IDENTITY_METADATA_KEYS:
                _raise_leak(label, "reportable identity metadata")
            _scan_text(str(value), f"{label} PDF metadata {key}", policy)
        try:
            xml_metadata = document.get_xml_metadata()
        except Exception:
            xml_metadata = ""
        if xml_metadata:
            _scan_text(xml_metadata, f"{label} PDF XML metadata", policy)
        for page_number, page in enumerate(document, start=1):
            try:
                text = page.get_text("text")
            except Exception as exc:
                raise ReviewerPacketError(
                    f"Could not extract PDF page text in {label} page {page_number}"
                ) from exc
            if text:
                _scan_text(text, f"{label} PDF page {page_number}", policy)
            try:
                links = page.get_links()
            except Exception:
                links = []
            for link in links:
                for key in ("uri", "file"):
                    if link.get(key):
                        _scan_text(
                            str(link[key]),
                            f"{label} PDF page {page_number} link",
                            policy,
                        )
            annotation = page.first_annot
            while annotation is not None:
                info = annotation.info or {}
                if info.get("title"):
                    _raise_leak(label, "reportable identity metadata")
                for value in info.values():
                    if value:
                        _scan_text(
                            str(value),
                            f"{label} PDF page {page_number} annotation",
                            policy,
                        )
                annotation = annotation.next
        try:
            embedded_names = document.embfile_names()
        except Exception:
            embedded_names = []
        for name in sorted(embedded_names):
            _validate_archive_name(name, label)
            _scan_text(name, f"{label} PDF attachment name", policy)
            try:
                embedded = document.embfile_get(name)
            except Exception as exc:
                raise ReviewerPacketError(
                    f"Could not inspect PDF attachment {name!r} in {label}"
                ) from exc
            _scan_blob(embedded, f"{label} PDF attachment {name}", policy, depth + 1)
    finally:
        document.close()


def _has_prefixed_pdf_signature(data: bytes) -> bool:
    prefix = data[: _MAX_PDF_PREAMBLE_BYTES + 16]
    match = _PDF_HEADER_PATTERN.search(prefix)
    if match is None or match.start() == 0 or match.start() > _MAX_PDF_PREAMBLE_BYTES:
        return False
    trailer = data[-_MAX_PDF_TRAILER_SCAN_BYTES:]
    startxref = trailer.rfind(b"startxref")
    eof = trailer.rfind(b"%%EOF")
    return 0 <= startxref < eof


def _scan_blob(
    data: bytes,
    label: str,
    policy: _ScanPolicy,
    depth: int = 0,
) -> None:
    _scan_raw_bytes(data, label, policy)
    if data.startswith(b"%PDF-") or _has_prefixed_pdf_signature(data):
        _scan_pdf(data, label, policy, depth)
        return
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        _scan_png(data, label, policy)
        return
    if data.startswith(b"\xff\xd8"):
        _scan_jpeg(data, label, policy)
        return
    if zipfile.is_zipfile(io.BytesIO(data)):
        _scan_zip(data, label, policy, depth)
        return
    _scan_decoded_text(data, label, policy)


def _scan_staged_packet(
    stage: Path,
    policy: _ScanPolicy,
    mapping_bytes: bytes,
    mapping_identity: tuple[int, int] | None = None,
) -> None:
    stage_inventory = _inventory_tree(stage, enforce_material_policy=False)
    encoded_mapping_patterns = _compile_encoded_forbidden_patterns(
        (mapping_bytes.decode("utf-8", errors="strict"),),
        include_case_variants=False,
    )
    mapping_policy = _ScanPolicy(
        identifiers=policy.identifiers,
        paths=policy.paths,
        forbidden_bytes=tuple(
            item for item in policy.forbidden_bytes + (mapping_bytes,) if item
        ),
        encoded_identifier_patterns=policy.encoded_identifier_patterns,
        encoded_sensitive_patterns=policy.encoded_sensitive_patterns,
        encoded_forbidden_patterns=(
            policy.encoded_forbidden_patterns + encoded_mapping_patterns
        ),
    )
    _assert_no_xattrs(stage)
    for kind, relative in stage_inventory:
        path = stage / PurePosixPath(relative)
        _assert_no_xattrs(path)
        _scan_text(relative, f"packet path {relative}", mapping_policy)
        if kind == "file":
            try:
                before = path.lstat()
            except (OSError, ValueError) as exc:
                raise ReviewerPacketError(
                    f"Could not inspect staged packet file {relative}"
                ) from exc
            identity = (before.st_dev, before.st_ino)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ReviewerPacketError(
                    f"Staged packet file is not single-link regular content: {relative}"
                )
            if mapping_identity is not None and identity == mapping_identity:
                raise ReviewerPacketError(
                    f"Staged packet file aliases the external mapping: {relative}"
                )
            data = _read_regular_bytes(path, f"staged packet file {relative}")
            try:
                after = path.lstat()
            except (OSError, ValueError) as exc:
                raise ReviewerPacketError(
                    f"Could not recheck staged packet file {relative}"
                ) from exc
            if (
                (after.st_dev, after.st_ino) != identity
                or not stat.S_ISREG(after.st_mode)
                or after.st_nlink != 1
            ):
                raise ReviewerPacketError(
                    f"Staged packet file changed during validation: {relative}"
                )
            _scan_blob(data, f"packet file {relative}", mapping_policy)


def _make_scan_policy(
    manifest_path: Path,
    manifest: dict[str, Any],
    prepared: list[_SourceCase],
    seed: bytes,
    seed_text: bytes,
    mapping_output: Path,
    seed_file: Path,
) -> _ScanPolicy:
    identifiers: set[str] = set()
    paths: set[str] = set()
    for case in manifest["cases"]:
        source_id = case["case_id"]
        identifiers.add(source_id)
        identifiers.add(unicodedata.normalize("NFC", source_id))
        paths.add(case["package_path"])
        paths.add(case["annotation_path"])
    for item in prepared:
        paths.add(str(item.package))
        paths.add(str(item.annotation))
    for path in (manifest_path, mapping_output, seed_file):
        try:
            paths.add(str(path.resolve(strict=False)))
        except (OSError, RuntimeError, ValueError):
            paths.add(str(path.absolute()))
    paths.discard("")
    identifiers.discard("")
    identifier_values = tuple(sorted(identifiers))
    path_values = tuple(sorted(paths))
    encoded_forbidden_values = tuple(
        sorted(
            set(path_values)
            | set(_ENCODED_LOCAL_PATH_MARKERS)
            | {seed_text.decode("ascii", errors="strict")}
        )
    )
    return _ScanPolicy(
        identifiers=identifier_values,
        paths=path_values,
        forbidden_bytes=(seed, seed_text),
        encoded_identifier_patterns=_compile_encoded_token_patterns(identifier_values),
        encoded_sensitive_patterns=_compile_encoded_token_patterns(
            tuple(sorted(_PROTECTED_TOKEN_MARKERS))
        ),
        encoded_forbidden_patterns=_compile_encoded_forbidden_patterns(
            encoded_forbidden_values
        ),
    )


def _packet_manifest(prepared: list[_SourceCase]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_scope": PACKET_SCOPE,
        "cases": [
            {
                "reviewer_case_id": item.reviewer_case_id,
                "source_package_sha256": item.case["expected_sha256"],
                "annotation_schema_version": item.annotation_schema_version,
            }
            for item in prepared
        ],
    }


def _mapping_contract(
    prepared: list[_SourceCase],
    packet_manifest_bytes: bytes,
    manifest_digest: bytes,
    selection_digest: bytes,
    seed: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "packet_manifest_sha256": hashlib.sha256(packet_manifest_bytes).hexdigest(),
        "source_manifest_sha256": manifest_digest.hex(),
        "selection_sha256": selection_digest.hex(),
        "anonymization": {
            "algorithm": ANONYMIZATION_ALGORITHM,
            "seed_commitment_sha256": hashlib.sha256(seed).hexdigest(),
        },
        "cases": [
            {
                "reviewer_case_id": item.reviewer_case_id,
                "source_case_id": item.case["case_id"],
                "source_package_sha256": item.case["expected_sha256"],
                "source_annotation_sha256": item.case["annotation_sha256"],
            }
            for item in prepared
        ],
    }


def _build_staged_packet(
    stage: Path,
    prepared: list[_SourceCase],
    packet_manifest: dict[str, Any],
) -> bytes:
    guide_path = Path(__file__).with_name("REVIEWER_GUIDE.md")
    guide_bytes = _read_regular_bytes(guide_path, "reviewer guide")
    _write_bytes(stage / "REVIEWER_GUIDE.md", guide_bytes)

    cases_dir = stage / "cases"
    forms_dir = stage / "forms"
    _make_directory(cases_dir)
    _make_directory(forms_dir)
    for item in prepared:
        reviewer_dir = cases_dir / item.reviewer_case_id
        _make_directory(reviewer_dir)
        _copy_materials(item.package, reviewer_dir / "materials", item.inventory)
        form = _blank_form(item.reviewer_case_id)
        try:
            validate_contract("reviewer_form_template.schema.json", form)
        except ContractError as exc:
            raise ReviewerPacketError(
                "Generated reviewer form template is invalid"
            ) from exc
        _write_bytes(forms_dir / f"{item.reviewer_case_id}.json", _serialize_json(form))

    try:
        validate_contract("reviewer_packet_manifest.schema.json", packet_manifest)
    except ContractError as exc:
        raise ReviewerPacketError("Generated packet manifest is invalid") from exc
    packet_manifest_bytes = _serialize_json(packet_manifest)
    _write_bytes(stage / "packet_manifest.json", packet_manifest_bytes)
    return packet_manifest_bytes


def _strict_json(path: Path, label: str) -> Any:
    raw = _read_regular_bytes(path, label)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReviewerPacketError(f"{label} is not strict UTF-8 JSON") from exc


def _validate_staged_packet(
    stage: Path,
    prepared: list[_SourceCase],
    expected_manifest: dict[str, Any],
    policy: _ScanPolicy,
    mapping_bytes: bytes,
    mapping_identity: tuple[int, int] | None = None,
) -> None:
    top_level = {path.name for path in stage.iterdir()}
    if top_level != {"REVIEWER_GUIDE.md", "packet_manifest.json", "cases", "forms"}:
        raise ReviewerPacketError("Staged packet has an unexpected top-level inventory")
    expected_guide = _read_regular_bytes(
        Path(__file__).with_name("REVIEWER_GUIDE.md"),
        "reviewer guide",
    )
    if (
        _read_regular_bytes(stage / "REVIEWER_GUIDE.md", "staged reviewer guide")
        != expected_guide
    ):
        raise ReviewerPacketError("Staged reviewer guide changed after generation")
    reviewer_ids = [item.reviewer_case_id for item in prepared]
    if {path.name for path in (stage / "cases").iterdir()} != set(reviewer_ids):
        raise ReviewerPacketError("Staged packet case inventory is inconsistent")
    if {path.name for path in (stage / "forms").iterdir()} != {
        f"{reviewer_id}.json" for reviewer_id in reviewer_ids
    }:
        raise ReviewerPacketError("Staged packet form inventory is inconsistent")

    loaded_manifest = _strict_json(stage / "packet_manifest.json", "packet manifest")
    try:
        validate_contract("reviewer_packet_manifest.schema.json", loaded_manifest)
    except ContractError as exc:
        raise ReviewerPacketError("Staged packet manifest is invalid") from exc
    if loaded_manifest != expected_manifest:
        raise ReviewerPacketError("Staged packet manifest changed after generation")

    for item in prepared:
        case_dir = stage / "cases" / item.reviewer_case_id
        if {path.name for path in case_dir.iterdir()} != {"materials"}:
            raise ReviewerPacketError(
                f"Staged reviewer case {item.reviewer_case_id} has extra content"
            )
        materials = case_dir / "materials"
        if _inventory_tree(materials) != item.inventory:
            raise ReviewerPacketError(
                f"Copied material inventory changed for {item.reviewer_case_id}"
            )
        try:
            source_hash = hash_tree(item.package)
            copied_hash = hash_tree(materials)
        except HashingError as exc:
            raise ReviewerPacketError(
                f"Could not verify copied materials for {item.reviewer_case_id}"
            ) from exc
        expected_hash = item.case["expected_sha256"]
        if source_hash != expected_hash or copied_hash != expected_hash:
            raise ReviewerPacketError(
                f"Copied materials hash mismatch for {item.reviewer_case_id}"
            )
        form = _strict_json(
            stage / "forms" / f"{item.reviewer_case_id}.json",
            f"form for {item.reviewer_case_id}",
        )
        try:
            validate_contract("reviewer_form_template.schema.json", form)
        except ContractError as exc:
            raise ReviewerPacketError(
                f"Staged form is invalid for {item.reviewer_case_id}"
            ) from exc
        if form != _blank_form(item.reviewer_case_id):
            raise ReviewerPacketError(
                f"Staged form is not blank for {item.reviewer_case_id}"
            )
    _scan_staged_packet(stage, policy, mapping_bytes, mapping_identity)


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = -1
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise ReviewerPacketError(f"Could not fsync directory: {directory}") from exc
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _fsync_tree(root: Path) -> None:
    directories = [root]
    for path in root.rglob("*"):
        if path.is_dir():
            directories.append(path)
    for directory in sorted(
        directories,
        key=lambda item: len(item.relative_to(root).parts),
        reverse=True,
    ):
        _fsync_directory(directory)


def _verify_mapping_file(
    path: Path,
    data: bytes,
    label: str,
) -> tuple[int, int]:
    try:
        before = path.lstat()
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"{label} disappeared") from exc
    identity = (before.st_dev, before.st_ino)
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
    ):
        raise ReviewerPacketError(
            f"{label} must be a single-link regular file with mode 0600"
        )
    _assert_no_xattrs(path)
    if _read_regular_bytes(path, label.casefold()) != data:
        raise ReviewerPacketError(f"{label} bytes changed")
    try:
        after = path.lstat()
    except (OSError, ValueError) as exc:
        raise ReviewerPacketError(f"{label} disappeared after verification") from exc
    if (
        (after.st_dev, after.st_ino) != identity
        or not stat.S_ISREG(after.st_mode)
        or stat.S_IMODE(after.st_mode) != 0o600
        or after.st_nlink != 1
    ):
        raise ReviewerPacketError(f"{label} changed during verification")
    return identity


def _write_mapping_stage(target: Path, data: bytes) -> Path:
    descriptor = -1
    stage: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}.stage-",
            dir=target.parent,
        )
        stage = Path(name)
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short mapping write")
            written += count
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _clear_xattrs(stage)
        _verify_mapping_file(stage, data, "Staged mapping")
        return stage
    except BaseException as exc:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass
            descriptor = -1
        if stage is not None:
            try:
                stage.unlink()
            except OSError:
                pass
        if isinstance(exc, ReviewerPacketError):
            raise
        if isinstance(exc, Exception):
            raise ReviewerPacketError(
                "Could not stage external reviewer mapping"
            ) from exc
        raise
    finally:
        if descriptor != -1:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _publish_no_replace(source: Path, target: Path) -> None:
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin":
        library = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(library, "renamex_np", None)
        if renamex_np is None:
            raise ReviewerPacketError("Atomic no-replace publication is unavailable")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        if renamex_np(source_bytes, target_bytes, 0x00000004) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), os.fspath(target))
        return
    if sys.platform.startswith("linux"):
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(library, "renameat2", None)
        if renameat2 is None:
            raise ReviewerPacketError("Atomic no-replace publication is unavailable")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, source_bytes, -100, target_bytes, 0x00000001) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), os.fspath(target))
        return
    if os.name == "nt":
        os.rename(source, target)
        return
    raise ReviewerPacketError("Atomic no-replace publication is unavailable")


def _cleanup_packet_stage(stage: Path | None) -> None:
    if stage is None:
        return
    try:
        value = stage.lstat()
    except (FileNotFoundError, OSError, ValueError):
        return
    try:
        if stat.S_ISDIR(value.st_mode) and not stat.S_ISLNK(value.st_mode):
            shutil.rmtree(stage)
        else:
            stage.unlink()
    except OSError:
        pass


def _cleanup_mapping_stage(stage: Path | None) -> None:
    if stage is None:
        return
    try:
        stage.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def export_reviewer_packet(
    manifest_path: Path | str,
    case_ids: Sequence[str],
    output_dir: Path | str,
    mapping_output: Path | str,
    seed_file: Path | str,
) -> dict[str, Any]:
    """Export one deterministic reviewer packet and its external source mapping."""

    manifest_file = _as_path(manifest_path, "manifest path")
    seed_path = _as_path(seed_file, "seed file")
    placement = _resolve_placement(output_dir, mapping_output)
    manifest, raw_manifest = _load_frozen_manifest(manifest_file)
    seed, seed_text = _read_seed(seed_path)
    selected = _select_cases(manifest, case_ids)
    manifest_digest = hashlib.sha256(raw_manifest).digest()
    ranked, selection_digest = _rank_cases(selected, seed, manifest_digest)
    prepared = _prepare_source_cases(manifest_file.parent, ranked)
    policy = _make_scan_policy(
        manifest_file,
        manifest,
        prepared,
        seed,
        seed_text,
        placement.mapping,
        seed_path,
    )
    packet_manifest = _packet_manifest(prepared)

    packet_stage: Path | None = None
    mapping_stage: Path | None = None
    try:
        packet_stage = Path(
            tempfile.mkdtemp(
                prefix=f".{placement.output.name}.stage-",
                dir=placement.output.parent,
            )
        )
        os.chmod(packet_stage, 0o700, follow_symlinks=False)
        _clear_xattrs(packet_stage)
        packet_manifest_bytes = _build_staged_packet(
            packet_stage,
            prepared,
            packet_manifest,
        )
        mapping = _mapping_contract(
            prepared,
            packet_manifest_bytes,
            manifest_digest,
            selection_digest,
            seed,
        )
        try:
            validate_contract("reviewer_mapping.schema.json", mapping)
        except ContractError as exc:
            raise ReviewerPacketError(
                "Generated external reviewer mapping is invalid"
            ) from exc
        mapping_bytes = _serialize_json(mapping)
        if seed in mapping_bytes or seed_text in mapping_bytes:
            raise ReviewerPacketError("Generated mapping exposes raw seed bytes")
        _validate_staged_packet(
            packet_stage,
            prepared,
            packet_manifest,
            policy,
            mapping_bytes,
        )
        _fsync_tree(packet_stage)
        mapping_stage = _write_mapping_stage(placement.mapping, mapping_bytes)
        mapping_stage_identity = _verify_mapping_file(
            mapping_stage,
            mapping_bytes,
            "Staged mapping",
        )
        _validate_staged_packet(
            packet_stage,
            prepared,
            packet_manifest,
            policy,
            mapping_bytes,
            mapping_stage_identity,
        )
        _fsync_tree(packet_stage)

        _recheck_before_mapping_publish(placement)
        if (
            _verify_mapping_file(mapping_stage, mapping_bytes, "Staged mapping")
            != mapping_stage_identity
        ):
            raise ReviewerPacketError("Staged mapping identity changed")
        _publish_no_replace(mapping_stage, placement.mapping)
        mapping_stage = None
        mapping_identity = _verify_mapping_file(
            placement.mapping,
            mapping_bytes,
            "Published mapping",
        )
        _fsync_directory(placement.mapping.parent)

        _recheck_before_packet_publish(placement, mapping_identity)
        _validate_staged_packet(
            packet_stage,
            prepared,
            packet_manifest,
            policy,
            mapping_bytes,
            mapping_identity,
        )
        if (
            _verify_mapping_file(
                placement.mapping,
                mapping_bytes,
                "Published mapping",
            )
            != mapping_identity
        ):
            raise ReviewerPacketError("Published mapping identity changed")
        _publish_no_replace(packet_stage, placement.output)
        packet_stage = None
        _fsync_directory(placement.output.parent)
    except BaseException as exc:
        _cleanup_mapping_stage(mapping_stage)
        _cleanup_packet_stage(packet_stage)
        if isinstance(exc, ReviewerPacketError):
            raise
        if isinstance(exc, Exception):
            raise ReviewerPacketError(f"Reviewer packet export failed: {exc}") from exc
        raise
    return packet_manifest


__all__ = ["ReviewerPacketError", "export_reviewer_packet"]
