# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_007

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

- Image panels screened: 1
- Source-data tables screened: 1

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| protocols | R1 | No files classified as protocols. |
| raw_images | R1 | No files classified as raw_images. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| BIOMED-STAT-0001 | R2 | stats.consistency_check | Figure_5_source.csv:row2:group=Control | SD is not consistent with SEM * sqrt(n) |
| BIOMED-STAT-0002 | R2 | stats.consistency_check | Figure_5_source.csv:row3:group=Treatment | SD is not consistent with SEM * sqrt(n) |
| BIOMED-STAT-0003 | R2 | stats.consistency_check | Figure_5_source.csv:row3:group=Treatment | SD and SEM are nearly identical despite n > 2 |
| BIOMED-STAT-0004 | R3 | stats.consistency_check | Figure_5_source.csv:row3:group=Treatment | p value is outside [0, 1] |

## Evidence Ledger

### BIOMED-STAT-0001

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_5_source.csv:row2:group=Control
- Finding Type: SD is not consistent with SEM * sqrt(n)
- Evidence: `{"message": "SD is not consistent with SEM * sqrt(n)", "evidence_type": "statistics_consistency", "sd": 5.0, "sem": 1.0, "n": 4.0, "expected_sd_from_sem": 2.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0002

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_5_source.csv:row3:group=Treatment
- Finding Type: SD is not consistent with SEM * sqrt(n)
- Evidence: `{"message": "SD is not consistent with SEM * sqrt(n)", "evidence_type": "statistics_consistency", "sd": 1.0, "sem": 1.0, "n": 9.0, "expected_sd_from_sem": 3.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0003

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_5_source.csv:row3:group=Treatment
- Finding Type: SD and SEM are nearly identical despite n > 2
- Evidence: `{"message": "SD and SEM are nearly identical despite n > 2", "evidence_type": "statistics_consistency", "sd": 1.0, "sem": 1.0, "n": 9.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0004

- Risk Level: R3
- Module: stats.consistency_check
- Location: Figure_5_source.csv:row3:group=Treatment
- Finding Type: p value is outside [0, 1]
- Evidence: `{"message": "p value is outside [0, 1]", "evidence_type": "statistics_consistency", "p_value": 1.2}`
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
  "case_id": "case_007",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "figures/Figure_5A.png",
    "manuscript.pdf",
    "source_data/Figure_5_source.csv",
    "statistics_code/analysis_notes.txt"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "protocols",
    "raw images",
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
      "finding_id": "BIOMED-STAT-0001",
      "risk_level": "R2",
      "finding_type": "SD is not consistent with SEM * sqrt(n)",
      "location": "Figure_5_source.csv:row2:group=Control",
      "evidence_type": "statistical_consistency_candidate",
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
    },
    {
      "finding_id": "BIOMED-STAT-0002",
      "risk_level": "R2",
      "finding_type": "SD is not consistent with SEM * sqrt(n)",
      "location": "Figure_5_source.csv:row3:group=Treatment",
      "evidence_type": "statistical_consistency_candidate",
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
    },
    {
      "finding_id": "BIOMED-STAT-0003",
      "risk_level": "R2",
      "finding_type": "SD and SEM are nearly identical despite n > 2",
      "location": "Figure_5_source.csv:row3:group=Treatment",
      "evidence_type": "statistical_consistency_candidate",
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
    },
    {
      "finding_id": "BIOMED-STAT-0004",
      "risk_level": "R3",
      "finding_type": "p value is outside [0, 1]",
      "location": "Figure_5_source.csv:row3:group=Treatment",
      "evidence_type": "statistical_consistency_candidate",
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
    "image_panels_screened": 1,
    "image_files_unreadable": 0,
    "source_tables_screened": 1,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
