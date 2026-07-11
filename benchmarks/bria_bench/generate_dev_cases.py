"""Generate deterministic first-party BRIA-Bench development fixtures."""

from __future__ import annotations

import argparse
import binascii
import csv
import hashlib
import json
import os
import shutil
import stat
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .contracts import validate_contract


DEV_CASE_IDS = (
    "dev_001_global_flip",
    "dev_002_independent_images",
    "dev_003_stats_shift",
    "dev_004_stats_independent",
    "dev_005_corrupt_image",
    "dev_006_manifest_laundering",
)

_IMAGE_SIZE = (256, 192)
PIXEL_GENERATOR_VERSION = "sha256-counter-v1"
PIXEL_GENERATOR_DOMAIN = b"BRIA-Bench Task 10 RGB pixels v1\x00"
PIXEL_GENERATOR_SPEC = (
    "SHA-256(domain || uint64be(seed) || uint64be(counter)); counter starts at 0"
)
PNG_ENCODER_VERSION = "png-rgb8-filter0-deflate-stored-v1"
PNG_ENCODER_SPEC = (
    "PNG RGB8 256x192; filter 0; zlib 0x7801; DEFLATE stored blocks <=65535; "
    "Adler-32 and PNG CRC-32"
)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CONTROL_VALUES = (
    "1.13",
    "2.47",
    "3.82",
    "5.26",
    "6.91",
    "8.34",
    "9.78",
    "11.05",
    "12.63",
    "14.27",
    "15.84",
    "17.39",
)
_SHIFTED_VALUES = (
    "1.113e+01",
    "1.247e+01",
    "1.382e+01",
    "1.526e+01",
    "1.691e+01",
    "1.834e+01",
    "1.978e+01",
    "2.105e+01",
    "2.263e+01",
    "2.427e+01",
    "2.584e+01",
    "2.739e+01",
)
_INDEPENDENT_VALUES = (
    "7.62",
    "3.19",
    "10.44",
    "1.87",
    "8.53",
    "12.26",
    "4.71",
    "9.38",
    "15.07",
    "0.64",
    "6.35",
    "13.81",
)
_PACKAGE_NOTE = """BRIA-Bench controlled development fixture

This package is a first-party procedural fixture created for deterministic software testing.
It describes no real paper, no real person, no real patient, and no private record.
It contains no third-party asset. All included text, tables, and images were created for this fixture.
The materials are controlled development data, not a public-realism sample or a headline-accuracy case.
"""
_LICENSE = """License identifier: CC0-1.0
CC0 1.0 Universal dedication

The repository authors created these first-party fixture materials and dedicate them to the public domain under CC0 1.0 Universal.
To the extent possible under law, the creators waive copyright and related rights in these fixture materials.
See https://creativecommons.org/publicdomain/zero/1.0/ for the CC0 1.0 legal terms.
"""
_MANUSCRIPTS = {
    "dev_001_global_flip": (
        "Controlled Figure 1 contains two procedurally generated panels supplied for image-similarity development checks.\n"
    ),
    "dev_002_independent_images": (
        "Controlled Figure 2 contains two independently generated panels supplied as an image-similarity negative control.\n"
    ),
    "dev_003_stats_shift": (
        "Controlled Figure 3 source data contain twelve paired control and treatment values for numerical-consistency development checks.\n"
    ),
    "dev_004_stats_independent": (
        "Controlled Figure 4 source data contain twelve independent control and treatment pairs as a numerical negative control.\n"
    ),
    "dev_005_corrupt_image": (
        "Controlled Figure 5 includes one readable image and one deliberately incomplete image for material-intake coverage checks.\n"
    ),
    "dev_006_manifest_laundering": (
        "Controlled Figure 6 includes two related panels and a machine-readable assembly declaration for provenance-context checks.\n"
    ),
}


class DevelopmentCaseError(ValueError):
    """Raised when controlled development fixtures cannot be published safely."""

    def __init__(self, message: str, *, cleanup_staging: bool = True) -> None:
        super().__init__(message)
        self.cleanup_staging = cleanup_staging


@dataclass(slots=True)
class _PublishState:
    destination: Path
    backup: Path
    prior_existed: bool
    backup_moved: bool = False
    staged_published: bool = False


