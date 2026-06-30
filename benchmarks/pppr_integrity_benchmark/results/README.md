# Benchmark Results

This directory stores small result summaries only. It does not store third-party
article files, figures, PubPeer comments, or screenshots.

## Public Smoke 2026-06-30

`public_smoke_2026-06-30.json` records the current real public-data smoke run:

- ORI public image-forensics samples: 13 images screened, 2 detector-scope recall labels, 2 hits.
- Two ORI observations are retained as `scope_gap` labels rather than recall misses:
  same-section overlap (`fig_a` / `fig_b`) and low-contrast copy-move (`weak_background_large`).
- PMC Open Access `PMC10009402.1`: XML, PDF, and 4 media images screened as a material-coverage control.
- Boundary checks: 0 risk-cap violations and 0 misconduct-verdict violations.

The scope-gap labels are intentional evidence about remaining detector work. They are not counted
as recall misses because they sit outside the current pixel-copy detector gate, and they are not
clean/no-concern conclusions.
