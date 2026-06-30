# Building a Public-Concern Benchmark

This project can use post-publication public concern sources to evaluate the auditor, but the
benchmark must stay narrow and careful:

> PubPeer-derived cases are public-concern-triggered evaluation cases, not adjudicated misconduct
> labels.

The benchmark should test whether the auditor can surface reproducible risk signals from public
article materials, while preserving benign explanations, source limitations, and risk caps.

## Source Roles

| Source | Recommended role | Not allowed |
| --- | --- | --- |
| PubPeer | Case discovery and weak public-concern metadata, preferably via approved API access or manual curation | Scraping comments, republishing comment text, treating comments as misconduct truth |
| Crossref / Retraction Watch Database | Publication-status and retraction/correction metadata | Pixel-level or figure-level truth by itself |
| PMC Open Access Subset | Legally reusable article XML/PDF/figures/supplementary files, subject to article license | Assuming every PMC article is reusable |
| ORI forensic image samples | Small image-forensics unit tests and examples | Article-level benchmark truth |

Primary references:

- PubPeer FAQ: https://pubpeer.com/static/faq
- PubPeer terms: https://pubpeer.com/static/tos
- Crossref Retraction Watch documentation: https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/
- PMC Open Access Subset: https://pmc.ncbi.nlm.nih.gov/tools/openftlist/
- ORI samples: https://ori.hhs.gov/samples

## Benchmark Layout

```text
benchmarks/pppr_integrity_benchmark/
├── DATASET_CARD.md
├── LABELING_GUIDE.md
├── LICENSE_NOTES.md
├── labels.schema.json
├── sources/
│   ├── pubpeer_cases_manifest.csv
│   ├── rwdb_cases_manifest.csv
│   ├── pmc_oa_manifest.csv
│   └── ori_samples_manifest.csv
├── labels/
│   ├── article_level_labels.csv
│   ├── finding_level_labels.jsonl
│   ├── expected_risk_calibration.jsonl
│   └── adjudication_notes.md
├── splits/
│   ├── dev_cases.txt
│   ├── test_cases.txt
│   └── hidden_cases.txt
└── scripts/
    ├── build_rwdb_index.py
    ├── build_pmc_oa_packages.py
    ├── normalize_pubpeer_manifest.py
    ├── run_auditor_on_benchmark.py
    ├── make_matched_controls.py
    └── evaluate_audit_outputs.py
```

## Label Layers

Use two layers.

Article-level labels answer whether an article had a public concern, correction, expression of
concern, retraction, or known publication-status event at the snapshot date. They do not identify a
specific figure/panel problem.

Finding-level labels answer what a human annotator can verify from public materials:

- location: figure, panel, table, source-data row, paragraph;
- issue type: image, western blot/gel, microscopy, numeric/statistical, text, reporting, metadata;
- evidence coordinates where possible;
- benign explanations considered;
- expected risk range under this project's R0-R4 rules;
- label strength and adjudication status.

Do not use fields such as `misconduct: true`, `fraud: true`, or `fake: true`.

## Blind Evaluation Design

Avoid label leakage:

1. Build an audit package from article materials only.
2. Do not give PubPeer comments, retraction reasons, or labels to the auditor for content-only runs.
3. Run `scripts/audit_package.py` on each package.
4. Compare `AUDIT_JSON_SUMMARY.json`, detector outputs, and coverage against offline labels.

Separate experiments:

- `content_only`: no network metadata enrichment and no public-concern metadata in the package.
- `metadata_enriched`: explicitly evaluates status/metadata lookups separately.
- `full_workflow`: combines content audit, allowed metadata, calibration, and report review.

## Metrics

Report more than recall:

- finding-level recall;
- panel-level recall;
- candidate precision;
- false escalation rate;
- risk-cap violation rate;
- R1 completeness-gap correctness;
- benign-explanation preservation rate;
- coverage disclosure completeness;
- crash rate and time per package.

For this project, risk-cap violation rate is a core safety metric. A tool that overstates public
concerns is not acceptable for pre-submission self-audit or public-material triage.
