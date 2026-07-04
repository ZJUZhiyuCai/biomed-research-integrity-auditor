#!/usr/bin/env python3
"""Build and run the Lu/Xiongbin Lu public-concern benchmark subset.

The generated packages are local-only by default. This runner downloads public
article HTML, selected public figure exports, PMC OA XML/PDF files when
available, and metadata-only placeholders into tmp/. It does not copy PubPeer
comments or commit third-party article materials.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "benchmarks" / "pppr_integrity_benchmark"
PYTHON = sys.executable
PMC_OA_BUCKET = "pmc-oa-opendata"
PMC_OA_HTTPS_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"
JCI_BASE = "https://www.jci.org"
USER_AGENT = "biomed-integrity-auditor-public-benchmark/0.1"

CASE_MANIFEST = BENCH / "sources" / "lu_xiongbin_public_cases.csv"
LABELS = BENCH / "labels" / "lu_xiongbin_finding_level_labels.jsonl"

JCI_DOWNLOADS = {
    "lu_jci_atractylenolide_public_figures": {
        "article_id": "146832",
        "figures": ["2", "6"],
    },
    "lu_jci_cohesin_public_figures": {
        "article_id": "98727",
        "figures": ["8", "9"],
    },
}

PMC_DOWNLOADS = {
    "lu_stm_her2low_public_xml": "PMC8351376.1",
    "lu_acs_cold_nanomat_public_xml": "PMC5968444.1",
}


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def request_url(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def absolute_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return urllib.parse.urljoin(JCI_BASE, url)
    return url


def download_url(
    url: str,
    target: Path,
    *,
    require_prefix: bytes | None = None,
    decompress_gzip: bool = False,
) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with urllib.request.urlopen(request_url(url), timeout=90) as response:
        data = response.read()
        final_url = response.geturl()
        content_type = response.headers.get("content-type", "")
    if decompress_gzip and data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    check_data = data.lstrip() if require_prefix == b"<" else data
    if require_prefix and not check_data.startswith(require_prefix):
        raise ValueError(f"Downloaded {url} but content did not start with {require_prefix!r}")
    target.write_bytes(data)
    return {
        "url": url,
        "final_url": final_url,
        "target": str(target),
        "bytes": len(data),
        "content_type": content_type,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def s3_to_https(uri: str) -> str:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "s3" or parsed.netloc != PMC_OA_BUCKET:
        raise ValueError(f"Unsupported PMC OA URI: {uri}")
    key = parsed.path.lstrip("/")
    return f"{PMC_OA_HTTPS_BASE}/{urllib.parse.quote(key)}"


def load_rows(manifest: Path = CASE_MANIFEST) -> list[dict[str, str]]:
    with manifest.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_label_rows(labels_path: Path = LABELS) -> list[dict[str, Any]]:
    labels = []
    if not labels_path.is_file():
        return labels
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            labels.append(json.loads(line))
    return labels


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def case_note(row: dict[str, str], downloads: list[dict[str, Any]], skipped: list[str]) -> str:
    lines = [
        f"# Public Benchmark Case: {row['case_id']}",
        "",
        "This local package is for external public-material triage only.",
        "It is not a misconduct verdict and does not contain non-public source records.",
        "",
        f"- Original title: {row.get('original_title', '')}",
        f"- Original DOI: {row.get('original_doi', '')}",
        f"- Public status: {row.get('public_status', '')}",
        f"- Status source: {row.get('status_url', '')}",
        f"- Known public location(s): {row.get('known_public_locations', '')}",
        f"- Material strategy: {row.get('material_strategy', '')}",
        "",
        "Downloaded local materials:",
    ]
    if downloads:
        for item in downloads:
            target = item.get("target", "")
            lines.append(f"- {Path(str(target)).name} ({item.get('bytes', 0)} bytes)")
    else:
        lines.append("- none")
    if skipped:
        lines.append("")
        lines.append("Skipped or unavailable materials:")
        for item in skipped:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_package_metadata(package_dir: Path, row: dict[str, str], downloads: list[dict[str, Any]], skipped: list[str]) -> None:
    payload = {
        "case_id": row["case_id"],
        "case_kind": row.get("case_kind", ""),
        "original_title": row.get("original_title", ""),
        "original_doi": row.get("original_doi", ""),
        "original_pmid": row.get("original_pmid", ""),
        "original_pmcid": row.get("original_pmcid", ""),
        "journal": row.get("journal", ""),
        "public_status": row.get("public_status", ""),
        "status_date": row.get("status_date", ""),
        "status_url": row.get("status_url", ""),
        "known_public_locations": row.get("known_public_locations", ""),
        "material_strategy": row.get("material_strategy", ""),
        "benchmark_label_role": row.get("evaluation_role", ""),
        "local_only": True,
        "downloads": downloads,
        "skipped": skipped,
    }
    write_json(package_dir / "PACKAGE_SOURCE_METADATA.json", payload)
    (package_dir / "PUBLIC_STATUS_NOTE.md").write_text(
        case_note(row, downloads, skipped),
        encoding="utf-8",
    )


def jci_figure_image_url(article_id: str, figure_number: str) -> str:
    page_url = f"{JCI_BASE}/articles/view/{article_id}/figure/{figure_number}"
    with urllib.request.urlopen(request_url(page_url), timeout=60) as response:
        html = response.read().decode("utf-8", errors="replace")
    image_re = re.compile(r'<img[^>]+src="([^"]*JCI' + re.escape(article_id) + r'\.f' + re.escape(figure_number) + r'\.jpg)"')
    match = image_re.search(html)
    if not match:
        raise ValueError(f"Could not find JCI figure image for article {article_id} figure {figure_number}")
    return absolute_url(match.group(1))


def build_jci_package(row: dict[str, str], output_root: Path) -> dict[str, Any]:
    case_id = row["case_id"]
    plan = JCI_DOWNLOADS[case_id]
    article_id = str(plan["article_id"])
    package_dir = output_root / "packages" / case_id
    manuscript_dir = package_dir / "manuscript"
    figures_dir = package_dir / "figures"
    supplementary_dir = package_dir / "supplementary"
    downloads: list[dict[str, Any]] = []
    skipped: list[str] = []

    article_url = f"{JCI_BASE}/articles/view/{article_id}"
    downloads.append(download_url(article_url, manuscript_dir / f"JCI{article_id}.html"))

    sd_url = f"{JCI_BASE}/articles/view/{article_id}/sd/pdf/render/1"
    try:
        downloads.append(download_url(sd_url, supplementary_dir / f"JCI{article_id}.supplement.pdf", require_prefix=b"%PDF"))
    except Exception as exc:
        skipped.append(f"supplement PDF unavailable from {sd_url}: {exc}")

    for figure_number in plan["figures"]:
        try:
            image_url = jci_figure_image_url(article_id, str(figure_number))
            downloads.append(
                download_url(
                    image_url,
                    figures_dir / f"JCI{article_id}.f{figure_number}.jpg",
                )
            )
        except Exception as exc:
            skipped.append(f"figure {figure_number} unavailable from JCI article {article_id}: {exc}")

    write_package_metadata(package_dir, row, downloads, skipped)
    return {
        "case_id": case_id,
        "package_dir": str(package_dir),
        "download_count": len(downloads),
        "skipped": skipped,
    }


def load_pmc_metadata(pmcid_version: str, cache_dir: Path) -> dict[str, Any]:
    metadata_url = f"{PMC_OA_HTTPS_BASE}/metadata/{urllib.parse.quote(pmcid_version)}.json"
    target = cache_dir / "pmc_metadata" / f"{pmcid_version}.json"
    download = download_url(metadata_url, target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["_metadata_url"] = metadata_url
    payload["_metadata_download"] = download
    return payload


def pmc_filename(uri: str) -> str:
    return Path(urllib.parse.urlparse(s3_to_https(uri)).path).name


def build_pmc_package(row: dict[str, str], output_root: Path) -> dict[str, Any]:
    case_id = row["case_id"]
    pmcid_version = PMC_DOWNLOADS[case_id]
    metadata = load_pmc_metadata(pmcid_version, output_root / "cache")
    package_dir = output_root / "packages" / case_id
    manuscript_dir = package_dir / "manuscript"
    downloads: list[dict[str, Any]] = [metadata["_metadata_download"]]
    skipped: list[str] = []

    for key, prefix in (("xml_url", b"<"), ("pdf_url", b"%PDF")):
        uri = metadata.get(key)
        if not uri:
            skipped.append(f"PMC OA metadata has no {key}")
            continue
        url = s3_to_https(str(uri))
        target = manuscript_dir / pmc_filename(str(uri))
        try:
            downloads.append(download_url(url, target, require_prefix=prefix, decompress_gzip=(key == "xml_url")))
        except Exception as exc:
            skipped.append(f"{key} unavailable from PMC OA S3: {exc}")

    for uri in metadata.get("media_urls", []) or []:
        url = s3_to_https(str(uri))
        target = package_dir / "figures" / Path(urllib.parse.urlparse(url).path).name
        try:
            downloads.append(download_url(url, target))
        except Exception as exc:
            skipped.append(f"media unavailable from PMC OA S3: {exc}")
    if not metadata.get("media_urls"):
        skipped.append("PMC OA metadata has no media_urls")

    write_package_metadata(package_dir, row, downloads, skipped)
    return {
        "case_id": case_id,
        "package_dir": str(package_dir),
        "download_count": len(downloads),
        "skipped": skipped,
        "pmcid_version": pmcid_version,
        "pmc_title": metadata.get("title", ""),
    }


def build_metadata_only_package(row: dict[str, str], output_root: Path) -> dict[str, Any]:
    case_id = row["case_id"]
    package_dir = output_root / "packages" / case_id
    package_dir.mkdir(parents=True, exist_ok=True)
    downloads: list[dict[str, Any]] = []
    skipped = ["metadata-only row; original article materials are not downloaded or redistributed"]
    write_package_metadata(package_dir, row, downloads, skipped)
    return {
        "case_id": case_id,
        "package_dir": str(package_dir),
        "download_count": 0,
        "skipped": skipped,
    }


def build_package(row: dict[str, str], output_root: Path) -> dict[str, Any]:
    case_id = row["case_id"]
    if case_id in JCI_DOWNLOADS:
        return build_jci_package(row, output_root)
    if case_id in PMC_DOWNLOADS:
        return build_pmc_package(row, output_root)
    return build_metadata_only_package(row, output_root)


def write_local_metadata(output_root: Path, rows: list[dict[str, str]], case_ids: list[str]) -> Path:
    wanted = set(case_ids)
    local_sources = [row for row in rows if row["case_id"] in wanted]
    write_csv(output_root / "sources" / "lu_xiongbin_public_cases.csv", list(rows[0].keys()), local_sources)

    labels = [label for label in load_label_rows() if label.get("case_id") in wanted]
    labels_path = output_root / "labels" / "lu_xiongbin_finding_level_labels.jsonl"
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(
        "".join(json.dumps(label, ensure_ascii=False) + "\n" for label in labels),
        encoding="utf-8",
    )

    splits_dir = output_root / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    (splits_dir / "dev_cases.txt").write_text("\n".join(case_ids) + "\n", encoding="utf-8")
    (splits_dir / "test_cases.txt").write_text("", encoding="utf-8")
    (splits_dir / "hidden_cases.txt").write_text("", encoding="utf-8")
    return labels_path


def run_command(cmd: list[str]) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 3),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def run_auditor_and_eval(output_root: Path, labels_path: Path, scan_profile: str) -> dict[str, Any]:
    audit_outputs = output_root / "audit_outputs"
    audit = run_command([
        PYTHON,
        "benchmarks/pppr_integrity_benchmark/scripts/run_auditor_on_benchmark.py",
        "--packages-dir",
        str(output_root / "packages"),
        "--output-dir",
        str(audit_outputs),
        "--split",
        str(output_root / "splits" / "dev_cases.txt"),
        "--mode",
        "external_public_material",
        "--scan-profile",
        scan_profile,
        "--summary",
        str(output_root / "benchmark_run_summary.json"),
    ])
    evaluation = run_command([
        PYTHON,
        "benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py",
        "--labels",
        str(labels_path),
        "--outputs-root",
        str(audit_outputs),
        "--output",
        str(output_root / "lu_public_eval.json"),
    ])
    return {"audit": audit, "evaluation": evaluation}


def summarize_outputs(output_root: Path, case_ids: list[str]) -> list[dict[str, Any]]:
    rows = []
    for case_id in case_ids:
        summary_path = output_root / "audit_outputs" / case_id / "AUDIT_JSON_SUMMARY.json"
        if not summary_path.is_file():
            rows.append({"case_id": case_id, "missing_summary": True})
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        coverage = summary.get("audit_coverage", {}) or {}
        rows.append({
            "case_id": case_id,
            "overall_risk": summary.get("overall_risk"),
            "finding_count": len(summary.get("findings", []) or []),
            "image_panels_screened": coverage.get("image_panels_screened", 0),
            "image_screening_input_files": coverage.get("image_screening_input_files", 0),
            "image_screening_derived_images": coverage.get("image_screening_derived_images", 0),
            "keypoint_pairs_screened": coverage.get("keypoint_pairs_screened", 0),
            "keypoint_candidates": coverage.get("keypoint_candidates", 0),
            "composite_image_like_panels_screened": coverage.get("local_patch_composite_image_like_panels_screened", 0),
            "chart_text_axis_tiles_suppressed": coverage.get("local_patch_chart_text_axis_tiles_suppressed", 0),
            "source_tables_screened": coverage.get("source_tables_screened", 0),
            "audit_coverage_gap": coverage.get("audit_coverage_gap", False),
            "modules_executed": coverage.get("modules_executed", []),
            "modules_not_executed": coverage.get("modules_not_executed", []),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "tmp" / "lu_xiongbin_public_benchmark")
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--case-id", action="append", help="Limit to one or more case ids from the Lu public manifest.")
    parser.add_argument("--scan-profile", default="deep", choices=["quick", "standard", "deep"])
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--keep-existing", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    if not args.keep_existing:
        clean_dir(output_root)
    else:
        output_root.mkdir(parents=True, exist_ok=True)

    rows = load_rows()
    if args.case_id:
        wanted = set(args.case_id)
        rows = [row for row in rows if row["case_id"] in wanted]
        missing = sorted(wanted - {row["case_id"] for row in rows})
        if missing:
            raise SystemExit(f"Unknown Lu benchmark case id(s): {', '.join(missing)}")
    case_ids = [row["case_id"] for row in rows]

    build_results = [build_package(row, output_root) for row in rows]
    labels_path = write_local_metadata(output_root, load_rows(), case_ids)

    run_results: dict[str, Any] | None = None
    if not args.build_only:
        run_results = run_auditor_and_eval(output_root, labels_path, args.scan_profile)

    summary = {
        "benchmark": "lu_xiongbin_public_concern_subset",
        "snapshot_date": args.snapshot_date,
        "case_count": len(case_ids),
        "cases": case_ids,
        "build_results": build_results,
        "run_results": run_results,
        "output_rows": summarize_outputs(output_root, case_ids) if run_results else [],
        "scope_note": (
            "This benchmark subset uses public status/location evidence for quality-control evaluation. "
            "Labels are reference-only until public-material observations are independently verified. "
            "No PubPeer comments, non-public source records, or third-party article materials are committed."
        ),
    }
    summary_path = output_root / "lu_public_benchmark_summary.json"
    write_json(summary_path, summary)
    print(json.dumps({
        "summary": str(summary_path),
        "case_count": len(case_ids),
        "build_only": args.build_only,
        "scan_profile": args.scan_profile,
    }, indent=2))

    if run_results and (run_results["audit"]["returncode"] != 0 or run_results["evaluation"]["returncode"] != 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
