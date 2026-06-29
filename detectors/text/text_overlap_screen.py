#!/usr/bin/env python3
"""Package-internal text-overlap detector for biomedical audit packages."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEXT_EXTS = {".txt", ".md", ".pdf"}
INCLUDED_PARTS = {
    "manuscript",
    "supplementary",
    "supplement",
    "prior_drafts",
    "prior_draft",
    "drafts",
    "thesis",
    "preprints",
    "preprint",
    "lab_previous_papers",
    "previous_papers",
}
SECTION_NAMES = {
    "abstract",
    "introduction",
    "methods",
    "materials and methods",
    "results",
    "discussion",
    "conclusion",
}
RISKY_SECTIONS = {"results", "abstract", "conclusion", "discussion"}
DISCLOSURE_PATTERNS = [
    r"\bpreprint\b",
    r"\bthesis\b",
    r"\bdisclos\w*\b",
    r"\bderived from\b",
    r"\badapted from\b",
    r"\breproduced from\b",
]


@dataclass
class Paragraph:
    doc_id: str
    path: str
    category: str
    paragraph_id: str
    section: str
    text: str
    tokens: list[str]
    shingles: set[tuple[str, ...]]


def path_category(path: Path, root: Path) -> str | None:
    rel_parts = path.relative_to(root).parts
    lowered_parts = [part.lower() for part in rel_parts]
    lowered_name = path.name.lower()
    for part in lowered_parts:
        if part in INCLUDED_PARTS:
            return part
    if any(part.startswith("supp") for part in lowered_parts):
        return "supplementary"
    if any(part in lowered_name for part in ("manuscript", "paper", "article", "maintext")):
        return "manuscript"
    return None


def collect_text_files(root: Path) -> list[tuple[Path, str]]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        category = path_category(path, root)
        if category:
            files.append((path, category))
    return files


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(tokens: list[str], ngram: int) -> set[tuple[str, ...]]:
    if len(tokens) < ngram:
        return set()
    return {tuple(tokens[idx:idx + ngram]) for idx in range(len(tokens) - ngram + 1)}


def is_heading(paragraph: str) -> str | None:
    clean = normalize_space(paragraph).lower().strip(":")
    if clean in SECTION_NAMES:
        return "methods" if clean == "materials and methods" else clean
    for section in SECTION_NAMES:
        if clean.startswith(section + ":"):
            return "methods" if section == "materials and methods" else section
    return None


def split_paragraphs(text: str) -> list[str]:
    blocks = [normalize_space(block) for block in re.split(r"\n\s*\n", text) if normalize_space(block)]
    if len(blocks) > 1:
        return blocks
    sentences = re.split(r"(?<=[.!?])\s+", normalize_space(text))
    return [item for item in sentences if len(tokenize(item)) >= 20]


def parse_paragraphs(root: Path, path: Path, category: str, ngram: int, min_tokens: int) -> list[Paragraph]:
    rel = str(path.relative_to(root))
    current_section = "unknown"
    paragraphs: list[Paragraph] = []
    for raw in split_paragraphs(read_text(path)):
        heading = is_heading(raw)
        if heading:
            current_section = heading
            body = re.sub(r"^[A-Za-z ]+:\s*", "", raw).strip()
            if len(tokenize(body)) < min_tokens:
                continue
            raw = body
        tokens = tokenize(raw)
        if len(tokens) < min_tokens:
            continue
        section = current_section
        lowered = raw.lower()
        for candidate in SECTION_NAMES:
            if lowered.startswith(candidate + ":"):
                section = "methods" if candidate == "materials and methods" else candidate
                break
        paragraphs.append(Paragraph(
            doc_id=rel,
            path=rel,
            category=category,
            paragraph_id=f"{rel}#p{len(paragraphs) + 1:03d}",
            section=section,
            text=normalize_space(raw),
            tokens=tokens,
            shingles=shingles(tokens, ngram),
        ))
    return paragraphs


def jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def overlap_examples(left: set[tuple[str, ...]], right: set[tuple[str, ...]], limit: int = 5) -> list[str]:
    return [" ".join(item) for item in sorted(left & right)[:limit]]


def has_disclosure(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in DISCLOSURE_PATTERNS)


def classify_overlap(left: Paragraph, right: Paragraph, score: float) -> tuple[str, str, list[str]]:
    combined = f"{left.text}\n{right.text}"
    disclosed = has_disclosure(combined)
    sections = {left.section, right.section}
    categories = {left.category, right.category}
    tags = ["text_overlap_candidate"]

    if "methods" in sections:
        return "methods_boilerplate_overlap", "R2_max", tags + ["methods_boilerplate_overlap"]

    if disclosed and categories & {"thesis", "preprints", "preprint"}:
        return "self_overlap_candidate", "R2_max", tags + ["self_overlap_candidate", "disclosed_prior_text_overlap"]

    if "results" in sections and score >= 0.45 and not disclosed:
        return "text_overlap_candidate", "R3_possible", tags + ["results_text_overlap"]

    if sections & {"abstract", "conclusion"} and score >= 0.50 and not disclosed:
        return "text_overlap_candidate", "R3_possible", tags + ["abstract_conclusion_overlap"]

    return "text_overlap_candidate", "R2_possible", tags


def allowed_pair(left: Paragraph, right: Paragraph) -> bool:
    if left.doc_id == right.doc_id:
        return False
    if left.category == right.category and left.category == "manuscript":
        return False
    return True


def candidate_from_pair(
    left: Paragraph,
    right: Paragraph,
    score: float,
    examples: list[str],
    idx: int,
) -> dict[str, Any]:
    candidate_type, risk_suggestion, tags = classify_overlap(left, right, score)
    return {
        "candidate_id": f"TEXTOVERLAP-{idx:04d}",
        "detector": "text.text_overlap_screen",
        "candidate_type": candidate_type,
        "locations": [left.paragraph_id, right.paragraph_id],
        "evidence": {
            "document_a": left.path,
            "document_b": right.path,
            "section_a": left.section,
            "section_b": right.section,
            "paragraph_id_a": left.paragraph_id,
            "paragraph_id_b": right.paragraph_id,
            "similarity_score": round(score, 6),
            "overlapping_ngram_examples": examples,
            "text_snippet_a": left.text[:360],
            "text_snippet_b": right.text[:360],
        },
        "evidence_strength": "candidate",
        "risk_suggestion": risk_suggestion,
        "risk_cap_tags": sorted(set(tags)),
        "benign_explanations": [
            "standard methods or protocol boilerplate may be legitimately reused",
            "text may derive from a disclosed thesis, preprint, protocol, or prior draft",
            "overlap requires section-aware human review before escalation",
        ],
        "required_materials": [
            "prior version or source document",
            "disclosure statement or citation trail",
            "journal policy context for text reuse",
        ],
        "recommended_action": "Review overlapping paragraphs with disclosure, citation, and journal-policy context; do not treat overlap as a misconduct verdict.",
        "requires_contextual_calibration": True,
    }


def scan(root: Path, ngram: int, threshold: float, min_tokens: int) -> dict[str, Any]:
    paragraphs: list[Paragraph] = []
    errors = []
    for path, category in collect_text_files(root):
        try:
            paragraphs.extend(parse_paragraphs(root, path, category, ngram, min_tokens))
        except Exception as exc:  # noqa: BLE001 - unreadable text should not abort package audit.
            errors.append({"path": str(path.relative_to(root)), "error": str(exc)})

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for idx, left in enumerate(paragraphs):
        for right in paragraphs[idx + 1:]:
            if not allowed_pair(left, right):
                continue
            key = tuple(sorted((left.paragraph_id, right.paragraph_id)))
            if key in seen:
                continue
            score = jaccard(left.shingles, right.shingles)
            if score < threshold:
                continue
            examples = overlap_examples(left.shingles, right.shingles)
            if not examples:
                continue
            seen.add(key)
            candidates.append(candidate_from_pair(left, right, score, examples, len(candidates) + 1))

    return {
        "detector_name": "text.text_overlap_screen",
        "detector_version": "0.4.1",
        "input": {
            "root": str(root),
            "ngram": ngram,
            "threshold": threshold,
            "min_tokens": min_tokens,
            "scope": "package_internal_and_lab_corpus_only",
        },
        "paragraphs_screened": len(paragraphs),
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--ngram", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--min-tokens", type=int, default=24)
    parser.add_argument("--output", type=Path, default=Path("text_overlap_candidates.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    result = scan(root, args.ngram, args.threshold, args.min_tokens)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "paragraphs_screened": result["paragraphs_screened"],
        "candidates": len(result["candidates"]),
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
