#!/usr/bin/env python3
"""Assemble a Markdown biomedical integrity audit report from JSON artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calibrators.contract_validation import ContractError, validate_instance  # noqa: E402


SUMMARY_SCHEMA = ROOT / "schemas" / "audit_summary.schema.json"
CALIBRATED_SCHEMA = ROOT / "schemas" / "calibrated_findings.schema.json"
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
RISK_LABELS = {
    "R0": ("No issue found in supplied materials", "所供材料范围内未发现具体问题"),
    "R1": ("Completeness gap", "材料完整性缺口"),
    "R2": ("Reviewable reporting concern", "需要复核的报告或弱信号问题"),
    "R3": ("Integrity concern requiring explanation", "需要解释的完整性关注"),
    "R4": ("High-risk inconsistency", "高风险不一致"),
}
RISK_MEANINGS = {
    "R0": (
        "No specific issue was detected within the supplied materials and current detector scope.",
        "在已提供材料和当前检测模块范围内，未检出具体候选问题。",
    ),
    "R1": (
        "The audit cannot fully check the claim or material because key source/raw/protocol records are missing or a module could not run.",
        "关键 source/raw/protocol 记录缺失，或部分模块无法运行，因此不能完整核验相关材料或结论。",
    ),
    "R2": (
        "The item is usually handled by clarifying methods, legends, source tables, or disclosure records.",
        "通常可通过补充方法、图注、source table 或披露记录来处理。",
    ),
    "R3": (
        "A reproducible anomaly remains and should be explained with source/raw records before submission or public response.",
        "存在可复现异常，投稿或公开回应前应使用 source/raw 记录解释。",
    ),
    "R4": (
        "The supplied materials appear directly inconsistent and should be paused for internal review before any external use.",
        "所供材料之间似乎存在直接不一致，外部使用前应暂停并做内部复核。",
    ),
}
MODE_LABELS = {
    "internal_presubmission": ("Pre-submission internal audit", "投稿前内部自查"),
    "external_public_material": ("External public-material triage", "外部公开材料初筛"),
    "response_to_concern": ("Response-to-concern audit", "关注回应审计"),
}
REPORT_TITLES = {
    "internal_presubmission": "Biomedical Research Integrity Audit / 生物医药研究诚信审计报告",
    "external_public_material": "Biomedical Literature Concern Triage / 生物医药公开材料关注初筛报告",
    "response_to_concern": "Biomedical Concern Response Audit / 生物医药关注回应审计报告",
}
MODULE_LABELS = {
    "image.global_near_duplicate": ("Global near-duplicate image screen", "整图近重复图像筛查"),
    "image.local_patch_reuse": ("Local patch / copy-move image screen", "局部 patch / 同图复制移动筛查"),
    "stats.consistency_check": ("Statistical consistency screen", "统计一致性筛查"),
    "stats.pseudoreplication_screen": ("Unit-of-analysis screen", "分析单位/伪重复筛查"),
    "text.text_overlap_screen": ("Package-internal text-overlap screen", "包内文本重叠筛查"),
    "text.external_literature_search": ("External phrase-search triage", "外部短语检索初筛"),
    "audit.coverage": ("Audit coverage check", "审计覆盖检查"),
    "image_global_near_duplicate": ("Global near-duplicate image screen", "整图近重复图像筛查"),
    "image_local_patch_and_same_image_copy_move": ("Local patch and copy-move image screen", "局部 patch 与同图复制移动筛查"),
    "statistics_consistency": ("Statistical consistency screen", "统计一致性筛查"),
    "pseudoreplication": ("Unit-of-analysis screen", "分析单位/伪重复筛查"),
    "package_internal_text_overlap": ("Package-internal text-overlap screen", "包内文本重叠筛查"),
    "methodology_readiness_checklist": ("Methodology readiness checklist", "方法学准备度清单"),
}
MATERIAL_LABELS = {
    "ethics_irb": ("Ethics / IRB records", "伦理/IRB 文件"),
    "figure_assembly": ("Figure assembly files or manifest", "组图工程文件或 manifest"),
    "figures": ("Exported figure panels", "导出的图版/面板"),
    "protocols": ("Protocols / methods records", "实验方案/方法记录"),
    "raw_images": ("Raw or uncropped images", "原始或未裁剪图像"),
    "source_data": ("Source-data tables", "源数据表"),
    "supplementary": ("Supplementary files", "补充材料"),
    "statistics_code": ("Statistics / analysis code", "统计/分析代码"),
}
FINDING_LABELS = {
    "image_reuse_cluster": ("Image similarity cluster", "图像相似性簇"),
    "local_patch_reuse": ("Local patch similarity candidate", "局部 patch 相似候选"),
    "same_image_copy_move": ("Same-image copy-move candidate", "同图复制移动候选"),
    "unresolved_fig_raw_similarity": ("Unresolved figure-to-raw similarity", "未解析的图像到原始图相似性"),
    "audit_coverage_gap": ("Audit coverage gap", "审计覆盖缺口"),
    "external_literature_search_gap": ("External-search coverage gap", "外部检索覆盖缺口"),
    "external_text_match_candidate": ("External text-match candidate", "外部文本匹配候选"),
}
JSON_BLOCK_MARKER = "```json AUDIT_JSON_SUMMARY"


def humanize(value: str) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip()


def bilingual(en: str, zh: str) -> str:
    return f"{en} / {zh}"


def label_pair(value: str, mapping: dict[str, tuple[str, str]]) -> str:
    if value in mapping:
        return bilingual(*mapping[value])
    text = humanize(value)
    return text if text else "Not documented / 未记录"


def risk_label(risk: str) -> str:
    return f"{risk} - {label_pair(risk, RISK_LABELS)}"


def risk_meaning(risk: str) -> str:
    en, zh = RISK_MEANINGS.get(risk, RISK_MEANINGS["R1"])
    return f"{en}\n\n{zh}"


def md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def bullet_list(items: list[str], empty: str = "None recorded / 未记录") -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def clipped(value: str, limit: int = 180) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def sentence_join(items: list[str]) -> str:
    cleaned = [str(item).strip().rstrip(".") for item in items if str(item).strip()]
    return "; ".join(cleaned)


def load_json(path: Path | None, default: Any) -> Any:
    if path is None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def coerce_finding(item: dict[str, Any], idx: int) -> dict[str, Any]:
    if "calibrated_risk_level" not in item:
        raise ContractError(
            f"finding {item.get('finding_id', idx)!r} is not calibrated; "
            "report_assembler only accepts calibrator output with calibrated_risk_level"
        )
    result = dict(item)
    result.setdefault("finding_id", f"BIOMED-GEN-{idx:04d}")
    result["risk_level"] = result["calibrated_risk_level"]
    result.setdefault("module", "Structured Finding")
    result.setdefault("location", "")
    result.setdefault("finding_type", result.get("type", "Structured audit finding"))
    result.setdefault("evidence_type", humanize(result.get("module", "structured_finding")).lower())
    result.setdefault("evidence", "")
    if RISK_ORDER.get(result.get("risk_level", "R0"), 0) >= RISK_ORDER["R3"]:
        result.setdefault("benign_explanations_considered", [
            "rounding, normalization, export, or reporting differences may explain the observation",
            "source/raw records are needed before escalation",
        ])
        result.setdefault("required_materials_to_resolve", [
            "source data",
            "raw records",
            "analysis file or code",
        ])
        result.setdefault("recommended_action", "Verify against source/raw records and analysis files before escalation.")
    else:
        result.setdefault("benign_explanations_considered", [])
        result.setdefault("required_materials_to_resolve", [])
        result.setdefault("recommended_action", "")
    return result


def normalize_findings(payloads: list[Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, list):
            findings.extend(coerce_finding(item, idx) for idx, item in enumerate(payload, start=1))
        elif isinstance(payload, dict):
            if isinstance(payload.get("findings"), list):
                if "candidate_count" in payload:
                    validate_instance(payload, CALIBRATED_SCHEMA, "calibrated findings")
                findings.extend(coerce_finding(item, idx) for idx, item in enumerate(payload["findings"], start=1))
            elif isinstance(payload.get("candidates"), list):
                raise ContractError("report_assembler received uncalibrated detector candidates")
            elif payload.get("missing_materials"):
                raise ContractError("report_assembler received manifest/missing materials as findings input")
    return findings


def normalize_positive_evidence(payloads: list[Any]) -> list[dict[str, Any]]:
    positive = []
    for payload in payloads:
        if isinstance(payload, dict):
            positive.extend(payload.get("positive_evidence", []) or [])
    return positive


def table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = "| " + " | ".join(md_cell(cell) for cell in rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = ["| " + " | ".join(md_cell(cell) for cell in row) + " |" for row in rows[1:]]
    return "\n".join([header, sep, *body]) + "\n"


def normalized_mode(mode: str) -> str:
    if mode == "internal":
        return "internal_presubmission"
    if mode == "external":
        return "external_public_material"
    return mode


def overall_risk(findings: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    risks = [item.get("risk_level", "R0") for item in findings]
    if manifest.get("missing_materials"):
        risks.append("R1")
    return max(risks or ["R0"], key=lambda risk: RISK_ORDER.get(risk, -1))


def reviewed_materials(manifest: dict[str, Any]) -> list[str]:
    return [item.get("path", "") for item in manifest.get("files", []) if item.get("path")]


def missing_materials(manifest: dict[str, Any]) -> list[str]:
    return [humanize(item.get("category", "")) for item in manifest.get("missing_materials", []) if item.get("category")]


def missing_material_label(category: str) -> str:
    return label_pair(category, MATERIAL_LABELS)


def module_label(module: str) -> str:
    return label_pair(module, MODULE_LABELS)


def finding_label(finding_type: str) -> str:
    return label_pair(finding_type, FINDING_LABELS)


def file_count_word(count: int) -> str:
    return "file" if count == 1 else "files"


def evidence_metric_lines(evidence: Any) -> list[str]:
    """Summarize detector evidence without dumping raw JSON into the human report."""
    if evidence in ("", None):
        return ["No structured evidence summary was supplied; inspect calibrated artifacts for details."]
    if not isinstance(evidence, dict):
        return [clipped(str(evidence))]

    lines: list[str] = []
    representative = evidence.get("representative_edge")
    if not isinstance(representative, dict):
        edges = evidence.get("edges")
        if isinstance(edges, list) and edges and isinstance(edges[0], dict):
            representative = edges[0]
    if isinstance(representative, dict):
        left = representative.get("left")
        right = representative.get("right")
        if left and right:
            if left == right or representative.get("same_image"):
                lines.append(f"Same-image comparison within `{left}`.")
            else:
                lines.append(f"Compared `{left}` with `{right}`.")
        transform = representative.get("best_transform")
        if transform:
            lines.append(f"Best matching transform: `{transform}`.")
        hash_method = representative.get("best_hash_method")
        if hash_method:
            lines.append(f"Best hash method: `{hash_method}`.")
        for key, label in (
            ("best_hamming_distance", "Hamming distance"),
            ("hash_distance", "Tile hash distance"),
            ("score", "Local similarity score"),
            ("tile_hit_count", "Matching tile count"),
        ):
            if key in representative:
                lines.append(f"{label}: {representative[key]}.")
        if isinstance(representative.get("region_a"), dict):
            lines.append(f"Region A: {format_region(representative['region_a'])}.")
        if isinstance(representative.get("region_b"), dict):
            lines.append(f"Region B: {format_region(representative['region_b'])}.")
        crops = representative.get("evidence_crops")
        if isinstance(crops, dict) and crops:
            crop_paths = ", ".join(f"`{path}`" for path in crops.values())
            lines.append(f"Evidence crop files: {crop_paths}.")

    members = evidence.get("members")
    if isinstance(members, list) and members:
        shown = ", ".join(f"`{item}`" for item in members[:4])
        extra = f" (+{len(members) - 4} more)" if len(members) > 4 else ""
        lines.append(f"Similarity cluster members: {shown}{extra}.")
    if "threshold" in evidence:
        lines.append(f"Detector threshold: {evidence['threshold']}.")
    if isinstance(evidence.get("contextual_edges"), list):
        lines.append(f"Contextual edges reviewed: {len(evidence['contextual_edges'])}.")
    if isinstance(evidence.get("positive_traceability_edges"), list) and evidence["positive_traceability_edges"]:
        lines.append(f"Positive traceability edges in the same cluster: {len(evidence['positive_traceability_edges'])}.")

    scalar_keys = [
        "file",
        "sheet",
        "row",
        "column",
        "group",
        "comparison",
        "expected",
        "observed",
        "calculation",
        "query",
        "provider",
    ]
    for key in scalar_keys:
        value = evidence.get(key)
        if isinstance(value, (str, int, float)) and value != "":
            lines.append(f"{humanize(key).title()}: {clipped(str(value))}.")

    if not lines:
        simple = [
            f"{humanize(key).title()}: {clipped(str(value))}"
            for key, value in evidence.items()
            if isinstance(value, (str, int, float, bool)) and key not in {"cluster_id"}
        ]
        lines.extend(simple[:6])
    return lines or ["Structured evidence is available in `calibrated_findings.json`."]


def format_region(region: dict[str, Any]) -> str:
    parts = []
    for key in ("x", "y", "width", "height"):
        if key in region:
            parts.append(f"{key}={region[key]}")
    return ", ".join(parts) if parts else "not specified"


def observation_text(item: dict[str, Any]) -> str:
    finding_type = str(item.get("finding_type", ""))
    location = str(item.get("location", ""))
    module = str(item.get("module", ""))
    if finding_type == "image_reuse_cluster":
        return (
            f"The image screen found a near-duplicate image cluster at `{location}`. "
            "The observation should be checked against raw images, acquisition metadata, and the figure assembly history."
        )
    if finding_type in {"local_patch_reuse", "same_image_copy_move"}:
        return (
            f"The image screen found a repeated local region candidate at `{location}`. "
            "This is coordinate-level evidence requiring raw-image and processing-history review."
        )
    if finding_type == "unresolved_fig_raw_similarity":
        return (
            f"A figure panel appears similar to a raw/source image at `{location}`, but no machine-readable provenance link resolves it."
        )
    if "text" in module or "text" in finding_type:
        return (
            f"The text screen found a reviewable overlap candidate at `{location}`. "
            "Policy context, citation/disclosure history, and prior drafts are needed before escalation."
        )
    if "stat" in module or "numeric" in finding_type or "digit" in finding_type.lower():
        return (
            f"The statistics screen found a numerical consistency or weak forensic signal at `{location}`. "
            "This should be checked against source data and analysis code."
        )
    if "coverage" in finding_type:
        return (
            "The supplied package did not allow one or more audit modules to run completely. "
            "This is a coverage/completeness gap."
        )
    label = finding_label(finding_type)
    return f"A calibrated audit finding was reported at `{location}`: {label}."


def why_it_matters(item: dict[str, Any]) -> str:
    text = " ".join(str(item.get(key, "")) for key in ("module", "finding_type", "evidence_type")).lower()
    if "image" in text or "fig" in text:
        return (
            "Figures for distinct samples, fields, lanes, or conditions must be traceable to the correct source records. "
            "Similar image regions can be legitimate, but they need assembly and acquisition context."
        )
    if "stat" in text or "numeric" in text or "digit" in text:
        return (
            "Reported numerical summaries should be reproducible from the underlying observations and analysis choices. "
            "Weak statistical signals are triage prompts, not standalone conclusions."
        )
    if "text" in text:
        return (
            "Substantial text overlap can require citation, disclosure, or policy review, especially outside routine methods language."
        )
    if "coverage" in text or "missing" in text:
        return (
            "Missing material limits what the audit can verify. A no-finding result under incomplete coverage is not a correctness certificate."
        )
    return "The item affects traceability, reproducibility, or reporting completeness and should be resolved before relying on the audit as complete."


def zh_explanation_stub(kind: str) -> str:
    if kind == "observation":
        return "以上是检测器在所供材料中记录到的可复核观察；它不是对作者意图或责任的判断。"
    if kind == "why":
        return "该问题影响图表、数据或报告内容的可追溯性，因此需要用原始记录或 source data 复核。"
    return "请使用原始材料、组图记录和分析文件进行人工确认。"


def summary_finding(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": item.get("finding_id", ""),
        "risk_level": item.get("risk_level", "R0"),
        "finding_type": item.get("finding_type", ""),
        "location": item.get("location", ""),
        "evidence_type": item.get("evidence_type", item.get("module", "")),
        "benign_explanations_considered": item.get("benign_explanations_considered", []),
        "required_materials_to_resolve": item.get("required_materials_to_resolve", []),
        "recommended_action": item.get("recommended_action", ""),
    }


def summary_positive_provenance(positive_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in positive_evidence:
        for edge in item.get("edges", []) or []:
            left = str(edge.get("left", ""))
            right = str(edge.get("right", ""))
            left_role = str(edge.get("left_role", ""))
            right_role = str(edge.get("right_role", ""))
            if left_role == "figure_panel":
                figure_panel, source_record = left, right
            elif right_role == "figure_panel":
                figure_panel, source_record = right, left
            else:
                figure_panel, source_record = left, right

            provenance_edge = edge.get("provenance_edge") or {}
            evidence_source = str(
                provenance_edge.get("evidence_source")
                or edge.get("evidence_source")
                or "provenance graph"
            )
            key = (figure_panel, source_record, evidence_source)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "provenance_id": f"PROV-{len(rows) + 1:04d}",
                "relation_type": str(edge.get("contextual_tag") or "expected_traceability"),
                "figure_panel": figure_panel,
                "source_record": source_record,
                "evidence_source": evidence_source,
                "risk_effect": "positive_evidence",
            })
    return rows


def summary_traceability_gaps(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for item in findings:
        tags = set(str(tag) for tag in item.get("source_candidate_tags", []) or [])
        finding_type = str(item.get("finding_type", ""))
        evidence_type = str(item.get("evidence_type", ""))
        if "unresolved_fig_raw_similarity" not in tags | {finding_type, evidence_type}:
            continue
        gaps.append({
            "gap_id": f"TRACE-{len(gaps) + 1:04d}",
            "finding_type": finding_type or evidence_type,
            "risk_level": item.get("risk_level", "R1"),
            "location": item.get("location", ""),
            "required_materials_to_resolve": item.get("required_materials_to_resolve", []),
        })
    return gaps


def build_summary(
    mode: str,
    case_id: str | None,
    manifest: dict[str, Any],
    findings: list[dict[str, Any]],
    positive_evidence: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    claim_coverage: dict[str, Any] | None = None,
    methodology_checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    caps = []
    normalized = normalized_mode(mode)
    if normalized == "external_public_material" and not any(path.lower().endswith((".csv", ".xlsx", ".tif", ".tiff", ".czi", ".nd2", ".fcs")) for path in reviewed_materials(manifest)):
        caps.append("Public or presentation-layer materials only; source/raw-level verification is limited.")
    if manifest.get("missing_materials"):
        caps.append("Missing materials are completeness gaps, not evidence of misconduct.")
    for item in findings:
        caps.extend(item.get("risk_caps_applied", []) or [])
    return {
        "audit_mode": normalized,
        "case_id": case_id,
        "materials_reviewed": reviewed_materials(manifest),
        "materials_missing": missing_materials(manifest),
        "overall_risk": overall_risk(findings, manifest),
        "misconduct_verdict_present": False,
        "risk_caps_applied": sorted(set(caps)),
        "positive_provenance": summary_positive_provenance(positive_evidence or []),
        "traceability_gaps": summary_traceability_gaps(findings),
        "findings": [summary_finding(item) for item in findings],
        **({"audit_coverage": coverage} if coverage else {}),
        **({"claim_coverage": claim_coverage} if claim_coverage else {}),
        **({"methodology_checklist": methodology_checklist} if methodology_checklist else {}),
    }


def render_coverage(coverage: dict[str, Any] | None) -> list[str]:
    if not coverage:
        return []
    lines = ["## Audit Coverage / 本次检查覆盖", ""]
    lines += ["**Modules executed / 已执行模块**", ""]
    executed = coverage.get("modules_executed", []) or ["(none)"]
    lines += [f"- {module_label(str(item))} (`{item}`)" for item in executed]
    lines += ["", "**Modules not executed / 未执行模块**", ""]
    not_executed = coverage.get("modules_not_executed", []) or ["(none)"]
    lines += [f"- {item}" for item in not_executed]
    lines += ["", table([
        ["Coverage item / 覆盖项", "Value / 数值"],
        ["Image panels screened / 已筛图像面板", str(coverage.get("image_panels_screened", 0))],
        ["Unreadable image files / 不可读取图像", str(coverage.get("image_files_unreadable", 0))],
        ["Source-data tables screened / 已筛 source-data 表", str(coverage.get("source_tables_screened", 0))],
    ])]
    if coverage.get("image_files_unreadable"):
        lines += [f"- Image files that could not be read and were excluded from screening: {coverage['image_files_unreadable']}"]
    if coverage.get("detector_failures"):
        lines += [
            "",
            "**Detector execution failures / 检测器执行失败**",
            "",
            *[f"- {item}" for item in coverage["detector_failures"]],
        ]
    if coverage.get("audit_coverage_gap"):
        lines += [
            "- No detector could run on the supplied materials; this is a completeness gap, not a clean result.",
            "- 所供材料无法支持任何检测模块运行；这是完整性缺口，不是“干净”结论。",
        ]
    scope_note = coverage.get("scope_note")
    if scope_note:
        lines += [
            "",
            f"> {scope_note}",
            "> 中文提示：无发现只代表在当前材料和模块范围内未检出候选，不代表论文、图像或数据已被证明正确。",
        ]
    lines += [""]
    return lines


def render_claim_coverage(claim_coverage: dict[str, Any] | None) -> list[str]:
    if not claim_coverage:
        return []
    lines = ["## Claim Coverage / 声明-证据覆盖", ""]
    if not claim_coverage.get("supplied"):
        lines += [
            "No `claim_manifest.csv` was supplied for this audit run.",
            "",
            "本次未提供 `claim_manifest.csv`，因此没有逐条声明到证据的覆盖表。",
            "",
            "> Claim coverage is a claim-to-evidence completeness check, not a correctness verdict.",
            "> 声明覆盖只是完整性检查，不证明声明为真。",
            "",
        ]
        return lines
    lines += [table([
        ["Metric / 指标", "Count / 数量"],
        ["Claims declared / 已声明结论", str(claim_coverage.get("claims_declared", 0))],
        ["Claims with source data / 有 source data 的结论", str(claim_coverage.get("claims_with_source_data", 0))],
        ["Claims with raw records / 有 raw records 的结论", str(claim_coverage.get("claims_with_raw_records", 0))],
        ["Claims with analysis code / 有分析代码的结论", str(claim_coverage.get("claims_with_analysis_code", 0))],
        ["Claims with protocol link / 有 protocol 链接的结论", str(claim_coverage.get("claims_with_protocol_link", 0))],
        ["Claims with unresolved evidence gap / 仍有证据缺口的结论", str(claim_coverage.get("claims_with_unresolved_evidence_gap", 0))],
    ])]
    if claim_coverage.get("unresolved_claims"):
        lines += ["Unresolved claim-to-evidence gaps:", ""]
        for item in claim_coverage.get("unresolved_claims", []):
            reasons = ", ".join(item.get("gap_reasons", []) or ["not documented"])
            lines.append(f"- {item.get('claim_id', '')}: {reasons}")
        lines.append("")
    scope_note = claim_coverage.get("scope_note")
    if scope_note:
        lines += [f"> {scope_note}", ""]
    return lines


def methodology_status_label(status: str) -> str:
    labels = {
        "manual_review_ready": "Manual review ready / 可人工复核",
        "manual_review_limited": "Manual review limited / 人工复核材料有限",
        "materials_supplied_manual_review_required": "Materials supplied; manual review required / 已有材料，需人工复核",
        "partial_supporting_materials_manual_review_limited": "Partial support; manual review limited / 部分支撑材料，人工复核受限",
        "supporting_material_missing": "Supporting material missing / 缺少支撑材料",
        "not_requested": "Not requested for this domain scope / 本次领域范围未请求",
    }
    return labels.get(status, humanize(status))


def render_methodology_checklist(methodology_checklist: dict[str, Any] | None) -> list[str]:
    if not methodology_checklist:
        return []
    lines = ["## Methodology Readiness / 方法学准备度", ""]
    lines += [
        methodology_checklist.get(
            "boundary_note",
            "This checklist records supporting-material readiness for manual methodology review; it is not an automated compliance determination.",
        ),
        "",
        methodology_checklist.get(
            "boundary_note_zh",
            "本清单记录人工方法学复核的支撑材料准备度；不自动判定合规。",
        ),
        "",
    ]
    totals = methodology_checklist.get("totals", {}) or {}
    lines += [table([
        ["Item / 项目", "Count / 数量"],
        ["Requested modules / 本次请求模块", str(totals.get("modules_requested", 0))],
        ["Checks ready for manual review / 可进入人工复核的检查项", str(totals.get("checks_ready_for_manual_review", 0))],
        ["Checks with partial support / 部分支撑材料的检查项", str(totals.get("checks_partial_supporting_materials", 0))],
        ["Checks missing supporting materials / 缺少支撑材料的检查项", str(totals.get("checks_missing_supporting_materials", 0))],
    ])]

    requested_modules = [module for module in methodology_checklist.get("modules", []) or [] if module.get("requested")]
    if not requested_modules:
        lines += [
            "No methodology modules were requested by the domain scope.",
            "",
            "本次领域范围未请求具体方法学模块。",
            "",
        ]
        return lines

    module_rows = [["Module / 模块", "Standard / 标准", "Readiness / 准备度"]]
    for module in requested_modules:
        module_rows.append([
            f"{module.get('label_en', '')} / {module.get('label_zh', '')}",
            str(module.get("standard", "")),
            methodology_status_label(str(module.get("status", ""))),
        ])
    lines += [table(module_rows)]

    missing_rows = [["Module / 模块", "Check / 检查项", "Status / 状态", "Missing support / 缺少支撑", "Action / 动作"]]
    for module in requested_modules:
        for check in module.get("checks", []) or []:
            if check.get("status") not in {"supporting_material_missing", "partial_supporting_materials_manual_review_limited"}:
                continue
            missing_rows.append([
                f"{module.get('label_en', '')} / {module.get('label_zh', '')}",
                f"{check.get('label_en', '')} / {check.get('label_zh', '')}",
                methodology_status_label(str(check.get("status", ""))),
                ", ".join(check.get("missing_material_categories", []) or []),
                f"{check.get('recommended_action_en', '')} / {check.get('recommended_action_zh', '')}",
            ])
    if len(missing_rows) > 1:
        lines += [
            "**Material gaps for methodology review / 方法学复核材料缺口**",
            "",
            table(missing_rows),
        ]
    else:
        lines += [
            "All requested methodology modules have at least one supporting material category available for manual review.",
            "",
            "所有请求的方法学模块均至少具备一类可供人工复核的支撑材料。",
            "",
        ]

    ready_rows = [["Module / 模块", "Check / 检查项", "Status / 状态", "Supplied support / 已提供支撑"]]
    for module in requested_modules:
        for check in module.get("checks", []) or []:
            if check.get("status") not in {
                "materials_supplied_manual_review_required",
                "partial_supporting_materials_manual_review_limited",
            }:
                continue
            ready_rows.append([
                f"{module.get('label_en', '')} / {module.get('label_zh', '')}",
                f"{check.get('label_en', '')} / {check.get('label_zh', '')}",
                methodology_status_label(str(check.get("status", ""))),
                ", ".join(check.get("supplied_material_categories", []) or []),
            ])
    if len(ready_rows) > 1:
        lines += [
            "**Ready for human review / 可人工复核项目**",
            "",
            table(ready_rows),
        ]
    lines += [
        "> A ready item means supporting files exist; it does not mean the method is adequate or policy-compliant.",
        "> “可复核”只表示存在支撑文件；不代表方法充分或符合政策。",
        "",
    ]
    return lines


def render_quick_read(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    findings: list[dict[str, Any]],
    coverage: dict[str, Any] | None,
    mode: str,
) -> list[str]:
    missing_count = len(manifest.get("missing_materials", []) or [])
    finding_count = len(findings)
    reviewed_count = len(summary.get("materials_reviewed", []) or [])
    coverage_gap = bool((coverage or {}).get("audit_coverage_gap"))
    lines = [
        "## Quick Read / 快速结论",
        "",
        table([
            ["Item / 项目", "Result / 结果"],
            ["Mode / 模式", label_pair(mode, MODE_LABELS)],
            ["Overall risk / 总体风险", risk_label(summary.get("overall_risk", "R1"))],
            ["Candidate findings / 候选发现", str(finding_count)],
            ["Materials reviewed / 已审材料", f"{reviewed_count} {file_count_word(reviewed_count)}"],
            ["Missing material categories / 缺失材料类别", str(missing_count)],
            ["Coverage gap / 覆盖缺口", "yes / 是" if coverage_gap else "no / 否"],
        ]),
        "Read this first / 先读这一段：",
        "",
    ]
    if findings:
        top = sorted(findings, key=lambda item: RISK_ORDER.get(item.get("risk_level", "R0"), 0), reverse=True)[:3]
        lines += [
            "- The audit found candidate items that need review; the highest current level is "
            f"{risk_label(summary.get('overall_risk', 'R1'))}.",
            "- 本次审计检出需要复核的候选项；当前最高等级见上表。",
        ]
        for item in top:
            lines.append(
                f"- {item.get('finding_id', '')}: {finding_label(str(item.get('finding_type', '')))} "
                f"at `{item.get('location', '')}`."
            )
    elif missing_count or coverage_gap:
        lines += [
            "- No candidate findings were detected within the supplied materials and executed modules.",
            "- Overall risk remains R1 because missing materials or scope limits prevent a complete check.",
            "- 在已提供材料和已执行模块范围内未检出候选发现；但由于缺少材料或覆盖范围有限，总体仍为 R1。",
        ]
    else:
        lines += [
            "- No candidate findings were detected within the supplied materials and executed modules.",
            "- 未检出候选发现；这只说明当前材料与模块范围内未发现具体问题。",
        ]
    lines += [
        "",
        "> Important / 重要：This report does not prove the study, figures, or data are correct. It only describes the supplied scope and current screening results.",
        "> 本报告不证明研究、图像或数据正确；它只描述本次所供材料范围和当前筛查结果。",
        "",
    ]
    return lines


def render_findings(findings: list[dict[str, Any]]) -> list[str]:
    lines = ["## Findings / Evidence Ledger / 发现项与证据台账", ""]
    if not findings:
        lines += [
            "No candidate finding cards are present for this run.",
            "",
            "本次没有候选发现卡片。请仍然查看 Audit Coverage 和 Materials Needed，确认是否存在范围限制。",
            "",
        ]
        return lines
    for item in findings:
        finding_id = item.get("finding_id", "UNNUMBERED")
        lines += [
            f"### {finding_id}: {finding_label(str(item.get('finding_type', '')))}",
            "",
            table([
                ["Field / 字段", "Value / 内容"],
                ["Risk / 风险等级", risk_label(item.get("risk_level", ""))],
                ["Module / 模块", module_label(str(item.get("module", "")))],
                ["Location / 位置", item.get("location", "")],
            ]),
            "**What was observed / 观察到什么**",
            "",
            observation_text(item),
            "",
            zh_explanation_stub("observation"),
            "",
            "**Why it matters / 为什么需要复核**",
            "",
            why_it_matters(item),
            "",
            zh_explanation_stub("why"),
            "",
            "**Risk meaning / 风险含义**",
            "",
            risk_meaning(item.get("risk_level", "R1")),
            "",
            "**Evidence summary / 证据摘要**",
            "",
            *bullet_list(evidence_metric_lines(item.get("evidence"))),
            "",
            "**Possible benign explanations / 可能的良性解释**",
            "",
            *bullet_list(item.get("benign_explanations_considered", [])),
            "",
            "**Materials needed to resolve / 解决所需材料**",
            "",
            *bullet_list(item.get("required_materials_to_resolve", [])),
            "",
            "**Recommended action / 建议动作**",
            "",
            item.get("recommended_action", "") or "Verify against source/raw records before escalation. / 升级处理前请先核对 source/raw 记录。",
            "",
            f"_Note / 备注: {item.get('note', 'Calibrated finding; not a misconduct verdict. / 已校准发现；不是不端结论。')}_",
            "",
        ]
    return lines


def render_action_checklist(summary: dict[str, Any], manifest: dict[str, Any], findings: list[dict[str, Any]]) -> list[str]:
    lines = ["## Action Checklist / 下一步清单", ""]
    actions: list[tuple[str, str, str]] = []
    for item in findings:
        action = item.get("recommended_action", "")
        if action:
            actions.append((
                item.get("risk_level", "R1"),
                item.get("finding_id", ""),
                action,
            ))
    for item in manifest.get("missing_materials", []) or []:
        category = str(item.get("category", ""))
        actions.append((
            item.get("risk_level", "R1"),
            missing_material_label(category),
            f"Provide or document why this material is unavailable: {item.get('reason', category)}",
        ))
    methodology = summary.get("methodology_checklist") or {}
    for module in methodology.get("modules", []) or []:
        if not module.get("requested"):
            continue
        for check in module.get("checks", []) or []:
            if check.get("status") not in {"supporting_material_missing", "partial_supporting_materials_manual_review_limited"}:
                continue
            actions.append((
                "R1",
                f"{module.get('label_en', module.get('module_id', 'Methodology'))}",
                str(check.get("recommended_action_en") or "Add supporting material for methodology review."),
            ))
    if not actions:
        lines += [
            "- Preserve this report with the reviewed package snapshot.",
            "- Keep the machine-readable summary for future re-audit comparison.",
            "- 保存本报告和材料快照；保留机器摘要以便后续复审对比。",
            "",
        ]
        return lines
    rows = [["Priority / 优先级", "Item / 项目", "Action / 动作"]]
    for risk, item, action in sorted(actions, key=lambda row: RISK_ORDER.get(row[0], 0), reverse=True)[:12]:
        rows.append([risk_label(risk), item, action])
    lines += [table(rows)]
    if len(actions) > 12:
        lines += [f"_Additional actions omitted from this short checklist: {len(actions) - 12}._", ""]
    lines += [
        "> Use neutral internal language when following up. Ask for records and explanations; do not infer intent.",
        "> 跟进时使用中性语言：请求记录和解释，不推断主观意图。",
        "",
    ]
    return lines


def render_technical_appendix(findings: list[dict[str, Any]]) -> list[str]:
    lines = ["## Technical Appendix / 技术附录", ""]
    lines += [
        "The human sections above summarize detector evidence. Full structured payloads remain in `calibrated_findings.json`, detector output files, and the final `AUDIT_JSON_SUMMARY` block.",
        "",
        "上方主报告只摘要关键证据；完整结构化 payload 请查看 `calibrated_findings.json`、各检测器输出文件，以及末尾 `AUDIT_JSON_SUMMARY`。",
        "",
    ]
    if not findings:
        return lines
    rows = [["Finding / 发现", "Evidence details retained / 保留的技术细节"]]
    for item in findings:
        details = sentence_join(evidence_metric_lines(item.get("evidence"))[:4])
        rows.append([item.get("finding_id", ""), details or "See calibrated artifacts."])
    lines += [table(rows), ""]
    return lines


def render_report(
    mode: str,
    manifest: dict[str, Any],
    findings: list[dict[str, Any]],
    case_id: str | None,
    positive_evidence: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    claim_coverage: dict[str, Any] | None = None,
    methodology_checklist: dict[str, Any] | None = None,
) -> str:
    normalized = normalized_mode(mode)
    title = REPORT_TITLES.get(normalized, REPORT_TITLES["internal_presubmission"])
    positive_evidence = positive_evidence or []
    summary = build_summary(
        mode,
        case_id,
        manifest,
        findings,
        positive_evidence,
        coverage,
        claim_coverage,
        methodology_checklist,
    )
    validate_instance(summary, SUMMARY_SCHEMA, "audit summary")
    lines = [f"# {title}", ""]
    lines += render_quick_read(summary, manifest, findings, coverage, normalized)
    lines += ["## Scope / 范围", ""]
    lines += [
        f"- Mode / 模式: {label_pair(normalized, MODE_LABELS)} (`{mode}`)",
        f"- Case ID / 案例编号: `{case_id or 'not supplied'}`",
        f"- Package root / 材料目录: `{manifest.get('root', 'not supplied')}`",
        "",
    ]
    lines += render_coverage(coverage)
    lines += render_claim_coverage(claim_coverage)
    lines += render_methodology_checklist(methodology_checklist)

    lines += ["## Materials Needed / 需要补充的材料", ""]
    missing_rows = [["Material / 材料", "Risk / 风险", "Why needed / 为什么需要"]]
    for item in manifest.get("missing_materials", []):
        category = str(item.get("category", ""))
        missing_rows.append([
            missing_material_label(category),
            risk_label(item.get("risk_level", "R1")),
            item.get("reason", "") or "Needed for source/raw-level verification. / 用于 source/raw 级别复核。",
        ])
    if len(missing_rows) > 1:
        lines += [table(missing_rows)]
    else:
        lines += ["No missing expected material categories were reported.\n", "未报告预期材料类别缺失。\n"]

    if positive_evidence:
        lines += ["## Verified Traceability Evidence / 已验证可追溯证据", ""]
        rows = [["Figure/source relationship / 图像-来源关系", "Evidence source / 证据来源"]]
        for item in positive_evidence:
            for edge in item.get("edges", []):
                rows.append([
                    f"`{edge.get('left', '')}` -> `{edge.get('right', '')}`",
                    edge.get("provenance_edge", {}).get("evidence_source", "provenance graph"),
                ])
        lines += [table(rows)]
        lines += [
            "These links are positive provenance evidence, not image-reuse concerns.",
            "",
            "这些链接是正向可追溯证据，不是图像复用风险本身；它们也不等同于证明实验结论正确。",
            "",
        ]

    lines += ["## Risk Register / 风险登记", ""]
    risk_rows = [["Finding ID / 编号", "Risk / 风险", "Module / 模块", "Location / 位置", "Finding / 发现"]]
    for item in findings:
        risk_rows.append([
            item.get("finding_id", ""),
            risk_label(item.get("risk_level", "")),
            module_label(str(item.get("module", ""))),
            item.get("location", ""),
            finding_label(str(item.get("finding_type", ""))),
        ])
    if len(risk_rows) > 1:
        lines += [table(risk_rows)]
    else:
        lines += [
            "No candidate findings were detected within the supplied material and module scope.",
            "",
            "在已提供材料和已执行模块范围内，未检出候选发现。",
            "",
        ]

    lines += render_findings(findings)
    lines += render_action_checklist(summary, manifest, findings)
    lines += render_technical_appendix(findings)

    lines += [
        "## Integrity Boundary / 审计边界",
        "",
        "This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.",
        "",
        "本报告用于整理研究诚信风险和材料完整性缺口，不判断学术不端、主观意图或作者责任。",
        "",
        "## Audit JSON Summary / 机器可读摘要",
        "",
        JSON_BLOCK_MARKER,
        json.dumps(summary, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["internal", "external", "internal_presubmission", "external_public_material", "response_to_concern"],
        default="internal_presubmission",
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--findings", type=Path, action="append", default=[])
    parser.add_argument("--positive-evidence", type=Path, action="append", default=[])
    parser.add_argument("--coverage", type=Path)
    parser.add_argument("--claim-coverage", type=Path)
    parser.add_argument("--methodology-checklist", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--output", type=Path, default=Path("audit-report.md"))
    args = parser.parse_args()

    manifest = load_json(args.manifest, {})
    finding_payloads = [load_json(path, {}) for path in args.findings]
    positive_payloads = [load_json(path, {}) for path in args.positive_evidence]
    findings = normalize_findings(finding_payloads)
    positive_evidence = normalize_positive_evidence(positive_payloads)
    coverage = load_json(args.coverage, None) if args.coverage else None
    claim_coverage = load_json(args.claim_coverage, None) if args.claim_coverage else None
    methodology_checklist = load_json(args.methodology_checklist, None) if args.methodology_checklist else None
    args.output.write_text(
        render_report(
            args.mode,
            manifest,
            findings,
            args.case_id,
            positive_evidence,
            coverage,
            claim_coverage,
            methodology_checklist,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "findings": len(findings)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
