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
import signal
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

from provenance.panel_modality import CANONICAL_MODALITIES, normalize_modality
from scripts.csv_safety import csv_safe_row
from scripts.docx_structure_extract import scan as scan_docx_structure
from scripts.pdf_structure_extract import scan as scan_pdf_structure
from scripts.pptx_structure_extract import scan as scan_pptx_structure
from scripts.prism_project_intake import scan as scan_prism_project_intake
from scripts.xlsx_structure_extract import scan as scan_xlsx_structure
from scripts.submission_qc import (
    ACTION_FIELDNAMES,
    CLAIM_COLUMNS,
    IMAGE_REVIEW_TRACKER_FIELDS,
    IMAGE_TOOL_HANDOFF_FIELDS,
    correction_plan_rows,
    write_correction_plan_csv,
    write_correction_plan_markdown,
)

DEFAULT_RUNS_ROOT = ROOT / "audit_outputs" / "webapp"
MODES = {"internal_presubmission", "external_public_material", "response_to_concern"}
SCAN_PROFILES = {"quick", "standard", "deep"}
EXTERNAL_PROVIDERS = {"auto", "none", "fixture", "europepmc", "crossref"}
REFERENCE_CHECK_PROVIDERS = {"none", "crossref"}
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
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
CLAIM_STATUS_OPTIONS = ["draft", "ready", "complete", "resolved", "needs_review"]
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
VENDOR_RAW_IMAGE_SUFFIXES = {".czi", ".nd2", ".lif", ".oib", ".oir", ".vsi", ".svs"}
SOURCE_DATA_SUFFIXES = {".csv", ".tsv", ".xlsx", ".pzfx"}
PDF_SUFFIXES = {".pdf"}
DOCX_SUFFIXES = {".docx"}
PPTX_SUFFIXES = {".pptx"}
XLSX_SUFFIXES = {".xlsx"}
MAX_XLSX_ROWS_SCANNED = 500
CLAIM_FIELD_ALLOWED_ROLES = {
    "source_data": {"source_data"},
    "raw_record": {"figures", "raw_images"},
    "analysis_code": {"statistics_code"},
    "protocol": {"protocols"},
}
AUDIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
FILENAME_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+")
SAFE_ATTACHMENT_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]+")
FILENAME_STOP_TOKENS = {
    "acq",
    "acquisition",
    "analysis",
    "chart",
    "data",
    "export",
    "fig",
    "figure",
    "final",
    "graph",
    "image",
    "img",
    "panel",
    "plot",
    "processed",
    "raw",
    "result",
    "results",
    "source",
    "stat",
    "stats",
    "summary",
    "table",
    "value",
    "values",
}
MAX_PREP_SUGGESTIONS = 25


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


class ClaimManifestRowInput(BaseModel):
    claim_id: str
    claim_text: str
    manuscript_location: str = ""
    figure_or_table: str = ""
    source_data: str = ""
    raw_record: str = ""
    analysis_code: str = ""
    protocol: str = ""
    owner: str = ""
    status: str = "draft"


class ClaimManifestRequest(BaseModel):
    package_path: str
    rows: list[ClaimManifestRowInput] = Field(default_factory=list)


class ActionUpdateRequest(BaseModel):
    owner: Optional[str] = None
    status: Optional[str] = None
    human_note: Optional[str] = None
    accepted_with_reason: Optional[str] = None
    attachment_reference: Optional[str] = None


class ImageReviewUpdateRequest(BaseModel):
    review_owner: Optional[str] = None
    review_status: Optional[str] = None
    external_tool_or_method: Optional[str] = None
    review_result_note: Optional[str] = None
    attachment_reference: Optional[str] = None


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
    process_pid: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: Optional[str] = None
    pipeline_summary: Optional[dict[str, Any]] = None
    uploaded_package_dir: Optional[str] = None


