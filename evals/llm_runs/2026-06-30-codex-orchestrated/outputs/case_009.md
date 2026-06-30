# Biomedical Literature Concern Triage

## Scope

- Mode: external_public_material
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_009

## Audit Coverage

Modules executed in this run:

- image_global_near_duplicate
- image_local_patch_and_same_image_copy_move
- package_internal_text_overlap
- external_literature_search (europepmc)

Modules not executed in this run:

- statistics screening (no source_data CSV/TSV/XLSX supplied)
- methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened

- Image panels screened: 1
- Source-data tables screened: 0

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| protocols | R1 | No files classified as protocols. |
| raw_images | R1 | No files classified as raw_images. |

## Risk Register

No structured findings supplied.

## Evidence Ledger

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "external_public_material",
  "case_id": "case_009",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "figures/Figure_2_public_export.png",
    "manuscript.pdf",
    "review_context.txt"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "protocols",
    "raw images"
  ],
  "overall_risk": "R1",
  "misconduct_verdict_present": false,
  "risk_caps_applied": [
    "Missing materials are completeness gaps, not evidence of misconduct.",
    "Public or presentation-layer materials only; source/raw-level verification is limited."
  ],
  "positive_provenance": [],
  "traceability_gaps": [],
  "findings": [],
  "audit_coverage": {
    "modules_executed": [
      "image_global_near_duplicate",
      "image_local_patch_and_same_image_copy_move",
      "package_internal_text_overlap",
      "external_literature_search (europepmc)"
    ],
    "modules_not_executed": [
      "statistics screening (no source_data CSV/TSV/XLSX supplied)",
      "methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened"
    ],
    "image_panels_screened": 1,
    "image_files_unreadable": 0,
    "source_tables_screened": 0,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": "europepmc",
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
