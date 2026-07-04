"""Audit coverage summarization for human-facing reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.pipeline.common import (
    DOCX_EXTS,
    FCS_EXTS,
    IMAGE_EXTS,
    KEY_EXTS,
    PDF_EXTS,
    PPTX_EXTS,
    PSD_EXTS,
    PZFX_EXTS,
    SOURCE_EXTS,
    TEXT_EXTS,
    XLSX_EXTS,
    has_files,
    read_json,
)


RAW_CANDIDATE_ARTIFACTS = (
    "package_guardrail_candidates.json",
    "stats_consistency_candidates.json",
    "pseudoreplication_candidates.json",
    "global_image_candidates.json",
    "keypoint_image_candidates.json",
    "channel_metadata_candidates.json",
    "splice_forensics_candidates.json",
    "local_patch_candidates.json",
    "text_overlap_candidates.json",
    "external_literature_candidates.json",
    "format_coverage_candidates.json",
    "audit_coverage_candidates.json",
)


IMAGE_SCREENING_BOUNDARY = {
    "automated_checks": [
        "whole-image near-duplicate screening within the supplied package",
        "D4 transforms for whole-image matches (identity, 90/180/270 rotation, horizontal/vertical flip, transpose, transverse)",
        "OpenCV ORB keypoint plus RANSAC homography screening for rotated, rescaled, cropped, or perspective-shifted image candidates",
        "overlapping-tile local patch reuse across supplied images",
        "same-image copy-move screening for non-overlapping repeated regions",
        "limited low-contrast same-image probing and multi-frame TIFF-like frame screening",
        "same-field/different-channel manifest declarations checked against available frame/channel metadata",
        "weak ELA/JPEG residual, JPEG-ghost profile, noise-map, and CFA-like grid triage for localized export/residual anomalies",
    ],
    "automated_checks_zh": [
        "在所供材料包内部做整图近重复筛查",
        "整图匹配支持 D4 变换（原图、90/180/270 度旋转、水平/垂直翻转、转置、反转置）",
        "使用 OpenCV ORB keypoint 与 RANSAC homography 筛查旋转、缩放、裁剪或透视变化后的图像相似候选",
        "在所供图像之间做重叠 tile 的局部 patch 复用筛查",
        "在同一图像内部筛查非重叠区域的 copy-move 候选",
        "有限的低对比同图探测，以及 multi-frame TIFF-like 文件的逐帧筛查",
        "把同视野/不同通道 manifest 声明与已有 frame/channel metadata 做交叉核对",
        "用弱 ELA/JPEG residual、JPEG-ghost profile、noise-map 和 CFA-like grid triage 提示局部导出/残差异常",
    ],
    "not_covered": [
        "cross-paper or external image-corpus search",
        "elastic deformation, nonrigid registration, severe perspective distortion, or very low-feature images outside ORB/RANSAC limits",
        "specialist splice forensics beyond weak triage, such as sensor-pattern authentication, lighting/shadow inconsistency, or robust JPEG ghost analysis beyond weak profile prompts",
        "manual verification of whether a repeated region is scientifically justified by sample maps, lanes, channels, or raw acquisition metadata",
        "proof that a figure is authentic or free of manipulation",
    ],
    "not_covered_zh": [
        "跨论文或外部图像库检索",
        "ORB/RANSAC 能力之外的弹性形变、非刚性配准、严重透视扭曲或特征点很少的图像",
        "弱提示之外的专业拼接取证，例如传感器模式认证、光照/阴影不一致或弱 profile 提示之外的稳健 JPEG ghost 分析",
        "人工核验重复区域是否能被样本图、泳道、通道或原始采集元数据合理解释",
        "证明图像真实、未被处理或完全无问题",
    ],
    "interpretation_note": (
        "No image finding means no candidate was detected within these automated checks, supplied files, "
        "and runtime budgets. It is not a complete image-forensics clearance."
    ),
    "interpretation_note_zh": (
        "没有图像 finding 只代表在这些自动检查、所供文件和运行预算内未检出候选；"
        "这不是完整图像取证结论。"
    ),
}


def build_coverage(
    package: Path,
    output_dir: Path,
    detector_outputs: list[Path],
    external_provider: str | None,
    scan_profile: str = "standard",
) -> dict[str, Any]:
    """Summarize what the audit actually screened so a clean report is not mistaken for a clean paper."""

    def load_safe(name: str) -> dict[str, Any] | None:
        path = output_dir / name
        return read_json(path) if path.exists() else None

    unreadable_image_files: dict[str, dict[str, str]] = {}

    def record_unreadable_image_errors(payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        for error in payload.get("errors", []) or []:
            if not isinstance(error, dict):
                continue
            path_value = str(error.get("path") or "").strip()
            if not path_value:
                continue
            key = path_value.replace("\\", "/")
            unreadable_image_files.setdefault(key, {
                "path": key,
                "message": str(error.get("error") or error.get("message") or "could not be read"),
                "detector": str(payload.get("detector_name") or "image_screening"),
            })

    coverage: dict[str, Any] = {
        "modules_executed": [],
        "modules_not_executed": [],
        "image_panels_screened": 0,
        "image_files_unreadable": 0,
        "unreadable_image_files": [],
        "image_screening_input_files": 0,
        "image_screening_derived_images": 0,
        "image_screening_derived_sources": [],
        "image_screening_inputs_note": "",
        "keypoint_pairs_screened": 0,
        "keypoint_candidates": 0,
        "keypoint_screening_limits": [],
        "source_tables_screened": 0,
        "prism_pzfx_files_read": 0,
        "prism_tables_indexed": 0,
        "prism_graphs_indexed": 0,
        "prism_possible_graph_table_links": 0,
        "prism_project_errors": [],
        "prism_project_error_count": 0,
        "prism_project_review_items": [],
        "xlsx_files_structurally_read": 0,
        "xlsx_sheets_indexed": 0,
        "xlsx_formula_cells_scanned": 0,
        "xlsx_hidden_sheets": 0,
        "xlsx_merged_cell_ranges": 0,
        "xlsx_structure_errors": [],
        "xlsx_structure_error_count": 0,
        "xlsx_structure_review_items": [],
        "fcs_files_read": 0,
        "fcs_files_unreadable": 0,
        "fcs_total_events_reported": 0,
        "fcs_parameters_indexed": 0,
        "fcs_files_with_compensation_keywords": 0,
        "fcs_metadata_errors": [],
        "fcs_metadata_error_count": 0,
        "fcs_metadata_review_items": [],
        "pdf_files_screened": 0,
        "pdf_captions_extracted": 0,
        "pdf_table_like_blocks_extracted": 0,
        "pdf_structure_errors": [],
        "pdf_structure_error_count": 0,
        "docx_files_screened": 0,
        "docx_paragraphs_extracted": 0,
        "docx_captions_extracted": 0,
        "docx_table_like_blocks_extracted": 0,
        "docx_structure_errors": [],
        "docx_structure_error_count": 0,
        "docx_structure_warnings": [],
        "docx_structure_warning_count": 0,
        "pdf_embedded_images_extracted": 0,
        "pdf_embedded_image_files": [],
        "pdf_embedded_image_errors": [],
        "pdf_embedded_image_error_count": 0,
        "pptx_files_structurally_read": 0,
        "pptx_slides_read": 0,
        "pptx_text_paragraphs_extracted": 0,
        "pptx_speaker_note_paragraphs_extracted": 0,
        "pptx_alt_text_entries_extracted": 0,
        "pptx_explicit_path_mentions": 0,
        "pptx_explicit_path_pairs": 0,
        "pptx_structure_errors": [],
        "pptx_structure_error_count": 0,
        "pptx_structure_warnings": [],
        "pptx_structure_warning_count": 0,
        "pptx_structure_review_items": [],
        "pptx_embedded_images_extracted": 0,
        "pptx_embedded_image_files": [],
        "pptx_embedded_image_errors": [],
        "pptx_embedded_image_error_count": 0,
        "key_embedded_images_extracted": 0,
        "key_embedded_image_files": [],
        "key_embedded_image_errors": [],
        "key_embedded_image_error_count": 0,
        "psd_preview_images_extracted": 0,
        "psd_preview_image_files": [],
        "psd_preview_image_errors": [],
        "psd_preview_image_error_count": 0,
        "image_metadata_files_screened": 0,
        "image_metadata_multiframe_files": 0,
        "image_metadata_ome_files": 0,
        "image_metadata_channel_files": 0,
        "image_metadata_z_stack_files": 0,
        "image_metadata_manual_review_files": 0,
        "image_metadata_error_count": 0,
        "image_metadata_review_items": [],
        "channel_metadata_declarations_checked": 0,
        "channel_metadata_supported_declarations": 0,
        "channel_metadata_verification_gaps": 0,
        "channel_metadata_review_items": [],
        "splice_forensics_images_screened": 0,
        "splice_forensics_candidates": 0,
        "splice_forensics_limit_reached": False,
        "splice_forensics_review_items": [],
        "detector_failures": [],
        "raw_detector_candidate_count": 0,
        "positive_provenance_count": 0,
        "assembly_manifest_warnings": [],
        "assembly_manifest_warning_count": 0,
        "unsupported_relevant_files": [],
        "unsupported_relevant_file_count": 0,
        "audit_coverage_gap": False,
        "package_guardrail_active": False,
        "package_guardrail_image_screening_blocked": False,
        "image_screening_boundary": IMAGE_SCREENING_BOUNDARY,
        "external_literature_provider": external_provider,
        "scan_profile": scan_profile,
        "execution_mode": "sequential",
        "parallel_workstreams_enabled": False,
        "workstream_count": 0,
        "workstreams": [],
        "profile_parameters": (
            {
                "global_image_hash_threshold": 8,
                "keypoint_max_dimension": 1400,
                "keypoint_min_inliers": 18,
                "keypoint_min_inlier_ratio": 0.20,
                "keypoint_max_pair_comparisons": 5000,
                "local_patch_tile_size": 96,
                "local_patch_stride": 48,
                "local_patch_hash_threshold": 5,
            }
            if scan_profile == "deep"
            else {}
        ),
        "scope_note": (
            "A module with no findings means no candidate was detected within the current detector "
            "scope and supplied materials; it is not a guarantee of correctness. Methodology and "
            "reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and "
            "exhaustive external plagiarism-database search are not performed automatically and require "
            "human review."
        ),
    }

    guardrail_payload = load_safe("package_guardrail_candidates.json")
    if guardrail_payload:
        coverage["modules_executed"].append("package_intake_guardrail")
        guardrail_input = guardrail_payload.get("input", {}) or {}
        coverage["package_guardrail_active"] = True
        coverage["package_guardrail"] = guardrail_input
        coverage["package_guardrail_image_screening_blocked"] = bool(guardrail_input.get("image_screening_blocked"))
        if guardrail_input.get("image_screening_blocked"):
            coverage["modules_not_executed"].append(
                "image screening (blocked by package intake resource guardrail; not a clean result)"
            )

    workstream_payload = load_safe("workstreams.json")
    if workstream_payload:
        workstreams = workstream_payload.get("workstreams", []) or []
        coverage["execution_mode"] = str(workstream_payload.get("execution_mode", "sequential"))
        coverage["parallel_workstreams_enabled"] = bool(workstream_payload.get("parallel_enabled"))
        coverage["workstream_count"] = len(workstreams)
        coverage["workstreams"] = [
            {
                "phase": str(item.get("phase", "")),
                "name": str(item.get("name", "")),
                "status": str(item.get("status", "")),
                "elapsed_seconds": item.get("elapsed_seconds"),
                "output_count": item.get("output_count"),
            }
            for item in workstreams
            if isinstance(item, dict)
        ]
        coverage["workstream_scope_note"] = str(workstream_payload.get("scope_note", ""))
        coverage["modules_executed"].append("portable_parallel_workstream_orchestration")

    screening_payload = load_safe("image_screening_inputs.json")
    screening_original_images = (screening_payload or {}).get("original_images", []) or []
    screening_derived_images = (screening_payload or {}).get("derived_images", []) or []
    image_screening_has_inputs = bool(screening_original_images or screening_derived_images) or has_files(package, IMAGE_EXTS)

    if image_screening_has_inputs and not coverage.get("package_guardrail_image_screening_blocked"):
        coverage["modules_executed"].append("image_global_near_duplicate")
        if scan_profile == "quick":
            coverage["modules_not_executed"].append(
                "local patch / same-image copy-move deep image screening (skipped by quick scan profile)"
            )
            coverage["modules_not_executed"].append(
                "keypoint geometric image screening (skipped by quick scan profile)"
            )
            coverage["modules_not_executed"].append(
                "ELA/JPEG residual, JPEG-ghost profile, noise-map, and CFA-like grid splice-forensics triage (skipped by quick scan profile)"
            )
        else:
            coverage["modules_executed"].append("image_splice_forensics_triage")
            coverage["modules_executed"].append("image_keypoint_geometric_match")
            coverage["modules_executed"].append("image_local_patch_and_same_image_copy_move")
        global_payload = load_safe("global_image_candidates.json")
        if global_payload:
            coverage["image_panels_screened"] = int(global_payload.get("images_screened", 0) or 0)
            record_unreadable_image_errors(global_payload)
        if scan_profile != "quick":
            splice_payload = load_safe("splice_forensics_candidates.json")
            if splice_payload:
                record_unreadable_image_errors(splice_payload)
                coverage["splice_forensics_images_screened"] = int(
                    splice_payload.get("images_screened", 0) or 0
                )
                coverage["splice_forensics_candidates"] = int(
                    splice_payload.get("candidate_signal_count", 0) or 0
                )
                coverage["splice_forensics_limit_reached"] = bool(splice_payload.get("coverage_limit_reached"))
                coverage["splice_forensics_scope_note"] = str(splice_payload.get("scope_note", ""))
                review_items = []
                for item in splice_payload.get("diagnostics", []) or []:
                    if not isinstance(item, dict):
                        continue
                    if item.get("signals"):
                        review_items.append({
                            "path": str(item.get("path", "")),
                            "signals": item.get("signals", []) or [],
                            "ela_best_robust_z": item.get("ela_best_robust_z"),
                            "jpeg_ghost_best_robust_z": item.get("jpeg_ghost_best_robust_z"),
                            "jpeg_ghost_profile_range": item.get("jpeg_ghost_profile_range"),
                            "jpeg_ghost_min_quality": item.get("jpeg_ghost_min_quality"),
                            "noise_best_robust_z": item.get("noise_best_robust_z"),
                            "cfa_best_robust_z": item.get("cfa_best_robust_z"),
                            "cfa_best_mean": item.get("cfa_best_mean"),
                        })
                coverage["splice_forensics_review_items"] = review_items[:20]
                if coverage["splice_forensics_limit_reached"]:
                    coverage["modules_not_executed"].append(
                        "some ELA/JPEG residual, JPEG-ghost profile, noise-map, and CFA-like grid splice-forensics triage "
                        "(image budget reached; not a clean result)"
                    )
            keypoint_payload = load_safe("keypoint_image_candidates.json")
            if keypoint_payload:
                record_unreadable_image_errors(keypoint_payload)
                coverage["keypoint_pairs_screened"] = int(
                    keypoint_payload.get("pairwise_comparisons_attempted", 0) or 0
                )
                coverage["keypoint_candidates"] = int(keypoint_payload.get("candidate_pair_count", 0) or 0)
                keypoint_limits = keypoint_payload.get("comparison_limit_records", []) or []
                if keypoint_limits:
                    coverage["keypoint_screening_limits"] = keypoint_limits
                    coverage["keypoint_screening_limit_note"] = (
                        "Keypoint geometric screening reached a pair-comparison budget. This records partial "
                        "rotation/scale/perspective coverage and should be resolved with a focused deep scan "
                        "before treating geometric image coverage as complete."
                    )
                    coverage["modules_not_executed"].append(
                        "some keypoint geometric image pair comparisons "
                        "(runtime budget reached; not a clean result)"
                    )
            local_payload = load_safe("local_patch_candidates.json")
            if local_payload:
                record_unreadable_image_errors(local_payload)
                coverage["modality_routing_enabled"] = bool(
                    (local_payload.get("input") or {}).get("modality_routing_enabled")
                )
                excluded = local_payload.get("panels_excluded_from_deep_scan", []) or []
                conflicts = local_payload.get("modality_conflicts", []) or []
                local_limits = local_payload.get("tile_limit_records", []) or []
                composite_panel_records = local_payload.get("composite_panel_cut_records", []) or []
                composite_image_like_panels = int(local_payload.get("composite_image_like_panels_screened", 0) or 0)
                composite_presentation_skipped = int(
                    local_payload.get("composite_presentation_regions_skipped", 0) or 0
                )
                graphic_tiles_suppressed = int(local_payload.get("graphic_tiles_suppressed", 0) or 0)
                graphic_suppression_records = local_payload.get("graphic_tile_suppression_records", []) or []
                if conflicts:
                    coverage["modality_conflicts"] = conflicts
                    coverage["modality_conflict_note"] = (
                        "Panels listed below have mixed experimental and schematic/chart declarations on "
                        "authoritative manifest edges. Deep image screening was retained; this is not clearance."
                    )
                if excluded:
                    coverage["panels_excluded_from_deep_scan"] = excluded
                    coverage["deep_scan_exclusion_note"] = (
                        "Panels listed below were excluded from local patch / same-image copy-move "
                        "screening because of their declared modality. Exclusion records audit scope "
                        "only; it is not clearance, approval, or evidence that those panels are correct."
                    )
                    coverage["modules_not_executed"].append(
                        "local patch / same-image copy-move screening on "
                        f"{len(excluded)} schematic/chart panel(s) (modality-aware exclusion; not a clean result)"
                    )
                if composite_panel_records:
                    coverage["local_patch_composite_panel_cutter_enabled"] = bool(
                        (local_payload.get("input") or {}).get("composite_panel_cutter_enabled")
                    )
                    coverage["local_patch_composite_image_like_panels_screened"] = composite_image_like_panels
                    coverage["local_patch_composite_presentation_regions_skipped"] = composite_presentation_skipped
                    coverage["local_patch_composite_panel_cut_records"] = composite_panel_records[:20]
                    coverage["local_patch_composite_panel_cutter_note"] = (
                        "Exported composite figure panels were split into image-like subpanels before local "
                        "patch / same-image copy-move screening. Sparse chart/text/axis presentation regions "
                        "were not treated as biological image panels. This is routing and scope disclosure, "
                        "not clearance of skipped presentation regions."
                    )
                if graphic_tiles_suppressed:
                    coverage["local_patch_chart_text_axis_tiles_suppressed"] = graphic_tiles_suppressed
                    coverage["local_patch_chart_text_axis_suppression_records"] = graphic_suppression_records[:20]
                    coverage["local_patch_chart_text_axis_suppression_note"] = (
                        "Local patch / same-image copy-move screening suppressed sparse chart/text/axis/blank "
                        "presentation tiles in figure-panel exports before biological-image tile comparison. "
                        "This is a false-positive control and a scope disclosure, not clearance of the chart "
                        "or the surrounding figure panel."
                    )
                if local_limits:
                    coverage["local_patch_screening_limits"] = local_limits
                    coverage["local_patch_screening_limit_note"] = (
                        "Local patch / same-image copy-move screening reached a tile or comparison budget. "
                        "This records partial local image coverage and should be resolved with a focused deep scan "
                        "before treating local-patch coverage as complete."
                    )
                    coverage["modules_not_executed"].append(
                        "some local patch / same-image copy-move tile comparisons "
                        "(runtime budget reached; not a clean result)"
                    )
    elif not image_screening_has_inputs:
        coverage["modules_not_executed"].append("image screening (no image files supplied)")

    stats_payload = load_safe("stats_consistency_candidates.json")
    if stats_payload:
        coverage["modules_executed"].append("statistics_consistency")
        coverage["source_tables_screened"] = len(stats_payload.get("files_screened", []) or [])
    if has_files(package / "source_data", SOURCE_EXTS):
        coverage["modules_executed"].append("pseudoreplication")
    else:
        coverage["modules_not_executed"].append("pseudoreplication screening (no source_data CSV/TSV/XLSX/PZFX supplied)")
    if not stats_payload:
        coverage["modules_not_executed"].append(
            "statistics screening (no source_data or supplementary CSV/TSV/XLSX/PZFX source tables supplied)"
        )

    xlsx_payload = load_safe("xlsx_structure.json")
    if xlsx_payload:
        coverage["modules_executed"].append("xlsx_workbook_structure_intake")
        sheets = xlsx_payload.get("sheets", []) or []
        coverage["xlsx_files_structurally_read"] = len(xlsx_payload.get("xlsx_files", []) or [])
        coverage["xlsx_sheets_indexed"] = len(sheets)
        coverage["xlsx_formula_cells_scanned"] = sum(
            int(item.get("formula_cell_count_scanned", 0) or 0)
            for item in sheets
            if isinstance(item, dict)
        )
        coverage["xlsx_hidden_sheets"] = sum(
            1
            for item in sheets
            if isinstance(item, dict) and str(item.get("sheet_state", "visible")) != "visible"
        )
        coverage["xlsx_merged_cell_ranges"] = sum(
            int(item.get("merged_cell_range_count", 0) or 0)
            for item in sheets
            if isinstance(item, dict)
        )
        xlsx_errors = xlsx_payload.get("errors", []) or []
        if xlsx_errors:
            coverage["xlsx_structure_errors"] = xlsx_errors
            coverage["xlsx_structure_error_count"] = len(xlsx_errors)
            coverage["modules_not_executed"].append(
                "some XLSX workbook structure intake (workbook parsing failed; not a clean result)"
            )
        coverage["xlsx_structure_scope_note"] = str(xlsx_payload.get("scope_note", ""))
        review_items = []
        for item in sheets:
            if not isinstance(item, dict):
                continue
            review_items.append({
                "source_xlsx": str(item.get("source_xlsx", "")),
                "sheet_name": str(item.get("sheet_name", "")),
                "suggested_label": str(item.get("suggested_label", "")),
                "headers": item.get("headers", []) or [],
                "data_rows_scanned": item.get("data_rows_scanned"),
                "formula_cell_count_scanned": item.get("formula_cell_count_scanned"),
                "sheet_state": str(item.get("sheet_state", "")),
            })
        coverage["xlsx_structure_review_items"] = review_items[:20]
    elif has_files(package, XLSX_EXTS):
        coverage["modules_not_executed"].append(
            "XLSX workbook structure intake (no xlsx_structure.json artifact was produced)"
        )

    prism_payload = load_safe("prism_project_intake.json")
    if prism_payload:
        coverage["modules_executed"].append("prism_project_intake")
        coverage["prism_pzfx_files_read"] = len(prism_payload.get("pzfx_files", []) or [])
        coverage["prism_tables_indexed"] = len(prism_payload.get("tables", []) or [])
        coverage["prism_graphs_indexed"] = len(prism_payload.get("graphs", []) or [])
        coverage["prism_possible_graph_table_links"] = len(prism_payload.get("graph_table_links", []) or [])
        prism_errors = prism_payload.get("errors", []) or []
        if prism_errors:
            coverage["prism_project_errors"] = prism_errors
            coverage["prism_project_error_count"] = len(prism_errors)
            coverage["modules_not_executed"].append(
                "some GraphPad Prism project intake (PZFX metadata parse failed; not a clean result)"
            )
        coverage["prism_project_scope_note"] = str(prism_payload.get("scope_note", ""))
        review_items = []
        for item in prism_payload.get("graph_table_links", []) or []:
            if not isinstance(item, dict):
                continue
            review_items.append({
                "source_pzfx": str(item.get("source_pzfx", "")),
                "graph_title": str(item.get("graph_title", "")),
                "table_title": str(item.get("table_title", "")),
                "table_id": str(item.get("table_id", "")),
                "match_basis": str(item.get("match_basis", "")),
            })
        coverage["prism_project_review_items"] = review_items[:20]
    elif has_files(package, PZFX_EXTS):
        coverage["modules_not_executed"].append(
            "GraphPad Prism project intake (no prism_project_intake.json artifact was produced)"
        )

    fcs_payload = load_safe("fcs_metadata_intake.json")
    if fcs_payload:
        coverage["modules_executed"].append("flow_fcs_metadata_intake")
        totals = fcs_payload.get("totals", {}) or {}
        coverage["fcs_files_read"] = int(totals.get("readable_fcs_files", 0) or 0)
        coverage["fcs_files_unreadable"] = int(totals.get("unreadable_fcs_files", 0) or 0)
        coverage["fcs_total_events_reported"] = int(totals.get("total_events_reported", 0) or 0)
        coverage["fcs_parameters_indexed"] = int(totals.get("total_parameters_indexed", 0) or 0)
        coverage["fcs_files_with_compensation_keywords"] = int(totals.get("files_with_compensation_keywords", 0) or 0)
        fcs_errors = fcs_payload.get("errors", []) or []
        if fcs_errors:
            coverage["fcs_metadata_errors"] = fcs_errors
            coverage["fcs_metadata_error_count"] = len(fcs_errors)
            coverage["modules_not_executed"].append(
                "some FCS metadata intake (FCS header/text parsing failed; not a clean result)"
            )
        coverage["fcs_metadata_scope_note"] = str(fcs_payload.get("scope_note", ""))
        review_items = []
        for item in fcs_payload.get("fcs_files", []) or []:
            if not isinstance(item, dict) or item.get("parse_status") != "parsed":
                continue
            parameters = item.get("parameters", []) or []
            marker_labels = []
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    continue
                label = str(parameter.get("marker") or parameter.get("name") or "").strip()
                if label:
                    marker_labels.append(label)
            review_items.append({
                "path": str(item.get("path", "")),
                "event_count": item.get("event_count"),
                "parameter_count": item.get("parameter_count"),
                "cytometer": str(item.get("cytometer", "")),
                "date": str(item.get("date", "")),
                "compensation_present": bool(item.get("compensation_present")),
                "markers": marker_labels[:12],
            })
        coverage["fcs_metadata_review_items"] = review_items[:20]
    elif has_files(package, FCS_EXTS):
        coverage["modules_not_executed"].append(
            "FCS metadata intake (no fcs_metadata_intake.json artifact was produced)"
        )

    format_payload = load_safe("format_coverage_candidates.json")
    if format_payload:
        unsupported_rows: list[dict[str, Any]] = []
        for candidate in format_payload.get("candidates", []) or []:
            evidence = candidate.get("evidence") if isinstance(candidate, dict) else {}
            if not isinstance(evidence, dict):
                continue
            for path in evidence.get("files", []) or []:
                unsupported_rows.append({
                    "path": str(path),
                    "gap_type": str(evidence.get("gap_type", "unsupported_relevant_format")),
                    "message": str(evidence.get("message", "")),
                    "recommended_exports": evidence.get("recommended_exports", []) or [],
                })
        if unsupported_rows:
            coverage["unsupported_relevant_files"] = unsupported_rows
            coverage["unsupported_relevant_file_count"] = len(unsupported_rows)
            coverage["modules_not_executed"].append(
                "screening of some supplied document/source-data/PDF container files "
                "(unsupported format exports required; not a clean result)"
            )

    if has_files(package, TEXT_EXTS):
        coverage["modules_executed"].append("package_internal_text_overlap")
    else:
        coverage["modules_not_executed"].append("text-overlap screening (no manuscript/text supplied)")

    docx_structure_payload = load_safe("docx_structure.json")
    if docx_structure_payload:
        coverage["modules_executed"].append("docx_caption_table_structure_extraction")
        coverage["docx_files_screened"] = len(docx_structure_payload.get("docx_files", []) or [])
        coverage["docx_paragraphs_extracted"] = len(docx_structure_payload.get("paragraphs", []) or [])
        coverage["docx_captions_extracted"] = len(docx_structure_payload.get("captions", []) or [])
        coverage["docx_table_like_blocks_extracted"] = len(docx_structure_payload.get("table_like_blocks", []) or [])
        docx_warnings = docx_structure_payload.get("warnings", []) or []
        if docx_warnings:
            coverage["docx_structure_warnings"] = docx_warnings
            coverage["docx_structure_warning_count"] = len(docx_warnings)
            coverage["modules_not_executed"].append(
                "some DOCX review layers (comments, tracked changes, or embedded objects were detected; not a clean result)"
            )
        docx_errors = docx_structure_payload.get("errors", []) or []
        if docx_errors:
            coverage["docx_structure_errors"] = docx_errors
            coverage["docx_structure_error_count"] = len(docx_errors)
            coverage["modules_not_executed"].append(
                "some DOCX paragraph/caption/table structure extraction (DOCX parsing failed; not a clean result)"
            )
        coverage["docx_structure_scope_note"] = str(docx_structure_payload.get("scope_note", ""))
    elif has_files(package, DOCX_EXTS):
        coverage["modules_not_executed"].append(
            "DOCX paragraph/caption/table structure extraction (no docx_structure.json artifact was produced)"
        )

    pdf_structure_payload = load_safe("pdf_structure.json")
    if pdf_structure_payload:
        coverage["modules_executed"].append("pdf_caption_table_structure_extraction")
        coverage["pdf_files_screened"] = len(pdf_structure_payload.get("pdfs", []) or [])
        coverage["pdf_captions_extracted"] = len(pdf_structure_payload.get("captions", []) or [])
        coverage["pdf_table_like_blocks_extracted"] = len(pdf_structure_payload.get("table_like_blocks", []) or [])
        pdf_errors = pdf_structure_payload.get("errors", []) or []
        if pdf_errors:
            coverage["pdf_structure_errors"] = pdf_errors
            coverage["pdf_structure_error_count"] = len(pdf_errors)
            coverage["modules_not_executed"].append(
                "some PDF caption/table structure extraction (PDF text extraction failed; not a clean result)"
            )
        coverage["pdf_structure_scope_note"] = str(pdf_structure_payload.get("scope_note", ""))
    elif has_files(package, PDF_EXTS):
        coverage["modules_not_executed"].append(
            "PDF caption/table structure extraction (no pdf_structure.json artifact was produced)"
        )

    pdf_image_payload = load_safe("pdf_embedded_images.json")
    if pdf_image_payload:
        coverage["modules_executed"].append("pdf_embedded_image_extraction")
        pdf_images = pdf_image_payload.get("images", []) or []
        coverage["pdf_embedded_images_extracted"] = len(pdf_images)
        coverage["pdf_embedded_image_files"] = [
            {
                "source_pdf": str(item.get("source_pdf", "")),
                "page": item.get("page"),
                "output_path": str(item.get("output_path", "")),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in pdf_images
            if isinstance(item, dict)
        ]
        pdf_image_errors = pdf_image_payload.get("errors", []) or []
        if pdf_image_errors:
            coverage["pdf_embedded_image_errors"] = pdf_image_errors
            coverage["pdf_embedded_image_error_count"] = len(pdf_image_errors)
            coverage["modules_not_executed"].append(
                "some PDF embedded-image extraction (PDF image export failed; not a clean result)"
            )
        coverage["pdf_embedded_image_scope_note"] = str(pdf_image_payload.get("scope_note", ""))
    elif has_files(package, PDF_EXTS):
        coverage["modules_not_executed"].append(
            "PDF embedded-image extraction (no pdf_embedded_images.json artifact was produced)"
        )

    pptx_structure_payload = load_safe("pptx_structure.json")
    if pptx_structure_payload:
        coverage["modules_executed"].append("pptx_slide_text_path_structure_extraction")
        pptx_files = pptx_structure_payload.get("pptx_files", []) or []
        coverage["pptx_files_structurally_read"] = len(pptx_files)
        coverage["pptx_slides_read"] = len(pptx_structure_payload.get("slides", []) or [])
        coverage["pptx_text_paragraphs_extracted"] = sum(
            int(item.get("paragraph_count", 0) or 0)
            for item in pptx_structure_payload.get("slides", []) or []
            if isinstance(item, dict)
        )
        coverage["pptx_speaker_note_paragraphs_extracted"] = sum(
            int(item.get("speaker_note_paragraph_count", 0) or 0)
            for item in pptx_structure_payload.get("slides", []) or []
            if isinstance(item, dict)
        )
        coverage["pptx_alt_text_entries_extracted"] = sum(
            int(item.get("alt_text_count", 0) or 0)
            for item in pptx_structure_payload.get("slides", []) or []
            if isinstance(item, dict)
        )
        coverage["pptx_explicit_path_mentions"] = len(pptx_structure_payload.get("explicit_path_mentions", []) or [])
        coverage["pptx_explicit_path_pairs"] = len(pptx_structure_payload.get("explicit_path_pairs", []) or [])
        pptx_structure_errors = pptx_structure_payload.get("errors", []) or []
        if pptx_structure_errors:
            coverage["pptx_structure_errors"] = pptx_structure_errors
            coverage["pptx_structure_error_count"] = len(pptx_structure_errors)
            coverage["modules_not_executed"].append(
                "some PPTX text/path structure extraction (PPTX parsing failed; not a clean result)"
            )
        pptx_structure_warnings = pptx_structure_payload.get("warnings", []) or []
        if pptx_structure_warnings:
            coverage["pptx_structure_warnings"] = pptx_structure_warnings
            coverage["pptx_structure_warning_count"] = len(pptx_structure_warnings)
        coverage["pptx_structure_scope_note"] = str(pptx_structure_payload.get("scope_note", ""))
        review_items = []
        for item in pptx_structure_payload.get("explicit_path_pairs", []) or []:
            if not isinstance(item, dict):
                continue
            review_items.append({
                "source_pptx": str(item.get("evidence_source", "")).split("#", 1)[0],
                "slide": str(item.get("evidence_source", "")).split("#", 1)[-1],
                "figure_panel": str(item.get("source_path", "")),
                "source_record": str(item.get("target_path", "")),
                "relation_type": str(item.get("relation_type", "")),
            })
        coverage["pptx_structure_review_items"] = review_items[:20]
    elif has_files(package, PPTX_EXTS):
        coverage["modules_not_executed"].append(
            "PPTX text/path structure extraction (no pptx_structure.json artifact was produced)"
        )

    pptx_image_payload = load_safe("pptx_embedded_images.json")
    if pptx_image_payload:
        coverage["modules_executed"].append("pptx_embedded_image_extraction")
        pptx_images = pptx_image_payload.get("images", []) or []
        coverage["pptx_embedded_images_extracted"] = len(pptx_images)
        coverage["pptx_embedded_image_files"] = [
            {
                "source_pptx": str(item.get("source_pptx", "")),
                "referenced_slides": item.get("referenced_slides", []) or [],
                "output_path": str(item.get("output_path", "")),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in pptx_images
            if isinstance(item, dict)
        ]
        pptx_image_errors = pptx_image_payload.get("errors", []) or []
        if pptx_image_errors:
            coverage["pptx_embedded_image_errors"] = pptx_image_errors
            coverage["pptx_embedded_image_error_count"] = len(pptx_image_errors)
            coverage["modules_not_executed"].append(
                "some PPTX embedded-image extraction (PPTX media export failed; not a clean result)"
            )
        coverage["pptx_embedded_image_scope_note"] = str(pptx_image_payload.get("scope_note", ""))
    elif has_files(package, PPTX_EXTS):
        coverage["modules_not_executed"].append(
            "PPTX embedded-image extraction (no pptx_embedded_images.json artifact was produced)"
        )

    key_image_payload = load_safe("key_embedded_images.json")
    if key_image_payload:
        coverage["modules_executed"].append("key_embedded_image_extraction")
        key_images = key_image_payload.get("images", []) or []
        coverage["key_embedded_images_extracted"] = len(key_images)
        coverage["key_embedded_image_files"] = [
            {
                "source_key": str(item.get("source_key", "")),
                "internal_path": str(item.get("internal_path", "")),
                "output_path": str(item.get("output_path", "")),
                "width": item.get("width"),
                "height": item.get("height"),
            }
            for item in key_images
            if isinstance(item, dict)
        ]
        key_image_errors = key_image_payload.get("errors", []) or []
        if key_image_errors:
            coverage["key_embedded_image_errors"] = key_image_errors
            coverage["key_embedded_image_error_count"] = len(key_image_errors)
            coverage["modules_not_executed"].append(
                "some Keynote embedded-image extraction (Keynote media export failed; not a clean result)"
            )
        coverage["key_embedded_image_scope_note"] = str(key_image_payload.get("scope_note", ""))
    elif has_files(package, KEY_EXTS):
        coverage["modules_not_executed"].append(
            "Keynote embedded-image extraction (no key_embedded_images.json artifact was produced)"
        )

    psd_preview_payload = load_safe("psd_preview_images.json")
    if psd_preview_payload:
        coverage["modules_executed"].append("psd_flattened_preview_extraction")
        psd_images = psd_preview_payload.get("images", []) or []
        coverage["psd_preview_images_extracted"] = len(psd_images)
        coverage["psd_preview_image_files"] = [
            {
                "source_psd": str(item.get("source_psd", "")),
                "output_path": str(item.get("output_path", "")),
                "width": item.get("width"),
                "height": item.get("height"),
                "source_mode": str(item.get("source_mode", "")),
                "source_format": str(item.get("source_format", "")),
            }
            for item in psd_images
            if isinstance(item, dict)
        ]
        psd_preview_errors = psd_preview_payload.get("errors", []) or []
        if psd_preview_errors:
            coverage["psd_preview_image_errors"] = psd_preview_errors
            coverage["psd_preview_image_error_count"] = len(psd_preview_errors)
            coverage["modules_not_executed"].append(
                "some PSD flattened-preview extraction (PSD preview unavailable; not a clean result)"
            )
        coverage["psd_preview_image_scope_note"] = str(psd_preview_payload.get("scope_note", ""))
    elif has_files(package, PSD_EXTS):
        coverage["modules_not_executed"].append(
            "PSD flattened-preview extraction (no psd_preview_images.json artifact was produced)"
        )

    image_metadata_payload = load_safe("image_metadata.json")
    if image_metadata_payload:
        coverage["modules_executed"].append("image_frame_channel_metadata_intake")
        totals = image_metadata_payload.get("totals", {}) or {}
        coverage["image_metadata_files_screened"] = int(totals.get("readable_images", 0) or 0)
        coverage["image_metadata_multiframe_files"] = int(totals.get("multiframe_images", 0) or 0)
        coverage["image_metadata_ome_files"] = int(totals.get("ome_metadata_files", 0) or 0)
        coverage["image_metadata_channel_files"] = int(totals.get("channel_metadata_files", 0) or 0)
        coverage["image_metadata_z_stack_files"] = int(totals.get("z_stack_metadata_files", 0) or 0)
        coverage["image_metadata_manual_review_files"] = int(totals.get("manual_metadata_review_files", 0) or 0)
        coverage["image_metadata_error_count"] = int(totals.get("unreadable_images", 0) or len(image_metadata_payload.get("errors", []) or []))
        coverage["image_metadata_scope_note"] = str(image_metadata_payload.get("scope_note", ""))
        review_items = []
        for item in image_metadata_payload.get("images", []) or []:
            if not isinstance(item, dict):
                continue
            hints = item.get("microscopy_hints") or {}
            if (
                item.get("is_multiframe")
                or item.get("has_ome_xml")
                or hints.get("possible_multichannel")
                or hints.get("possible_z_stack")
                or item.get("manual_review_note")
            ):
                review_items.append({
                    "path": str(item.get("path", "")),
                    "n_frames": item.get("n_frames"),
                    "channel_count": item.get("channel_count"),
                    "z_stack_count": item.get("z_stack_count"),
                    "timepoint_count": item.get("timepoint_count"),
                    "metadata_status": str(item.get("metadata_status", "")),
                    "manual_review_note": str(item.get("manual_review_note", "")),
                })
        coverage["image_metadata_review_items"] = review_items[:20]
        if coverage["image_metadata_error_count"]:
            coverage["modules_not_executed"].append(
                "image metadata intake for some files (metadata extraction failed; not a clean result)"
            )
        if coverage["image_metadata_manual_review_files"]:
            coverage["modules_not_executed"].append(
                "structured channel/Z/T interpretation for some multi-frame image files "
                "(manual acquisition metadata review required; not a clean result)"
            )
    elif has_files(package, IMAGE_EXTS):
        coverage["modules_not_executed"].append(
            "image frame/channel/Z metadata intake (no image_metadata.json artifact was produced)"
        )

    channel_metadata_payload = load_safe("channel_metadata_candidates.json")
    if channel_metadata_payload:
        coverage["modules_executed"].append("image_channel_metadata_consistency")
        coverage["channel_metadata_declarations_checked"] = int(
            channel_metadata_payload.get("declarations_checked", 0) or 0
        )
        coverage["channel_metadata_supported_declarations"] = int(
            channel_metadata_payload.get("supported_declarations", 0) or 0
        )
        coverage["channel_metadata_verification_gaps"] = int(
            channel_metadata_payload.get("verification_gaps", 0) or 0
        )
        checked_relations = [
            item
            for item in channel_metadata_payload.get("checked_relations", []) or []
            if isinstance(item, dict)
        ]
        coverage["channel_metadata_review_items"] = checked_relations[:20]
        if coverage["channel_metadata_verification_gaps"]:
            coverage["modules_not_executed"].append(
                "machine-readable channel/acquisition metadata verification for "
                f"{coverage['channel_metadata_verification_gaps']} same-field/different-channel declaration(s) "
                "(metadata gap; not a clean result)"
            )
        coverage["channel_metadata_scope_note"] = str(channel_metadata_payload.get("scope_note", ""))
    elif has_files(package, IMAGE_EXTS):
        coverage["modules_not_executed"].append(
            "same-field/different-channel metadata consistency check (no channel_metadata_candidates.json artifact was produced)"
        )

    if scan_profile == "quick":
        coverage["modules_not_executed"].append("external literature phrase search (skipped by quick scan profile)")
    elif external_provider:
        coverage["modules_executed"].append(f"external_literature_search ({external_provider})")
    else:
        coverage["modules_not_executed"].append(
            "external literature phrase search (offline: private internal audit, or no provider/fixture)"
        )

    coverage["modules_executed"].append("methodology_readiness_checklist")
    coverage["modules_executed"].append("writing_submission_readiness")
    coverage["modules_not_executed"].append(
        "methodology/reporting-standard compliance determination (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): manual review required"
    )
    coverage["modules_not_executed"].append(
        "journal-specific writing, language, and reference correctness determination: manual review required"
    )

    assembly_payload = load_safe("assembly_links.json")
    if assembly_payload and assembly_payload.get("parsed_files"):
        warnings = [
            str(item)
            for item in assembly_payload.get("warnings", []) or []
            if str(item).strip()
        ]
        if warnings:
            coverage["assembly_manifest_warnings"] = warnings
            coverage["assembly_manifest_warning_count"] = len(warnings)

    raw_candidate_count = 0
    for name in RAW_CANDIDATE_ARTIFACTS:
        payload = load_safe(name)
        if payload:
            raw_candidate_count += len(payload.get("candidates", []) or [])
    coverage["raw_detector_candidate_count"] = raw_candidate_count

    for path in detector_outputs:
        payload = read_json(path)
        coverage["positive_provenance_count"] += len(payload.get("positive_evidence", []) or [])
        for error in payload.get("errors", []) or []:
            stage = payload.get("detector_name") or path.stem
            error_path = error.get("path") if isinstance(error, dict) else None
            label = f"{stage}: {error_path}" if error_path else str(stage)
            coverage["detector_failures"].append(label)
        for candidate in payload.get("candidates", []) or []:
            candidate_type = candidate.get("candidate_type")
            if candidate_type == "detector_execution_failure":
                stage = candidate.get("evidence", {}).get("stage") or candidate.get("candidate_id", "detector")
                coverage["detector_failures"].append(str(stage))
            elif candidate_type == "audit_coverage_gap":
                coverage["audit_coverage_gap"] = True

    if unreadable_image_files:
        coverage["unreadable_image_files"] = sorted(unreadable_image_files.values(), key=lambda item: item["path"])
        coverage["image_files_unreadable"] = len(unreadable_image_files)
        coverage["unreadable_image_action_required"] = True

    if screening_payload:
        coverage["image_screening_input_files"] = int(len(screening_original_images) + len(screening_derived_images))
        coverage["image_screening_derived_images"] = int(len(screening_derived_images))
        coverage["image_screening_derived_sources"] = [
            {
                "artifact": item.get("artifact", ""),
                "source_container": item.get("source_container", ""),
                "target_relative_path": item.get("target_relative_path", ""),
            }
            for item in screening_derived_images[:20]
        ]
        coverage["image_screening_inputs_note"] = str(screening_payload.get("scope_note", ""))

    return coverage