def _observation(
    observation_id: str,
    role: str,
    issue_family: str,
    location: dict[str, Any],
    risk_range: list[str],
    presence: str,
    benign_explanations: list[str],
    required_materials: list[str],
    *,
    expected_fact: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "observation_id": observation_id,
        "role": role,
        "issue_family": issue_family,
        "location": location,
        "risk_range": risk_range,
        "presence": presence,
        "benign_explanations": benign_explanations,
        "required_materials": required_materials,
    }
    if expected_fact is not None:
        result["expected_fact"] = expected_fact
    return result


def _annotations() -> dict[str, dict[str, Any]]:
    common_notes = (
        "First-party controlled development ground truth for detector and pipeline verification; "
        "excluded from public-realism and headline-accuracy reporting."
    )
    image_materials = [
        "original image files",
        "image acquisition metadata",
        "figure assembly history",
    ]
    numeric_materials = [
        "original source-data table",
        "analysis code or calculation record",
        "data export and rounding notes",
    ]
    payloads = {
        "dev_001_global_flip": {
            "negative_control": False,
            "expected_observations": [
                _observation(
                    "dev_001_global_flip_001",
                    "recall_label",
                    "image_global_similarity",
                    {
                        "file": "figures/Figure_1A.png",
                        "terms": [
                            "figures/Figure_1A.png",
                            "figures/Figure_1B.png",
                            "Figure 1A",
                            "Figure 1B",
                        ],
                    },
                    ["R3", "R3"],
                    "present",
                    [
                        "the panels may be documented derivatives of one acquisition",
                        "a declared orientation correction may explain the horizontal flip",
                    ],
                    image_materials,
                )
            ],
        },
        "dev_002_independent_images": {
            "negative_control": True,
            "expected_observations": [
                _observation(
                    "dev_002_independent_images_001",
                    "negative_guardrail",
                    "image_global_similarity",
                    {
                        "file": "figures/Figure_2A.png",
                        "terms": [
                            "figures/Figure_2A.png",
                            "figures/Figure_2B.png",
                            "Figure 2A",
                            "Figure 2B",
                        ],
                    },
                    ["R2", "R4"],
                    "absent",
                    [
                        "similar dimensions alone do not establish image reuse",
                        "independent procedural generation explains incidental hash proximity",
                    ],
                    image_materials,
                )
            ],
        },
        "dev_003_stats_shift": {
            "negative_control": False,
            "expected_observations": [
                _observation(
                    "dev_003_stats_shift_001",
                    "recall_label",
                    "statistics_or_numeric",
                    {
                        "file": "source_data/Figure_3_source.csv",
                        "terms": [
                            "Figure_3_source.csv",
                            "control",
                            "treatment",
                        ],
                    },
                    ["R1", "R2"],
                    "present",
                    [
                        "a documented normalization offset may explain the relationship",
                        "an export transformation may have added a constant to one column",
                    ],
                    numeric_materials,
                    expected_fact="twelve paired rows with a constant +10 shift",
                )
            ],
        },
        "dev_004_stats_independent": {
            "negative_control": True,
            "expected_observations": [
                _observation(
                    "dev_004_stats_independent_001",
                    "negative_guardrail",
                    "statistics_or_numeric",
                    {
                        "file": "source_data/Figure_4_source.csv",
                        "terms": [
                            "Figure_4_source.csv",
                            "control",
                            "treatment",
                        ],
                    },
                    ["R1", "R2"],
                    "absent",
                    [
                        "small tables can contain incidental numerical similarities",
                        "ordinary independent variation can produce isolated matching digits",
                    ],
                    numeric_materials,
                )
            ],
        },
        "dev_005_corrupt_image": {
            "negative_control": False,
            "expected_observations": [
                _observation(
                    "dev_005_corrupt_image_001",
                    "coverage_gap",
                    "material_or_coverage_gap",
                    {
                        "file": "figures/Figure_5B_truncated.png",
                        "terms": [
                            "figures/Figure_5B_truncated.png",
                            "Figure_5B_truncated.png",
                        ],
                    },
                    ["R1", "R1"],
                    "insufficient_materials",
                    [
                        "the file may have been interrupted during transfer",
                        "a complete readable export may exist outside the supplied package",
                    ],
                    [
                        "complete readable Figure_5B image",
                        "file-transfer or export record",
                        "manual review of the affected panel",
                    ],
                )
            ],
        },
        "dev_006_manifest_laundering": {
            "negative_control": False,
            "expected_observations": [
                _observation(
                    "dev_006_manifest_laundering_001",
                    "recall_label",
                    "image_global_similarity",
                    {
                        "file": "figures/Figure_6A.png",
                        "terms": [
                            "figures/Figure_6A.png",
                            "figures/Figure_6B.png",
                            "Figure 6A",
                            "Figure 6B",
                        ],
                    },
                    ["R3", "R3"],
                    "present",
                    [
                        "the panels may be orientation variants from one acquisition",
                        "a same-field relationship may be valid but remains unverified",
                    ],
                    [
                        "original image files for both panels",
                        "per-channel acquisition metadata",
                        "figure assembly history",
                    ],
                ),
                _observation(
                    "dev_006_manifest_laundering_002",
                    "coverage_gap",
                    "image_channel_metadata_gap",
                    {
                        "file": "figure_assembly/assembly_manifest.csv",
                        "terms": [
                            "figures/Figure_6A.png",
                            "figures/Figure_6B.png",
                            "same_field_different_channel",
                            "assembly_manifest.csv",
                        ],
                    },
                    ["R1", "R1"],
                    "insufficient_materials",
                    [
                        "channel metadata may exist in an original acquisition container",
                        "the supplied PNG exports may have omitted acquisition metadata",
                    ],
                    [
                        "original image files",
                        "channel metadata or channel map",
                        "figure assembly history",
                    ],
                ),
            ],
        },
    }
    annotations: dict[str, dict[str, Any]] = {}
    for case_id in DEV_CASE_IDS:
        annotation = {
            "schema_version": "1.0.0",
            "case_id": case_id,
            "negative_control": payloads[case_id]["negative_control"],
            "review_status": "controlled_ground_truth",
            "source_annotation_path": (
                f"benchmarks/bria_bench/annotations/dev/{case_id}.json"
            ),
            "expected_observations": payloads[case_id]["expected_observations"],
            "notes": common_notes,
        }
        validate_contract("annotation.schema.json", annotation)
        annotations[case_id] = annotation
    return annotations


