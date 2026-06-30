# Dataset Card: PPPR Integrity Benchmark

## Dataset Status

Scaffold only. No real PubPeer comments, article PDFs, or paper figures are included in this
repository.

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
