# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_018

## Audit Coverage

Modules executed in this run:

- statistics_consistency
- pseudoreplication
- package_internal_text_overlap

Modules not executed in this run:

- image screening (no image files supplied)
- external literature phrase search (offline: private internal audit, or no provider/fixture)
- methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened

- Image panels screened: 0
- Source-data tables screened: 2

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| figures | R1 | No files classified as figures. |
| protocols | R1 | No files classified as protocols. |
| raw_images | R1 | No files classified as raw_images. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| BIOMED-STAT-0001 | R2 | stats.consistency_check | cross-file numeric sequences | Identical numeric sequence appears in multiple files/figures |

## Evidence Ledger

### BIOMED-STAT-0001

- Risk Level: R2
- Module: stats.consistency_check
- Location: cross-file numeric sequences
- Finding Type: Identical numeric sequence appears in multiple files/figures
- Evidence: `{"message": "Identical numeric sequence appears in multiple files/figures", "evidence_type": "weak_forensic_triage_signal", "sequence_length": 8, "sequence_preview": [3.14, 4.22, 5.09, 6.31, 7.18, 8.44, 9.02, 10.67], "locations": [{"file": "Figure_2_assay_a.csv", "column": "assay_a_value", "rows": [2, 3, 4, 5, 6, 7, 8, 9]}, {"file": "Figure_5_assay_b.csv", "column": "assay_b_value", "rows": [2, 3, 4, 5, 6, 7, 8, 9]}]}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_018",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "manuscript.pdf",
    "source_data/Figure_2_assay_a.csv",
    "source_data/Figure_5_assay_b.csv",
    "statistics_code/analysis_notes.txt"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "figures",
    "protocols",
    "raw images",
    "supplementary"
  ],
  "overall_risk": "R2",
  "misconduct_verdict_present": false,
  "risk_caps_applied": [
    "Missing materials are completeness gaps, not evidence of misconduct."
  ],
  "positive_provenance": [],
  "traceability_gaps": [],
  "findings": [
    {
      "finding_id": "BIOMED-STAT-0001",
      "risk_level": "R2",
      "finding_type": "Identical numeric sequence appears in multiple files/figures",
      "location": "cross-file numeric sequences",
      "evidence_type": "weak_statistical_signal",
      "benign_explanations_considered": [
        "rounding, normalization, export, or reporting differences may explain the observation",
        "source/raw records and analysis code are needed before escalation"
      ],
      "required_materials_to_resolve": [
        "source data",
        "raw records where applicable",
        "analysis file or code"
      ],
      "recommended_action": "Inspect source data, analysis code, rounding, normalization, and benign explanations."
    }
  ],
  "audit_coverage": {
    "modules_executed": [
      "statistics_consistency",
      "pseudoreplication",
      "package_internal_text_overlap"
    ],
    "modules_not_executed": [
      "image screening (no image files supplied)",
      "external literature phrase search (offline: private internal audit, or no provider/fixture)",
      "methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened"
    ],
    "image_panels_screened": 0,
    "image_files_unreadable": 0,
    "source_tables_screened": 2,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
