#!/usr/bin/env python3
"""Assemble repeatable release bundles for GitHub Releases."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
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
BRIA_BENCH_PRIVATE_DIRECTORIES = frozenset(
    {
        "runs",
        "results",
        "reviewer_packets",
        "reviewer-packets",
        "reviewer_packet",
        "reviewer-packet",
        "mappings",
        "reviewer_mappings",
        "reviewer-mappings",
        "api_cache",
        "api-cache",
        ".api_cache",
        ".api-cache",
        "cache",
        ".cache",
        "metrics",
        "local_metrics",
        "local-metrics",
        "seeds",
        "identity",
        "identities",
    }
)
BRIA_BENCH_PRIVATE_FILE_PATTERNS = (
    re.compile(r"run_summary\.json\Z"),
    re.compile(r"metrics(?:[-_].+)?\.json\Z"),
    re.compile(r"local_metrics.*\.json\Z"),
    re.compile(r"reviewer_mapping.*\.json\Z"),
    re.compile(r".*_mapping\.json\Z"),
    re.compile(r"reviewer[-_]packet.*\.(?:json|zip)\Z"),
    re.compile(r"seed.*\.(?:json|txt)\Z"),
    re.compile(r".*identity.*\.json\Z"),
    re.compile(r".*api[-_]cache.*\.json\Z"),
)
BRIA_BENCH_RELEASE_SUMMARY = re.compile(
    r"results/(?:release_summary|public_summary)_[A-Za-z0-9._-]+\.json\Z"
)
BRIA_BENCH_PUBLIC_SCHEMAS = frozenset(
    {
        "schemas/annotation.schema.json",
        "schemas/benchmark_manifest.schema.json",
        "schemas/metrics.schema.json",
        "schemas/observation.schema.json",
        "schemas/reviewer_form_completed.schema.json",
        "schemas/reviewer_form_template.schema.json",
        "schemas/reviewer_mapping.schema.json",
        "schemas/reviewer_packet_manifest.schema.json",
        "schemas/run_result.schema.json",
    }
)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return False
    if _is_bria_bench_private_artifact(rel):
        return False
    return path.name not in EXCLUDED_SUFFIXES and path.suffix not in EXCLUDED_SUFFIXES


def should_prune_directory(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in rel.parts):
        return True
    return _is_bria_bench_private_directory(rel)


def _bria_bench_local_parts(rel: Path) -> tuple[str, ...] | None:
    parts = rel.parts
    if len(parts) < 2 or parts[:2] != ("benchmarks", "bria_bench"):
        return None
    return parts[2:]


def _is_bria_bench_private_directory(rel: Path) -> bool:
    local_parts = _bria_bench_local_parts(rel)
    if not local_parts or local_parts == ("results",):
        return False
    return any(part in BRIA_BENCH_PRIVATE_DIRECTORIES for part in local_parts)


def _is_bria_bench_private_artifact(rel: Path) -> bool:
    local_parts = _bria_bench_local_parts(rel)
    if not local_parts:
        return False
    local = Path(*local_parts).as_posix()
    if (
        local == "results/.gitkeep"
        or BRIA_BENCH_RELEASE_SUMMARY.fullmatch(local)
        or local in BRIA_BENCH_PUBLIC_SCHEMAS
    ):
        return False
    if local_parts[0] == "schemas":
        return True
    if any(part in BRIA_BENCH_PRIVATE_DIRECTORIES for part in local_parts[:-1]):
        return True
    return any(
        pattern.fullmatch(local_parts[-1])
        for pattern in BRIA_BENCH_PRIVATE_FILE_PATTERNS
    )


def _iter_directory_files(path: Path) -> list[Path]:
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(path, topdown=True):
        current_path = Path(current)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if not should_prune_directory(current_path / name)
        )
        for name in sorted(file_names):
            child = current_path / name
            if child.is_file() and should_include(child):
                files.append(child)
    return sorted(files)


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for item in INCLUDE_PATHS:
        path = ROOT / item
        if not path.exists():
            continue
        if path.is_file() and should_include(path):
            files.append(path)
            continue
        files.extend(_iter_directory_files(path))
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
    prefix = f"biomed_research_integrity_auditor-{project_version()}"
    candidates = [dist_dir / f"{prefix}.tar.gz"]
    candidates.extend(sorted(dist_dir.glob(f"{prefix}-*.whl")))
    for artifact in candidates:
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
