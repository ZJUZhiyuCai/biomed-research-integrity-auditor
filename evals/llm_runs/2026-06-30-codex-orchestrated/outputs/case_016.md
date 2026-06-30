# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_016

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
| BIOMED-STAT-0001 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day0<->treatment_day0 | Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal |
| BIOMED-STAT-0002 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day2<->treatment_day2 | Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal |
| BIOMED-STAT-0003 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day4<->treatment_day4 | Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal |
| BIOMED-STAT-0004 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day7<->treatment_day7 | Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal |
| BIOMED-STAT-0005 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day0<->treatment_day0 | Digit positions are preserved across paired columns |
| BIOMED-STAT-0006 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day2<->treatment_day2 | Digit positions are preserved across paired columns |
| BIOMED-STAT-0007 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day4<->treatment_day4 | Digit positions are preserved across paired columns |
| BIOMED-STAT-0008 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day7<->treatment_day7 | Digit positions are preserved across paired columns |
| BIOMED-STAT-0009 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control<->treatment | Time-stratified additive shifts across group columns |
| BIOMED-STAT-0010 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:control_day0,control_day2,control_day4,control_day7 | Repeated longitudinal increment pattern across animals/samples |
| BIOMED-STAT-0011 | R2 | stats.consistency_check | Figure_3c_3d_animals.csv:treatment_day0,treatment_day2,treatment_day4,treatment_day7 | Repeated longitudinal increment pattern across animals/samples |

## Evidence Ledger

