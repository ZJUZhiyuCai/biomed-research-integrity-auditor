# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_014

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
| protocols | R1 | No files classified as protocols. |
| raw_images | R1 | No files classified as raw_images. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| BIOMED-STAT-0001 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:normalized_treatment | Values disproportionately end in 0 or 5; possible rounding/convenience pattern |
| BIOMED-STAT-0002 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:numeric_precision | Numeric precision differs systematically across columns; weak triage signal |
| BIOMED-STAT-0003 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:control<->treatment | Columns show whole-column additive/subtractive shift; weak-to-moderate triage signal |
| BIOMED-STAT-0004 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:control<->normalized_treatment | Columns show whole-column multiplicative/divisive scaling; weak-to-moderate triage signal |
| BIOMED-STAT-0005 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:treatment<->normalized_treatment | Columns show whole-column affine linear transformation; weak-to-moderate triage signal |
| BIOMED-STAT-0006 | R2 | stats.consistency_check | Figure_8_endpoint_values.csv:control<->treatment | Digit positions are preserved across paired columns |

## Evidence Ledger

### BIOMED-STAT-0001

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:normalized_treatment
- Finding Type: Values disproportionately end in 0 or 5; possible rounding/convenience pattern
- Evidence: `{"message": "Values disproportionately end in 0 or 5; possible rounding/convenience pattern", "evidence_type": "weak_forensic_triage_signal", "column": "normalized_treatment", "values_screened": 8, "effective_min_count": 8, "zero_or_five_share": 1.0, "decimal_place_counts": {"4": 8}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0002

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:numeric_precision
- Finding Type: Numeric precision differs systematically across columns; weak triage signal
- Evidence: `{"message": "Numeric precision differs systematically across columns; weak triage signal", "evidence_type": "weak_forensic_triage_signal", "dominant_decimal_places_by_column": {"control": 2, "treatment": 2, "normalized_treatment": 4}, "decimal_place_counts_by_column": {"control": {"2": 8}, "treatment": {"2": 8}, "normalized_treatment": {"4": 8}}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0003

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:control<->treatment
- Finding Type: Columns show whole-column additive/subtractive shift; weak-to-moderate triage signal
- Evidence: `{"message": "Columns show whole-column additive/subtractive shift; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control", "right_column": "treatment", "paired_rows": 8, "slope": 1.0, "intercept": 7.5, "r2": 1.0, "max_abs_residual": 7.105427357601002e-15, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0004

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:control<->normalized_treatment
- Finding Type: Columns show whole-column multiplicative/divisive scaling; weak-to-moderate triage signal
- Evidence: `{"message": "Columns show whole-column multiplicative/divisive scaling; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control", "right_column": "normalized_treatment", "paired_rows": 8, "slope": 1.25, "intercept": -0.0, "r2": 1.0, "max_abs_residual": 1.7763568394002505e-15, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0005

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:treatment<->normalized_treatment
- Finding Type: Columns show whole-column affine linear transformation; weak-to-moderate triage signal
- Evidence: `{"message": "Columns show whole-column affine linear transformation; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "treatment", "right_column": "normalized_treatment", "paired_rows": 8, "slope": 1.25, "intercept": -9.375, "r2": 1.0, "max_abs_residual": 7.105427357601002e-15, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0006

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_8_endpoint_values.csv:control<->treatment
- Finding Type: Digit positions are preserved across paired columns
- Evidence: `{"message": "Digit positions are preserved across paired columns", "evidence_type": "weak_forensic_triage_signal", "left_column": "control", "right_column": "treatment", "paired_rows": 8, "preserved_digit_positions": {"terminal_digit": {"comparable_pairs": 8, "match_share": 1.0}}}`
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
  "case_id": "case_014",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "manuscript.pdf",
    "source_data/Figure_8_endpoint_values.csv",
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
      "finding_type": "Values disproportionately end in 0 or 5; possible rounding/convenience pattern",
      "location": "Figure_8_endpoint_values.csv:normalized_treatment",
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
      "finding_type": "Numeric precision differs systematically across columns; weak triage signal",
      "location": "Figure_8_endpoint_values.csv:numeric_precision",
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
      "finding_id": "BIOMED-STAT-0003",
      "risk_level": "R2",
      "finding_type": "Columns show whole-column additive/subtractive shift; weak-to-moderate triage signal",
      "location": "Figure_8_endpoint_values.csv:control<->treatment",
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
      "finding_id": "BIOMED-STAT-0004",
      "risk_level": "R2",
      "finding_type": "Columns show whole-column multiplicative/divisive scaling; weak-to-moderate triage signal",
      "location": "Figure_8_endpoint_values.csv:control<->normalized_treatment",
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
      "finding_id": "BIOMED-STAT-0005",
      "risk_level": "R2",
      "finding_type": "Columns show whole-column affine linear transformation; weak-to-moderate triage signal",
      "location": "Figure_8_endpoint_values.csv:treatment<->normalized_treatment",
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
      "finding_id": "BIOMED-STAT-0006",
      "risk_level": "R2",
      "finding_type": "Digit positions are preserved across paired columns",
      "location": "Figure_8_endpoint_values.csv:control<->treatment",
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
