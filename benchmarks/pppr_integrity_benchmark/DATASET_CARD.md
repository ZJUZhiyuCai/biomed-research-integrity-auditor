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

## Current Public Smoke Baseline

`results/public_smoke_2026-06-30.json` records a two-case run:

- `ori_samples_public_images`: three ORI public sample images screened; the single ORI unit recall
  label was not detected by default image detectors.
- `pmc_oa_pmc10009402_1`: one CC-BY PMC OA package with XML, PDF, and four media images screened
  as an unannotated material-coverage control.

This is a smoke baseline, not a finished PPPR benchmark. The ORI miss is tracked as a real-data
recall gap.

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
