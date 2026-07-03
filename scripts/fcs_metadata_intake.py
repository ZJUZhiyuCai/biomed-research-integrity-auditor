#!/usr/bin/env python3
"""Read basic Flow Cytometry Standard (FCS) metadata for intake review.

This helper indexes FCS header/text keywords so reviewers can see whether raw
flow files include event counts, channel/marker labels, instrument metadata,
and compensation hints. It does not parse event data, validate gates, or
determine whether compensation/analysis was correct.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FCS_EXTS = {".fcs"}
HEADER_SIZE = 58
HEADER_FIELDS = {
    "text_start": (10, 18),
    "text_end": (18, 26),
    "data_start": (26, 34),
    "data_end": (34, 42),
    "analysis_start": (42, 50),
    "analysis_end": (50, 58),
}
KEYWORDS_OF_INTEREST = (
    "$FIL",
    "$SRC",
    "$EXP",
    "$DATE",
    "$BTIM",
    "$ETIM",
    "$CYT",
    "$CYTSN",
    "$TOT",
    "$PAR",
    "$BYTEORD",
    "$DATATYPE",
    "$MODE",
    "$NEXTDATA",
)
COMPENSATION_KEYS = ("$SPILLOVER", "SPILLOVER", "$COMP", "COMP")


def collect_fcs_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if not path.is_symlink() and path.is_file() and path.suffix.lower() in FCS_EXTS
    )


def header_int(header: bytes, name: str) -> int | None:
    start, end = HEADER_FIELDS[name]
    text = header[start:end].decode("ascii", errors="ignore").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def parse_text_segment(data: bytes) -> dict[str, str]:
    if not data:
        return {}
    delimiter = chr(data[0])
    body = data[1:].decode("latin-1", errors="replace")
    if not delimiter:
        return {}
    parts = body.split(delimiter)
    if parts and parts[-1] == "":
        parts = parts[:-1]
    result: dict[str, str] = {}
    for idx in range(0, len(parts) - 1, 2):
        key = parts[idx].strip()
        value = parts[idx + 1].strip()
        if key:
            result[key.upper()] = value
    return result


def parse_int_keyword(text_keywords: dict[str, str], key: str) -> int | None:
    value = text_keywords.get(key.upper())
    if value is None or not value.strip():
        return None
    try:
        return int(float(value.strip()))
    except ValueError:
        return None


def parameter_records(text_keywords: dict[str, str]) -> list[dict[str, Any]]:
    count = parse_int_keyword(text_keywords, "$PAR") or 0
    records: list[dict[str, Any]] = []
    for idx in range(1, count + 1):
        prefix = f"$P{idx}"
        name = text_keywords.get(f"{prefix}N", "")
        marker = text_keywords.get(f"{prefix}S", "")
        bits = parse_int_keyword(text_keywords, f"{prefix}B")
        value_range = parse_int_keyword(text_keywords, f"{prefix}R")
        records.append({
            "index": idx,
            "name": name,
            "marker": marker,
            "bit_width": bits,
            "range": value_range,
        })
    return records


def compact_keywords(text_keywords: dict[str, str]) -> dict[str, str]:
    return {
        key: text_keywords[key]
        for key in KEYWORDS_OF_INTEREST
        if key in text_keywords and text_keywords[key]
    }


def parse_fcs(root: Path, path: Path) -> tuple[dict[str, Any], dict[str, Any] | None]:
    rel = str(path.relative_to(root))
    try:
        raw = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        error = {
            "path": rel,
            "stage": "fcs_metadata_intake",
            "error": f"could not read file: {exc}",
        }
        return {
            "path": rel,
            "parse_status": "error",
            "errors": [error],
        }, error
    if len(raw) < HEADER_SIZE:
        error = {
            "path": rel,
            "stage": "fcs_metadata_intake",
            "error": "file is shorter than the standard FCS header",
        }
        return {
            "path": rel,
            "parse_status": "error",
            "errors": [error],
        }, error

    header = raw[:HEADER_SIZE]
    version = header[:6].decode("ascii", errors="ignore").strip()
    text_start = header_int(header, "text_start")
    text_end = header_int(header, "text_end")
    if text_start is None or text_end is None or text_start < 0 or text_end < text_start or text_end >= len(raw):
        error = {
            "path": rel,
            "stage": "fcs_metadata_intake",
            "error": "FCS text segment offsets are missing or outside the file bounds",
        }
        return {
            "path": rel,
            "version": version,
            "parse_status": "error",
            "errors": [error],
        }, error

    text_keywords = parse_text_segment(raw[text_start:text_end + 1])
    parameters = parameter_records(text_keywords)
    spillover_keys = [
        key
        for key in COMPENSATION_KEYS
        if key in text_keywords and text_keywords[key].strip()
    ]
    event_count = parse_int_keyword(text_keywords, "$TOT")
    parameter_count = parse_int_keyword(text_keywords, "$PAR")
    record = {
        "path": rel,
        "version": version,
        "parse_status": "parsed",
        "text_start": text_start,
        "text_end": text_end,
        "data_start": header_int(header, "data_start"),
        "data_end": header_int(header, "data_end"),
        "analysis_start": header_int(header, "analysis_start"),
        "analysis_end": header_int(header, "analysis_end"),
        "event_count": event_count,
        "parameter_count": parameter_count,
        "cytometer": text_keywords.get("$CYT", ""),
        "cytometer_serial": text_keywords.get("$CYTSN", ""),
        "date": text_keywords.get("$DATE", ""),
        "file_keyword": text_keywords.get("$FIL", ""),
        "sample_source": text_keywords.get("$SRC", ""),
        "experimenter": text_keywords.get("$EXP", ""),
        "data_type": text_keywords.get("$DATATYPE", ""),
        "byte_order": text_keywords.get("$BYTEORD", ""),
        "compensation_keywords": spillover_keys,
        "compensation_present": bool(spillover_keys),
        "parameters": parameters,
        "keywords": compact_keywords(text_keywords),
        "interpretation": (
            "FCS metadata for MIFlowCyt-oriented intake review; not gating, compensation, "
            "or population-frequency verification"
        ),
        "errors": [],
    }
    return record, None


def scan(root: Path) -> dict[str, Any]:
    fcs_files: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in collect_fcs_files(root):
        record, error = parse_fcs(root, path)
        fcs_files.append(record)
        if error is not None:
            errors.append(error)

    readable = [item for item in fcs_files if item.get("parse_status") == "parsed"]
    return {
        "schema_version": "0.1.0",
        "extractor": "scripts.fcs_metadata_intake",
        "scope_note": (
            "Best-effort FCS metadata intake. Event counts, channel/marker labels, instrument "
            "metadata, and compensation-keyword presence support MIFlowCyt-oriented material "
            "review. This does not parse events, reconstruct gates, validate compensation, or "
            "verify reported population percentages."
        ),
        "input": {
            "package": str(root),
            "fcs_files": len(fcs_files),
        },
        "totals": {
            "fcs_files": len(fcs_files),
            "readable_fcs_files": len(readable),
            "unreadable_fcs_files": len(errors),
            "total_events_reported": sum(int(item.get("event_count") or 0) for item in readable),
            "total_parameters_indexed": sum(int(item.get("parameter_count") or 0) for item in readable),
            "files_with_compensation_keywords": sum(1 for item in readable if item.get("compensation_present")),
        },
        "fcs_files": fcs_files,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("fcs_metadata_intake.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    output = args.output.expanduser().resolve()
    payload = scan(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "fcs_files": payload["input"]["fcs_files"],
        "readable": payload["totals"]["readable_fcs_files"],
        "errors": len(payload["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
