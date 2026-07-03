"""Shared constants and helpers for the audit pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

DETECTOR_SCHEMA = ROOT / "schemas" / "detector_output.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
SUMMARY_SCHEMA = ROOT / "schemas" / "audit_summary.schema.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
VENDOR_RAW_IMAGE_CONTAINER_EXTS = {".czi", ".nd2", ".lif", ".oib", ".oir", ".vsi", ".svs"}
SOURCE_EXTS = {".csv", ".tsv", ".xlsx", ".pzfx"}
TEXT_EXTS = {".txt", ".md", ".pdf", ".docx"}
PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx"}
XLSX_EXTS = {".xlsx"}
PPTX_EXTS = {".pptx"}
KEY_EXTS = {".key"}
PSD_EXTS = {".psd"}
PZFX_EXTS = {".pzfx"}
FCS_EXTS = {".fcs"}
DOCUMENT_CONTAINER_EXTS = {".doc"}
LEGACY_SOURCE_EXTS = {".xls"}
PDF_IMAGE_CONTAINER_CATEGORIES = {"figures", "figure_assembly", "supplementary"}
OPAQUE_ASSEMBLY_CONTAINER_EXTS = {".ai", ".indd", ".key", ".ppt", ".psd"}

MODES = ("internal_presubmission", "external_public_material", "response_to_concern")
SCAN_PROFILES = ("quick", "standard", "deep")
EXTERNAL_LITERATURE_PROVIDERS = ("auto", "none", "fixture", "europepmc", "crossref")
REFERENCE_CHECK_PROVIDERS = ("none", "crossref")
EXTERNAL_LITERATURE_FIXTURE_NAMES = (
    "external_literature_fixture.json",
    "external_literature/fixture.json",
)


@dataclass(frozen=True)
class DetectorRunResult:
    output: Path
    ok: bool


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def has_files(path: Path, suffixes: set[str]) -> bool:
    return path.exists() and any(
        not item.is_symlink() and item.is_file() and item.suffix.lower() in suffixes
        for item in path.rglob("*")
    )


def find_external_literature_fixture(package: Path) -> Path | None:
    for name in EXTERNAL_LITERATURE_FIXTURE_NAMES:
        candidate = package / name
        if candidate.is_file():
            return candidate
    return None


def resolve_external_literature_provider(mode: str, requested: str, fixture_path: Path | None) -> str | None:
    if requested == "none":
        return None
    if requested == "fixture":
        if fixture_path is None:
            raise SystemExit("--external-literature-provider fixture requires --external-literature-fixture or a package fixture")
        return "fixture"
    if requested in {"europepmc", "crossref"}:
        return requested
    if fixture_path is not None:
        return "fixture"
    if mode == "external_public_material":
        return "europepmc"
    return None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def command_display(cmd: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in cmd)


def text_tail(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def stage_slug(stage: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", stage.lower()).strip("_") or "detector"


def manifest_mode(mode: str) -> str:
    return "external" if mode == "external_public_material" else "internal"
