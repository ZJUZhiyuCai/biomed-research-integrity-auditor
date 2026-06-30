# Dataset Card: PPPR Integrity Benchmark

## Dataset Status

Scaffold plus a small public-data smoke runner. No real PubPeer comments, article PDFs, or paper
figures are included in this repository.

`scripts/run_public_smoke_benchmark.py` can locally download a tiny ORI + PMC OA smoke set under
`tmp/`. Only compact result summaries without third-party content should be committed.

## Intended Use

Evaluate whether the auditor surfaces public, reproducible research-integrity risk signals from
article materials while preserving risk caps, benign explanations, and coverage boundaries.

## Not Intended For

- misconduct classification;
- author, lab, institution, or journal ranking;
- web-scale PubPeer mirroring;
- plagiarism-database replacement;
- proof that matched controls are correct.

## Sources

- PubPeer: case discovery and weak public-concern metadata.
- Crossref / Retraction Watch: article-level publication-status metadata.
- PMC Open Access: reusable article materials subject to license.
- ORI samples: image-forensics unit tests.

Labels may be marked `evaluation_role=recall_label`, `scope_gap`, or `reference_only`.
Only recall labels contribute to recall metrics. Scope-gap labels document public observations that
the current detector family is not yet expected to recover.

## Current Public Smoke Baseline

`results/public_smoke_2026-06-30.json` records a two-case run:

- `ori_samples_public_images`: 13 ORI public sample images screened; 2 detector-scope ORI recall
  labels were detected, while same-section overlap and low-contrast copy-move samples are retained
  as `scope_gap` labels for future detector work.
- `pmc_oa_pmc10009402_1`: one CC-BY PMC OA package with XML, PDF, and four media images screened
  as an unannotated material-coverage control.

This is a smoke baseline, not a finished PPPR benchmark. Scope-gap labels are real-data evidence
for future recall work, not clean/no-concern conclusions.

## Label Strengths

- `weak_pubpeer_signal`: public discussion exists, no independent manual verification yet.
- `manually_verified_public_evidence`: annotators verified the signal from public article materials.
- `journal_confirmed_correction`: journal issued a correction relevant to the concern.
- `journal_confirmed_retraction`: journal or Crossref/RWDB metadata records a retraction.
- `ori_unit_sample`: ORI sample used as an image-forensics unit case.

## Recommended Splits

- `dev_cases.txt`: cases visible to developers during tuning.
- `test_cases.txt`: cases used for release regression.
- `hidden_cases.txt`: labels withheld for blinded evaluation.

## Safety Notes

The benchmark must report public-concern and publication-status signals, not misconduct verdicts.
All labels should include benign explanations considered and materials needed to resolve the issue.