def create_app(output_root: Optional[Path] = None) -> FastAPI:
    settings = WebappSettings(ROOT, (output_root or DEFAULT_RUNS_ROOT).expanduser().resolve())
    settings.audits_dir.mkdir(parents=True, exist_ok=True)
    settings.packages_dir.mkdir(parents=True, exist_ok=True)
    mark_orphaned_jobs(settings)

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
            "example_packages": example_packages(),
        }

    @app.get("/api/audits")
    def list_audits() -> dict[str, Any]:
        jobs = [load_job(settings, audit_dir.name) for audit_dir in sorted(settings.audits_dir.iterdir()) if audit_dir.is_dir()]
        jobs = [job for job in jobs if job is not None]
        for job in jobs:
            finalize_from_completed_summary(settings, job)
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
                    "only; the audit pipeline cross-checks them against supplied files.\n\n"
                    "For submission QC, add claim_manifest.csv at the package root to link each\n"
                    "major manuscript claim to source data, raw records, analysis code, and protocols.\n"
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

    @app.post("/api/packages/claim-manifest")
    def save_claim_manifest(request: ClaimManifestRequest) -> dict[str, Any]:
        package = require_package_dir(request.package_path)
        rows = [validated_claim_manifest_row(package, row) for row in request.rows]
        manifest_path = package / "claim_manifest.csv"
        with manifest_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CLAIM_COLUMNS)
            writer.writeheader()
            writer.writerows(csv_safe_row(row, CLAIM_COLUMNS) for row in rows)
        return {
            "manifest_path": str(manifest_path),
            "rows_written": len(rows),
            "inventory": package_inventory(package),
        }

    @app.get("/api/audits/{audit_id}")
    def get_audit(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        refresh_pipeline_summary(job)
        finalize_from_completed_summary(settings, job)
        save_job(settings, job)
        return job_response(settings, job)

    @app.get("/api/audits/{audit_id}/summary")
    def get_summary(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        refresh_pipeline_summary(job)
        finalize_from_completed_summary(settings, job)
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

    @app.post("/api/audits/{audit_id}/cancel")
    def cancel_audit(audit_id: str) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        if job.status not in {"queued", "running", "cancel_requested"}:
            return job_response(settings, job)
        job.status = "cancel_requested"
        job.error = "Cancellation requested by the local user"
        save_job(settings, job)
        if job.process_pid:
            terminate_process(job.process_pid)
        return job_response(settings, job)

    @app.patch("/api/audits/{audit_id}/actions/{action_id}")
    def update_action(audit_id: str, action_id: str, request: ActionUpdateRequest) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        if job.status not in {"completed", "failed", "canceled"}:
            raise HTTPException(status_code=409, detail="Action trackers are editable after an audit writes outputs")
        output_dir = Path(job.output_dir).resolve()
        trackers = update_action_trackers(output_dir, action_id, request)
        return {"action_trackers": trackers}

    @app.patch("/api/audits/{audit_id}/image-review/{review_item_id}")
    def update_image_review(audit_id: str, review_item_id: str, request: ImageReviewUpdateRequest) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        if job.status not in {"completed", "failed", "canceled"}:
            raise HTTPException(status_code=409, detail="Image review trackers are editable after an audit writes outputs")
        output_dir = Path(job.output_dir).resolve()
        tracker_rows = update_image_review_tracker(output_dir, review_item_id, request)
        return {
            "image_review_packet": image_review_packet_summary(output_dir / "submission_qc_packet", output_dir),
            "image_review_tracker": tracker_rows,
        }

    @app.post("/api/audits/{audit_id}/attachments")
    async def upload_attachment(
        audit_id: str,
        file: UploadFile = File(...),
        target_type: str = Form("action"),
        target_id: str = Form(""),
    ) -> dict[str, Any]:
        job = require_job(settings, audit_id)
        if job.status not in {"completed", "failed", "canceled"}:
            raise HTTPException(status_code=409, detail="Attachments can be added after an audit writes outputs")
        output_dir = Path(job.output_dir).resolve()
        ensure_attachment_target_exists(output_dir, target_type, target_id)
        attachment = await save_qc_attachment(output_dir, file, target_type, target_id)
        response: dict[str, Any] = {"attachment": attachment}
        if target_type == "action":
            response["action_trackers"] = update_action_trackers(
                output_dir,
                target_id,
                ActionUpdateRequest(attachment_reference=attachment["attachment_reference"]),
            )
        elif target_type == "image_review":
            response["image_review_tracker"] = update_image_review_tracker(
                output_dir,
                target_id,
                ImageReviewUpdateRequest(attachment_reference=attachment["attachment_reference"]),
            )
            response["image_review_packet"] = image_review_packet_summary(output_dir / "submission_qc_packet", output_dir)
        else:
            raise HTTPException(status_code=400, detail="target_type must be action or image_review")
        return response

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
        if job.status in {"queued", "running", "cancel_requested"}:
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
    claim_manifest = read_claim_manifest(package)
    prism_hints = build_prism_material_prep_hints(package, files_by_role)
    pdf_hints = build_pdf_material_prep_hints(package, files_by_role)
    docx_hints = build_docx_material_prep_hints(package, files_by_role)
    pptx_hints = build_pptx_material_prep_hints(package, files_by_role)
    xlsx_hints = build_xlsx_material_prep_hints(package, files_by_role)
    material_prep_suggestions = build_material_prep_suggestions(
        files_by_role,
        manifest,
        claim_manifest,
        prism_hints,
        pdf_hints,
        docx_hints,
        pptx_hints,
        xlsx_hints,
    )
    return {
        "package_path": str(package),
        "exists": True,
        "folders": folders,
        "files_by_role": files_by_role,
        "file_counts": {key: len(value) for key, value in files_by_role.items()},
        "assembly_manifest": manifest,
        "claim_manifest": claim_manifest,
        "relation_types": sorted(ALLOWED_MANIFEST_RELATIONS),
        "relation_allowed_source_roles": {
            key: sorted(value) for key, value in RELATION_ALLOWED_SOURCE_ROLES.items()
        },
        "modality_options": list(CANONICAL_MODALITIES),
        "claim_manifest_columns": CLAIM_COLUMNS,
        "claim_status_options": CLAIM_STATUS_OPTIONS,
        "material_prep_suggestions": material_prep_suggestions,
        "inventory_warnings": inventory_warnings,
        "scan_limit_reached": limit_reached,
        "scan_limits": {
            "max_files": INVENTORY_MAX_FILES,
            "max_depth": INVENTORY_MAX_DEPTH,
        },
        "scope_note": (
            "Assembly-manifest rows are declarations for audit context only; "
            "the pipeline cross-checks them against supplied files. Claim-manifest rows "
            "record claim-to-evidence completeness and do not prove claim correctness."
        ),
    }


def example_packages() -> list[dict[str, str]]:
    examples = [
        (
            "minimal_package",
            "Minimal self-audit package",
            "Small package for a quick first local run.",
        ),
        (
            "full_presubmission_package",
            "Full pre-submission package",
            "Larger example with figure-to-raw traceability records.",
        ),
    ]
    rows: list[dict[str, str]] = []
    for package_id, label, description in examples:
        path = ROOT / "examples" / package_id
        if path.is_dir():
            rows.append({
                "id": package_id,
                "label": label,
                "description": description,
                "path": str(path),
            })
    return rows


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
    if top == "raw_images" and suffix in IMAGE_SUFFIXES | VENDOR_RAW_IMAGE_SUFFIXES:
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


def build_material_prep_suggestions(
    files_by_role: dict[str, list[str]],
    manifest: dict[str, Any],
    claim_manifest: dict[str, Any],
    prism_hints: dict[str, Any] | None = None,
    pdf_hints: dict[str, Any] | None = None,
    docx_hints: dict[str, Any] | None = None,
    pptx_hints: dict[str, Any] | None = None,
    xlsx_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Draft manifest rows from filename similarity only.

    These are typing aids for the local webapp. They are deliberately not
    written to disk and not treated as evidence by the audit pipeline.
    """
    figures = sorted(files_by_role.get("figures", []))
    raw_images = sorted(files_by_role.get("raw_images", []))
    source_tables = sorted(files_by_role.get("source_data", []))
    analysis_files = sorted(files_by_role.get("statistics_code", []))
    protocol_files = sorted(files_by_role.get("protocols", []))
    existing_pairs = {
        (str(row.get("figure_panel", "")), str(row.get("source_record", "")))
        for row in manifest.get("rows", []) or []
    }
    suggested_pairs: set[tuple[str, str]] = set()
    per_figure_links: dict[str, dict[str, str]] = {}
    for row in manifest.get("rows", []) or []:
        figure = str(row.get("figure_panel", "") or "")
        source = str(row.get("source_record", "") or "")
        source_role = inventory_role(Path(source))
        if figure in figures and source in files_by_role.get(source_role, []) and source_role in {"raw_images", "source_data"}:
            per_figure_links.setdefault(figure, {})[source_role] = source

    assembly_rows: list[dict[str, str]] = []
    filename_match_warnings: list[str] = []
    for figure in figures:
        raw_match, ambiguous_raw_matches = filename_match_result(figure, raw_images)
        source_match, ambiguous_source_matches = filename_match_result(figure, source_tables)
        if ambiguous_raw_matches and "raw_images" not in per_figure_links.get(figure, {}):
            filename_match_warnings.append(filename_ambiguity_warning(figure, "raw_images", ambiguous_raw_matches))
        if ambiguous_source_matches and "source_data" not in per_figure_links.get(figure, {}):
            filename_match_warnings.append(filename_ambiguity_warning(figure, "source_data", ambiguous_source_matches))
        for match_path, role in ((raw_match, "raw_images"), (source_match, "source_data")):
            if not match_path or (figure, match_path) in existing_pairs:
                continue
            shared = ", ".join(sorted(filename_tokens(figure) & filename_tokens(match_path))) or "filename"
            row = {
                "figure_panel": figure,
                "source_record": match_path,
                "relation_type": "declared_derived_from",
                "modality": infer_manifest_modality(figure, match_path, role),
                "notes": (
                    f"Filename-based starter suggestion using shared token(s): {shared}. "
                    "Review before saving; declaration only, not verified provenance."
                ),
                "suggestion_reason": f"shared filename token(s): {shared}",
            }
            assembly_rows.append(row)
            suggested_pairs.add((figure, match_path))
            per_figure_links.setdefault(figure, {})[role] = match_path
            if len(assembly_rows) >= MAX_PREP_SUGGESTIONS:
                break
        if len(assembly_rows) >= MAX_PREP_SUGGESTIONS:
            break

    prism_graph_table_links = (prism_hints or {}).get("graph_table_links", []) or []
    prism_matched_claim_keys: set[tuple[str, str]] = set()
    for link in prism_graph_table_links:
        if len(assembly_rows) >= MAX_PREP_SUGGESTIONS:
            break
        source_pzfx = str(link.get("source_pzfx", "") or "")
        graph_title = str(link.get("graph_title", "") or "")
        table_title = str(link.get("table_title", "") or "")
        if source_pzfx not in source_tables or not graph_title:
            continue
        figure_match = best_token_match(graph_title, figures)
        if not figure_match:
            continue
        pair = (figure_match, source_pzfx)
        prism_matched_claim_keys.add((graph_title, source_pzfx))
        per_figure_links.setdefault(figure_match, {})["source_data"] = source_pzfx
        if pair in existing_pairs or pair in suggested_pairs:
            continue
        row = {
            "figure_panel": figure_match,
            "source_record": source_pzfx,
            "relation_type": "declared_derived_from",
            "modality": "chart",
            "notes": (
                f"Prism graph-title starter suggestion: graph `{graph_title}` points to table "
                f"`{table_title or link.get('table_id', '')}` in this PZFX file. Review before saving; "
                "declaration only, not verified provenance."
            ),
            "suggestion_reason": f"Prism graph `{graph_title}` has a possible source table hint",
        }
        assembly_rows.append(row)
        suggested_pairs.add(pair)

    pptx_links = (pptx_hints or {}).get("links", []) or []
    for link in pptx_links:
        if len(assembly_rows) >= MAX_PREP_SUGGESTIONS:
            break
        figure = str(link.get("figure_panel", "") or "")
        source = str(link.get("source_record", "") or "")
        if figure not in figures or source not in [*raw_images, *source_tables]:
            continue
        pair = (figure, source)
        source_role = inventory_role(Path(source))
        if pair in existing_pairs or pair in suggested_pairs or source_role not in {"raw_images", "source_data"}:
            continue
        evidence_source = str(link.get("evidence_source", "") or "")
        row = {
            "figure_panel": figure,
            "source_record": source,
            "relation_type": "declared_derived_from",
            "modality": infer_manifest_modality(figure, source, source_role),
            "notes": (
                f"PPTX text/notes/alt-text starter suggestion from {evidence_source}. Review before saving; "
                "PPTX text is a declaration aid, not verified provenance."
            ),
            "suggestion_reason": f"PPTX text/notes/alt text explicitly names {figure} and {source}",
        }
        assembly_rows.append(row)
        suggested_pairs.add(pair)
        per_figure_links.setdefault(figure, {})[source_role] = source

    existing_claim_figures = {
        str(row.get("figure_or_table", ""))
        for row in claim_manifest.get("rows", []) or []
        if str(row.get("figure_or_table", "")).strip()
    }
    existing_claim_ids = {
        str(row.get("claim_id", ""))
        for row in claim_manifest.get("rows", []) or []
        if str(row.get("claim_id", "")).strip()
    }
    claim_rows: list[dict[str, str]] = []
    next_claim_index = next_available_claim_index(existing_claim_ids)
    for figure in figures:
        if figure in existing_claim_figures:
            continue
        links = per_figure_links.get(figure, {})
        if not links:
            continue
        source_ref = links.get("source_data", "")
        suggestion_reason = "starter row from filename-linked figure evidence; paste exact claim text before adding"
        if source_ref.lower().endswith(".pzfx"):
            suggestion_reason = (
                "starter row from Prism graph/PZFX-linked figure evidence; paste exact claim text and review "
                "exported graph/table/source records before adding"
            )
        claim_id = f"C-{next_claim_index:03d}"
        next_claim_index += 1
        claim_rows.append({
            "claim_id": claim_id,
            "claim_text": "",
            "manuscript_location": "",
            "figure_or_table": figure,
            "source_data": source_ref,
            "raw_record": links.get("raw_images", ""),
            "analysis_code": best_filename_match(figure, analysis_files) or "",
            "protocol": best_filename_match(figure, protocol_files) or "",
            "owner": "",
            "status": "draft",
            "suggestion_reason": suggestion_reason,
        })
        if len(claim_rows) >= MAX_PREP_SUGGESTIONS:
            break

    claim_keys = {
        (str(row.get("figure_or_table", "")), str(row.get("source_data", "")))
        for row in claim_rows
    }
    for link in prism_graph_table_links:
        if len(claim_rows) >= MAX_PREP_SUGGESTIONS:
            break
        source_pzfx = str(link.get("source_pzfx", "") or "")
        graph_title = str(link.get("graph_title", "") or "")
        if not source_pzfx or not graph_title or source_pzfx not in source_tables:
            continue
        if (graph_title, source_pzfx) in prism_matched_claim_keys or (graph_title, source_pzfx) in claim_keys:
            continue
        claim_id = f"C-{next_claim_index:03d}"
        next_claim_index += 1
        claim_rows.append({
            "claim_id": claim_id,
            "claim_text": "",
            "manuscript_location": "",
            "figure_or_table": graph_title,
            "source_data": source_pzfx,
            "raw_record": "",
            "analysis_code": best_filename_match(source_pzfx, analysis_files) or "",
            "protocol": best_filename_match(source_pzfx, protocol_files) or "",
            "owner": "",
            "status": "draft",
            "suggestion_reason": (
                f"Prism graph `{graph_title}` has a possible table link in {source_pzfx}; "
                "paste exact claim text and review exported graph/source files before saving"
            ),
        })
        claim_keys.add((graph_title, source_pzfx))

    xlsx_sheet_hints = (xlsx_hints or {}).get("sheets", []) or []
    for sheet in xlsx_sheet_hints:
        if len(claim_rows) >= MAX_PREP_SUGGESTIONS:
            break
        source_xlsx = str(sheet.get("source_xlsx", "") or "")
        label = str(sheet.get("suggested_label", "") or "")
        if not source_xlsx or not label or source_xlsx not in source_tables:
            continue
        if not xlsx_label_looks_claim_like(label):
            continue
        key = (label, source_xlsx)
        if key in claim_keys:
            continue
        claim_id = f"C-{next_claim_index:03d}"
        next_claim_index += 1
        claim_rows.append({
            "claim_id": claim_id,
            "claim_text": "",
            "manuscript_location": "",
            "figure_or_table": label,
            "source_data": source_xlsx,
            "raw_record": "",
            "analysis_code": best_filename_match(source_xlsx, analysis_files) or "",
            "protocol": best_filename_match(source_xlsx, protocol_files) or "",
            "owner": "",
            "status": "draft",
            "suggestion_reason": (
                f"XLSX sheet/header detected for `{label}` in {source_xlsx}; paste exact claim text "
                "and verify the workbook sheet before saving"
            ),
        })
        claim_keys.add(key)

    pdf_caption_hints = (pdf_hints or {}).get("captions", []) or []
    docx_caption_hints = (docx_hints or {}).get("captions", []) or []
    existing_claim_labels = {
        str(row.get("figure_or_table", "")).strip().lower()
        for row in claim_manifest.get("rows", []) or []
        if str(row.get("figure_or_table", "")).strip()
    }
    existing_claim_labels.update(
        str(row.get("figure_or_table", "")).strip().lower()
        for row in claim_rows
        if str(row.get("figure_or_table", "")).strip()
    )
    for caption in [*pdf_caption_hints, *docx_caption_hints]:
        if len(claim_rows) >= MAX_PREP_SUGGESTIONS:
            break
        label = str(caption.get("label", "") or "").strip()
        if not label or label.lower() in existing_claim_labels:
            continue
        claim_id = f"C-{next_claim_index:03d}"
        next_claim_index += 1
        document_path = str(caption.get("path", "") or "")
        page = str(caption.get("page", "") or "")
        source_type = str(caption.get("source_type", "") or ("PDF" if page else "DOCX"))
        caption_text = str(caption.get("text", "") or "")
        snippet = caption_text[:180] + ("..." if len(caption_text) > 180 else "")
        location = f"{document_path} p. {page}".strip() if page else document_path
        claim_rows.append({
            "claim_id": claim_id,
            "claim_text": "",
            "manuscript_location": location,
            "figure_or_table": label,
            "source_data": "",
            "raw_record": "",
            "analysis_code": "",
            "protocol": "",
            "owner": "",
            "status": "draft",
            "suggestion_reason": (
                f"{source_type} caption detected for `{label}`; paste the exact claim text and link "
                f"source/raw evidence before saving. Caption snippet: {snippet}"
            ),
        })
        existing_claim_labels.add(label.lower())

    return {
        "assembly_rows": assembly_rows,
        "claim_rows": claim_rows,
        "prism_graph_table_links": prism_graph_table_links,
        "prism_errors": (prism_hints or {}).get("errors", []) or [],
        "pdf_captions": pdf_caption_hints,
        "pdf_table_like_blocks": (pdf_hints or {}).get("table_like_blocks", []) or [],
        "pdf_errors": (pdf_hints or {}).get("errors", []) or [],
        "docx_captions": docx_caption_hints,
        "docx_table_like_blocks": (docx_hints or {}).get("table_like_blocks", []) or [],
        "docx_warnings": (docx_hints or {}).get("warnings", []) or [],
        "docx_errors": (docx_hints or {}).get("errors", []) or [],
        "pptx_links": pptx_links,
        "pptx_warnings": (pptx_hints or {}).get("warnings", []) or [],
        "xlsx_sheets": xlsx_sheet_hints,
        "xlsx_errors": (xlsx_hints or {}).get("errors", []) or [],
        "filename_match_warnings": filename_match_warnings[:MAX_PREP_SUGGESTIONS],
        "scope_note": (
            "Suggestions are filename-based starter rows for human review. "
            "PPTX slide text, speaker notes, alt text, Prism graph/table hints, PDF/DOCX captions, and XLSX sheet/header hints may also seed drafts when available. "
            "They are not written until the user saves them, and saved manifests remain "
            "declarations that the audit pipeline cross-checks."
        ),
    }


def build_prism_material_prep_hints(package: Path, files_by_role: dict[str, list[str]]) -> dict[str, Any]:
    if not any(path.lower().endswith(".pzfx") for path in files_by_role.get("source_data", [])):
        return {"graph_table_links": [], "errors": []}
    try:
        payload = scan_prism_project_intake(package)
    except Exception as exc:  # noqa: BLE001 - keep inspect lightweight and non-fatal.
        return {
            "graph_table_links": [],
            "errors": [f"Prism material-prep hint scan failed: {exc.__class__.__name__}"],
        }
    links: list[dict[str, str]] = []
    for item in payload.get("graph_table_links", []) or []:
        source_pzfx = str(item.get("source_pzfx", "") or "")
        if source_pzfx not in files_by_role.get("source_data", []):
            continue
        links.append({
            "source_pzfx": source_pzfx,
            "graph_id": str(item.get("graph_id", "") or ""),
            "graph_title": str(item.get("graph_title", "") or ""),
            "table_id": str(item.get("table_id", "") or ""),
            "table_title": str(item.get("table_title", "") or ""),
            "match_basis": str(item.get("match_basis", "") or ""),
            "interpretation": str(item.get("interpretation", "") or "possible Prism graph-to-table linkage; not verified provenance"),
        })
        if len(links) >= MAX_PREP_SUGGESTIONS:
            break
    errors = [
        f"{item.get('path', 'PZFX')}: {item.get('error', 'Prism parse error')}"
        for item in payload.get("errors", []) or []
    ]
    return {"graph_table_links": links, "errors": errors}


def build_pdf_material_prep_hints(package: Path, files_by_role: dict[str, list[str]]) -> dict[str, Any]:
    all_paths = [path for paths in files_by_role.values() for path in paths]
    if not any(Path(path).suffix.lower() in PDF_SUFFIXES for path in all_paths):
        return {"captions": [], "table_like_blocks": [], "errors": []}
    try:
        payload = scan_pdf_structure(package)
    except Exception as exc:  # noqa: BLE001 - inspect should remain lightweight and non-fatal.
        return {
            "captions": [],
            "table_like_blocks": [],
            "errors": [f"PDF material-prep hint scan failed: {exc.__class__.__name__}"],
        }
    captions: list[dict[str, str]] = []
    for item in payload.get("captions", []) or []:
        captions.append({
            "caption_id": str(item.get("caption_id", "") or ""),
            "path": str(item.get("path", "") or ""),
            "page": str(item.get("page", "") or ""),
            "kind": str(item.get("kind", "") or ""),
            "label": str(item.get("label", "") or ""),
            "text": str(item.get("text", "") or ""),
        })
        if len(captions) >= MAX_PREP_SUGGESTIONS:
            break
    table_like_blocks: list[dict[str, str]] = []
    for item in payload.get("table_like_blocks", []) or []:
        table_like_blocks.append({
            "block_id": str(item.get("block_id", "") or ""),
            "path": str(item.get("path", "") or ""),
            "page": str(item.get("page", "") or ""),
            "row_count": str(item.get("row_count", "") or ""),
            "column_count_estimate": str(item.get("column_count_estimate", "") or ""),
        })
        if len(table_like_blocks) >= MAX_PREP_SUGGESTIONS:
            break
    errors = [
        f"{item.get('path', 'PDF')}: {item.get('error', 'PDF structure extraction error')}"
        for item in payload.get("errors", []) or []
    ]
    return {"captions": captions, "table_like_blocks": table_like_blocks, "errors": errors}


def build_docx_material_prep_hints(package: Path, files_by_role: dict[str, list[str]]) -> dict[str, Any]:
    all_paths = [path for paths in files_by_role.values() for path in paths]
    docx_paths = [path for path in all_paths if Path(path).suffix.lower() in DOCX_SUFFIXES]
    if not docx_paths:
        return {"captions": [], "table_like_blocks": [], "warnings": [], "errors": []}
    try:
        payload = scan_docx_structure(package)
    except Exception as exc:  # noqa: BLE001 - surface as prep warning, not hard failure.
        return {
            "captions": [],
            "table_like_blocks": [],
            "warnings": [],
            "errors": [f"DOCX material-prep hint scan failed: {exc.__class__.__name__}"],
        }
    captions: list[dict[str, str]] = []
    table_like_blocks: list[dict[str, str]] = []
    docx_path_set = set(docx_paths)
    for item in payload.get("captions", []) or []:
        rel = str(item.get("path", "") or "")
        if rel not in docx_path_set:
            continue
        captions.append({
            "caption_id": str(item.get("caption_id", "") or ""),
            "path": rel,
            "page": "",
            "kind": str(item.get("kind", "") or ""),
            "label": str(item.get("label", "") or ""),
            "text": str(item.get("text", "") or ""),
            "source_type": "DOCX",
        })
        if len(captions) >= MAX_PREP_SUGGESTIONS:
            break
    for item in payload.get("table_like_blocks", []) or []:
        rel = str(item.get("path", "") or "")
        if rel not in docx_path_set:
            continue
        table_like_blocks.append({
            "block_id": str(item.get("block_id", "") or ""),
            "path": rel,
            "page": "",
            "row_count": str(item.get("row_count", "") or ""),
            "column_count_estimate": str(item.get("column_count_estimate", "") or ""),
        })
        if len(table_like_blocks) >= MAX_PREP_SUGGESTIONS:
            break
    errors = [
        f"{item.get('path', 'DOCX')}: {item.get('error', 'DOCX structure extraction error')}"
        for item in payload.get("errors", []) or []
    ]
    warnings = [
        f"{item.get('path', 'DOCX')}: {item.get('message', 'DOCX review-layer material is outside structure extraction')}"
        for item in payload.get("warnings", []) or []
    ]
    return {"captions": captions, "table_like_blocks": table_like_blocks, "warnings": warnings, "errors": errors}


def build_pptx_material_prep_hints(package: Path, files_by_role: dict[str, list[str]]) -> dict[str, Any]:
    pptx_paths = [
        path
        for path in files_by_role.get("figure_assembly", [])
        if Path(path).suffix.lower() in PPTX_SUFFIXES
    ]
    if not pptx_paths:
        return {"links": [], "warnings": []}
    try:
        payload = scan_pptx_structure(package)
    except Exception as exc:  # noqa: BLE001 - surface as prep warning, not hard failure.
        return {"links": [], "warnings": [f"PPTX material-prep hint scan failed: {exc.__class__.__name__}"]}
    links: list[dict[str, str]] = []
    for item in payload.get("explicit_path_pairs", []) or []:
        extraction_method = str(item.get("extraction_method", "") or "")
        if extraction_method not in {
            "pptx_slide_explicit_paths",
            "pptx_notes_explicit_paths",
            "pptx_alt_text_explicit_paths",
        }:
            continue
        figure = str(item.get("source_path", "") or "")
        source = str(item.get("target_path", "") or "")
        if not figure.startswith("figures/") or not (source.startswith("raw_images/") or source.startswith("source_data/")):
            continue
        links.append({
            "figure_panel": figure,
            "source_record": source,
            "evidence_source": str(item.get("evidence_source", "") or ""),
            "relation_type": str(item.get("relation_type", "") or "declared_derived_from"),
            "interpretation": "PPTX text/notes/alt text names a figure/source pair for manifest preparation; not verified provenance",
        })
        if len(links) >= MAX_PREP_SUGGESTIONS:
            break
    warnings: list[str] = []
    for item in payload.get("warnings", []) or []:
        text = str(item.get("warning") or item.get("error") or item) if isinstance(item, dict) else str(item)
        if "pptx" in text.lower() or "figure_assembly" in text.lower():
            warnings.append(text)
    for item in payload.get("errors", []) or []:
        text = str(item.get("error") or item) if isinstance(item, dict) else str(item)
        if "pptx" in text.lower() or "figure_assembly" in text.lower():
            warnings.append(text)
    return {"links": links, "warnings": warnings[:MAX_PREP_SUGGESTIONS]}


def build_xlsx_material_prep_hints(package: Path, files_by_role: dict[str, list[str]]) -> dict[str, Any]:
    xlsx_paths = [
        path
        for path in files_by_role.get("source_data", [])
        if Path(path).suffix.lower() in XLSX_SUFFIXES
    ]
    if not xlsx_paths:
        return {"sheets": [], "errors": []}
    try:
        payload = scan_xlsx_structure(package)
    except Exception as exc:  # noqa: BLE001 - inspect should remain lightweight and non-fatal.
        return {"sheets": [], "errors": [f"XLSX material-prep hint scan failed: {exc.__class__.__name__}"]}
    sheets: list[dict[str, Any]] = []
    xlsx_path_set = set(xlsx_paths)
    for item in payload.get("sheets", []) or []:
        rel = str(item.get("source_xlsx", "") or "")
        if rel not in xlsx_path_set:
            continue
        sheets.append({
            "source_xlsx": rel,
            "sheet_name": str(item.get("sheet_name", "") or ""),
            "suggested_label": str(item.get("suggested_label", "") or ""),
            "header_row": str(item.get("header_row", "") or ""),
            "headers": item.get("headers", []) or [],
            "data_rows_scanned": str(item.get("data_rows_scanned", "") or ""),
            "row_scan_capped": bool(item.get("row_scan_capped")),
            "formula_cell_count_scanned": int(item.get("formula_cell_count_scanned", 0) or 0),
            "sheet_state": str(item.get("sheet_state", "") or "visible"),
            "interpretation": str(
                item.get("interpretation")
                or "XLSX sheet/header metadata for claim-manifest preparation; not a statistical validation result"
            ),
        })
        if len(sheets) >= MAX_PREP_SUGGESTIONS:
            break
    errors = [
        f"{item.get('path', 'XLSX')}: {item.get('error', 'XLSX structure extraction error')}"
        for item in payload.get("errors", []) or []
    ]
    return {"sheets": sheets, "errors": errors[:MAX_PREP_SUGGESTIONS]}


def cell_to_display_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def suggested_xlsx_label(path: str, sheet_name: str) -> str:
    if xlsx_label_looks_claim_like(sheet_name):
        return sheet_name
    stem = Path(path).stem.replace("_", " ").replace("-", " ").strip()
    if xlsx_label_looks_claim_like(stem):
        return stem
    return f"{Path(path).name}#{sheet_name}"


def xlsx_label_looks_claim_like(label: str) -> bool:
    lowered = label.lower()
    return bool(re.search(r"\b(fig(?:ure)?|table|supp(?:lementary)?|extended\s+data)\b", lowered))


def text_tokens(value: str) -> set[str]:
    tokens = {normalize_filename_token(token) for token in FILENAME_TOKEN_RE.findall(value.lower())}
    return {token for token in tokens if token not in FILENAME_STOP_TOKENS and len(token) > 0}


def normalize_filename_token(token: str) -> str:
    token = token.lower().strip()
    if token.isdigit():
        return str(int(token)) if token else token
    return token


def filename_tokens(path: str) -> set[str]:
    return text_tokens(Path(path).stem)


def best_filename_match(target: str, candidates: list[str]) -> str:
    return best_token_match(Path(target).stem, candidates)


def best_token_match(target_text: str, candidates: list[str]) -> str:
    best_match, _ambiguous_matches = token_match_result(target_text, candidates)
    return best_match


def filename_match_result(target: str, candidates: list[str]) -> tuple[str, list[str]]:
    return token_match_result(Path(target).stem, candidates)


def token_match_result(target_text: str, candidates: list[str]) -> tuple[str, list[str]]:
    target_tokens = text_tokens(target_text)
    if not target_tokens:
        return "", []
    scored: list[tuple[float, int, str]] = []
    for candidate in candidates:
        candidate_tokens = filename_tokens(candidate)
        shared = target_tokens & candidate_tokens
        if not shared:
            continue
        numeric_shared = any(token.isdigit() for token in shared)
        if not numeric_shared and len(shared) < 2:
            continue
        union = target_tokens | candidate_tokens
        score = len(shared) / max(len(union), 1)
        scored.append((score, len(shared), candidate))
    if not scored:
        return "", []
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].lower()))
    top_score, top_shared, top_candidate = scored[0]
    ambiguous_matches = [
        candidate
        for score, shared_count, candidate in scored
        if score == top_score and shared_count == top_shared
    ]
    if len(ambiguous_matches) > 1:
        return "", sorted(ambiguous_matches, key=str.lower)
    return top_candidate, []


def filename_ambiguity_warning(figure: str, role: str, candidates: list[str]) -> str:
    candidate_text = "; ".join(candidates[:5])
    extra = "" if len(candidates) <= 5 else f"; +{len(candidates) - 5} more"
    return (
        f"Ambiguous filename starter suggestion for {figure} against {role}: "
        f"{candidate_text}{extra}. No row was suggested; choose the correct record manually before saving."
    )


def infer_manifest_modality(figure: str, source: str, role: str) -> str:
    if role == "source_data":
        return "chart"
    combined = f"{figure} {source}".lower()
    if any(token in combined for token in ("blot", "gel", "wb", "western")):
        return "western_blot"
    if any(token in combined for token in ("dapi", "fitc", "if", "ihc", "micro", "confocal", "histology")):
        return "microscopy"
    return "other"


def next_available_claim_index(existing_ids: set[str]) -> int:
    numbers = []
    for claim_id in existing_ids:
        match = re.search(r"(\d+)$", claim_id)
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


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


def read_claim_manifest(package: Path) -> dict[str, Any]:
    manifest_path = package / "claim_manifest.csv"
    if not manifest_path.is_file():
        alternate = package / "submission_readiness" / "claim_manifest.csv"
        manifest_path = alternate if alternate.is_file() else manifest_path
    if not manifest_path.is_file():
        return {"path": None, "rows": [], "row_count": 0, "warnings": []}
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    with manifest_path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        missing = [col for col in CLAIM_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            warnings.append(f"Missing columns: {', '.join(missing)}")
        for row in reader:
            rows.append({col: str(row.get(col, "") or "") for col in CLAIM_COLUMNS})
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


def validated_claim_manifest_row(package: Path, row: ClaimManifestRowInput) -> dict[str, str]:
    claim_id = row.claim_id.strip()
    claim_text = row.claim_text.strip()
    if not claim_id:
        raise HTTPException(status_code=400, detail="claim_id is required")
    if not claim_text:
        raise HTTPException(status_code=400, detail="claim_text is required")
    status = row.status.strip().lower() or "draft"
    if status not in CLAIM_STATUS_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported claim status: {status}")
    return {
        "claim_id": claim_id,
        "claim_text": claim_text,
        "manuscript_location": row.manuscript_location.strip(),
        "figure_or_table": row.figure_or_table.strip(),
        "source_data": validate_optional_package_refs(
            package,
            row.source_data,
            "source_data",
            CLAIM_FIELD_ALLOWED_ROLES["source_data"],
        ),
        "raw_record": validate_optional_package_refs(
            package,
            row.raw_record,
            "raw_record",
            CLAIM_FIELD_ALLOWED_ROLES["raw_record"],
        ),
        "analysis_code": validate_optional_package_refs(
            package,
            row.analysis_code,
            "analysis_code",
            CLAIM_FIELD_ALLOWED_ROLES["analysis_code"],
        ),
        "protocol": validate_optional_package_refs(
            package,
            row.protocol,
            "protocol",
            CLAIM_FIELD_ALLOWED_ROLES["protocol"],
        ),
        "owner": row.owner.strip(),
        "status": status,
    }


def validate_optional_package_refs(package: Path, value: str, field: str, allowed_roles: set[str]) -> str:
    refs: list[str] = []
    for item in str(value or "").replace("|", ";").split(";"):
        item = item.strip()
        if not item:
            continue
        rel = validate_package_relative_file(package, item, field)
        role = inventory_role(Path(rel))
        if role not in allowed_roles:
            raise HTTPException(
                status_code=400,
                detail=f"{field} must point to one of: {', '.join(sorted(allowed_roles))}",
            )
        refs.append(rel)
    return ";".join(refs)


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
    payload.setdefault("process_pid", None)
    return AuditJob(**payload)


def require_job(settings: WebappSettings, audit_id: str) -> AuditJob:
    job = load_job(settings, audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return job


def mark_orphaned_jobs(settings: WebappSettings) -> None:
    for audit_dir in sorted(settings.audits_dir.iterdir()):
        if not audit_dir.is_dir():
            continue
        job = load_job(settings, audit_dir.name)
        if job is None or job.status not in {"queued", "running", "cancel_requested"}:
            continue
        job.status = "failed"
        job.process_pid = None
        job.error = (
            "The local webapp restarted while this audit was still running. "
            "Re-run the audit before relying on this output."
        )
        save_job(settings, job)


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


def read_process_stream(stream: Any, chunks: list[str]) -> None:
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            chunks.append(line)
    finally:
        stream.close()


def terminate_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return


def run_job(settings: WebappSettings, audit_id: str) -> None:
    job = require_job(settings, audit_id)
    if job.status == "cancel_requested":
        job.status = "canceled"
        job.error = "Audit canceled before the pipeline started"
        save_job(settings, job)
        return
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
        job.process_pid = process.pid
        save_job(settings, job)

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        stdout_thread = threading.Thread(
            target=read_process_stream,
            args=(process.stdout, stdout_chunks),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=read_process_stream,
            args=(process.stderr, stderr_chunks),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        completed_from_summary = False
        summary_seen_at: float | None = None
        while process.poll() is None:
            current = load_job(settings, audit_id)
            if current and current.status == "cancel_requested":
                terminate_process(process.pid)
            job.stdout_tail = text_tail("".join(stdout_chunks))
            job.stderr_tail = text_tail("".join(stderr_chunks))
            refresh_pipeline_summary(job)
            if job.pipeline_summary:
                summary_seen_at = summary_seen_at or time.time()
                if time.time() - summary_seen_at > 2.0:
                    # The orchestrator writes pipeline_summary.json only after
                    # all audit artifacts are complete. If the CLI process then
                    # hangs during final stdout/teardown, unblock the local UI
                    # and classify the run from the completed summary.
                    terminate_process(process.pid)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.kill(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    completed_from_summary = True
                    break
            else:
                summary_seen_at = None
            save_job(settings, job)
            time.sleep(0.5)

        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
        job.returncode = process.returncode
        job.process_pid = None
        job.stdout_tail = text_tail("".join(stdout_chunks))
        job.stderr_tail = text_tail("".join(stderr_chunks))
        refresh_pipeline_summary(job)
        latest = load_job(settings, audit_id)
        if latest and latest.status == "cancel_requested":
            job.status = "canceled"
            job.error = "Audit canceled by the local user"
        else:
            job.status = "completed" if job.pipeline_summary and (process.returncode == 0 or completed_from_summary) else "failed"
        if job.status == "failed":
            job.error = "Audit pipeline failed or did not write pipeline_summary.json"
    except Exception as exc:  # noqa: BLE001 - API must persist failures for local review.
        job.status = "failed"
        job.error = str(exc)
        job.process_pid = None
    save_job(settings, job)


def refresh_pipeline_summary(job: AuditJob) -> None:
    summary_path = Path(job.output_dir) / "pipeline_summary.json"
    if summary_path.is_file():
        job.pipeline_summary = json.loads(summary_path.read_text(encoding="utf-8"))


def completed_summary_artifacts(job: AuditJob) -> bool:
    output_dir = Path(job.output_dir)
    return bool(
        job.pipeline_summary
        and (output_dir / "AUDIT_JSON_SUMMARY.json").is_file()
        and (output_dir / "audit-report.md").is_file()
        and (output_dir / "START_HERE.md").is_file()
    )


def finalize_from_completed_summary(settings: WebappSettings, job: AuditJob) -> None:
    if job.status not in {"queued", "running"}:
        return
    refresh_pipeline_summary(job)
    if not completed_summary_artifacts(job):
        return
    if job.process_pid:
        terminate_process(job.process_pid)
    job.status = "completed"
    job.returncode = 0 if job.returncode is None else job.returncode
    job.error = None
    job.process_pid = None
    save_job(settings, job)


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


def action_csv(path: Path) -> list[dict[str, str]]:
    rows = read_csv_artifact(path)
    return [{field: str(row.get(field, "") or "") for field in ACTION_FIELDNAMES} for row in rows]


def write_action_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ACTION_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, ACTION_FIELDNAMES))


def image_review_tracker_csv(path: Path) -> list[dict[str, str]]:
    rows = read_csv_artifact(path)
    return [{field: str(row.get(field, "") or "") for field in IMAGE_REVIEW_TRACKER_FIELDS} for row in rows]


def write_image_review_tracker_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_REVIEW_TRACKER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_REVIEW_TRACKER_FIELDS))


def write_image_handoff_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_TOOL_HANDOFF_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_safe_row(row, IMAGE_TOOL_HANDOFF_FIELDS))


RESOLVED_STATUSES = {"resolved", "done", "complete", "completed"}
ACCEPTED_STATUSES = {"accepted", "accepted_with_reason", "accepted-with-reason"}
NON_ACTIONABLE_STATUSES = {"false_positive", "false-positive", "non_actionable", "not_applicable"}


def update_action_trackers(output_dir: Path, action_id: str, request: ActionUpdateRequest) -> dict[str, Any]:
    tracker_files = {
        "unresolved": output_dir / "unresolved_actions.csv",
        "resolved": output_dir / "resolved_actions.csv",
        "accepted_with_reason": output_dir / "accepted_with_reason.csv",
    }
    trackers = {name: action_csv(path) for name, path in tracker_files.items()}
    found: dict[str, str] | None = None
    found_bucket: str | None = None
    for bucket, rows in trackers.items():
        for row in rows:
            if row.get("action_id") == action_id:
                found = row
                found_bucket = bucket
                break
        if found is not None:
            break
    if found is None or found_bucket is None:
        raise HTTPException(status_code=404, detail=f"Action not found: {action_id}")

    updated = dict(found)
    for field in ("owner", "status", "human_note", "accepted_with_reason", "attachment_reference"):
        value = getattr(request, field)
        if value is not None:
            updated[field] = value.strip()

    for rows in trackers.values():
        rows[:] = [row for row in rows if row.get("action_id") != action_id]

    normalized_status = updated.get("status", "").strip().lower()
    if (
        normalized_status in ACCEPTED_STATUSES
        or normalized_status in NON_ACTIONABLE_STATUSES
        or updated.get("accepted_with_reason", "").strip()
    ):
        target = "accepted_with_reason"
        if not updated.get("status"):
            updated["status"] = "accepted_with_reason"
    elif normalized_status in RESOLVED_STATUSES:
        target = "resolved"
        if not updated.get("status"):
            updated["status"] = "resolved"
    else:
        target = "unresolved"
    trackers[target].append({field: updated.get(field, "") for field in ACTION_FIELDNAMES})

    for name, path in tracker_files.items():
        write_action_csv(path, trackers[name])

    plan_rows = correction_plan_rows([
        *trackers["unresolved"],
        *trackers["resolved"],
        *trackers["accepted_with_reason"],
    ])
    write_correction_plan_csv(output_dir / "correction_plan.csv", plan_rows)
    write_correction_plan_markdown(output_dir / "correction_plan.md", plan_rows)

    packet_dir = output_dir / "submission_qc_packet"
    if packet_dir.is_dir():
        for name, rows in trackers.items():
            write_action_csv(packet_dir / tracker_files[name].name, rows)
        write_correction_plan_csv(packet_dir / "correction_plan.csv", plan_rows)
        write_correction_plan_markdown(packet_dir / "correction_plan.md", plan_rows)

    return trackers


def update_image_review_tracker(
    output_dir: Path,
    review_item_id: str,
    request: ImageReviewUpdateRequest,
) -> list[dict[str, str]]:
    review_dir = output_dir / "submission_qc_packet" / "image_review_packet"
    tracker_path = review_dir / "image_review_tracker.csv"
    if not tracker_path.is_file():
        raise HTTPException(status_code=404, detail="Image review tracker has not been generated")
    rows = image_review_tracker_csv(tracker_path)
    target: dict[str, str] | None = None
    for row in rows:
        if row.get("review_item_id") == review_item_id:
            target = row
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"Image review item not found: {review_item_id}")

    for field in (
        "review_owner",
        "review_status",
        "external_tool_or_method",
        "review_result_note",
        "attachment_reference",
    ):
        value = getattr(request, field)
        if value is not None:
            target[field] = value.strip()

    if not target.get("review_status"):
        target["review_status"] = "unresolved"

    write_image_review_tracker_csv(tracker_path, rows)
    sync_image_handoff_with_tracker(review_dir, target)
    return rows


def sync_image_handoff_with_tracker(review_dir: Path, tracker_row: dict[str, str]) -> None:
    handoff_path = review_dir / "external_tool_handoff.csv"
    if not handoff_path.is_file():
        return
    handoff_rows = [
        {field: str(row.get(field, "") or "") for field in IMAGE_TOOL_HANDOFF_FIELDS}
        for row in read_csv_artifact(handoff_path)
    ]
    source_finding_id = str(tracker_row.get("source_finding_id", "") or "")
    review_item_id = str(tracker_row.get("review_item_id", "") or "")
    ordinal = review_item_id.rsplit("-", 1)[-1] if "-" in review_item_id else ""
    updated = False
    for row in handoff_rows:
        same_finding = source_finding_id and row.get("source_finding_id") == source_finding_id
        same_ordinal = ordinal and row.get("handoff_item_id", "").endswith(ordinal)
        if not (same_finding or same_ordinal):
            continue
        row["review_status"] = tracker_row.get("review_status", "")
        row["reviewer"] = tracker_row.get("review_owner", "")
        row["external_result_reference"] = tracker_row.get("attachment_reference", "")
        updated = True
    if updated:
        write_image_handoff_csv(handoff_path, handoff_rows)


def safe_attachment_component(value: str, fallback: str) -> str:
    name = SAFE_ATTACHMENT_COMPONENT_RE.sub("_", Path(value or "").name.strip()).strip("._-")
    if not name:
        name = fallback
    return name[:120]


def ensure_attachment_target_exists(output_dir: Path, target_type: str, target_id: str) -> None:
    if target_type == "action":
        for name in ("unresolved_actions.csv", "resolved_actions.csv", "accepted_with_reason.csv"):
            if any(row.get("action_id") == target_id for row in action_csv(output_dir / name)):
                return
        raise HTTPException(status_code=404, detail=f"Action not found: {target_id}")
    if target_type == "image_review":
        tracker_path = output_dir / "submission_qc_packet" / "image_review_packet" / "image_review_tracker.csv"
        if not tracker_path.is_file():
            raise HTTPException(status_code=404, detail="Image review tracker has not been generated")
        if any(row.get("review_item_id") == target_id for row in image_review_tracker_csv(tracker_path)):
            return
        raise HTTPException(status_code=404, detail=f"Image review item not found: {target_id}")
    raise HTTPException(status_code=400, detail="target_type must be action or image_review")


async def save_qc_attachment(
    output_dir: Path,
    upload: UploadFile,
    target_type: str,
    target_id: str,
) -> dict[str, str]:
    if target_type not in {"action", "image_review"}:
        raise HTTPException(status_code=400, detail="target_type must be action or image_review")
    packet_dir = output_dir / "submission_qc_packet"
    if not packet_dir.is_dir():
        raise HTTPException(status_code=404, detail="Submission QC packet has not been generated")
    if not target_id.strip():
        raise HTTPException(status_code=400, detail="target_id is required")

    safe_target_id = safe_attachment_component(target_id, "item")
    original_name = safe_attachment_component(upload.filename or "attachment.bin", "attachment.bin")
    stored_name = f"{int(time.time())}-{uuid4().hex[:8]}-{original_name}"
    attachment_dir = safe_join(packet_dir.resolve(), f"attachments/{target_type}/{safe_target_id}")
    attachment_dir.mkdir(parents=True, exist_ok=True)
    attachment_path = safe_join(attachment_dir.resolve(), stored_name)

    size = 0
    with attachment_path.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ATTACHMENT_BYTES:
                handle.close()
                attachment_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Attachment exceeds the local size limit")
            handle.write(chunk)

    packet_rel = attachment_path.relative_to(packet_dir).as_posix()
    output_rel = attachment_path.relative_to(output_dir).as_posix()
    return {
        "attachment_reference": packet_rel,
        "artifact_path": output_rel,
        "filename": original_name,
        "stored_filename": stored_name,
        "bytes": str(size),
        "target_type": target_type,
        "target_id": target_id,
    }


def submission_qc_packet_summary(output_dir: Path) -> dict[str, Any]:
    packet_dir = output_dir / "submission_qc_packet"
    if not packet_dir.is_dir():
        return {
            "available": False,
            "files": [],
            "audience_exports": {},
            "image_review_packet": {"available": False, "handoff_rows": []},
            "download_url": None,
        }
    files = sorted(path.name for path in packet_dir.iterdir() if path.is_file())
    audience_dir = packet_dir / "audience_exports"
    audience_exports = {}
    if audience_dir.is_dir():
        for path in sorted(audience_dir.iterdir(), key=lambda item: item.name.lower()):
            if path.is_file() and path.suffix.lower() == ".md":
                audience_exports[path.stem.lower()] = f"audience_exports/{path.name}"
    image_review_packet = image_review_packet_summary(packet_dir, output_dir)
    return {
        "available": True,
        "files": files,
        "audience_exports": audience_exports,
        "image_review_packet": image_review_packet,
        "download_url": "submission-qc-packet.zip",
    }


def image_review_packet_summary(packet_dir: Path, output_dir: Path) -> dict[str, Any]:
    review_dir = packet_dir / "image_review_packet"
    if not review_dir.is_dir():
        return {"available": False, "handoff_rows": []}
    manifest = read_optional_json_artifact(review_dir / "image_review_manifest.json") or {}
    action_index = image_review_action_index(output_dir)
    review_index = image_review_tracker_index(review_dir)
    handoff_rows = read_csv_artifact(review_dir / "external_tool_handoff.csv")
    handoff_rows = [
        enrich_handoff_row(
            {field: str(row.get(field, "") or "") for field in IMAGE_TOOL_HANDOFF_FIELDS},
            action_index,
            review_index,
        )
        for row in handoff_rows
    ]
    files = sorted(path.name for path in review_dir.iterdir() if path.is_file())
    return {
        "available": True,
        "files": files,
        "candidate_count": int(manifest.get("candidate_count", len(handoff_rows)) or 0),
        "external_handoff_count": len(handoff_rows),
        "handoff_rows": handoff_rows[:12],
        "external_tool_handoff_csv": "image_review_packet/external_tool_handoff.csv"
        if (review_dir / "external_tool_handoff.csv").is_file()
        else "",
        "external_tool_handoff_guide": "image_review_packet/EXTERNAL_TOOL_HANDOFF.md"
        if (review_dir / "EXTERNAL_TOOL_HANDOFF.md").is_file()
        else "",
        "tracker_csv": "image_review_packet/image_review_tracker.csv"
        if (review_dir / "image_review_tracker.csv").is_file()
        else "",
    }


def image_review_tracker_index(review_dir: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    tracker_rows = image_review_tracker_csv(review_dir / "image_review_tracker.csv")
    for row in tracker_rows:
        finding_id = str(row.get("source_finding_id", "") or "").strip()
        review_id = str(row.get("review_item_id", "") or "").strip()
        if finding_id:
            indexed[f"finding:{finding_id}"] = row
        if review_id:
            indexed[f"review:{review_id}"] = row
            ordinal = review_id.rsplit("-", 1)[-1] if "-" in review_id else ""
            if ordinal:
                indexed[f"ordinal:{ordinal}"] = row
    return indexed


def image_review_action_index(output_dir: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    tracker_files = {
        "unresolved": output_dir / "unresolved_actions.csv",
        "resolved": output_dir / "resolved_actions.csv",
        "accepted_with_reason": output_dir / "accepted_with_reason.csv",
    }
    for bucket, path in tracker_files.items():
        for row in action_csv(path):
            finding_id = str(row.get("source_finding_id", "") or "").strip()
            if not finding_id:
                continue
            indexed[finding_id] = {**row, "bucket": bucket}
    return indexed


def enrich_handoff_row(
    row: dict[str, str],
    action_index: dict[str, dict[str, str]],
    review_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    source_finding_id = str(row.get("source_finding_id", "") or "").strip()
    ordinal = str(row.get("handoff_item_id", "") or "").rsplit("-", 1)[-1]
    review = (
        review_index.get(f"finding:{source_finding_id}")
        or review_index.get(f"ordinal:{ordinal}")
        or {}
    )
    if review:
        row = {
            **row,
            "review_item_id": str(review.get("review_item_id", "")),
            "review_status": str(review.get("review_status", "")) or str(row.get("review_status", "")),
            "reviewer": str(review.get("review_owner", "")) or str(row.get("reviewer", "")),
            "external_tool_or_method": str(review.get("external_tool_or_method", "")),
            "review_result_note": str(review.get("review_result_note", "")),
            "attachment_reference": str(review.get("attachment_reference", "")),
            "external_result_reference": str(review.get("attachment_reference", ""))
            or str(row.get("external_result_reference", "")),
        }
    action = action_index.get(source_finding_id)
    if not action:
        return {
            **row,
            "linked_action_id": "",
            "linked_action_status": "",
            "linked_action_owner": "",
            "linked_action_attachment_reference": "",
            "linked_action_bucket": "",
        }
    return {
        **row,
        "linked_action_id": str(action.get("action_id", "")),
        "linked_action_status": str(action.get("status", "")),
        "linked_action_owner": str(action.get("owner", "")),
        "linked_action_attachment_reference": str(action.get("attachment_reference", "")),
        "linked_action_bucket": str(action.get("bucket", "")),
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
    "prism_project_intake.json",
    "fcs_metadata_intake.json",
    "image_metadata.json",
    "channel_metadata_candidates.json",
    "splice_forensics_candidates.json",
    "psd_preview_images.json",
    "unresolved_actions.csv",
    "correction_plan.csv",
    "correction_plan.md",
    "resolved_actions.csv",
    "accepted_with_reason.csv",
    "missing_materials.csv",
    "verified_traceability.csv",
    "re_audit_diff.json",
    "re_audit_diff.csv",
    "re_audit_diff.md",
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
    if as_posix.startswith("submission_qc_packet/image_review_packet/") and len(relative.parts) == 3:
        return relative.name in {
            "README.md",
            "image_review_manifest.json",
            "image_review_candidates.csv",
            "image_review_tracker.csv",
            "external_tool_handoff.csv",
            "EXTERNAL_TOOL_HANDOFF.md",
            "image_files.csv",
        }
    if as_posix.startswith("submission_qc_packet/audience_exports/") and len(relative.parts) == 3:
        return relative.name in {"README.md", "PI_BRIEF.md", "COAUTHOR_ACTIONS.md", "JOURNAL_RESPONSE_DRAFT.md"}
    if as_posix.startswith("submission_qc_packet/attachments/") and len(relative.parts) >= 4:
        return True
    return False


def write_packet_zip(packet_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(packet_dir.rglob("*"), key=lambda item: item.relative_to(packet_dir).as_posix().lower()):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(packet_dir).as_posix())


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
