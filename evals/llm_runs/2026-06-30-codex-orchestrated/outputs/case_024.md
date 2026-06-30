# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_024

## Audit Coverage

Modules executed in this run:

- image_global_near_duplicate
- image_local_patch_and_same_image_copy_move
- statistics_consistency
- pseudoreplication
- package_internal_text_overlap

Modules not executed in this run:

- external literature phrase search (offline: private internal audit, or no provider/fixture)
- methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened

- Image panels screened: 4
- Source-data tables screened: 1

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| protocols | R1 | No files classified as protocols. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| LOCALPATCH-0001 | R3 | image.local_patch_reuse | figures/Figure_6B.png / figures/Figure_7C.png | local_patch_reuse |

## Evidence Ledger

### LOCALPATCH-0001

- Risk Level: R3
- Module: image.local_patch_reuse
- Location: figures/Figure_6B.png / figures/Figure_7C.png
- Finding Type: local_patch_reuse
- Evidence: `{"edges": [{"left": "figures/Figure_6B.png", "right": "figures/Figure_7C.png", "similarity_scope": "local_patch", "same_image": false, "region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "tile_hits": [{"region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "hash_distances": {"average_hash": 0, "difference_hash": 0}, "tile_stddev_a": 60.245, "tile_stddev_b": 60.245}], "tile_hit_count": 1, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "evidence_crops": {"crop_a": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_A.png", "crop_b": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_B.png", "side_by_side": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_side_by_side.png"}}], "representative_edge": {"left": "figures/Figure_6B.png", "right": "figures/Figure_7C.png", "similarity_scope": "local_patch", "same_image": false, "region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "tile_hits": [{"region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "hash_distances": {"average_hash": 0, "difference_hash": 0}, "tile_stddev_a": 60.245, "tile_stddev_b": 60.245}], "tile_hit_count": 1, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "evidence_crops": {"crop_a": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_A.png", "crop_b": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_B.png", "side_by_side": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_side_by_side.png"}}, "tile_size": 128, "stride": 64, "context": {"reuse_disclosed": false, "loading_control_disclosed": false, "same_experiment_claimed": false, "same_membrane_claimed": false, "source_data_available": true, "raw_images_available": true, "risk_cap_tags": []}, "contextual_edges": [{"left": "figures/Figure_6B.png", "right": "figures/Figure_7C.png", "similarity_scope": "local_patch", "same_image": false, "region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "tile_hits": [{"region_a": {"x": 64, "y": 64, "width": 128, "height": 128}, "region_b": {"x": 64, "y": 64, "width": 128, "height": 128}, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "hash_distances": {"average_hash": 0, "difference_hash": 0}, "tile_stddev_a": 60.245, "tile_stddev_b": 60.245}], "tile_hit_count": 1, "best_transform": "identity", "score": 1.0, "hash_distance": 0, "evidence_crops": {"crop_a": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_A.png", "crop_b": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_B.png", "side_by_side": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/evidence/local_patch/LOCALPATCH-0001_side_by_side.png"}, "left_role": "figure_panel", "right_role": "figure_panel", "contextual_tag": "local_patch_cross_context", "reportable_as_risk": true, "positive_evidence": false, "risk_suggestion": "R3_possible"}], "positive_traceability_edges": [], "provenance_graph": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_024/provenance_graph.json"}`
- Benign explanations considered: same raw field, channel, membrane, or crop may be intentionally reused with disclosure, same-image local similarities can arise from repeated biological structures or image registration artifacts, image registration, compression, or downsampling may create local similarities, source/raw records are needed before escalation
- Required materials to resolve: original image files, acquisition metadata, figure assembly file, sample, field, channel, or lane map
- Recommended action: Inspect local patch coordinates against raw images, acquisition metadata, and figure assembly records before escalation.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_024",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "figure_assembly/assembly_manifest.csv",
    "figures/Figure_6B.png",
    "figures/Figure_7C.png",
    "manuscript.pdf",
    "raw_images/acquisition_X006.png",
    "raw_images/acquisition_X007.png",
    "source_data/Figure_6_7_source.csv"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "protocols",
    "supplementary"
  ],
  "overall_risk": "R3",
  "misconduct_verdict_present": false,
  "risk_caps_applied": [
    "Missing materials are completeness gaps, not evidence of misconduct."
  ],
  "positive_provenance": [],
  "traceability_gaps": [],
  "findings": [
    {
      "finding_id": "LOCALPATCH-0001",
      "risk_level": "R3",
      "finding_type": "local_patch_reuse",
      "location": "figures/Figure_6B.png / figures/Figure_7C.png",
      "evidence_type": "local_patch_reuse",
      "benign_explanations_considered": [
        "same raw field, channel, membrane, or crop may be intentionally reused with disclosure",
        "same-image local similarities can arise from repeated biological structures or image registration artifacts",
        "image registration, compression, or downsampling may create local similarities",
        "source/raw records are needed before escalation"
      ],
      "required_materials_to_resolve": [
        "original image files",
        "acquisition metadata",
        "figure assembly file",
        "sample, field, channel, or lane map"
      ],
      "recommended_action": "Inspect local patch coordinates against raw images, acquisition metadata, and figure assembly records before escalation."
    }
  ],
  "audit_coverage": {
    "modules_executed": [
      "image_global_near_duplicate",
      "image_local_patch_and_same_image_copy_move",
      "statistics_consistency",
      "pseudoreplication",
      "package_internal_text_overlap"
    ],
    "modules_not_executed": [
      "external literature phrase search (offline: private internal audit, or no provider/fixture)",
      "methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened"
    ],
    "image_panels_screened": 4,
    "image_files_unreadable": 0,
    "source_tables_screened": 1,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
