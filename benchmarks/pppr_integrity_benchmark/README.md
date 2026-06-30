# PPPR Integrity Benchmark Scaffold

This directory defines a **post-publication public concern benchmark** scaffold for validating the
biomedical research-integrity auditor.

It intentionally contains schemas, manifests, scripts, documentation, and compact result summaries
only. It does not contain PubPeer comments, non-OA articles, or third-party paper figures. Real ORI
and PMC OA materials are downloaded into `tmp/` by the public smoke runner when you choose to run it.

Use it to build local or releasable benchmark packages from permitted sources:

- PubPeer: discovery / weak public-concern metadata only.
- Crossref Retraction Watch data: publication-status metadata.
- PMC Open Access: article materials when the license permits.
- ORI samples: small image-forensics unit tests.

See:

- `DATASET_CARD.md`
- `LABELING_GUIDE.md`
- `LICENSE_NOTES.md`
- `labels.schema.json`
- `docs/benchmarking_with_pubpeer_and_rwdb.md`
- `docs/data_ethics_and_legal_boundaries.md`

## Quick Local Smoke

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/build_rwdb_index.py \
  --input path/to/retraction_watch.csv \
  --output /tmp/rwdb_cases_manifest.csv

python3 benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py \
  --labels benchmarks/pppr_integrity_benchmark/labels/finding_level_labels.jsonl \
  --outputs-root audit_outputs \
  --output /tmp/pppr_eval.json
```

Empty label files are valid while the benchmark is being curated.

## Public-Data Smoke

To build and run a tiny real public-data smoke benchmark:

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py \
  --output-root tmp/pppr_public_smoke
```

The smoke benchmark downloads:

- a small ORI public image-forensics sample package;
- one PMC Open Access S3 package (`PMC10009402.1` by default).

Generated packages, article files, figures, labels, splits, audit outputs, and
evaluation files are written under `tmp/pppr_public_smoke/` and are not committed.
Result summaries may be committed under `results/` when they contain no third-party
content.

Current baseline: `results/public_smoke_2026-06-30.json` records 2 public cases,
0 risk-cap violations, 0 boundary-language violations, and 2/2 detector-scope ORI recall
labels hit (`finding_level_recall: 1.0`). ORI same-section overlap and low-contrast copy-move
samples are retained as `scope_gap` labels for future detector work, not as clean-paper or
no-concern conclusions.
