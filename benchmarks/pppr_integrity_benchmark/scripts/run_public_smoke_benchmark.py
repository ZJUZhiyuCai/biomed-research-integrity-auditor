#!/usr/bin/env python3
"""Build and run a tiny public-data PPPR smoke benchmark.

The generated benchmark is intentionally local-only by default. It downloads a
small ORI image-forensics sample package and one PMC Open Access package, runs
the auditor, and evaluates the ORI unit label as a recall smoke test.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "benchmarks" / "pppr_integrity_benchmark"
PYTHON = sys.executable
ORI_BASE_URL = "https://ori.hhs.gov"
PMC_OA_BUCKET = "pmc-oa-opendata"
PMC_OA_HTTPS_BASE = "https://pmc-oa-opendata.s3.amazonaws.com"


@dataclass(frozen=True)
class ORISample:
    sample_id: str
    source_path: str
    issue_type: str
    modality: str
    notes: str

    @property
    def source_url(self) -> str:
        return urllib.parse.urljoin(ORI_BASE_URL, self.source_path)


DEFAULT_ORI_SAMPLES = (
    ORISample(
        "fig_a",
        "/sites/default/files/2018-04/fig_a.jpg",
        "image_local_reuse",
        "microscopy",
        "ORI public sample image A; paired with fig_b for public discrepancy smoke testing.",
    ),
    ORISample(
        "fig_b",
        "/sites/default/files/2018-04/fig_b.jpg",
        "image_local_reuse",
        "microscopy",
        "ORI public sample image B; paired with fig_a for public discrepancy smoke testing.",
    ),
    ORISample(
        "weak_background_large",
        "/sites/default/files/2018-04/weak_background_large.jpg",
        "same_image_copy_move",
        "western_blot_or_gel",
        "ORI public sample for weak-background image-forensics practice.",
    ),
)


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def download_url(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response:
        target.write_bytes(response.read())


def s3_to_https(uri: str) -> str:
    """Convert a PMC OA s3:// URI with optional md5 query into HTTPS."""
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "s3" or parsed.netloc != PMC_OA_BUCKET:
        raise ValueError(f"Unsupported PMC OA URI: {uri}")
    key = parsed.path.lstrip("/")
    return f"{PMC_OA_HTTPS_BASE}/{urllib.parse.quote(key)}"


def load_pmc_metadata(pmcid_version: str, cache_dir: Path) -> dict[str, Any]:
    metadata_url = f"{PMC_OA_HTTPS_BASE}/metadata/{urllib.parse.quote(pmcid_version)}.json"
    target = cache_dir / "pmc_metadata" / f"{pmcid_version}.json"
    download_url(metadata_url, target)
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["_metadata_url"] = metadata_url
    return payload


