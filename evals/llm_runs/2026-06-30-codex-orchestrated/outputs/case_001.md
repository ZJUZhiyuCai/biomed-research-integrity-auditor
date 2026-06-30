# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_001

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

- Image panels screened: 6
- Source-data tables screened: 1

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| figure_assembly | R1 | No files classified as figure_assembly. |
| supplementary | R1 | No files classified as supplementary. |

## Verified Traceability Evidence

- figures/Figure_1A_control.png is traceable to raw_images/acquisition_A001.png via figure_assembly/assembly_manifest.txt.
- figures/Figure_1A_treatment.png is traceable to raw_images/acquisition_A002.png via figure_assembly/assembly_manifest.txt.
- figures/Figure_2A_blot.png is traceable to raw_images/full_membrane_A003.png via figure_assembly/assembly_manifest.txt.

These links are positive provenance evidence, not image-reuse concerns.

## Risk Register

No structured findings supplied.

## Evidence Ledger

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_001",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "ethics_irb/approval.txt",
    "figure_assembly/assembly_manifest.txt",
    "figures/Figure_1A_control.png",
    "figures/Figure_1A_treatment.png",
    "figures/Figure_2A_blot.png",
    "manuscript.pdf",
    "protocols/study_protocol.txt",
    "raw_images/acquisition_A001.png",
    "raw_images/acquisition_A002.png",
    "raw_images/full_membrane_A003.png",
    "source_data/Figure_1_source.csv"
  ],
  "materials_missing": [
    "figure assembly",
    "supplementary"
  ],
  "overall_risk": "R1",
  "misconduct_verdict_present": false,
  "risk_caps_applied": [
    "Missing materials are completeness gaps, not evidence of misconduct."
  ],
  "positive_provenance": [
    {
      "provenance_id": "PROV-0001",
      "relation_type": "expected_traceability",
      "figure_panel": "figures/Figure_1A_control.png",
      "source_record": "raw_images/acquisition_A001.png",
      "evidence_source": "figure_assembly/assembly_manifest.txt",
      "risk_effect": "positive_evidence"
    },
    {
      "provenance_id": "PROV-0002",
      "relation_type": "expected_traceability",
      "figure_panel": "figures/Figure_1A_treatment.png",
      "source_record": "raw_images/acquisition_A002.png",
      "evidence_source": "figure_assembly/assembly_manifest.txt",
      "risk_effect": "positive_evidence"
    },
    {
      "provenance_id": "PROV-0003",
      "relation_type": "expected_traceability",
      "figure_panel": "figures/Figure_2A_blot.png",
      "source_record": "raw_images/full_membrane_A003.png",
      "evidence_source": "figure_assembly/assembly_manifest.txt",
      "risk_effect": "positive_evidence"
    }
  ],
  "traceability_gaps": [],
  "findings": [],
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
    "image_panels_screened": 6,
    "image_files_unreadable": 0,
    "source_tables_screened": 1,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
