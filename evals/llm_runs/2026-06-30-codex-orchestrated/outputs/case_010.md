# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_010

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
| STAT-PSEUDO-0001 | R3 | stats.pseudoreplication_screen | Figure_6_field_measurements.csv:group=all | pseudoreplication_candidate |

## Evidence Ledger

### STAT-PSEUDO-0001

- Risk Level: R3
- Module: stats.pseudoreplication_screen
- Location: Figure_6_field_measurements.csv:group=all
- Finding Type: pseudoreplication_candidate
- Evidence: `{"file": "/Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_010/source_data/Figure_6_field_measurements.csv", "group": "all", "biological_id_column": "animal_id", "technical_id_column": "field_id", "biological_unit_count": 3, "technical_unit_count": 30, "row_count": 30, "reported_n_basis_values": ["field"], "reported_n_appears_technical": true}`
- Benign explanations considered: analysis may use a nested or mixed-effects model, technical replicates may have been averaged before inferential testing, reported n may be descriptive rather than inferential
- Required materials to resolve: analysis code, statistical model specification, raw measurements by biological unit, reported n definition from methods or legend
- Recommended action: Verify whether inferential n counts biological units; reanalyse at the biological-unit level or justify a nested model.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_010",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "manuscript.pdf",
    "protocols/animal_sample_map.txt",
    "source_data/Figure_6_field_measurements.csv"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "figures",
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
      "finding_id": "STAT-PSEUDO-0001",
      "risk_level": "R3",
      "finding_type": "pseudoreplication_candidate",
      "location": "Figure_6_field_measurements.csv:group=all",
      "evidence_type": "pseudoreplication_candidate",
      "benign_explanations_considered": [
        "analysis may use a nested or mixed-effects model",
        "technical replicates may have been averaged before inferential testing",
        "reported n may be descriptive rather than inferential"
      ],
      "required_materials_to_resolve": [
        "analysis code",
        "statistical model specification",
        "raw measurements by biological unit",
        "reported n definition from methods or legend"
      ],
      "recommended_action": "Verify whether inferential n counts biological units; reanalyse at the biological-unit level or justify a nested model."
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
