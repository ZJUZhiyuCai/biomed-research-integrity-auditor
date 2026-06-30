# Benchmark Results

This directory stores small result summaries only. It does not store third-party
article files, figures, PubPeer comments, or screenshots.

## Public Smoke 2026-06-30

`public_smoke_2026-06-30.json` records the first real public-data smoke run:

- ORI public image-forensics samples: 3 images screened, 1 unit recall label, 0 hits.
- PMC Open Access `PMC10009402.1`: XML, PDF, and 4 media images screened as a material-coverage control.
- Boundary checks: 0 risk-cap violations and 0 misconduct-verdict violations.

The ORI miss is intentional evidence: the default image detectors did not recover
that public unit label in this run. Treat it as a real-data recall gap to improve,
not as a clean result.
