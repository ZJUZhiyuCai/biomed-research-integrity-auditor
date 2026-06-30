# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_015

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
- Source-data tables screened: 1

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| figures | R1 | No files classified as figures. |
| raw_images | R1 | No files classified as raw_images. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| BIOMED-STAT-0001 | R2 | stats.consistency_check | Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28 | Longitudinal trajectories are unusually linear/mechanical across rows |
| BIOMED-STAT-0002 | R2 | stats.consistency_check | Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28 | Repeated longitudinal increment pattern across animals/samples |

## Evidence Ledger

### BIOMED-STAT-0001

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28
- Finding Type: Longitudinal trajectories are unusually linear/mechanical across rows
- Evidence: `{"message": "Longitudinal trajectories are unusually linear/mechanical across rows", "evidence_type": "weak_forensic_triage_signal", "time_columns": ["day0", "day7", "day14", "day21", "day28"], "rows_screened": 6, "linear_rows": [{"row": "M01", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}, {"row": "M02", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}, {"row": "M03", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}, {"row": "M04", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}, {"row": "M05", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}, {"row": "M06", "increments": [8.0, 8.0, 8.0, 8.0], "max_increment_deviation": 0.0}], "linear_row_share": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0002

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28
- Finding Type: Repeated longitudinal increment pattern across animals/samples
- Evidence: `{"message": "Repeated longitudinal increment pattern across animals/samples", "evidence_type": "weak_forensic_triage_signal", "time_columns": ["day0", "day7", "day14", "day21", "day28"], "repeated_increment_patterns": {"(8.0, 8.0, 8.0, 8.0)": ["M01", "M02", "M03", "M04", "M05", "M06"]}}`
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
  "case_id": "case_015",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "manuscript.pdf",
    "protocols/animal_measurement_log.txt",
    "source_data/Figure_9_longitudinal_animals.csv"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "figures",
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
      "finding_type": "Longitudinal trajectories are unusually linear/mechanical across rows",
      "location": "Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28",
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
    },
    {
      "finding_id": "BIOMED-STAT-0002",
      "risk_level": "R2",
      "finding_type": "Repeated longitudinal increment pattern across animals/samples",
      "location": "Figure_9_longitudinal_animals.csv:day0,day7,day14,day21,day28",
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
    "source_tables_screened": 1,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
