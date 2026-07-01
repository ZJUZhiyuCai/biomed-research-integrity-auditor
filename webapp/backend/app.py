"""FastAPI wrapper around the existing biomedical audit CLI.

The backend deliberately does not recompute, reinterpret, or mutate integrity
results. It starts the validated CLI, persists job state, and serves the JSON
and evidence artifacts that the pipeline writes.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from typing import Any, Optional
from uuid import uuid4
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from provenance.panel_modality import CANONICAL_MODALITIES, normalize_modality  # noqa: E402
from scripts.csv_safety import csv_safe_row  # noqa: E402

DEFAULT_RUNS_ROOT = ROOT / "audit_outputs" / "webapp"
MODES = {"internal_presubmission", "external_public_material", "response_to_concern"}
SCAN_PROFILES = {"quick", "standard", "deep"}
EXTERNAL_PROVIDERS = {"auto", "none", "fixture", "europepmc", "crossref"}
REFERENCE_CHECK_PROVIDERS = {"none", "crossref"}
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
INVENTORY_MAX_FILES = 5000
INVENTORY_MAX_DEPTH = 12
RECOMMENDED_PACKAGE_DIRS = [
    "figures",
    "raw_images",
    "figure_assembly",
    "source_data",
    "protocols",
    "statistics_code",
    "supplementary",
    "ethics_irb",
]
ASSEMBLY_MANIFEST_COLUMNS = ["figure_panel", "source_record", "relation_type", "modality", "notes"]
ALLOWED_MANIFEST_RELATIONS = {
    "declared_derived_from",
    "same_field_different_channel",
    "same_membrane_reprobe",
}
RELATION_ALLOWED_SOURCE_ROLES = {
    "declared_derived_from": {"raw_images", "source_data"},
    "same_field_different_channel": {"figures", "raw_images"},
    "same_membrane_reprobe": {"figures", "raw_images"},
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SOURCE_DATA_SUFFIXES = {".csv", ".tsv", ".xlsx"}
AUDIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")


class AuditCreateRequest(BaseModel):
    package_path: Optional[str] = Field(default=None, description="Local package directory to audit.")
    mode: str = "internal_presubmission"
    scan_profile: str = "standard"
    domains: str = "wetlab,animal,cell"
    external_literature_provider: str = "auto"
    reference_check_provider: str = "none"
    compare_to_audit_id: Optional[str] = Field(
        default=None,
        description="Optional completed audit id to compare this run against.",
    )


class PackagePathRequest(BaseModel):
    package_path: str = Field(description="Local package directory to inspect or scaffold.")


class ManifestRowInput(BaseModel):
    figure_panel: str
    source_record: str
    relation_type: str = "declared_derived_from"
    modality: str = ""
    notes: str = ""


class AssemblyManifestRequest(BaseModel):
    package_path: str
    rows: list[ManifestRowInput] = Field(default_factory=list)


@dataclass
class WebappSettings:
    repo_root: Path
    runs_root: Path

    @property
    def audits_dir(self) -> Path:
        return self.runs_root / "audits"

    @property
    def packages_dir(self) -> Path:
        return self.runs_root / "uploaded_packages"


@dataclass
class AuditJob:
    audit_id: str
    status: str
    package_path: str
    mode: str
    scan_profile: str
    domains: str
    external_literature_provider: str
    reference_check_provider: str
    output_dir: str
    created_at: float
    updated_at: float
    command: list[str]
    returncode: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: Optional[str] = None
    pipeline_summary: Optional[dict[str, Any]] = None
    uploaded_package_dir: Optional[str] = None


def create_app(output_root: Optional[Path] = None) -> FastAPI:
    settings = WebappSettings(ROOT, (output_root or DEFAULT_RUNS_ROOT).expanduser().resolve())
    settings.audits_dir.mkdir(parents=True, exist_ok=True)
    settings.packages_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Biomedical Research Integrity Self-Audit",
        version="0.6.2",
        description="Local-first wrapper around scripts/audit_package.py.",
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": app.version,
            "runs_root": str(settings.runs_root),
            "local_first": True,
        }

    @app.get("/api/audits")
    def list_audits() -> dict[str, Any]:
        jobs = [load_job(settings, audit_dir.name) for audit_dir in sorted(settings.audits_dir.iterdir()) if audit_dir.is_dir()]
        jobs = [job for job in jobs if job is not None]
        jobs.sort(key=lambda job: job.updated_at, reverse=True)
        return {"audits": [job_response(settings, job) for job in jobs]}

    @app.post("/api/audits")
    def create_audit(request: AuditCreateRequest) -> dict[str, Any]:
        if not request.package_path:
            raise HTTPException(status_code=400, detail="package_path is required for JSON audit creation")
        package = Path(request.package_path).expanduser().resolve()
        if not package.exists() or not package.is_dir():
            raise HTTPException(status_code=404, detail=f"Package directory not found: {package}")
        compare_to = resolve_compare_to(settings, request.compare_to_audit_id)
        job = prepare_job(
            settings,
            package,
            request.mode,
            request.scan_profile,
            request.domains,
            request.external_literature_provider,
            request.reference_check_provider,
            compare_to=compare_to,
        )
        save_job(settings, job)
        threading.Thread(target=run_job, args=(settings, job.audit_id), daemon=True).start()
        return job_response(settings, job)

    @app.post("/api/audits/upload")
    async def create_audit_from_zip(
        file: UploadFile = File(...),
        mode: str = Form("internal_presubmission"),
        scan_profile: str = Form("standard"),
        domains: str = Form("wetlab,animal,cell"),
        external_literature_provider: str = Form("auto"),
        reference_check_provider: str = Form("none"),
        compare_to_audit_id: Optional[str] = Form(None),
    ) -> dict[str, Any]:
        audit_id = new_audit_id(file.filename or "uploaded_package")
        upload_root = settings.packages_dir / audit_id
        upload_root.mkdir(parents=True, exist_ok=False)
        zip_path = upload_root / "package.zip"
        size = 0
        with zip_path.open("wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ZIP_BYTES:
                    shutil.rmtree(upload_root, ignore_errors=True)
                    raise HTTPException(status_code=413, detail="Uploaded zip exceeds the local size limit")
                handle.write(chunk)
        package = upload_root / "package"
        try:
            extract_zip_safely(zip_path, package)
        except ValueError as exc:
            shutil.rmtree(upload_root, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        compare_to = resolve_compare_to(settings, compare_to_audit_id)
        job = prepare_job(
            settings,
            package,
            mode,
            scan_profile,
            domains,
            external_literature_provider,
            reference_check_provider,
            audit_id=audit_id,
            uploaded_package_dir=upload_root,
            compare_to=compare_to,
        )
        save_job(settings, job)
        threading.Thread(target=run_job, args=(settings, job.audit_id), daemon=True).start()
        return job_response(settings, job)

    @app.post("/api/packages/inspect")
    def inspect_package(request: PackagePathRequest) -> dict[str, Any]:
        package = require_package_dir(request.package_path)
        return {"inventory": package_inventory(package)}

    @app.post("/api/packages/scaffold")
    def scaffold_package(request: PackagePathRequest) -> dict[str, Any]:
        package = require_scaffold_target(request.package_path)
        package.mkdir(parents=True, exist_ok=True)
        for dirname in RECOMMENDED_PACKAGE_DIRS:
            (package / dirname).mkdir(exist_ok=True)
        note_path = package / "PACKAGE_NOTE.txt"
        if not note_path.exists():
            note_path.write_text(
                (
                    "Local self-audit package scaffold.\n\n"
                    "Add exported figure panels under figures/, raw/source images under raw_images/,\n"
                    "source tables under source_data/, and declare figure-source relationships in\n"
                    "figure_assembly/assembly_manifest.csv. Manifest declarations are audit material\n"
                    "only; the audit pipeline cross-checks them against supplied files.\n"
                ),
                encoding="utf-8",
            )
        return {"inventory": package_inventory(package)}

    @app.post("/api/packages/assembly-manifest")
    def save_assembly_manifest(request: AssemblyManifestRequest) -> dict[str, Any]:
        package = require_package_dir(request.package_path)
        rows = [validated_manifest_row(package, row) for row in request.rows]
        manifest_dir = package / "figure_assembly"
        manifest_dir.mkdir(exist_ok=True)
        manifest_path = manifest_dir / "assembly_manifest.csv"
        with manifest_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ASSEMBLY_MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(csv_safe_row(row, ASSEMBLY_MANIFEST_COLUMNS) for row in rows)
        return {
            "manifest_path": str(manifest_path),
            "rows_written": len(rows),
            "inventory": package_inventory(package),
        }

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        refresh_pipeline_summary(job)
        save_job(settings, job)
        return job_response(settings, job)

    @app.get("/api/audits/{audit_id}/summary")
    def get_summary(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        output_dir = Path(job.output_dir)
        return {
            "audit": job_response(settings, job),
            "audit_summary": read_json_artifact(output_dir / "AUDIT_JSON_SUMMARY.json"),
            "coverage": read_json_artifact(output_dir / "coverage.json"),
            "calibrated_findings": read_json_artifact(output_dir / "calibrated_findings.json"),
            "pipeline_summary": read_json_artifact(output_dir / "pipeline_summary.json"),
            "claim_coverage": read_optional_json_artifact(output_dir / "claim_coverage.json"),
            "action_trackers": {
                "unresolved": read_csv_artifact(output_dir / "unresolved_actions.csv"),
                "resolved": read_csv_artifact(output_dir / "resolved_actions.csv"),
                "accepted_with_reason": read_csv_artifact(output_dir / "accepted_with_reason.csv"),
            },
            "correction_plan": read_csv_artifact(output_dir / "correction_plan.csv"),
            "re_audit_diff": read_optional_json_artifact(output_dir / "re_audit_diff.json"),
            "submission_qc_packet": submission_qc_packet_summary(output_dir),
            "writing_readiness": read_optional_json_artifact(output_dir / "writing_readiness.json"),
        }

    @app.get("/api/audits/{audit_id}/report.md")
    def get_report(audit_id: str) -> PlainTextResponse:
        job = require_job(settings, audit_id)
        report = safe_artifact(Path(job.output_dir), "audit-report.md")
        if not report.is_file():
            raise HTTPException(status_code=404, detail="Report has not been generated yet")
        return PlainTextResponse(report.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")

    @app.get("/api/audits/{audit_id}/evidence/{relpath:path}")
    def get_evidence(audit_id: str, relpath: str) -> FileResponse:
        job = require_job(settings, audit_id)
        evidence_base = (Path(job.output_dir) / "evidence").resolve()
        evidence_path = safe_join(evidence_base, relpath)
        if not evidence_path.is_file():
            raise HTTPException(status_code=404, detail="Evidence file not found for this audit")
        return FileResponse(evidence_path)

    @app.get("/api/audits/{audit_id}/artifact/{relpath:path}")
    def get_artifact(audit_id: str, relpath: str) -> FileResponse:
        job = require_job(settings, audit_id)
        if not artifact_download_allowed(relpath):
            raise HTTPException(status_code=400, detail="Artifact is not exposed by the webapp")
        artifact_path = safe_artifact(Path(job.output_dir), relpath)
        if not artifact_path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file not found for this audit")
        return FileResponse(artifact_path)

    @app.get("/api/audits/{audit_id}/submission-qc-packet.zip")
    def get_submission_qc_packet(audit_id: str) -> FileResponse:
        job = require_job(settings, audit_id)
        output_dir = Path(job.output_dir).resolve()
        packet_dir = safe_artifact(output_dir, "submission_qc_packet")
        if not packet_dir.is_dir():
            raise HTTPException(status_code=404, detail="Submission QC packet has not been generated yet")
        zip_path = output_dir / "submission_qc_packet.zip"
        write_packet_zip(packet_dir, zip_path)
        return FileResponse(zip_path, filename=f"{audit_id}-submission-qc-packet.zip")

    @app.delete("/api/audits/{audit_id}")
    def delete_audit(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        if job.status in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="Running audits cannot be deleted")
        shutil.rmtree(Path(job.output_dir), ignore_errors=True)
        if job.uploaded_package_dir:
            upload_dir = Path(job.uploaded_package_dir)
            if is_relative_to(upload_dir.resolve(), settings.packages_dir.resolve()):
                shutil.rmtree(upload_dir, ignore_errors=True)
        return {"deleted": audit_id}

    dist_dir = ROOT / "webapp" / "frontend" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")

    return app


def require_package_dir(package_path: str) -> Path:
    package = Path(package_path).expanduser().resolve()
    if not package.exists() or not package.is_dir():
        raise HTTPException(status_code=404, detail=f"Package directory not found: {package}")
    return package


def require_scaffold_target(package_path: str) -> Path:
    package = Path(package_path).expanduser().resolve()
    if package.exists() and not package.is_dir():
        raise HTTPException(status_code=400, detail=f"Scaffold target is not a directory: {package}")
    if not package.exists() and not package.parent.exists():
        raise HTTPException(status_code=404, detail=f"Parent directory not found: {package.parent}")
    return package


def package_inventory(package: Path) -> dict[str, Any]:
    folders = {dirname: (package / dirname).is_dir() for dirname in RECOMMENDED_PACKAGE_DIRS}
    files_by_role: dict[str, list[str]] = {
        "figures": [],
        "raw_images": [],
        "figure_assembly": [],
        "source_data": [],
        "protocols": [],
        "statistics_code": [],
        "supplementary": [],
        "ethics_irb": [],
        "other": [],
    }
    files, inventory_warnings, limit_reached = bounded_package_files(package)
    for path in files:
        rel = path.relative_to(package).as_posix()
        role = inventory_role(path.relative_to(package))
        files_by_role.setdefault(role, []).append(rel)
    manifest = read_assembly_manifest(package)
    return {
        "package_path": str(package),
        "exists": True,
        "folders": folders,
        "files_by_role": files_by_role,
        "file_counts": {key: len(value) for key, value in files_by_role.items()},
        "assembly_manifest": manifest,
        "relation_types": sorted(ALLOWED_MANIFEST_RELATIONS),
        "relation_allowed_source_roles": {
            key: sorted(value) for key, value in RELATION_ALLOWED_SOURCE_ROLES.items()
        },
        "modality_options": list(CANONICAL_MODALITIES),
        "inventory_warnings": inventory_warnings,
        "scan_limit_reached": limit_reached,
        "scan_limits": {
            "max_files": INVENTORY_MAX_FILES,
            "max_depth": INVENTORY_MAX_DEPTH,
        },
        "scope_note": (
            "Assembly-manifest rows are declarations for audit context only; "
            "the pipeline cross-checks them against supplied files."
        ),
    }


def bounded_package_files(package: Path) -> tuple[list[Path], list[str], bool]:
    files: list[Path] = []
    warnings: list[str] = []
    pending: list[tuple[Path, int]] = [(package, 0)]
    while pending:
        directory, depth = pending.pop(0)
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name.lower())
        except OSError as exc:
            rel = directory.relative_to(package).as_posix() if directory != package else "."
            warnings.append(f"Could not read {rel}: {exc.__class__.__name__}")
            continue
        for entry in entries:
            rel = entry.relative_to(package).as_posix()
            if entry.is_symlink():
                warnings.append(f"Skipped symlink: {rel}")
                continue
            if entry.is_dir():
                if depth >= INVENTORY_MAX_DEPTH:
                    warnings.append(f"Skipped directory beyond max depth {INVENTORY_MAX_DEPTH}: {rel}")
                    continue
                pending.append((entry, depth + 1))
                continue
            if not entry.is_file():
                continue
            files.append(entry)
            if len(files) >= INVENTORY_MAX_FILES:
                warnings.append(
                    f"Inventory stopped after {INVENTORY_MAX_FILES} files; choose a narrower package directory."
                )
                return files, warnings, True
    return files, warnings, False


def inventory_role(relative_path: Path) -> str:
    parts = relative_path.parts
    if not parts:
        return "other"
    top = parts[0]
    suffix = relative_path.suffix.lower()
    if top == "figures" and suffix in IMAGE_SUFFIXES:
        return "figures"
    if top == "raw_images" and suffix in IMAGE_SUFFIXES:
        return "raw_images"
    if top == "source_data" and suffix in SOURCE_DATA_SUFFIXES:
        return "source_data"
    if top in {
        "figure_assembly",
        "protocols",
        "statistics_code",
        "supplementary",
        "ethics_irb",
    }:
        return top
    return "other"


def read_assembly_manifest(package: Path) -> dict[str, Any]:
    manifest_path = package / "figure_assembly" / "assembly_manifest.csv"
    if not manifest_path.is_file():
        return {"path": None, "rows": [], "row_count": 0, "warnings": []}
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    with manifest_path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        missing = [col for col in ASSEMBLY_MANIFEST_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            warnings.append(f"Missing columns: {', '.join(missing)}")
        for row in reader:
            rows.append({col: str(row.get(col, "") or "") for col in ASSEMBLY_MANIFEST_COLUMNS})
    return {
        "path": manifest_path.relative_to(package).as_posix(),
        "rows": rows,
        "row_count": len(rows),
        "warnings": warnings,
    }


def validated_manifest_row(package: Path, row: ManifestRowInput) -> dict[str, str]:
    figure = validate_package_relative_file(package, row.figure_panel, "figure_panel")
    source = validate_package_relative_file(package, row.source_record, "source_record")
    relation_type = row.relation_type.strip()
    if relation_type not in ALLOWED_MANIFEST_RELATIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported relation_type: {relation_type}")
    figure_role = inventory_role(Path(figure))
    source_role = inventory_role(Path(source))
    if figure_role != "figures":
        raise HTTPException(status_code=400, detail="figure_panel must point to an image under figures/")
    allowed_source_roles = RELATION_ALLOWED_SOURCE_ROLES[relation_type]
    if source_role not in allowed_source_roles:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{relation_type} source_record must point to one of: "
                f"{', '.join(sorted(allowed_source_roles))}"
            ),
        )
    if source == figure:
        raise HTTPException(status_code=400, detail="source_record must differ from figure_panel")
    return {
        "figure_panel": figure,
        "source_record": source,
        "relation_type": relation_type,
        "modality": normalize_modality(row.modality),
        "notes": row.notes.strip(),
    }


def validate_package_relative_file(package: Path, value: str, field: str) -> str:
    if not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} is required")
    relative = Path(value.strip().replace("\\", "/"))
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        raise HTTPException(status_code=400, detail=f"Invalid package-relative path for {field}")
    candidate = (package / relative).resolve()
    if not is_relative_to(candidate, package.resolve()):
        raise HTTPException(status_code=400, detail=f"Invalid package-relative path for {field}")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Referenced file not found for {field}: {relative}")
    return relative.as_posix()


def validate_mode_profile_and_provider(mode: str, scan_profile: str, provider: str, reference_provider: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode}")
    if scan_profile not in SCAN_PROFILES:
        raise HTTPException(status_code=400, detail=f"Unsupported scan profile: {scan_profile}")
    if provider not in EXTERNAL_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported external literature provider: {provider}")
    if reference_provider not in REFERENCE_CHECK_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported reference check provider: {reference_provider}")


def new_audit_id(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", Path(name).stem.lower()).strip("-") or "audit"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug[:28]}-{uuid4().hex[:8]}"


def prepare_job(
    settings: WebappSettings,
    package: Path,
    mode: str,
    scan_profile: str,
    domains: str,
    external_literature_provider: str,
    reference_check_provider: str,
    audit_id: Optional[str] = None,
    uploaded_package_dir: Optional[Path] = None,
    compare_to: Optional[Path] = None,
) -> AuditJob:
    validate_mode_profile_and_provider(mode, scan_profile, external_literature_provider, reference_check_provider)
    audit_id = audit_id or new_audit_id(package.name)
    output_dir = (settings.audits_dir / audit_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        "scripts/audit_package.py",
        str(package),
        "--mode",
        mode,
        "--scan-profile",
        scan_profile,
        "--output-dir",
        str(output_dir),
        "--domains",
        domains,
        "--external-literature-provider",
        external_literature_provider,
        "--reference-check-provider",
        reference_check_provider,
        "--case-id",
        package.name,
    ]
    if compare_to is not None:
        command.extend(["--compare-to", str(compare_to)])
    now = time.time()
    return AuditJob(
        audit_id=audit_id,
        status="queued",
        package_path=str(package),
        mode=mode,
        scan_profile=scan_profile,
        domains=domains,
        external_literature_provider=external_literature_provider,
        reference_check_provider=reference_check_provider,
        output_dir=str(output_dir),
        created_at=now,
        updated_at=now,
        command=command,
        uploaded_package_dir=str(uploaded_package_dir.resolve()) if uploaded_package_dir else None,
    )


def job_file(settings: WebappSettings, audit_id: str) -> Path:
    validate_audit_id(audit_id)
    return settings.audits_dir / audit_id / "job.json"


def validate_audit_id(audit_id: str) -> str:
    if not AUDIT_ID_RE.fullmatch(audit_id):
        raise HTTPException(status_code=400, detail="Invalid audit id")
    return audit_id


def save_job(settings: WebappSettings, job: AuditJob) -> None:
    job.updated_at = time.time()
    path = job_file(settings, job.audit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(asdict(job), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def load_job(settings: WebappSettings, audit_id: str) -> Optional[AuditJob]:
    path = job_file(settings, audit_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("scan_profile", "standard")
    payload.setdefault("reference_check_provider", "none")
    return AuditJob(**payload)


def require_job(settings: WebappSettings, audit_id: str) -> AuditJob:
    job = load_job(settings, audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return job


def resolve_compare_to(settings: WebappSettings, audit_id: Optional[str]) -> Path | None:
    if not audit_id:
        return None
    previous = require_job(settings, audit_id)
    if previous.status != "completed":
        raise HTTPException(status_code=400, detail="compare_to_audit_id must refer to a completed audit")
    output_dir = Path(previous.output_dir).resolve()
    if not output_dir.is_dir():
        raise HTTPException(status_code=404, detail="Previous audit output directory is missing")
    return output_dir


def run_job(settings: WebappSettings, audit_id: str) -> None:
    job = require_job(settings, audit_id)
    job.status = "running"
    save_job(settings, job)
    try:
        process = subprocess.Popen(
            job.command,
            cwd=settings.repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        stdout, stderr = process.communicate()
        job.returncode = process.returncode
        job.stdout_tail = text_tail(stdout)
        job.stderr_tail = text_tail(stderr)
        refresh_pipeline_summary(job)
        job.status = "completed" if process.returncode == 0 and job.pipeline_summary else "failed"
        if job.status == "failed":
            job.error = "Audit pipeline failed or did not write pipeline_summary.json"
    except Exception as exc:  # noqa: BLE001 - API must persist failures for local review.
        job.status = "failed"
        job.error = str(exc)
    save_job(settings, job)


def refresh_pipeline_summary(job: AuditJob) -> None:
    summary_path = Path(job.output_dir) / "pipeline_summary.json"
    if summary_path.is_file():
        job.pipeline_summary = json.loads(summary_path.read_text(encoding="utf-8"))


def job_response(settings: WebappSettings, job: AuditJob) -> dict[str, Any]:
    output_dir = Path(job.output_dir)
    return {
        "audit_id": job.audit_id,
        "status": job.status,
        "mode": job.mode,
        "scan_profile": job.scan_profile,
        "domains": job.domains,
        "external_literature_provider": job.external_literature_provider,
        "reference_check_provider": job.reference_check_provider,
        "package_path": job.package_path,
        "output_dir": job.output_dir,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "returncode": job.returncode,
        "error": job.error,
        "stdout_tail": job.stdout_tail,
        "stderr_tail": job.stderr_tail,
        "pipeline_summary": job.pipeline_summary,
        "artifacts": {
            "summary": str(output_dir / "AUDIT_JSON_SUMMARY.json"),
            "coverage": str(output_dir / "coverage.json"),
            "calibrated_findings": str(output_dir / "calibrated_findings.json"),
            "report": str(output_dir / "audit-report.md"),
            "evidence_dir": str(output_dir / "evidence"),
            "claim_coverage": str(output_dir / "claim_coverage.json"),
            "unresolved_actions": str(output_dir / "unresolved_actions.csv"),
            "correction_plan_csv": str(output_dir / "correction_plan.csv"),
            "correction_plan_md": str(output_dir / "correction_plan.md"),
            "resolved_actions": str(output_dir / "resolved_actions.csv"),
            "accepted_with_reason": str(output_dir / "accepted_with_reason.csv"),
            "re_audit_diff": str(output_dir / "re_audit_diff.json"),
            "writing_readiness": str(output_dir / "writing_readiness.json"),
            "submission_qc_packet": str(output_dir / "submission_qc_packet"),
        },
        "runs_root": str(settings.runs_root),
    }


def read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def read_optional_json_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_artifact(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def submission_qc_packet_summary(output_dir: Path) -> dict[str, Any]:
    packet_dir = output_dir / "submission_qc_packet"
    if not packet_dir.is_dir():
        return {"available": False, "files": [], "download_url": None}
    files = sorted(path.name for path in packet_dir.iterdir() if path.is_file())
    return {
        "available": True,
        "files": files,
        "download_url": "submission-qc-packet.zip",
    }


EXPOSED_ARTIFACTS = {
    "audit-report.md",
    "AUDIT_JSON_SUMMARY.json",
    "coverage.json",
    "calibrated_findings.json",
    "pipeline_summary.json",
    "claim_coverage.json",
    "claim_coverage.csv",
    "methodology_checklist.json",
    "methodology_checklist.csv",
    "writing_readiness.json",
    "writing_readiness.csv",
    "unresolved_actions.csv",
    "correction_plan.csv",
    "correction_plan.md",
    "resolved_actions.csv",
    "accepted_with_reason.csv",
    "missing_materials.csv",
    "verified_traceability.csv",
    "re_audit_diff.json",
    "re_audit_diff.csv",
}


def artifact_download_allowed(relpath: str) -> bool:
    relative = Path(relpath)
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        return False
    as_posix = relative.as_posix()
    if as_posix in EXPOSED_ARTIFACTS:
        return True
    if as_posix.startswith("submission_qc_packet/") and len(relative.parts) == 2:
        return True
    return False


def write_packet_zip(packet_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(packet_dir.iterdir(), key=lambda item: item.name.lower()):
            if path.is_file():
                archive.write(path, arcname=path.name)


def safe_artifact(output_dir: Path, relpath: str) -> Path:
    return safe_join(output_dir.resolve(), relpath)


def safe_join(base: Path, relpath: str) -> Path:
    relative = Path(relpath)
    if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    candidate = (base / relative).resolve()
    if not is_relative_to(candidate, base):
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    return candidate


def is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def extract_zip_safely(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValueError("Uploaded zip has too many files for a local audit package")
        total = 0
        for info in infos:
            total += info.file_size
            if total > MAX_ZIP_BYTES:
                raise ValueError("Uploaded zip expands beyond the local size limit")
            member = Path(info.filename)
            if member.is_absolute() or any(part in {"..", ""} for part in member.parts):
                raise ValueError("Uploaded zip contains an unsafe path")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError("Uploaded zip contains a symlink, which is not accepted for local audit packages")
            target = (destination / member).resolve()
            if not is_relative_to(target, destination.resolve()):
                raise ValueError("Uploaded zip contains a path outside the package")
        archive.extractall(destination)


def text_tail(value: str, limit: int = 8000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]