def _manifest_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for index, case_id in enumerate(DEV_CASE_IDS):
        cases.append(
            {
                "case_id": case_id,
                "track": "blinded_challenge" if index < 4 else "robustness_scale",
                "split": "dev",
                "package_path": f"cases/dev/{case_id}",
                "annotation_path": f"annotations/dev/{case_id}.json",
                "mode": "internal_presubmission",
                "scan_profile": "quick",
                "redistributable": True,
                "license": "CC0-1.0",
                "headline_eligible": False,
                "source": "benchmarks.bria_bench.generate_dev_cases",
                "notes": (
                    "First-party controlled development fixture for internal detector and "
                    "pipeline verification; not public realism and excluded from headline accuracy."
                ),
            }
        )
    return cases


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _counter_mode_bytes(seed: int, length: int) -> bytes:
    prefix = PIXEL_GENERATOR_DOMAIN + seed.to_bytes(8, "big", signed=False)
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(
            hashlib.sha256(prefix + counter.to_bytes(8, "big", signed=False)).digest()
        )
        counter += 1
    return bytes(output[:length])


def _noise_pixels(seed: int) -> bytes:
    return _counter_mode_bytes(seed, _IMAGE_SIZE[0] * _IMAGE_SIZE[1] * 3)


def _flip_horizontal(pixels: bytes) -> bytes:
    row_size = _IMAGE_SIZE[0] * 3
    if len(pixels) != row_size * _IMAGE_SIZE[1]:
        raise DevelopmentCaseError("RGB pixel buffer has the wrong length")
    flipped = bytearray()
    for row_start in range(0, len(pixels), row_size):
        row = pixels[row_start : row_start + row_size]
        for column in range(row_size - 3, -1, -3):
            flipped.extend(row[column : column + 3])
    return bytes(flipped)


def _adler32(data: bytes) -> int:
    first = 1
    second = 0
    modulus = 65521
    for offset in range(0, len(data), 5552):
        for value in data[offset : offset + 5552]:
            first = (first + value) % modulus
            second = (second + first) % modulus
    return (second << 16) | first


def _stored_zlib_stream(data: bytes) -> bytes:
    stream = bytearray(b"\x78\x01")
    for offset in range(0, len(data), 65535):
        block = data[offset : offset + 65535]
        final = offset + len(block) == len(data)
        stream.append(1 if final else 0)
        stream.extend(struct.pack("<HH", len(block), len(block) ^ 0xFFFF))
        stream.extend(block)
    stream.extend(struct.pack(">I", _adler32(data)))
    return bytes(stream)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)
    )


