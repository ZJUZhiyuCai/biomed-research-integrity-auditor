# PPPR Integrity Benchmark Scaffold

This directory defines a **post-publication public concern benchmark** scaffold for validating the
biomedical research-integrity auditor.

It intentionally contains schemas, manifests, scripts, and documentation only. It does not contain
PubPeer comments, non-OA articles, or third-party paper figures.

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
