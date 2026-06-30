# Biomedical Research Integrity Pre-submission Audit

## Scope

- Mode: internal_presubmission
- Package root: /Users/rosscai/Documents/biomed-research-integrity-auditor/evals/cases/case_026

## Audit Coverage

Modules executed in this run:

- package_internal_text_overlap

Modules not executed in this run:

- image screening (no image files supplied)
- statistics screening (no source_data CSV/TSV/XLSX supplied)
- external literature phrase search (offline: private internal audit, or no provider/fixture)
- methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened

- Image panels screened: 0
- Source-data tables screened: 0

> A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review.

## Missing Materials Matrix

| Category | Risk | Reason |
| --- | --- | --- |
| ethics_irb | R1 | No files classified as ethics_irb. |
| figure_assembly | R1 | No files classified as figure_assembly. |
| figures | R1 | No files classified as figures. |
| protocols | R1 | No files classified as protocols. |
| raw_images | R1 | No files classified as raw_images. |
| source_data | R1 | No files classified as source_data. |
| supplementary | R1 | No files classified as supplementary. |

## Risk Register

| Finding ID | Risk | Module | Location | Finding |
| --- | --- | --- | --- | --- |
| TEXTOVERLAP-0001 | R3 | text.text_overlap_screen | lab_previous_papers/paper_b.txt#p001 / manuscript.pdf#p001 | text_overlap_candidate |

## Evidence Ledger

### TEXTOVERLAP-0001

- Risk Level: R3
- Module: text.text_overlap_screen
- Location: lab_previous_papers/paper_b.txt#p001 / manuscript.pdf#p001
- Finding Type: text_overlap_candidate
- Evidence: `{"document_a": "lab_previous_papers/paper_b.txt", "document_b": "manuscript.pdf", "section_a": "results", "section_b": "results", "paragraph_id_a": "lab_previous_papers/paper_b.txt#p001", "paragraph_id_b": "manuscript.pdf#p001", "similarity_score": 1.0, "overlapping_ngram_examples": ["a consistent shift in the", "a sustained increase in nuclear", "across all quantified fields with", "after excluding low intensity fields", "after twenty four hours quantification"], "text_snippet_a": "The treatment group showed a sustained increase in nuclear signal intensity across all quantified fields, with the strongest response observed after twenty four hours. Quantification from independent biological replicates showed a consistent shift in the same direction, and the effect remained visible when the analysis was repeated after excluding low intens", "text_snippet_b": "The treatment group showed a sustained increase in nuclear signal intensity across all quantified fields, with the strongest response observed after twenty four hours. Quantification from independent biological replicates showed a consistent shift in the same direction, and the effect remained visible when the analysis was repeated after excluding low intens"}`
- Benign explanations considered: standard methods or protocol boilerplate may be legitimately reused, text may derive from a disclosed thesis, preprint, protocol, or prior draft, overlap requires section-aware human review before escalation
- Required materials to resolve: prior version or source document, disclosure statement or citation trail, journal policy context for text reuse
- Recommended action: Review overlapping paragraphs with disclosure, citation, and journal-policy context; do not treat overlap as a misconduct verdict.
- Note: Calibrated from detector candidate; not a misconduct verdict.

## Boundary

This report identifies research-integrity risks and completeness gaps. It does not determine misconduct, intent, or author guilt.

## Audit JSON Summary

```json AUDIT_JSON_SUMMARY
{
  "audit_mode": "internal_presubmission",
  "case_id": "case_026",
  "materials_reviewed": [
    "PACKAGE_NOTE.txt",
    "lab_previous_papers/paper_b.txt",
    "manuscript.pdf"
  ],
  "materials_missing": [
    "ethics irb",
    "figure assembly",
    "figures",
    "protocols",
    "raw images",
    "source data",
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
      "finding_id": "TEXTOVERLAP-0001",
      "risk_level": "R3",
      "finding_type": "text_overlap_candidate",
      "location": "lab_previous_papers/paper_b.txt#p001 / manuscript.pdf#p001",
      "evidence_type": "text_overlap_candidate",
      "benign_explanations_considered": [
        "standard methods or protocol boilerplate may be legitimately reused",
        "text may derive from a disclosed thesis, preprint, protocol, or prior draft",
        "overlap requires section-aware human review before escalation"
      ],
      "required_materials_to_resolve": [
        "prior version or source document",
        "disclosure statement or citation trail",
        "journal policy context for text reuse"
      ],
      "recommended_action": "Review overlapping paragraphs with disclosure, citation, and journal-policy context; do not treat overlap as a misconduct verdict."
    }
  ],
  "audit_coverage": {
    "modules_executed": [
      "package_internal_text_overlap"
    ],
    "modules_not_executed": [
      "image screening (no image files supplied)",
      "statistics screening (no source_data CSV/TSV/XLSX supplied)",
      "external literature phrase search (offline: private internal audit, or no provider/fixture)",
      "methodology/reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession): guided checklist, not auto-screened"
    ],
    "image_panels_screened": 0,
    "image_files_unreadable": 0,
    "source_tables_screened": 0,
    "detector_failures": [],
    "audit_coverage_gap": false,
    "external_literature_provider": null,
    "scope_note": "A module with no findings means no candidate was detected within the current detector scope and supplied materials; it is not a guarantee of correctness. Methodology and reporting-standard compliance (ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics accession) and exhaustive external plagiarism-database search are not performed automatically and require human review."
  }
}
```
