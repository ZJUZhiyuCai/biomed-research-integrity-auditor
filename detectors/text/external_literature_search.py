#!/usr/bin/env python3
"""External literature/library phrase-search detector for supplied package text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from detectors.text.text_overlap_screen import Paragraph, collect_text_files, normalize_space, parse_paragraphs, tokenize  # noqa: E402


PROVIDERS = {"fixture", "europepmc", "crossref"}
PROVIDER_ENDPOINTS = {
    "fixture": "local fixture file",
    "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    "crossref": "https://api.crossref.org/works",
}


def anchor_phrase(text: str, words: int) -> str | None:
    normalized = normalize_space(text)
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        tokens = tokenize(sentence)
        if len(tokens) >= words:
            return " ".join(tokens[:words])
    tokens = tokenize(normalized)
    if len(tokens) >= words:
        return " ".join(tokens[:words])
    return None


def collect_query_paragraphs(root: Path, ngram: int, min_tokens: int, max_queries: int) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    for path, category in collect_text_files(root):
        try:
            paragraphs.extend(parse_paragraphs(root, path, category, ngram, min_tokens))
        except Exception:
            continue
    priority = {"results": 0, "abstract": 1, "conclusion": 2, "discussion": 3, "unknown": 4, "methods": 5}
    paragraphs.sort(key=lambda item: (priority.get(item.section, 6), item.path, item.paragraph_id))
    return paragraphs[:max_queries]


def load_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_search(query: str, fixture: dict[str, Any]) -> list[dict[str, Any]]:
    query_results = fixture.get("queries", {})
    if query in query_results:
        return list(query_results[query])
    for key, results in query_results.items():
        if key in query or query in key:
            return list(results)
    return list(fixture.get("default_results", []))


def europepmc_search(query: str, rows: int, timeout: float) -> list[dict[str, Any]]:
    import requests

    response = requests.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": f'"{query}"', "format": "json", "pageSize": rows},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in payload.get("resultList", {}).get("result", [])[:rows]:
        full_text = item.get("fullTextUrlList") or {}
        full_text_urls = full_text.get("fullTextUrl") or [{}]
        results.append({
            "title": item.get("title"),
            "doi": item.get("doi"),
            "pmid": item.get("pmid"),
            "pmcid": item.get("pmcid"),
            "year": item.get("pubYear"),
            "source": item.get("source"),
            "url": full_text_urls[0].get("url"),
        })
    return results


def crossref_search(query: str, rows: int, timeout: float) -> list[dict[str, Any]]:
    import requests

    response = requests.get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": query, "rows": rows},
        timeout=timeout,
        headers={"User-Agent": "biomed-research-integrity-auditor/0.4"},
    )
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in payload.get("message", {}).get("items", [])[:rows]:
        title = item.get("title") or []
        results.append({
            "title": title[0] if title else None,
            "doi": item.get("DOI"),
            "year": (item.get("issued", {}).get("date-parts") or [[None]])[0][0],
            "source": "crossref",
            "url": item.get("URL"),
        })
    return results


def result_source_id(provider: str, result: dict[str, Any], index: int) -> str:
    for key in ("doi", "pmcid", "pmid", "url", "title"):
        value = result.get(key)
        if value:
            return f"{provider}:{key}:{value}"
    return f"{provider}:result:{index}"


def result_with_provenance(provider: str, result: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(result)
    item["external_record_provenance"] = {
        "source_id": result_source_id(provider, result, index),
        "provider": provider,
        "provider_endpoint": PROVIDER_ENDPOINTS.get(provider, provider),
        "result_index": index,
        "retrieval_basis": "exact phrase bibliographic search",
        "title": result.get("title"),
        "doi": result.get("doi"),
        "pmid": result.get("pmid"),
        "pmcid": result.get("pmcid"),
        "url": result.get("url"),
    }
    return item


def search_provider(provider: str, query: str, rows: int, timeout: float, fixture: dict[str, Any] | None) -> list[dict[str, Any]]:
    if provider == "fixture":
        if fixture is None:
            raise ValueError("fixture provider requires --fixture")
        return fixture_search(query, fixture)
    if provider == "europepmc":
        return europepmc_search(query, rows, timeout)
    if provider == "crossref":
        return crossref_search(query, rows, timeout)
    raise ValueError(f"unsupported provider: {provider}")


def candidate_from_results(
    paragraph: Paragraph,
    query: str,
    provider: str,
    results: list[dict[str, Any]],
    idx: int,
) -> dict[str, Any]:
    return {
        "candidate_id": f"EXTTEXT-{idx:04d}",
        "detector": "text.external_literature_search",
        "candidate_type": "external_text_match_candidate",
        "locations": [paragraph.paragraph_id],
        "evidence": {
            "provider": provider,
            "query": query,
            "query_provenance": {
                "query_source": "supplied_package_text",
                "source_document": paragraph.path,
                "section": paragraph.section,
                "paragraph_id": paragraph.paragraph_id,
                "anchor_strategy": "first sentence or paragraph prefix after normalization",
                "provider_endpoint": PROVIDER_ENDPOINTS.get(provider, provider),
                "search_mode": "exact phrase triage",
            },
            "document": paragraph.path,
            "section": paragraph.section,
            "paragraph_id": paragraph.paragraph_id,
            "text_snippet": paragraph.text[:360],
            "result_count": len(results),
            "results": [
                result_with_provenance(provider, result, index)
                for index, result in enumerate(results[:5], start=1)
            ],
        },
        "evidence_strength": "candidate",
        "risk_suggestion": "R2_or_R3_pending_context",
        "risk_cap_tags": ["external_text_search_candidate", "text_overlap_candidate"],
        "benign_explanations": [
            "the phrase may be a standard method, shared protocol, or disclosed prior text",
            "bibliographic search can return partial or coincidental matches requiring manual review",
            "journal policy, citation trail, and author disclosure determine significance",
        ],
        "required_materials": [
            "candidate external article or record",
            "citation and disclosure context",
            "journal text-reuse policy",
        ],
        "recommended_action": "Manually compare the external result with the supplied manuscript text before escalation.",
        "requires_contextual_calibration": True,
    }


def candidate_from_search_errors(provider: str, errors: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    locations = sorted({str(item.get("paragraph_id", "")) for item in errors if item.get("paragraph_id")})
    return {
        "candidate_id": f"EXTTEXT-GAP-{idx:04d}",
        "detector": "text.external_literature_search",
        "candidate_type": "external_literature_search_gap",
        "locations": locations or ["external_literature_search"],
        "evidence": {
            "provider": provider,
            "provider_endpoint": PROVIDER_ENDPOINTS.get(provider, provider),
            "message": "External phrase-search triage did not complete for the selected query set; do not treat this as clean external coverage.",
            "failed_query_count": len(errors),
            "errors": errors[:5],
            "provenance": {
                "query_source": "supplied_package_text",
                "retrieval_basis": "exact phrase bibliographic search",
                "coverage_effect": "external literature search coverage gap",
            },
        },
        "evidence_strength": "weak_signal",
        "risk_suggestion": "R1_max",
        "risk_cap_tags": ["external_literature_search_gap", "audit_coverage_gap", "completeness_gap"],
        "benign_explanations": [
            "the external provider may have been unavailable, rate-limited, or unreachable",
            "the supplied text may require manual search in publisher or institutional databases",
        ],
        "required_materials": [
            "successful external search logs or manually reviewed external-source records",
            "citation and disclosure context for any later manual matches",
        ],
        "recommended_action": "Repeat or manually document external literature search before treating external text coverage as complete.",
        "requires_contextual_calibration": True,
    }


def scan(
    root: Path,
    provider: str,
    fixture_path: Path | None,
    max_queries: int,
    rows: int,
    timeout: float,
    phrase_words: int,
    ngram: int,
    min_tokens: int,
) -> dict[str, Any]:
    fixture = load_fixture(fixture_path) if fixture_path else None
    paragraphs = collect_query_paragraphs(root, ngram, min_tokens, max_queries)
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    queries = []
    search_provenance = []
    for paragraph in paragraphs:
        query = anchor_phrase(paragraph.text, phrase_words)
        if not query:
            continue
        queries.append({"paragraph_id": paragraph.paragraph_id, "query": query})
        try:
            results = search_provider(provider, query, rows, timeout, fixture)
        except Exception as exc:  # noqa: BLE001 - external search failure is a coverage limitation, not a verdict.
            errors.append({"paragraph_id": paragraph.paragraph_id, "provider": provider, "query": query, "error": str(exc)})
            search_provenance.append({
                "paragraph_id": paragraph.paragraph_id,
                "provider": provider,
                "provider_endpoint": PROVIDER_ENDPOINTS.get(provider, provider),
                "query": query,
                "status": "error",
                "result_count": 0,
            })
            continue
        search_provenance.append({
            "paragraph_id": paragraph.paragraph_id,
            "provider": provider,
            "provider_endpoint": PROVIDER_ENDPOINTS.get(provider, provider),
            "query": query,
            "status": "ok",
            "result_count": len(results),
            "result_source_ids": [
                result_source_id(provider, result, index)
                for index, result in enumerate(results[:5], start=1)
            ],
        })
        if results:
            candidates.append(candidate_from_results(paragraph, query, provider, results, len(candidates) + 1))
    # Any failed query is a coverage limitation. Emit it even when other queries
    # returned matches, so partial external coverage is never reported as complete.
    if errors:
        candidates.append(candidate_from_search_errors(provider, errors, len(candidates) + 1))

    return {
        "detector_name": "text.external_literature_search",
        "detector_version": "0.2.0",
        "input": {
            "root": str(root),
            "provider": provider,
            "fixture": str(fixture_path) if fixture_path else None,
            "max_queries": max_queries,
            "rows": rows,
            "timeout": timeout,
            "phrase_words": phrase_words,
            "scope": "external_literature_phrase_search_triage",
        },
        "queries": queries,
        "external_search_provenance": search_provenance,
        "candidates": candidates,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package_dir", type=Path)
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="europepmc")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--max-queries", type=int, default=6)
    parser.add_argument("--rows", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--phrase-words", type=int, default=12)
    parser.add_argument("--ngram", type=int, default=5)
    parser.add_argument("--min-tokens", type=int, default=24)
    parser.add_argument("--output", type=Path, default=Path("external_literature_candidates.json"))
    args = parser.parse_args()

    root = args.package_dir.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Package directory not found: {root}")
    result = scan(
        root=root,
        provider=args.provider,
        fixture_path=args.fixture.expanduser().resolve() if args.fixture else None,
        max_queries=args.max_queries,
        rows=args.rows,
        timeout=args.timeout,
        phrase_words=args.phrase_words,
        ngram=args.ngram,
        min_tokens=args.min_tokens,
    )
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "queries": len(result["queries"]),
        "candidates": len(result["candidates"]),
        "errors": len(result["errors"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
