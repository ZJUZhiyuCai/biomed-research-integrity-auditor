#!/usr/bin/env python3
"""Build local audit-package skeletons from a PMC OA manifest.

The script copies only local files named in the manifest. It does not download from PMC.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path


REDISTRIBUTABLE_TRUE = {"1", "true", "yes", "y"}


def copy_file(source: Path, target: Path) -> bool:
    if not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_tree_files(source_dir: Path, target_dir: Path) -> int:
    if not source_dir.is_dir():
        return 0
    count = 0
    for path in sorted(source_dir.rglob("*")):
        if path.is_file():
            target = target_dir / path.relative_to(source_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
    return count


def rel_path(value: str, base_dir: Path) -> Path | None:
    value = str(value or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def build_packages(manifest: Path, output_dir: Path, source_base: Path, allow_nonredistributable: bool) -> list[dict[str, object]]:
    results = []
    with manifest.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader, start=1):
            case_id = row.get("case_id") or f"pmc_oa_{idx:06d}"
            redistributable = str(row.get("redistributable", "")).strip().lower() in REDISTRIBUTABLE_TRUE
            package = output_dir / case_id
            package.mkdir(parents=True, exist_ok=True)
            copied = 0
            skipped = []

            if not redistributable and not allow_nonredistributable:
                skipped.append("marked non-redistributable; wrote metadata only")
            else:
                xml = rel_path(row.get("xml_path", ""), source_base)
                pdf = rel_path(row.get("pdf_path", ""), source_base)
                figures = rel_path(row.get("figures_dir", ""), source_base)
                supplementary = rel_path(row.get("supplementary_dir", ""), source_base)
                if xml and copy_file(xml, package / "manuscript" / xml.name):
                    copied += 1
                elif xml:
                    skipped.append(f"missing xml_path: {xml}")
                if pdf and copy_file(pdf, package / "manuscript" / pdf.name):
                    copied += 1
                elif pdf:
                    skipped.append(f"missing pdf_path: {pdf}")
                if figures:
                    copied += copy_tree_files(figures, package / "figures")
                    if not figures.exists():
                        skipped.append(f"missing figures_dir: {figures}")
                if supplementary:
                    copied += copy_tree_files(supplementary, package / "supplementary")
                    if not supplementary.exists():
                        skipped.append(f"missing supplementary_dir: {supplementary}")

            metadata = {
                "case_id": case_id,
                "doi": row.get("doi", ""),
                "pmid": row.get("pmid", ""),
                "pmcid": row.get("pmcid", ""),
                "license": row.get("license", ""),
                "license_url": row.get("license_url", ""),
                "redistributable": redistributable,
                "source_manifest": str(manifest),
                "notes": row.get("notes", ""),
            }
            (package / "PACKAGE_SOURCE_METADATA.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            results.append({
                "case_id": case_id,
                "package": str(package),
                "copied_files": copied,
                "skipped": skipped,
            })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-base", type=Path, default=Path("."))
    parser.add_argument("--allow-nonredistributable-copy", action="store_true")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    if not args.manifest.is_file():
        raise SystemExit(f"PMC OA manifest not found: {args.manifest}")
    results = build_packages(
        args.manifest.expanduser().resolve(),
        args.output_dir.expanduser().resolve(),
        args.source_base.expanduser().resolve(),
        args.allow_nonredistributable_copy,
    )
    payload = {"packages": results, "package_count": len(results)}
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