def _encode_png(pixels: bytes) -> bytes:
    row_size = _IMAGE_SIZE[0] * 3
    if len(pixels) != row_size * _IMAGE_SIZE[1]:
        raise DevelopmentCaseError("RGB pixel buffer has the wrong length")
    scanlines = b"".join(
        b"\x00" + pixels[row_start : row_start + row_size]
        for row_start in range(0, len(pixels), row_size)
    )
    header = struct.pack(
        ">IIBBBBB",
        _IMAGE_SIZE[0],
        _IMAGE_SIZE[1],
        8,
        2,
        0,
        0,
        0,
    )
    return b"".join(
        (
            _PNG_SIGNATURE,
            _png_chunk(b"IHDR", header),
            _png_chunk(b"IDAT", _stored_zlib_stream(scanlines)),
            _png_chunk(b"IEND", b""),
        )
    )


def _write_png(path: Path, pixels: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_encode_png(pixels))


def _write_pairs(path: Path, treatments: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("control", "treatment"))
        writer.writerows(zip(_CONTROL_VALUES, treatments))


def _write_package(case_id: str, destination: Path) -> None:
    destination.mkdir(parents=True)
    _write_text(destination / "PACKAGE_NOTE.txt", _PACKAGE_NOTE)
    _write_text(destination / "LICENSE.txt", _LICENSE)
    _write_text(destination / "manuscript" / "manuscript.txt", _MANUSCRIPTS[case_id])

    if case_id == "dev_001_global_flip":
        pixels = _noise_pixels(1001)
        _write_png(destination / "figures" / "Figure_1A.png", pixels)
        _write_png(
            destination / "figures" / "Figure_1B.png",
            _flip_horizontal(pixels),
        )
    elif case_id == "dev_002_independent_images":
        _write_png(destination / "figures" / "Figure_2A.png", _noise_pixels(2001))
        _write_png(destination / "figures" / "Figure_2B.png", _noise_pixels(2002))
    elif case_id == "dev_003_stats_shift":
        _write_pairs(
            destination / "source_data" / "Figure_3_source.csv", _SHIFTED_VALUES
        )
    elif case_id == "dev_004_stats_independent":
        _write_pairs(
            destination / "source_data" / "Figure_4_source.csv", _INDEPENDENT_VALUES
        )
    elif case_id == "dev_005_corrupt_image":
        valid = destination / "figures" / "Figure_5A_valid.png"
        _write_png(valid, _noise_pixels(5001))
        truncated = destination / "figures" / "Figure_5B_truncated.png"
        truncated.write_bytes(valid.read_bytes()[:24])
    elif case_id == "dev_006_manifest_laundering":
        pixels = _noise_pixels(6001)
        _write_png(destination / "figures" / "Figure_6A.png", pixels)
        _write_png(
            destination / "figures" / "Figure_6B.png",
            _flip_horizontal(pixels),
        )
        assembly = destination / "figure_assembly" / "assembly_manifest.csv"
        assembly.parent.mkdir(parents=True)
        with assembly.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(
                ("figure_panel", "source_record", "relation_type", "modality", "notes")
            )
            writer.writerow(
                (
                    "figures/Figure_6A.png",
                    "figures/Figure_6B.png",
                    "same_field_different_channel",
                    "microscopy",
                    "same field exported as two declared channels",
                )
            )
    else:  # pragma: no cover - guarded by the fixed case list.
        raise DevelopmentCaseError(f"unknown development case: {case_id}")


