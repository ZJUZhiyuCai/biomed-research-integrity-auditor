#!/usr/bin/env python3
"""Assemble repeatable release bundles for GitHub Releases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "release"
INCLUDE_PATHS = (
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "requirements.txt",
    "pyproject.toml",
    "MANIFEST.in",
    "Makefile",
    "schemas",
    "skill",
    "scripts",
    "detectors",
    "calibrators",
    "provenance",
    "webapp",
    "docs",
    "examples",
    "benchmarks",
    "evals",
)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "audit_outputs",
    "tmp",
    ".pytest_cache",
    "test-results",
    "playwright-report",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".DS_Store"}


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    return path.name not in EXCLUDED_SUFFIXES and path.suffix not in EXCLUDED_SUFFIXES


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for item in INCLUDE_PATHS:
        path = ROOT / item
        if not path.exists():
            continue
        if path.is_file() and should_include(path):
            files.append(path)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and should_include(child):
                files.append(child)
    return files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_zip(output: Path, files: list[Path], prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, Path(prefix) / path.relative_to(ROOT))


def copy_dist_artifacts(output_dir: Path) -> list[Path]:
    copied: list[Path] = []
    dist_dir = ROOT / "dist"
    if not dist_dir.exists():
        return copied
    for artifact in sorted(dist_dir.glob("biomed_research_integrity_auditor-*")):
        if artifact.is_file():
            target = output_dir / artifact.name
            target.write_bytes(artifact.read_bytes())
            copied.append(target)
    return copied


def write_frontend_zip(output_dir: Path, version: str) -> Path | None:
    dist = ROOT / "webapp" / "frontend" / "dist"
    if not dist.exists():
        return None
    files = [path for path in sorted(dist.rglob("*")) if path.is_file()]
    output = output_dir / f"biomed-research-integrity-auditor-webapp-dist-{version}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(dist))
    return output


def write_manifest(output_dir: Path, artifacts: list[Path], version: str) -> None:
    rows = [
        {
            "artifact": artifact.name,
            "bytes": artifact.stat().st_size,
            "sha256": sha256(artifact),
        }
        for artifact in artifacts
    ]
    manifest = {
        "project": "biomed-research-integrity-auditor",
        "version": version,
        "artifacts": rows,
        "scope_note": (
            "These are build/release artifacts. Registry publication to PyPI/Homebrew "
            "requires maintainer credentials or trusted-publishing configuration."
        ),
    }
    (output_dir / "release_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "SHA256SUMS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["artifact", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    version = project_version()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"biomed-research-integrity-auditor-{version}"
    source_zip = output_dir / f"{prefix}-source-bundle.zip"
    write_zip(source_zip, iter_source_files(), prefix)

    artifacts = [source_zip]
    artifacts.extend(copy_dist_artifacts(output_dir))
    frontend_zip = write_frontend_zip(output_dir, version)
    if frontend_zip is not None:
        artifacts.append(frontend_zip)

    write_manifest(output_dir, artifacts, version)
    print(f"Release artifacts written to {output_dir}")
    for artifact in artifacts:
        print(f"  {artifact.name}  {sha256(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