def safe_case_id(value: str) -> str:
    return value.lower().replace(".", "_").replace("-", "_")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def build_ori_package(output_root: Path, snapshot_date: str) -> dict[str, Any]:
    case_id = "ori_samples_public_images"
    package_dir = output_root / "packages" / case_id
    figures_dir = package_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "manuscript").mkdir(exist_ok=True)
    (package_dir / "manuscript" / "PUBLIC_SAMPLE_NOTE.txt").write_text(
        "Public ORI image-forensics samples for detector smoke testing. "
        "These files are public unit samples, not article-level misconduct labels.\n",
        encoding="utf-8",
    )
    rows = []
    downloaded = []
    for sample in DEFAULT_ORI_SAMPLES:
        suffix = Path(urllib.parse.urlparse(sample.source_url).path).suffix
        target = figures_dir / f"{sample.sample_id}{suffix}"
        download_url(sample.source_url, target)
        downloaded.append(str(target.relative_to(package_dir)))
        rows.append({
            "case_id": case_id,
            "source_url": sample.source_url,
            "sample_id": sample.sample_id,
            "issue_type": sample.issue_type,
            "modality": sample.modality,
            "local_path": str(target.relative_to(package_dir)),
            "label_strength": "ori_unit_sample",
            "snapshot_date": snapshot_date,
            "notes": sample.notes,
        })
    (package_dir / "PACKAGE_SOURCE_METADATA.json").write_text(
        json.dumps({
            "case_id": case_id,
            "source": "ORI public samples",
            "source_url": "https://ori.hhs.gov/samples",
            "snapshot_date": snapshot_date,
            "notes": (
                "ORI samples are used here as image-forensics unit tests. "
                "A detector miss is a recall gap, not evidence about an article."
            ),
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "case_id": case_id,
        "package_dir": str(package_dir),
        "downloaded_files": downloaded,
        "ori_manifest_rows": rows,
    }


def build_pmc_package(output_root: Path, pmcid_version: str, snapshot_date: str) -> dict[str, Any]:
    metadata = load_pmc_metadata(pmcid_version, output_root / "cache")
    case_id = f"pmc_oa_{safe_case_id(pmcid_version)}"
    package_dir = output_root / "packages" / case_id
    manuscript_dir = package_dir / "manuscript"
    figures_dir = package_dir / "figures"
    manuscript_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    copied_files = []
    for key, destination_dir in (("xml_url", manuscript_dir), ("pdf_url", manuscript_dir)):
        uri = metadata.get(key)
        if not uri:
            continue
        url = s3_to_https(str(uri))
        filename = Path(urllib.parse.urlparse(url).path).name
        target = destination_dir / filename
        download_url(url, target)
        copied_files.append(str(target.relative_to(package_dir)))

    for uri in metadata.get("media_urls", []) or []:
        url = s3_to_https(str(uri))
        filename = Path(urllib.parse.urlparse(url).path).name
        target = figures_dir / filename
        download_url(url, target)
        copied_files.append(str(target.relative_to(package_dir)))

    package_metadata = {
        "case_id": case_id,
        "pmcid_version": pmcid_version,
        "source": "PMC Open Access S3",
        "metadata_url": metadata.get("_metadata_url", ""),
        "pmcid": metadata.get("pmcid", ""),
        "pmid": str(metadata.get("pmid", "") or ""),
        "doi": metadata.get("doi", ""),
        "title": metadata.get("title", ""),
        "license": metadata.get("license_code", ""),
        "license_url": metadata.get("license_url", ""),
        "is_retracted": metadata.get("is_retracted", False),
        "snapshot_date": snapshot_date,
    }
    (package_dir / "PACKAGE_SOURCE_METADATA.json").write_text(
        json.dumps(package_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "case_id": case_id,
        "package_dir": str(package_dir),
        "copied_files": copied_files,
        "pmc_manifest_row": {
            "case_id": case_id,
            "doi": metadata.get("doi", ""),
            "pmid": str(metadata.get("pmid", "") or ""),
            "pmcid": metadata.get("pmcid", ""),
            "pmc_oa_url": metadata.get("_metadata_url", ""),
            "license": metadata.get("license_code", ""),
            "license_url": metadata.get("license_url", ""),
            "redistributable": "true",
            "xml_path": "manuscript/" + Path(str(metadata.get("xml_url", "")).split("?", 1)[0]).name if metadata.get("xml_url") else "",
            "pdf_path": "manuscript/" + Path(str(metadata.get("pdf_url", "")).split("?", 1)[0]).name if metadata.get("pdf_url") else "",
            "figures_dir": "figures",
            "supplementary_dir": "",
            "snapshot_date": snapshot_date,
            "notes": "Downloaded from PMC OA S3 for local smoke testing; no source/raw data included.",
        },
    }


def write_labels_and_splits(output_root: Path, case_ids: list[str], snapshot_date: str) -> Path:
    labels_dir = output_root / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    labels_path = labels_dir / "finding_level_labels.jsonl"
    label = {
        "case_id": "ori_samples_public_images",
        "label_id": "ORI-L0001",
        "source": "ori_unit_sample",
        "source_url": "https://ori.hhs.gov/samples",
        "paper_location": {
            "figure": "fig_a / fig_b",
            "panel": "",
            "caption_text": "ORI public sample pair used for discrepancy-finding practice.",
        },
        "issue_type": "image_local_reuse",
        "modality": "microscopy",
        "evidence": {
            "public_files": ["figures/fig_a.jpg", "figures/fig_b.jpg"],
            "snapshot_date": snapshot_date,
        },
        "label_strength": "ori_unit_sample",
        "expected_risk": "R2_or_R3",
        "benign_explanation_possible": True,
        "benign_explanation_type": "public training sample; requires source/raw images for article-level interpretation",
        "required_materials_to_resolve": ["original image files", "acquisition metadata", "processing history"],
        "notes": "Unit recall label only; not an article-level concern label.",
    }
    labels_path.write_text(json.dumps(label, ensure_ascii=False) + "\n", encoding="utf-8")

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


def run_auditor_and_eval(output_root: Path, labels_path: Path) -> dict[str, Any]:
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
        str(output_root / "public_smoke_eval.json"),
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
            "source_tables_screened": coverage.get("source_tables_screened", 0),
            "audit_coverage_gap": coverage.get("audit_coverage_gap", False),
            "modules_executed": coverage.get("modules_executed", []),
            "modules_not_executed": coverage.get("modules_not_executed", []),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "tmp" / "pppr_public_smoke")
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    parser.add_argument("--pmcid-version", action="append")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--keep-existing", action="store_true")
    args = parser.parse_args()

    output_root = args.output_root.expanduser().resolve()
    if not args.keep_existing:
        clean_dir(output_root)
    else:
        output_root.mkdir(parents=True, exist_ok=True)

    sources_dir = output_root / "sources"
    case_ids: list[str] = []
    ori = build_ori_package(output_root, args.snapshot_date)
    case_ids.append(str(ori["case_id"]))
    write_csv(
        sources_dir / "ori_samples_manifest.csv",
        ["case_id", "source_url", "sample_id", "issue_type", "modality", "local_path", "label_strength", "snapshot_date", "notes"],
        ori["ori_manifest_rows"],
    )

    pmc_rows = []
    pmc_cases = []
    pmcid_versions = args.pmcid_version or ["PMC10009402.1"]
    for pmcid_version in pmcid_versions:
        pmc = build_pmc_package(output_root, pmcid_version, args.snapshot_date)
        pmc_cases.append(pmc)
        case_ids.append(str(pmc["case_id"]))
        pmc_rows.append(pmc["pmc_manifest_row"])
    write_csv(
        sources_dir / "pmc_oa_manifest.csv",
        ["case_id", "doi", "pmid", "pmcid", "pmc_oa_url", "license", "license_url", "redistributable", "xml_path", "pdf_path", "figures_dir", "supplementary_dir", "snapshot_date", "notes"],
        pmc_rows,
    )

    labels_path = write_labels_and_splits(output_root, case_ids, args.snapshot_date)
    commands: dict[str, Any] = {}
    if not args.build_only:
        commands = run_auditor_and_eval(output_root, labels_path)

    summary = {
        "benchmark": "pppr_public_smoke",
        "snapshot_date": args.snapshot_date,
        "output_root": str(output_root),
        "sources": {
            "ori_samples": "https://ori.hhs.gov/samples",
            "pmc_oa_aws": "https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/",
            "pmc_oa_service": "https://pmc.ncbi.nlm.nih.gov/tools/oa-service/",
        },
        "case_ids": case_ids,
        "ori_package": ori,
        "pmc_packages": pmc_cases,
        "labels": str(labels_path),
        "commands": commands,
        "audit_results": summarize_outputs(output_root, case_ids) if not args.build_only else [],
        "scope_note": (
            "Public smoke labels are recall and coverage checks, not misconduct truth. "
            "PMC OA cases are material-coverage controls unless manually annotated."
        ),
    }
    summary_path = output_root / "public_smoke_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "summary": str(summary_path),
        "case_ids": case_ids,
        "audit_results": summary["audit_results"],
    }, indent=2, ensure_ascii=False))
    command_failures = [
        name for name, payload in commands.items()
        if isinstance(payload, dict) and payload.get("returncode", 0) != 0
    ]
    return 1 if command_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
