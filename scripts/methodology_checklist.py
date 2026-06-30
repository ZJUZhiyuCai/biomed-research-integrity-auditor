#!/usr/bin/env python3
"""Build a structured methodology/reporting-standard readiness checklist."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

try:
    from scripts.csv_safety import csv_safe_row
except ImportError:  # pragma: no cover - supports direct script execution.
    from csv_safety import csv_safe_row


STATUS_READY = "materials_supplied_manual_review_required"
STATUS_PARTIAL = "partial_supporting_materials_manual_review_limited"
STATUS_MISSING = "supporting_material_missing"
STATUS_NOT_REQUESTED = "not_requested"


CHECKLIST_MODULES: list[dict[str, Any]] = [
    {
        "module_id": "wetlab_general",
        "domains": ["wetlab"],
        "standard": "General wet-lab reproducibility",
        "label_en": "Wet-lab reproducibility records",
        "label_zh": "湿实验可复核记录",
        "checks": [
            {
                "check_id": "wetlab_protocol",
                "label_en": "Protocol or methods record is available for manual review.",
                "label_zh": "提供 protocol 或 methods 记录供人工复核。",
                "materials": ["protocols"],
                "action_en": "Add the experiment protocol, ELN extract, batch log, or methods worksheet.",
                "action_zh": "补充实验方案、ELN 摘录、批次记录或方法工作表。",
            },
            {
                "check_id": "wetlab_source_data",
                "label_en": "Source data are available for figure and table checks.",
                "label_zh": "提供 source data 以核对图表。",
                "materials": ["source_data"],
                "action_en": "Add source-data CSV/TSV/XLSX files with group labels, units, and n.",
                "action_zh": "补充带组别、单位和 n 的 source-data CSV/TSV/XLSX。",
            },
            {
                "check_id": "wetlab_raw_or_assembly",
                "label_en": "Raw images or figure assembly records are available when figures are supplied.",
                "label_zh": "提供图像时，应提供 raw images 或组图记录。",
                "materials": ["raw_images", "figure_assembly"],
                "action_en": "Add raw/uncropped image files or a figure assembly manifest/workfile.",
                "action_zh": "补充 raw/uncropped 图像或组图 manifest/工程文件。",
            },
        ],
    },
    {
        "module_id": "animal",
        "domains": ["animal"],
        "standard": "ARRIVE-oriented animal reporting",
        "label_en": "Animal study reporting",
        "label_zh": "动物实验报告要点",
        "checks": [
            {
                "check_id": "animal_design",
                "label_en": "Study design, outcomes, sample-size rationale, inclusion/exclusion, and statistics can be checked.",
                "label_zh": "可核对研究设计、结局、样本量依据、纳排标准和统计方法。",
                "materials": ["protocols", "source_data", "statistics_code"],
                "action_en": "Add protocol/design notes, source tables, and analysis code or statistical plan.",
                "action_zh": "补充 protocol/设计说明、source table 和分析代码或统计计划。",
            },
            {
                "check_id": "animal_bias_control",
                "label_en": "Randomization, blinding, allocation, and exclusion records can be reviewed.",
                "label_zh": "可复核随机化、盲法、分组分配和排除记录。",
                "materials": ["protocols"],
                "action_en": "Add randomization/blinding records, allocation sheets, or protocol sections.",
                "action_zh": "补充随机化/盲法记录、分组表或 protocol 相关章节。",
            },
            {
                "check_id": "animal_ethics_welfare",
                "label_en": "Ethics/IACUC approval, welfare monitoring, humane endpoints, strain/sex/age details can be reviewed.",
                "label_zh": "可核对伦理/IACUC、福利监测、人道终点、品系/性别/年龄信息。",
                "materials": ["ethics_irb", "protocols"],
                "action_en": "Add ethics approval and animal protocol/welfare documentation.",
                "action_zh": "补充伦理批件和动物 protocol/福利记录。",
            },
        ],
    },
    {
        "module_id": "clinical",
        "domains": ["clinical"],
        "standard": "CONSORT/ICMJE-oriented clinical reporting",
        "label_en": "Clinical study reporting",
        "label_zh": "临床研究报告要点",
        "checks": [
            {
                "check_id": "clinical_registration_protocol",
                "label_en": "Trial registration, protocol, and statistical analysis plan can be reviewed.",
                "label_zh": "可核对注册、protocol 和统计分析计划。",
                "materials": ["clinical_registration", "protocols", "statistics_code"],
                "action_en": "Add registry record, protocol, SAP, and analysis scripts when applicable.",
                "action_zh": "按适用情况补充注册记录、protocol、SAP 和分析脚本。",
            },
            {
                "check_id": "clinical_ethics_consent",
                "label_en": "IRB/ethics approval and consent materials can be reviewed.",
                "label_zh": "可核对 IRB/伦理批件和知情同意材料。",
                "materials": ["ethics_irb"],
                "action_en": "Add IRB/ethics approval and consent template or waiver documentation.",
                "action_zh": "补充 IRB/伦理批件和知情同意模板或豁免文件。",
            },
            {
                "check_id": "clinical_flow_outcomes",
                "label_en": "CONSORT flow, outcomes, adverse events, and data-sharing statements can be checked.",
                "label_zh": "可核对 CONSORT 流程、结局、不良事件和数据共享说明。",
                "materials": ["supplementary", "source_data", "protocols"],
                "action_en": "Add participant-flow, outcome, adverse-event, and data-sharing support files.",
                "action_zh": "补充受试者流程、结局、不良事件和数据共享支撑文件。",
            },
        ],
    },
    {
        "module_id": "cell",
        "domains": ["cell"],
        "standard": "Cell-line and reagent reporting",
        "label_en": "Cell and reagent reporting",
        "label_zh": "细胞与试剂报告要点",
        "checks": [
            {
                "check_id": "cell_identity_qc",
                "label_en": "Cell source, STR authentication, mycoplasma status, and passage records can be reviewed.",
                "label_zh": "可核对细胞来源、STR 鉴定、支原体状态和传代记录。",
                "materials": ["protocols", "source_data"],
                "action_en": "Add cell-line QC records, STR/mycoplasma reports, or passage logs.",
                "action_zh": "补充细胞质控、STR/支原体报告或传代记录。",
            },
            {
                "check_id": "cell_reagents_controls",
                "label_en": "Antibody/RRID, catalog/lot, transfection, treatment, and control records can be reviewed.",
                "label_zh": "可核对抗体/RRID、货号/批号、转染、处理和对照记录。",
                "materials": ["protocols", "supplementary"],
                "action_en": "Add reagent tables, antibody/RRID information, lot numbers, and control descriptions.",
                "action_zh": "补充试剂表、抗体/RRID、批号和对照说明。",
            },
        ],
    },
    {
        "module_id": "flow",
        "domains": ["flow"],
        "standard": "MIFlowCyt-oriented flow reporting",
        "label_en": "Flow cytometry reporting",
        "label_zh": "流式细胞术报告要点",
        "checks": [
            {
                "check_id": "flow_raw_gating",
                "label_en": "FCS files, workspace/gating hierarchy, compensation, and controls can be reviewed.",
                "label_zh": "可核对 FCS 文件、workspace/gating 层级、补偿和对照。",
                "materials": ["flow_fcs", "protocols"],
                "action_en": "Add FCS files, workspace/gating files, compensation records, and FMO/isotype controls.",
                "action_zh": "补充 FCS、workspace/gating 文件、补偿记录和 FMO/isotype 对照。",
            },
            {
                "check_id": "flow_denominator_instrument",
                "label_en": "Population denominators, instrument, software, and acquisition settings can be checked.",
                "label_zh": "可核对群体分母、仪器、软件和采集设置。",
                "materials": ["flow_fcs", "protocols", "source_data"],
                "action_en": "Add instrument/software settings and source tables with denominators.",
                "action_zh": "补充仪器/软件设置和带分母的 source table。",
            },
        ],
    },
    {
        "module_id": "omics",
        "domains": ["omics"],
        "standard": "Omics repository and analysis reproducibility",
        "label_en": "Omics reporting",
        "label_zh": "组学报告要点",
        "checks": [
            {
                "check_id": "omics_accession_metadata",
                "label_en": "Repository accession, raw data/counts, and sample metadata can be reviewed.",
                "label_zh": "可核对数据库 accession、原始数据/counts 和样本元数据。",
                "materials": ["omics_accession", "source_data"],
                "action_en": "Add GEO/SRA/ArrayExpress/PRIDE accession and sample metadata tables.",
                "action_zh": "补充 GEO/SRA/ArrayExpress/PRIDE accession 和样本元数据表。",
            },
            {
                "check_id": "omics_analysis_code",
                "label_en": "Batch handling, normalization, differential analysis, and multiple testing can be reviewed.",
                "label_zh": "可核对批次处理、标准化、差异分析和多重检验。",
                "materials": ["statistics_code", "protocols", "source_data"],
                "action_en": "Add analysis code/notebooks and normalization/differential-analysis records.",
                "action_zh": "补充分析代码/notebook 和标准化/差异分析记录。",
            },
        ],
    },
]


def category_files(manifest: dict[str, Any], category: str) -> list[str]:
    return [
        str(item.get("path", ""))
        for item in manifest.get("files", []) or []
        if item.get("category") == category and item.get("path")
    ]


def supplied_categories(manifest: dict[str, Any]) -> set[str]:
    counts = manifest.get("category_counts", {}) or {}
    return {str(category) for category, count in counts.items() if int(count or 0) > 0}


def check_status(manifest: dict[str, Any], materials: list[str]) -> tuple[str, list[str], list[str]]:
    supplied = supplied_categories(manifest)
    present = [category for category in materials if category in supplied]
    missing = [category for category in materials if category not in supplied]
    if present:
        return STATUS_READY, present, missing
    return STATUS_MISSING, present, missing


def build_methodology_checklist(manifest: dict[str, Any]) -> dict[str, Any]:
    requested_domains = {str(item).strip().lower() for item in manifest.get("domains", []) or [] if str(item).strip()}
    modules: list[dict[str, Any]] = []
    totals = {
        "modules_requested": 0,
        "checks_ready_for_manual_review": 0,
        "checks_partial_supporting_materials": 0,
        "checks_missing_supporting_materials": 0,
        "checks_not_requested": 0,
    }

    for module in CHECKLIST_MODULES:
        module_domains = set(module["domains"])
        requested = bool(module_domains & requested_domains)
        checks: list[dict[str, Any]] = []
        if requested:
            totals["modules_requested"] += 1
        for check in module["checks"]:
            materials = list(check["materials"])
            if requested:
                status, present, missing = check_status(manifest, materials)
                supplied_files = {
                    category: category_files(manifest, category)[:8]
                    for category in present
                }
                if status == STATUS_READY and missing:
                    status = STATUS_PARTIAL
                if status == STATUS_READY:
                    totals["checks_ready_for_manual_review"] += 1
                elif status == STATUS_PARTIAL:
                    totals["checks_partial_supporting_materials"] += 1
                else:
                    totals["checks_missing_supporting_materials"] += 1
            else:
                status, present, missing, supplied_files = STATUS_NOT_REQUESTED, [], materials, {}
                totals["checks_not_requested"] += 1
            checks.append({
                "check_id": check["check_id"],
                "label_en": check["label_en"],
                "label_zh": check["label_zh"],
                "status": status,
                "supporting_material_categories": materials,
                "supplied_material_categories": present,
                "missing_material_categories": missing,
                "supplied_files": supplied_files,
                "recommended_action_en": check["action_en"],
                "recommended_action_zh": check["action_zh"],
            })
        modules.append({
            "module_id": module["module_id"],
            "label_en": module["label_en"],
            "label_zh": module["label_zh"],
            "standard": module["standard"],
            "domains": list(module["domains"]),
            "requested": requested,
            "status": (
                "manual_review_ready"
                if requested and any(check["status"] == STATUS_READY for check in checks)
                else "manual_review_limited"
                if requested and any(check["status"] == STATUS_PARTIAL for check in checks)
                else STATUS_MISSING
                if requested
                else STATUS_NOT_REQUESTED
            ),
            "checks": checks,
        })

    return {
        "version": "0.1.0",
        "scope": "methodology/reporting-standard readiness checklist",
        "requested_domains": sorted(requested_domains),
        "modules": modules,
        "totals": totals,
        "boundary_note": (
            "This checklist reports whether supporting materials are available for manual methodology review. "
            "It does not determine ARRIVE, CONSORT, ICMJE, MIFlowCyt, omics, or journal-policy compliance."
        ),
        "boundary_note_zh": (
            "本清单只记录是否具备人工方法学复核所需的支撑材料；不自动判定 ARRIVE、CONSORT、ICMJE、"
            "MIFlowCyt、组学数据库或期刊政策合规。"
        ),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_methodology_checklist_csv(path: Path, checklist: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "module_id",
                "module_label_en",
                "module_label_zh",
                "standard",
                "requested",
                "check_id",
                "check_label_en",
                "check_label_zh",
                "status",
                "supporting_material_categories",
                "supplied_material_categories",
                "missing_material_categories",
                "recommended_action_en",
                "recommended_action_zh",
            ],
        )
        writer.writeheader()
        for module in checklist.get("modules", []) or []:
            for check in module.get("checks", []) or []:
                row = {
                    "module_id": module.get("module_id", ""),
                    "module_label_en": module.get("label_en", ""),
                    "module_label_zh": module.get("label_zh", ""),
                    "standard": module.get("standard", ""),
                    "requested": module.get("requested", False),
                    "check_id": check.get("check_id", ""),
                    "check_label_en": check.get("label_en", ""),
                    "check_label_zh": check.get("label_zh", ""),
                    "status": check.get("status", ""),
                    "supporting_material_categories": ";".join(check.get("supporting_material_categories", []) or []),
                    "supplied_material_categories": ";".join(check.get("supplied_material_categories", []) or []),
                    "missing_material_categories": ";".join(check.get("missing_material_categories", []) or []),
                    "recommended_action_en": check.get("recommended_action_en", ""),
                    "recommended_action_zh": check.get("recommended_action_zh", ""),
                }
                writer.writerow(csv_safe_row(row, writer.fieldnames or []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("methodology_checklist.json"))
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    checklist = build_methodology_checklist(manifest)
    write_json(args.output, checklist)
    if args.csv:
        write_methodology_checklist_csv(args.csv, checklist)
    print(json.dumps({
        "output": str(args.output),
        "modules_requested": checklist["totals"]["modules_requested"],
        "checks_missing_supporting_materials": checklist["totals"]["checks_missing_supporting_materials"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
