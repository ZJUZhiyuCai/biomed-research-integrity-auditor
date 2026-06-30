# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_004

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
| IMGCLUSTER-0001 | R3 | image.global_near_duplicate | figures/Figure_2B.png / figures/Figure_4D.png | image_reuse_cluster |

## Evidence Ledger

### IMGCLUSTER-0001

- Risk Level: R3
- Module: image.global_near_duplicate
- Location: figures/Figure_2B.png / figures/Figure_4D.png
- Finding Type: image_reuse_cluster
- Evidence: `{"cluster_id": "IMGCLUSTER-0001", "members": ["figures/Figure_2B.png", "figures/Figure_4D.png", "raw_images/field_C017.png", "raw_images/field_D044.png"], "edges": [{"left": "figures/Figure_2B.png", "right": "figures/Figure_4D.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, {"left": "figures/Figure_2B.png", "right": "raw_images/field_C017.png", "best_transform": "identity", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, {"left": "figures/Figure_2B.png", "right": "raw_images/field_D044.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, {"left": "figures/Figure_4D.png", "right": "raw_images/field_C017.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, {"left": "figures/Figure_4D.png", "right": "raw_images/field_D044.png", "best_transform": "identity", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, {"left": "raw_images/field_C017.png", "right": "raw_images/field_D044.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}], "representative_edge": {"left": "figures/Figure_2B.png", "right": "figures/Figure_4D.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, "threshold": 6, "context": {"reuse_disclosed": false, "loading_control_disclosed": false, "same_experiment_claimed": false, "same_membrane_claimed": false, "source_data_available": true, "raw_images_available": true, "risk_cap_tags": []}, "contextual_edges": [{"left": "figures/Figure_2B.png", "right": "figures/Figure_4D.png", "best_transform": "flip_h", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}, "left_role": "figure_panel", "right_role": "figure_panel", "contextual_tag": "cross_context_reuse_candidate", "reportable_as_risk": true, "positive_evidence": false, "risk_suggestion": "R3_possible"}], "positive_traceability_edges": [], "provenance_graph": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_004/provenance_graph.json"}`
- Benign explanations considered: same field or membrane intentionally reused with disclosure, adjacent crop or shared source image, figure assembly placeholder or export artifact
- Required materials to resolve: original image files, acquisition metadata, figure assembly file, sample or lane map
- Recommended action: Inspect the image cluster against raw images and sample identity before risk escalation.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_004",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "figure_assembly/assembly_manifest.txt",
    "figures/Figure_2B.png",
    "figures/Figure_4D.png",
    "manuscript.pdf",
    "raw_images/field_C017.png",
    "raw_images/field_D044.png",
    "source_data/Figure_2_4_source.csv"
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
      "finding_id": "IMGCLUSTER-0001",
      "risk_level": "R3",
      "finding_type": "image_reuse_cluster",
      "location": "figures/Figure_2B.png / figures/Figure_4D.png",
      "evidence_type": "image_reuse_cluster",
      "benign_explanations_considered": [
        "same field or membrane intentionally reused with disclosure",
        "adjacent crop or shared source image",
        "figure assembly placeholder or export artifact"
      ],
      "required_materials_to_resolve": [
        "original image files",
        "acquisition metadata",
        "figure assembly file",
        "sample or lane map"
      ],
      "recommended_action": "Inspect the image cluster against raw images and sample identity before risk escalation."
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
