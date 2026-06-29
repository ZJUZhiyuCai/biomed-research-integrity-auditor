#!/usr/bin/env python3
"""Join detector candidates with package context before risk calibration."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import validate_instance  # noqa: E402


DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
TEXT_EXTS = {".txt", ".md", ".pdf", ".csv", ".tsv", ".json", ".yaml", ".yml"}
SOURCE_EXTS = {".csv", ".tsv", ".xlsx", ".xls"}
RAW_IMAGE_EXTS = {".czi", ".nd2", ".lif", ".oib", ".oir", ".svs", ".vsi", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def read_package_text(package: Path) -> str:
    chunks = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 - context extraction should be best effort.
            continue
        if text.strip():
            chunks.append(f"\n--- {path.relative_to(package)} ---\n{text}")
    return "\n".join(chunks).lower()


def has_source_data(package: Path) -> bool:
    source_dir = package / "source_data"
    return source_dir.exists() and any(path.is_file() and path.suffix.lower() in SOURCE_EXTS for path in source_dir.rglob("*"))


def has_raw_images(package: Path) -> bool:
    raw_dir = package / "raw_images"
    return raw_dir.exists() and any(path.is_file() and path.suffix.lower() in RAW_IMAGE_EXTS for path in raw_dir.rglob("*"))


def contains_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def package_context(package: Path) -> dict[str, Any]:
    text = read_package_text(package)
    reuse_disclosed = contains_any(text, [
        r"\bdisclos\w*\b.{0,80}\breus\w*\b",
        r"\breus\w*\b.{0,80}\bdisclos\w*\b",
        r"\bintentionally reused\b",
        r"\bsame loading control\b",
        r"\bsame gapdh loading control\b",
        r"\bloading control was reused\b",
        r"\bsame membrane\b",
        r"\breprobed\b",
    ])
    loading_control_disclosed = "loading control" in text and contains_any(text, [r"\breus\w*\b", r"\bsame\b"])
    negated_same_membrane = contains_any(text, [
        r"does not state.{0,80}same membrane",
        r"not state.{0,80}same membrane",
        r"no shared membrane",
        r"no same membrane",
        r"without.{0,80}same membrane",
    ])
    same_membrane_claimed = not negated_same_membrane and contains_any(text, [
        r"\bsame membrane\b",
        r"\bshared membrane\b",
        r"\bmembrane was reprobed\b",
        r"\breprobed\b",
    ])
    same_experiment_claimed = not negated_same_membrane and contains_any(text, [
        r"\bsame experiment\b",
        r"\bsame membrane\b",
        r"\bshared membrane\b",
        r"\breprobed\b",
    ])
    source_available = has_source_data(package)
    raw_available = has_raw_images(package)
    risk_cap_tags = []
    if reuse_disclosed and loading_control_disclosed and (same_membrane_claimed or same_experiment_claimed) and (source_available or raw_available):
        risk_cap_tags.append("disclosed_legitimate_reuse")
    elif reuse_disclosed:
        risk_cap_tags.append("disclosed_unjustified_reuse")

    return {
        "reuse_disclosed": reuse_disclosed,
        "loading_control_disclosed": loading_control_disclosed,
        "same_experiment_claimed": same_experiment_claimed,
        "same_membrane_claimed": same_membrane_claimed,
        "source_data_available": source_available,
        "raw_images_available": raw_available,
        "risk_cap_tags": risk_cap_tags,
    }


def is_image_candidate(candidate: dict[str, Any]) -> bool:
    joined = " ".join(str(candidate.get(key, "")) for key in ("detector", "candidate_type"))
    return "image" in joined


def enrich_candidates(payload: dict[str, Any], package: Path) -> dict[str, Any]:
    validate_instance(payload, DETECTOR_SCHEMA, "detector output before contextual join")
    context = package_context(package)
    enriched = []
    for candidate in payload.get("candidates", []):
        item = dict(candidate)
        if is_image_candidate(item):
            evidence = dict(item.get("evidence", {}))
            evidence["context"] = context
            item["evidence"] = evidence
            item["context"] = context
            tags = list(item.get("risk_cap_tags", []) or [])
            for tag in context["risk_cap_tags"]:
                if tag not in tags:
                    tags.append(tag)
            item["risk_cap_tags"] = tags
        enriched.append(item)

    result = {
        "detector_name": "contextual_joiner",
        "detector_version": "0.3.0",
        "input": {
            "source_detector": payload.get("detector_name", ""),
            "package": str(package),
        },
        "candidates": enriched,
        "errors": [],
    }
    validate_instance(result, DETECTOR_SCHEMA, "contextually enriched candidates")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("contextual_candidates.json"))
    args = parser.parse_args()

    payload = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    result = enrich_candidates(payload, args.package.expanduser().resolve())
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "candidates": len(result["candidates"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