def _write_annotation(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _canonical_root(value: Path | str, *, label: str) -> Path:
    raw = Path(value).expanduser().absolute()
    if raw.is_symlink():
        raise DevelopmentCaseError(f"{label} must not be a symlink: {raw}")
    return raw.resolve(strict=False)


def _validate_root(path: Path, *, label: str) -> None:
    if path.exists():
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise DevelopmentCaseError(f"{label} must be an actual directory: {path}")


def _remove_path(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        path.unlink()
    elif stat.S_ISDIR(metadata.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def _publish_targets(
    targets: list[tuple[Path, Path, Path]],
    *,
    recovery_roots: Sequence[Path],
) -> None:
    for _, destination, _ in targets:
        if destination.exists() or destination.is_symlink():
            metadata = destination.lstat()
            expected_directory = destination.suffix != ".json"
            if stat.S_ISLNK(metadata.st_mode):
                raise DevelopmentCaseError(
                    f"owned destination is a symlink: {destination}"
                )
            if expected_directory != stat.S_ISDIR(metadata.st_mode):
                raise DevelopmentCaseError(
                    f"owned destination has the wrong filesystem type: {destination}"
                )

    records: list[_PublishState] = []
    try:
        for staged, destination, backup in targets:
            state = _PublishState(destination, backup, destination.exists())
            records.append(state)
            if state.prior_existed:
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, backup)
                state.backup_moved = True
            os.replace(staged, destination)
            state.staged_published = True
    except BaseException as publication_error:
        rollback_errors: list[BaseException] = []
        for state in reversed(records):
            try:
                if state.staged_published:
                    _remove_path(state.destination)
                if state.backup_moved:
                    os.replace(state.backup, state.destination)
            except BaseException as rollback_error:  # noqa: BLE001
                rollback_errors.append(rollback_error)
        if rollback_errors:
            recovery_names = ", ".join(sorted({root.name for root in recovery_roots}))
            raise DevelopmentCaseError(
                "development case publication failed and rollback was incomplete; "
                f"retain recovery directories: {recovery_names}",
                cleanup_staging=False,
            ) from publication_error
        raise


def _stage_root(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=".bria-dev-stage-", dir=parent))


def generate_dev_cases(
    output_root: Path | str,
    *,
    annotations_root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Generate and transactionally publish the six controlled development cases.

    ``output_root`` owns only directories named by :data:`DEV_CASE_IDS`. When an
    annotation root is supplied, the matching six JSON files are part of the same
    rollback-aware publication. Other children of either root are preserved.
    """

    output = _canonical_root(output_root, label="development package root")
    annotation_output = (
        _canonical_root(annotations_root, label="development annotation root")
        if annotations_root is not None
        else None
    )
    if annotation_output is not None and (
        output == annotation_output
        or output.is_relative_to(annotation_output)
        or annotation_output.is_relative_to(output)
    ):
        raise DevelopmentCaseError("package and annotation roots overlap")
    _validate_root(output, label="development package root")
    if annotation_output is not None:
        _validate_root(annotation_output, label="development annotation root")

    package_stage: Path | None = None
    annotation_stage: Path | None = None
    created_roots: list[Path] = []
    cleanup_staging = True
    try:
        if not output.exists():
            output.mkdir(parents=True)
            created_roots.append(output)
        package_stage = _stage_root(output.parent)
        package_payload = package_stage / "payload"
        package_backup = package_stage / "backup"
        for case_id in DEV_CASE_IDS:
            _write_package(case_id, package_payload / case_id)

        targets: list[tuple[Path, Path, Path]] = [
            (
                package_payload / case_id,
                output / case_id,
                package_backup / case_id,
            )
            for case_id in DEV_CASE_IDS
        ]
        if annotation_output is not None:
            if not annotation_output.exists():
                annotation_output.mkdir(parents=True)
                created_roots.append(annotation_output)
            annotation_stage = _stage_root(annotation_output.parent)
            annotation_payload = annotation_stage / "payload"
            annotation_backup = annotation_stage / "backup"
            for case_id, payload in _annotations().items():
                _write_annotation(annotation_payload / f"{case_id}.json", payload)
                targets.append(
                    (
                        annotation_payload / f"{case_id}.json",
                        annotation_output / f"{case_id}.json",
                        annotation_backup / f"{case_id}.json",
                    )
                )

        recovery_roots = [package_stage]
        if annotation_stage is not None:
            recovery_roots.append(annotation_stage)
        _publish_targets(targets, recovery_roots=recovery_roots)
        return _manifest_cases()
    except DevelopmentCaseError as exc:
        cleanup_staging = exc.cleanup_staging
        raise
    except Exception as exc:
        raise DevelopmentCaseError(
            f"could not generate development cases: {exc}"
        ) from exc
    finally:
        if cleanup_staging:
            for staging in (annotation_stage, package_stage):
                if staging is not None and staging.exists():
                    shutil.rmtree(staging)
            for root in reversed(created_roots):
                try:
                    root.rmdir()
                except OSError:
                    pass


def _default_annotations_root(output: Path) -> Path | None:
    if output.name == "dev" and output.parent.name == "cases":
        return output.parent.parent / "annotations" / "dev"
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate deterministic first-party BRIA-Bench development cases."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--annotations-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    annotations = args.annotations_output
    if annotations is None:
        annotations = _default_annotations_root(args.output)
    try:
        cases = generate_dev_cases(args.output, annotations_root=annotations)
    except DevelopmentCaseError as exc:
        message = " ".join(str(exc).splitlines()).strip()
        print(f"bria-dev-cases: error: {message}", file=sys.stderr)
        return 2
    print(json.dumps({"case_ids": [case["case_id"] for case in cases]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
