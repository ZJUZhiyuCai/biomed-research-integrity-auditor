# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_012

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

- Image panels screened: 2
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
| IMGCLUSTER-0001 | R1 | image.global_near_duplicate | figures/Figure_1A.png / raw_images/acquisition_L001.png | unresolved_fig_raw_similarity |

## Evidence Ledger

### IMGCLUSTER-0001

- Risk Level: R1
- Module: image.global_near_duplicate
- Location: figures/Figure_1A.png / raw_images/acquisition_L001.png
- Finding Type: unresolved_fig_raw_similarity
- Evidence: `{"cluster_id": "IMGCLUSTER-0001", "members": ["figures/Figure_1A.png", "raw_images/acquisition_L001.png"], "edges": [{"left": "figures/Figure_1A.png", "right": "raw_images/acquisition_L001.png", "best_transform": "identity", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}], "representative_edge": {"left": "figures/Figure_1A.png", "right": "raw_images/acquisition_L001.png", "best_transform": "identity", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}}, "threshold": 6, "context": {"reuse_disclosed": false, "loading_control_disclosed": false, "same_experiment_claimed": false, "same_membrane_claimed": false, "source_data_available": true, "raw_images_available": true, "risk_cap_tags": []}, "contextual_edges": [{"left": "figures/Figure_1A.png", "right": "raw_images/acquisition_L001.png", "best_transform": "identity", "best_hash_method": "average_hash", "best_hamming_distance": 0, "all_method_distances": {"average_hash": 0, "difference_hash": 0, "perceptual_hash": 0}, "left_role": "figure_panel", "right_role": "raw_image", "contextual_tag": "unresolved_fig_raw_similarity", "reportable_as_risk": true, "positive_evidence": false, "risk_suggestion": "R1_max", "required_materials_to_resolve": ["figure-source map", "assembly manifest", "raw image metadata"]}], "positive_traceability_edges": [], "provenance_graph": "/Users/rosscai/Documents/biomed-research-integrity-auditor/tmp/llm_eval_work/case_012/provenance_graph.json"}`
- Benign explanations considered: figure panel may be a direct export or crop from the raw/source image, source relationship may exist but was not supplied in a machine-readable manifest
- Required materials to resolve: figure-source map, assembly manifest, raw image metadata
- Recommended action: Document the figure-to-raw/source relationship before treating the image similarity as a reuse concern.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_012",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "figures/Figure_1A.png",
    "manuscript.pdf",
    "raw_images/acquisition_L001.png",
    "source_data/Figure_1_source.csv"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "protocols",
    "supplementary"
  ],
  "overall_risk": "R1",
  "misconduct_verdict_present": false,
  "risk_caps_applied": [
    "Missing materials are completeness gaps, not evidence of misconduct."
  ],
  "positive_provenance": [],
  "traceability_gaps": [
    {
      "gap_id": "TRACE-0001",
      "finding_type": "unresolved_fig_raw_similarity",
      "risk_level": "R1",
      "location": "figures/Figure_1A.png / raw_images/acquisition_L001.png",
      "required_materials_to_resolve": [
        "figure-source map",
        "assembly manifest",
        "raw image metadata"
      ]
    }
  ],
  "findings": [
    {
      "finding_id": "IMGCLUSTER-0001",
      "risk_level": "R1",
      "finding_type": "unresolved_fig_raw_similarity",
      "location": "figures/Figure_1A.png / raw_images/acquisition_L001.png",
      "evidence_type": "unresolved_fig_raw_similarity",
      "benign_explanations_considered": [
        "figure panel may be a direct export or crop from the raw/source image",
        "source relationship may exist but was not supplied in a machine-readable manifest"
      ],
      "required_materials_to_resolve": [
        "figure-source map",
        "assembly manifest",
        "raw image metadata"
      ],
      "recommended_action": "Document the figure-to-raw/source relationship before treating the image similarity as a reuse concern."
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
    "image_panels_screened": 2,
    "image_files_unreadable": 0,
    "source_tables_screened": 1,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