### BIOMED-STAT-0001

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day0<->treatment_day0
- Finding Type: Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal
- Evidence: `{"message": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day0", "right_column": "treatment_day0", "paired_rows": 8, "slope": 1.0, "intercept": 10.0, "r2": 1.0, "max_abs_residual": 0.0, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0002

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day2<->treatment_day2
- Finding Type: Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal
- Evidence: `{"message": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day2", "right_column": "treatment_day2", "paired_rows": 8, "slope": 1.0, "intercept": 20.0, "r2": 1.0, "max_abs_residual": 1.4210854715202004e-14, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0003

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day4<->treatment_day4
- Finding Type: Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal
- Evidence: `{"message": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day4", "right_column": "treatment_day4", "paired_rows": 8, "slope": 1.0, "intercept": 30.0, "r2": 1.0, "max_abs_residual": 7.105427357601002e-15, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0004

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day7<->treatment_day7
- Finding Type: Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal
- Evidence: `{"message": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day7", "right_column": "treatment_day7", "paired_rows": 8, "slope": 1.0, "intercept": 40.0, "r2": 1.0, "max_abs_residual": 1.4210854715202004e-14, "same_rank_order": true, "centered_residual_correlation": 1.0}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0005

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day0<->treatment_day0
- Finding Type: Digit positions are preserved across paired columns
- Evidence: `{"message": "Digit positions are preserved across paired columns", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day0", "right_column": "treatment_day0", "paired_rows": 8, "preserved_digit_positions": {"ones_digit": {"comparable_pairs": 8, "match_share": 1.0}, "first_decimal_digit": {"comparable_pairs": 8, "match_share": 1.0}, "terminal_digit": {"comparable_pairs": 8, "match_share": 1.0}}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0006

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day2<->treatment_day2
- Finding Type: Digit positions are preserved across paired columns
- Evidence: `{"message": "Digit positions are preserved across paired columns", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day2", "right_column": "treatment_day2", "paired_rows": 8, "preserved_digit_positions": {"ones_digit": {"comparable_pairs": 8, "match_share": 1.0}, "first_decimal_digit": {"comparable_pairs": 8, "match_share": 1.0}, "terminal_digit": {"comparable_pairs": 8, "match_share": 1.0}}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0007

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day4<->treatment_day4
- Finding Type: Digit positions are preserved across paired columns
- Evidence: `{"message": "Digit positions are preserved across paired columns", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day4", "right_column": "treatment_day4", "paired_rows": 8, "preserved_digit_positions": {"ones_digit": {"comparable_pairs": 8, "match_share": 1.0}, "first_decimal_digit": {"comparable_pairs": 8, "match_share": 1.0}, "terminal_digit": {"comparable_pairs": 8, "match_share": 1.0}}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0008

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day7<->treatment_day7
- Finding Type: Digit positions are preserved across paired columns
- Evidence: `{"message": "Digit positions are preserved across paired columns", "evidence_type": "weak_forensic_triage_signal", "left_column": "control_day7", "right_column": "treatment_day7", "paired_rows": 8, "preserved_digit_positions": {"ones_digit": {"comparable_pairs": 8, "match_share": 1.0}, "first_decimal_digit": {"comparable_pairs": 8, "match_share": 1.0}, "terminal_digit": {"comparable_pairs": 8, "match_share": 1.0}}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0009

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control<->treatment
- Finding Type: Time-stratified additive shifts across group columns
- Evidence: `{"message": "Time-stratified additive shifts across group columns", "evidence_type": "weak_forensic_triage_signal", "group_column_bases": ["control", "treatment"], "timepoint_offsets": [{"time": "day0", "left_column": "control_day0", "right_column": "treatment_day0", "offset": 10.0, "paired_rows": 8}, {"time": "day2", "left_column": "control_day2", "right_column": "treatment_day2", "offset": 20.0, "paired_rows": 8}, {"time": "day4", "left_column": "control_day4", "right_column": "treatment_day4", "offset": 30.0, "paired_rows": 8}, {"time": "day7", "left_column": "control_day7", "right_column": "treatment_day7", "offset": 40.0, "paired_rows": 8}], "unique_offsets": [10.0, 20.0, 30.0, 40.0]}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0010

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:control_day0,control_day2,control_day4,control_day7
- Finding Type: Repeated longitudinal increment pattern across animals/samples
- Evidence: `{"message": "Repeated longitudinal increment pattern across animals/samples", "evidence_type": "weak_forensic_triage_signal", "time_columns": ["control_day0", "control_day2", "control_day4", "control_day7"], "repeated_increment_patterns": {"(1.4, 1.7, 2.7)": ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08"]}}`
- Benign explanations considered: rounding, normalization, export, or reporting differences may explain the observation, source/raw records and analysis code are needed before escalation
- Required materials to resolve: source data, raw records where applicable, analysis file or code
- Recommended action: Inspect source data, analysis code, rounding, normalization, and benign explanations.
- Note: Calibrated from detector candidate; not a misconduct verdict.

### BIOMED-STAT-0011

- Risk Level: R2
- Module: stats.consistency_check
- Location: Figure_3c_3d_animals.csv:treatment_day0,treatment_day2,treatment_day4,treatment_day7
- Finding Type: Repeated longitudinal increment pattern across animals/samples
- Evidence: `{"message": "Repeated longitudinal increment pattern across animals/samples", "evidence_type": "weak_forensic_triage_signal", "time_columns": ["treatment_day0", "treatment_day2", "treatment_day4", "treatment_day7"], "repeated_increment_patterns": {"(11.4, 11.7, 12.7)": ["A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08"]}}`
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
  "case_id": "case_016",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "manuscript.pdf",
    "source_data/Figure_3c_3d_animals.csv",
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
      "finding_type": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal",
      "location": "Figure_3c_3d_animals.csv:control_day0<->treatment_day0",
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
      "finding_type": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal",
      "location": "Figure_3c_3d_animals.csv:control_day2<->treatment_day2",
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
      "finding_type": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal",
      "location": "Figure_3c_3d_animals.csv:control_day4<->treatment_day4",
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
      "finding_type": "Adjacent/paired time columns show whole-column additive/subtractive shift; weak-to-moderate triage signal",
      "location": "Figure_3c_3d_animals.csv:control_day7<->treatment_day7",
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
      "finding_type": "Digit positions are preserved across paired columns",
      "location": "Figure_3c_3d_animals.csv:control_day0<->treatment_day0",
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
      "location": "Figure_3c_3d_animals.csv:control_day2<->treatment_day2",
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
      "finding_id": "BIOMED-STAT-0007",
      "risk_level": "R2",
      "finding_type": "Digit positions are preserved across paired columns",
      "location": "Figure_3c_3d_animals.csv:control_day4<->treatment_day4",
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
      "finding_id": "BIOMED-STAT-0008",
      "risk_level": "R2",
      "finding_type": "Digit positions are preserved across paired columns",
      "location": "Figure_3c_3d_animals.csv:control_day7<->treatment_day7",
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
      "finding_id": "BIOMED-STAT-0009",
      "risk_level": "R2",
      "finding_type": "Time-stratified additive shifts across group columns",
      "location": "Figure_3c_3d_animals.csv:control<->treatment",
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
      "finding_id": "BIOMED-STAT-0010",
      "risk_level": "R2",
      "finding_type": "Repeated longitudinal increment pattern across animals/samples",
      "location": "Figure_3c_3d_animals.csv:control_day0,control_day2,control_day4,control_day7",
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
      "finding_id": "BIOMED-STAT-0011",
      "risk_level": "R2",
      "finding_type": "Repeated longitudinal increment pattern across animals/samples",
      "location": "Figure_3c_3d_animals.csv:treatment_day0,treatment_day2,treatment_day4,treatment_day7",
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
