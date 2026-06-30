"""FastAPI wrapper around the existing biomedical audit CLI.

The backend deliberately does not recompute, reinterpret, or mutate integrity
results. It starts the validated CLI, persists job state, and serves the JSON
and evidence artifacts that the pipeline writes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
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
DEFAULT_RUNS_ROOT = ROOT / "audit_outputs" / "webapp"
MODES = {"internal_presubmission", "external_public_material", "response_to_concern"}
EXTERNAL_PROVIDERS = {"auto", "none", "fixture", "europepmc", "crossref"}
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000


class AuditCreateRequest(BaseModel):
    package_path: Optional[str] = Field(default=None, description="Local package directory to audit.")
    mode: str = "internal_presubmission"
    domains: str = "wetlab,animal,cell"
    external_literature_provider: str = "auto"


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
    domains: str
    external_literature_provider: str
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
        version="0.5.0",
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
        job = prepare_job(settings, package, request.mode, request.domains, request.external_literature_provider)
        save_job(settings, job)
        threading.Thread(target=run_job, args=(settings, job.audit_id), daemon=True).start()
        return job_response(settings, job)

    @app.post("/api/audits/upload")
    async def create_audit_from_zip(
        file: UploadFile = File(...),
        mode: str = Form("internal_presubmission"),
        domains: str = Form("wetlab,animal,cell"),
        external_literature_provider: str = Form("auto"),
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
        job = prepare_job(
            settings,
            package,
            mode,
            domains,
            external_literature_provider,
            audit_id=audit_id,
            uploaded_package_dir=upload_root,
        )
        save_job(settings, job)
        threading.Thread(target=run_job, args=(settings, job.audit_id), daemon=True).start()
        return job_response(settings, job)

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


def validate_mode_and_provider(mode: str, provider: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {mode}")
    if provider not in EXTERNAL_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported external literature provider: {provider}")


def new_audit_id(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", Path(name).stem.lower()).strip("-") or "audit"
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{slug[:28]}-{uuid4().hex[:8]}"


def prepare_job(
    settings: WebappSettings,
    package: Path,
    mode: str,
    domains: str,
    external_literature_provider: str,
    audit_id: Optional[str] = None,
    uploaded_package_dir: Optional[Path] = None,
) -> AuditJob:
    validate_mode_and_provider(mode, external_literature_provider)
    audit_id = audit_id or new_audit_id(package.name)
    output_dir = (settings.audits_dir / audit_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        "scripts/audit_package.py",
        str(package),
        "--mode",
        mode,
        "--output-dir",
        str(output_dir),
        "--domains",
        domains,
        "--external-literature-provider",
        external_literature_provider,
        "--case-id",
        package.name,
    ]
    now = time.time()
    return AuditJob(
        audit_id=audit_id,
        status="queued",
        package_path=str(package),
        mode=mode,
        domains=domains,
        external_literature_provider=external_literature_provider,
        output_dir=str(output_dir),
        created_at=now,
        updated_at=now,
        command=command,
        uploaded_package_dir=str(uploaded_package_dir.resolve()) if uploaded_package_dir else None,
    )


def job_file(settings: WebappSettings, audit_id: str) -> Path:
    return settings.audits_dir / audit_id / "job.json"


def save_job(settings: WebappSettings, job: AuditJob) -> None:
    job.updated_at = time.time()
    path = job_file(settings, job.audit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(job), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_job(settings: WebappSettings, audit_id: str) -> Optional[AuditJob]:
    path = job_file(settings, audit_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return AuditJob(**payload)


def require_job(settings: WebappSettings, audit_id: str) -> AuditJob:
    job = load_job(settings, audit_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return job


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
        "domains": job.domains,
        "external_literature_provider": job.external_literature_provider,
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
        },
        "runs_root": str(settings.runs_root),
    }


def read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


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
            target = (destination / member).resolve()
            if not is_relative_to(target, destination.resolve()):
                raise ValueError("Uploaded zip contains a path outside the package")
        archive.extractall(destination)


def text_tail(value: str, limit: int = 8000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]
