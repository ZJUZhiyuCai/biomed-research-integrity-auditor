"""Intake and provenance artifact builders for the audit pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.pipeline.common import (
    DOCX_EXTS,
    FCS_EXTS,
    IMAGE_EXTS,
    KEY_EXTS,
    PDF_EXTS,
    PPTX_EXTS,
    PSD_EXTS,
    PYTHON,
    PZFX_EXTS,
    ROOT,
    XLSX_EXTS,
    command_display,
    has_files,
    manifest_mode,
    run,
    text_tail,
    write_json,
)


def build_manifest(package: Path, mode: str, domains: str, output_dir: Path) -> Path:
    manifest = output_dir / "manifest.json"
    run([
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/build_package_manifest.py",
        str(package),
        "--mode",
        manifest_mode(mode),
        "--domains",
        domains,
        "--output",
        str(manifest),
    ])
    return manifest


def build_provenance(package: Path, manifest: Path, output_dir: Path) -> Path:
    figure_source_map = output_dir / "figure_source_map.json"
    run([
        PYTHON,
        "skill/biomed-research-integrity-auditor/scripts/figure_source_map.py",
        str(manifest),
        "--output",
        str(figure_source_map),
    ])

    figure_source_links = output_dir / "figure_source_links.json"
    run([
        PYTHON,
        "provenance/parse_figure_source_map.py",
        str(figure_source_map),
        "--output",
        str(figure_source_links),
    ])

    assembly_links = output_dir / "assembly_links.json"
    run([
        PYTHON,
        "provenance/parse_assembly_manifest.py",
        str(package),
        "--output",
        str(assembly_links),
    ])

    provenance_graph = output_dir / "provenance_graph.json"
    run([
        PYTHON,
        "provenance/build_resource_graph.py",
        "--manifest",
        str(manifest),
        "--links",
        str(assembly_links),
        "--links",
        str(figure_source_links),
        "--output",
        str(provenance_graph),
    ])
    return provenance_graph


def build_pdf_structure(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PDF_EXTS):
        return None
    output = output_dir / "pdf_structure.json"
    cmd = [
        PYTHON,
        "scripts/pdf_structure_extract.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.2.0",
        "extractor": "scripts.pdf_structure_extract",
        "scope_note": (
            "PDF structure extraction did not complete. Embedded PDF image export is handled "
            "by pdf_embedded_images.json when that artifact is available."
        ),
        "input": {
            "package": str(package),
            "pdf_files": 0,
            "command": command_display(cmd),
        },
        "pdfs": [],
        "captions": [],
        "table_like_blocks": [],
        "errors": [
            {
                "stage": "pdf_structure_extraction",
                "error": "pdf structure extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_docx_structure(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, DOCX_EXTS):
        return None
    output = output_dir / "docx_structure.json"
    cmd = [
        PYTHON,
        "scripts/docx_structure_extract.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.docx_structure_extract",
        "scope_note": (
            "DOCX structure extraction did not complete. DOCX text may still be used by text screening "
            "when readable, but paragraph/caption/table structure remains an intake coverage gap."
        ),
        "input": {
            "package": str(package),
            "docx_files": 0,
            "command": command_display(cmd),
        },
        "docx_files": [],
        "paragraphs": [],
        "captions": [],
        "table_like_blocks": [],
        "warnings": [],
        "errors": [
            {
                "stage": "docx_structure_extraction",
                "error": "docx structure extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_prism_project_intake(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PZFX_EXTS):
        return None
    output = output_dir / "prism_project_intake.json"
    cmd = [
        PYTHON,
        "scripts/prism_project_intake.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.prism_project_intake",
        "scope_note": (
            "GraphPad Prism PZFX project intake did not complete. Prism project structure remains "
            "a source-data coverage gap until CSV/XLSX exports or parseable PZFX metadata are supplied."
        ),
        "input": {
            "package": str(package),
            "pzfx_files": 0,
            "command": command_display(cmd),
        },
        "pzfx_files": [],
        "tables": [],
        "graphs": [],
        "graph_table_links": [],
        "errors": [
            {
                "stage": "prism_project_intake",
                "error": "prism project intake exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_xlsx_structure(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, XLSX_EXTS):
        return None
    output = output_dir / "xlsx_structure.json"
    cmd = [
        PYTHON,
        "scripts/xlsx_structure_extract.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.xlsx_structure_extract",
        "scope_note": (
            "XLSX workbook structure intake did not complete. XLSX files may still be used by source-data "
            "detectors when readable, but workbook sheet/header/formula metadata remains a coverage gap."
        ),
        "input": {
            "package": str(package),
            "xlsx_files": 0,
            "command": command_display(cmd),
        },
        "xlsx_files": [],
        "sheets": [],
        "errors": [
            {
                "stage": "xlsx_structure_extraction",
                "error": "xlsx structure extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_fcs_metadata_intake(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, FCS_EXTS):
        return None
    output = output_dir / "fcs_metadata_intake.json"
    cmd = [
        PYTHON,
        "scripts/fcs_metadata_intake.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.fcs_metadata_intake",
        "scope_note": (
            "FCS metadata intake did not complete. Flow cytometry raw-file metadata remains "
            "a coverage gap until readable FCS files, gating/workspace files, and source exports are supplied."
        ),
        "input": {
            "package": str(package),
            "fcs_files": 0,
            "command": command_display(cmd),
        },
        "totals": {
            "fcs_files": 0,
            "readable_fcs_files": 0,
            "unreadable_fcs_files": 0,
            "total_events_reported": 0,
            "total_parameters_indexed": 0,
            "files_with_compensation_keywords": 0,
        },
        "fcs_files": [],
        "errors": [
            {
                "stage": "fcs_metadata_intake",
                "error": "FCS metadata intake exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_pdf_embedded_images(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PDF_EXTS):
        return None
    output = output_dir / "pdf_embedded_images.json"
    image_dir = output_dir / "pdf_embedded_images"
    cmd = [
        PYTHON,
        "scripts/pdf_embedded_image_extract.py",
        str(package),
        "--output",
        str(output),
        "--image-dir",
        str(image_dir),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.pdf_embedded_image_extract",
        "scope_note": (
            "PDF embedded-image extraction did not complete. PDF images remain presentation-layer "
            "container content and are not raw/source records."
        ),
        "input": {
            "package": str(package),
            "pdf_files": 0,
            "image_dir": str(image_dir),
            "command": command_display(cmd),
        },
        "pdfs": [],
        "images": [],
        "errors": [
            {
                "stage": "pdf_embedded_image_extraction",
                "error": "pdf embedded-image extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_pptx_embedded_images(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PPTX_EXTS):
        return None
    output = output_dir / "pptx_embedded_images.json"
    image_dir = output_dir / "pptx_embedded_images"
    cmd = [
        PYTHON,
        "scripts/pptx_embedded_image_extract.py",
        str(package),
        "--output",
        str(output),
        "--image-dir",
        str(image_dir),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.pptx_embedded_image_extract",
        "scope_note": (
            "PPTX embedded-image extraction did not complete. PPTX images remain presentation-layer "
            "figure-assembly content and are not raw/source records."
        ),
        "input": {
            "package": str(package),
            "pptx_files": 0,
            "image_dir": str(image_dir),
            "command": command_display(cmd),
        },
        "pptx_files": [],
        "images": [],
        "errors": [
            {
                "stage": "pptx_embedded_image_extraction",
                "error": "pptx embedded-image extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_pptx_structure(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PPTX_EXTS):
        return None
    output = output_dir / "pptx_structure.json"
    cmd = [
        PYTHON,
        "scripts/pptx_structure_extract.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.pptx_structure_extract",
        "scope_note": (
            "PPTX text/path structure extraction did not complete. PPTX files remain "
            "presentation-layer assembly containers until explicit panel/source exports or "
            "structured assembly manifests are supplied."
        ),
        "input": {
            "package": str(package),
            "pptx_files": 0,
            "command": command_display(cmd),
        },
        "pptx_files": [],
        "slides": [],
        "explicit_path_mentions": [],
        "explicit_path_pairs": [],
        "warnings": [],
        "errors": [
            {
                "stage": "pptx_structure_extraction",
                "error": "pptx structure extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_key_embedded_images(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, KEY_EXTS):
        return None
    output = output_dir / "key_embedded_images.json"
    image_dir = output_dir / "key_embedded_images"
    cmd = [
        PYTHON,
        "scripts/key_embedded_image_extract.py",
        str(package),
        "--output",
        str(output),
        "--image-dir",
        str(image_dir),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.key_embedded_image_extract",
        "scope_note": (
            "Keynote embedded-image extraction did not complete. Keynote images remain presentation-layer "
            "figure-assembly content and are not raw/source records."
        ),
        "input": {
            "package": str(package),
            "key_files": 0,
            "image_dir": str(image_dir),
            "command": command_display(cmd),
        },
        "key_files": [],
        "images": [],
        "errors": [
            {
                "stage": "key_embedded_image_extraction",
                "error": "key embedded-image extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_psd_preview_images(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, PSD_EXTS):
        return None
    output = output_dir / "psd_preview_images.json"
    image_dir = output_dir / "psd_preview_images"
    cmd = [
        PYTHON,
        "scripts/psd_preview_extract.py",
        str(package),
        "--output",
        str(output),
        "--image-dir",
        str(image_dir),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.psd_preview_extract",
        "scope_note": (
            "PSD flattened-preview extraction did not complete. PSD files remain opaque "
            "presentation-layer figure-assembly content and are not raw/source records."
        ),
        "input": {
            "package": str(package),
            "psd_files": 0,
            "image_dir": str(image_dir),
            "command": command_display(cmd),
        },
        "psd_files": [],
        "images": [],
        "errors": [
            {
                "stage": "psd_preview_extraction",
                "error": "psd preview extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output


def build_image_metadata(package: Path, output_dir: Path) -> Path | None:
    if not has_files(package, IMAGE_EXTS):
        return None
    output = output_dir / "image_metadata.json"
    cmd = [
        PYTHON,
        "scripts/image_metadata_extract.py",
        str(package),
        "--output",
        str(output),
    ]
    result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode == 0 and output.exists():
        return output
    payload = {
        "schema_version": "0.1.0",
        "extractor": "scripts.image_metadata_extract",
        "scope_note": (
            "Image metadata extraction did not complete. Frame/channel/Z-stack metadata "
            "should be reviewed manually from acquisition records before interpreting multi-channel relationships."
        ),
        "input": {
            "image_files": 0,
            "command": command_display(cmd),
        },
        "totals": {
            "image_files": 0,
            "readable_images": 0,
            "unreadable_images": 0,
            "multiframe_images": 0,
            "ome_metadata_files": 0,
            "channel_metadata_files": 0,
            "z_stack_metadata_files": 0,
            "manual_metadata_review_files": 0,
        },
        "images": [],
        "errors": [
            {
                "stage": "image_metadata_extraction",
                "error": "image metadata extractor exited non-zero or did not write output",
                "returncode": result.returncode,
                "stdout_tail": text_tail(result.stdout),
                "stderr_tail": text_tail(result.stderr),
            }
        ],
    }
    write_json(output, payload)
    return output
