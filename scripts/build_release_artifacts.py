#!/usr/bin/env python3
"""Assemble repeatable release bundles for GitHub Releases."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import zipfile

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "release"
NORMALIZED_ARCHIVE_EPOCH = 315532800
NORMALIZED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
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
    re.compile(r"run[-_]summary\.json\Z"),
    re.compile(r"metrics(?:[-_].+)?\.json\Z"),
    re.compile(r"local[-_]metrics.*\.json\Z"),
    re.compile(r"reviewer[-_]mapping.*\.json\Z"),
    re.compile(r".*[-_]mapping\.json\Z"),
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


def _write_normalized_zip_member(
    archive: zipfile.ZipFile,
    source: Path,
    archive_name: str,
) -> None:
    info = zipfile.ZipInfo(archive_name, date_time=NORMALIZED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if source.stat().st_mode & 0o111 else 0o644
    info.external_attr = (stat.S_IFREG | mode) << 16
    archive.writestr(info, source.read_bytes())


def _normalize_zip_archive(source: Path, target: Path) -> None:
    with (
        zipfile.ZipFile(source, "r") as input_archive,
        zipfile.ZipFile(
            target,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as output_archive,
    ):
        for source_info in sorted(input_archive.infolist(), key=lambda item: item.filename):
            is_directory = source_info.is_dir()
            filename = source_info.filename.rstrip("/") + "/" if is_directory else source_info.filename
            target_info = zipfile.ZipInfo(filename, date_time=NORMALIZED_ZIP_TIMESTAMP)
            target_info.compress_type = zipfile.ZIP_STORED if is_directory else zipfile.ZIP_DEFLATED
            target_info.create_system = 3
            mode = 0o755 if is_directory or (source_info.external_attr >> 16) & 0o111 else 0o644
            file_type = stat.S_IFDIR if is_directory else stat.S_IFREG
            target_info.external_attr = (file_type | mode) << 16
            data = b"" if is_directory else input_archive.read(source_info)
            output_archive.writestr(target_info, data)


def _normalize_tar_gz_archive(source: Path, target: Path) -> None:
    with (
        tarfile.open(source, "r:gz") as input_archive,
        target.open("wb") as raw_output,
        gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_output,
            mtime=NORMALIZED_ARCHIVE_EPOCH,
        ) as compressed_output,
        tarfile.open(
            fileobj=compressed_output,
            mode="w",
            format=tarfile.PAX_FORMAT,
        ) as output_archive,
    ):
        for source_info in sorted(input_archive.getmembers(), key=lambda item: item.name):
            target_info = tarfile.TarInfo(source_info.name)
            target_info.type = source_info.type
            target_info.linkname = source_info.linkname
            target_info.size = source_info.size if source_info.isfile() else 0
            target_info.mode = (
                0o755
                if source_info.isdir() or source_info.mode & 0o111
                else 0o644
            )
            target_info.mtime = NORMALIZED_ARCHIVE_EPOCH
            target_info.uid = 0
            target_info.gid = 0
            target_info.uname = ""
            target_info.gname = ""
            target_info.devmajor = source_info.devmajor
            target_info.devminor = source_info.devminor
            if source_info.isfile():
                extracted = input_archive.extractfile(source_info)
                if extracted is None:
                    raise ValueError(f"Could not read sdist member: {source_info.name}")
                with extracted:
                    output_archive.addfile(target_info, extracted)
            else:
                output_archive.addfile(target_info)


def write_zip(output: Path, files: list[Path], prefix: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            archive_name = (Path(prefix) / path.relative_to(ROOT)).as_posix()
            _write_normalized_zip_member(archive, path, archive_name)


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
            if artifact.suffix == ".whl":
                _normalize_zip_archive(artifact, target)
            else:
                _normalize_tar_gz_archive(artifact, target)
            copied.append(target)
    return copied


def write_frontend_zip(output_dir: Path, version: str) -> Path | None:
    dist = ROOT / "webapp" / "frontend" / "dist"
    if not dist.exists():
        return None
    files = [path for path in sorted(dist.rglob("*")) if path.is_file()]
    output = output_dir / f"biomed-research-integrity-auditor-webapp-dist-{version}.zip"
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in files:
            _write_normalized_zip_member(
                archive,
                path,
                path.relative_to(dist).as_posix(),
            )
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
