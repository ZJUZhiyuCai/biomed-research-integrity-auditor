#!/usr/bin/env python3
"""Build a writing and submission-readiness artifact for manuscript packages.

This module is deliberately separated from integrity detectors. It records
readiness checks for author workflow and journal submission preparation; it
does not emit calibrated findings, risk levels, or misconduct conclusions.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.csv_safety import csv_safe_row  # noqa: E402
from detectors.text.text_overlap_screen import read_text  # noqa: E402


TEXT_EXTS = {".txt", ".md", ".pdf"}
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|XXX|INSERT|PLACEHOLDER|AUTHOR QUERY)\b", re.I)
FIGURE_REF_RE = re.compile(r"\b(?:Fig\.?|Figure)\s+([A-Za-z0-9]+)", re.I)
REFERENCE_HEADING_RE = re.compile(r"^\s*(references|bibliography)\s*$", re.I | re.M)
STATUS_READY = "ready_for_manual_review"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_NOT_RUN = "not_run"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def collect_text_files(package: Path) -> list[Path]:
    return [
        path
        for path in sorted(package.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in TEXT_EXTS
        and "submission_qc_packet" not in path.parts
    ]


def read_text_bundle(package: Path) -> tuple[str, list[dict[str, str]]]:
    parts = []
    errors = []
    for path in collect_text_files(package):
        try:
            text = read_text(path)
            if text.strip():
                parts.append(f"\n\n===== {path.relative_to(package).as_posix()} =====\n\n{text}")
        except Exception as exc:  # noqa: BLE001 - readiness should record extraction gaps.
            errors.append({
                "path": path.relative_to(package).as_posix(),
                "error": str(exc),
            })
    return "\n".join(parts), errors


def sentence_lengths(text: str) -> list[int]:
    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    lengths = []
    for sentence in sentences:
        words = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", sentence)
        if words:
            lengths.append(len(words))
    return lengths


def extract_dois(text: str) -> list[str]:
    dois = []
    seen = set()
    for match in DOI_RE.finditer(text):
        doi = match.group(0).rstrip(".,;:)］】").lower()
        if doi not in seen:
            seen.add(doi)
            dois.append(doi)
    return dois


def extract_reference_section(text: str) -> str:
    match = REFERENCE_HEADING_RE.search(text)
    if not match:
        return ""
    return text[match.end():]


def check_crossref(doi: str, timeout: float = 8.0) -> dict[str, Any]:
    url = f"https://api.crossref.org/works/{doi}"
    result: dict[str, Any] = {
        "doi": doi,
        "provider": "crossref",
        "status": STATUS_NOT_RUN,
        "relation_flags": [],
        "title": "",
        "message": "",
    }
    try:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "biomed-research-integrity-auditor/0.6"})
    except requests.RequestException as exc:
        result.update({"status": STATUS_NOT_RUN, "message": f"Crossref request failed: {exc.__class__.__name__}"})
        return result
    if response.status_code == 404:
        result.update({"status": STATUS_NEEDS_ATTENTION, "message": "DOI not found by Crossref"})
        return result
    if response.status_code >= 400:
        result.update({"status": STATUS_NOT_RUN, "message": f"Crossref HTTP {response.status_code}"})
        return result
    try:
        message = response.json().get("message", {})
    except ValueError:
        result.update({"status": STATUS_NOT_RUN, "message": "Crossref returned non-JSON response"})
        return result
    relations = message.get("relation", {}) or {}
    relation_flags = [
        key
        for key in sorted(relations)
        if any(token in key.lower() for token in ("retract", "correct", "update", "expression"))
    ]
    titles = message.get("title", []) or []
    result.update({
        "status": STATUS_NEEDS_ATTENTION if relation_flags else STATUS_READY,
        "relation_flags": relation_flags,
        "title": str(titles[0]) if titles else "",
        "message": "Crossref metadata reviewed" if not relation_flags else "Crossref relation metadata needs manual review",
    })
    return result


def check_references(text: str, provider: str) -> dict[str, Any]:
    reference_text = extract_reference_section(text)
    dois = extract_dois(reference_text or text)
    provider_results = [check_crossref(doi) for doi in dois] if provider == "crossref" else []
    status = STATUS_READY if dois else STATUS_NEEDS_ATTENTION
    if provider == "crossref" and any(item["status"] == STATUS_NEEDS_ATTENTION for item in provider_results):
        status = STATUS_NEEDS_ATTENTION
    return {
        "status": status,
        "provider": provider,
        "references_section_detected": bool(reference_text),
        "doi_count": len(dois),
        "dois": dois,
        "provider_results": provider_results,
        "manual_note": (
            "DOI/retraction metadata is a reference-readiness aid only. Crossref relation metadata can be incomplete; "
            "manual reference review remains required."
        ),
    }


def check_language(text: str) -> dict[str, Any]:
    lengths = sentence_lengths(text)
    long_sentences = sum(1 for length in lengths if length >= 45)
    placeholders = sorted(set(match.group(0) for match in PLACEHOLDER_RE.finditer(text)))
    figure_refs = sorted(set(match.group(1) for match in FIGURE_REF_RE.finditer(text)))
    issues = []
    if long_sentences:
        issues.append("long_sentence_review")
    if placeholders:
        issues.append("placeholder_text_present")
    status = STATUS_NEEDS_ATTENTION if issues else STATUS_READY
    return {
        "status": status,
        "sentence_count": len(lengths),
        "long_sentence_count": long_sentences,
        "placeholder_tokens": placeholders,
        "figure_reference_tokens": figure_refs,
        "manual_note": "Language checks are lightweight readability prompts, not grammar certification.",
    }


def check_submission_files(package: Path) -> dict[str, Any]:
    expected = {
        "cover_letter": ["cover_letter", "cover-letter"],
        "title_page": ["title_page", "title-page"],
        "ethics_statement": ["ethics", "irb"],
        "data_availability": ["data_availability", "data-availability"],
        "author_contributions": ["author_contribution", "contributions"],
    }
    names = [path.relative_to(package).as_posix().lower() for path in package.rglob("*") if path.is_file()]
    rows = {}
    missing = []
    for key, tokens in expected.items():
        matched = [name for name in names if any(token in name for token in tokens)]
        rows[key] = matched
        if not matched:
            missing.append(key)
    return {
        "status": STATUS_NEEDS_ATTENTION if missing else STATUS_READY,
        "expected_items": rows,
        "missing_items": missing,
        "manual_note": "Submission-file checks are generic; journal-specific requirements still require manual review.",
    }


def build_writing_readiness(package: Path, reference_provider: str = "none") -> dict[str, Any]:
    text, extraction_errors = read_text_bundle(package)
    language = check_language(text) if text.strip() else {
        "status": STATUS_NEEDS_ATTENTION,
        "sentence_count": 0,
        "long_sentence_count": 0,
        "placeholder_tokens": [],
        "figure_reference_tokens": [],
        "manual_note": "No manuscript text was extracted for readability checks.",
    }
    references = check_references(text, reference_provider) if text.strip() else {
        "status": STATUS_NEEDS_ATTENTION,
        "provider": reference_provider,
        "references_section_detected": False,
        "doi_count": 0,
        "dois": [],
        "provider_results": [],
        "manual_note": "No manuscript text was extracted for reference checks.",
    }
    submission = check_submission_files(package)
    checks = [
        {
            "check_id": "language_readability",
            "label_en": "Language/readability prompts reviewed",
            "label_zh": "语言与可读性提示已检查",
            "status": language["status"],
            "recommended_action_en": "Resolve placeholders and review unusually long sentences before submission.",
            "recommended_action_zh": "投稿前处理占位文本，并人工复核过长句。",
        },
        {
            "check_id": "reference_doi_status",
            "label_en": "Reference DOI/status metadata reviewed",
            "label_zh": "参考文献 DOI/状态元数据已检查",
            "status": references["status"],
            "recommended_action_en": "Verify references manually; use Crossref checks as opt-in metadata only.",
            "recommended_action_zh": "人工核对参考文献；Crossref 只作为可选元数据辅助。",
        },
        {
            "check_id": "submission_files",
            "label_en": "Generic submission files reviewed",
            "label_zh": "通用投稿文件已检查",
            "status": submission["status"],
            "recommended_action_en": "Add or document missing cover letter, title page, ethics, data availability, and contribution files when required.",
            "recommended_action_zh": "按期刊要求补充或说明 cover letter、title page、伦理、数据可得性和作者贡献文件。",
        },
    ]
    needs_attention = sum(1 for item in checks if item["status"] == STATUS_NEEDS_ATTENTION)
    return {
        "schema_version": "0.1.0",
        "created_at": utc_now(),
        "scope": "writing_submission_readiness_only",
        "overall_status": STATUS_NEEDS_ATTENTION if needs_attention else STATUS_READY,
        "scope_note": (
            "Writing/submission readiness is separate from research-integrity findings. "
            "It does not change R0-R4 and is not a misconduct or correctness verdict."
        ),
        "checks": checks,
        "language_checks": language,
        "reference_checks": references,
        "submission_checks": submission,
        "text_extraction_errors": extraction_errors,
    }


def write_csv(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["check_id", "status", "label_en", "label_zh", "recommended_action_en", "recommended_action_zh"])
        writer.writeheader()
        for row in payload.get("checks", []) or []:
            writer.writerow(csv_safe_row(row, writer.fieldnames or []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--reference-provider", choices=["none", "crossref"], default="none")
    parser.add_argument("--output", type=Path, default=Path("writing_readiness.json"))
    parser.add_argument("--csv", type=Path, default=Path("writing_readiness.csv"))
    args = parser.parse_args()

    package = args.package_dir.expanduser().resolve()
    if not package.is_dir():
        raise SystemExit(f"Package directory not found: {package}")
    payload = build_writing_readiness(package, args.reference_provider)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(args.csv, payload)
    print(json.dumps({
        "output": str(args.output),
        "csv": str(args.csv),
        "overall_status": payload["overall_status"],
        "checks": len(payload["checks"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
