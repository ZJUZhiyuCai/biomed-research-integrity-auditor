# Biomedical Research Integrity Auditor

An open Codex skill, detector pipeline, and blind-evaluation harness for biomedical research integrity review.

This is deliberately **not** a "paper fraud detector." It is a risk-auditing workflow for manuscripts, figures, source data, reporting checklists, and public literature-concern triage. The skill is designed to surface evidence-backed integrity risks, benign explanations, missing materials, and next actions without making misconduct verdicts.

中文简介：这是一个面向生物医药论文和研究材料的“研究诚信风险审计器”。它不判定作者造假，也不输出学术不端结论，而是帮助作者、审稿人或机构内部团队做投稿前自查和外部公开材料的风险分级。

## New here? Start with the self-audit guide

If you are an author who wants to run a pre-submission self-audit, read
[`docs/self-audit-guide.md`](docs/self-audit-guide.md). It explains how to prepare materials,
run the audit, and read the report — and which conclusions you may not draw. Two runnable
example packages are in [`examples/`](examples/):

```bash
python3 scripts/audit_package.py examples/minimal_package --output-dir audit_outputs/minimal
python3 scripts/audit_package.py examples/full_presubmission_package --output-dir audit_outputs/full
```

## What Is Included

- `skill/biomed-research-integrity-auditor/` - the installable Codex skill.
- `detectors/` - scriptable candidate detectors that emit evidence but not final verdicts.
- `calibrators/` - risk-cap and evidence-strength calibration.
- `scripts/audit_package.py` - the default contract-first orchestrator for package audits.
- `provenance/` - resource graph builders that distinguish expected traceability from reuse risk.
- `schemas/` - shared JSON/YAML contracts for detector output, paper objects, and source-data expectations.
- `evals/` - neutral synthetic manuscript packages for blind testing.
- `evals/run_eval.py` - prompt generation and JSON-summary scoring.
- `evals/run_script_baseline.py` - non-LLM detector baseline runner.
- `evals/generate_synthetic_cases.py` - deterministic synthetic package generator.
- `examples/` - runnable example packages (`minimal_package/`, `full_presubmission_package/`) for first-time self-audit users.
- `docs/self-audit-guide.md` - non-developer guide to preparing materials, running the audit, and reading the report.
- `docs/architecture.md` - audit pipeline architecture.
- `docs/design-notes.md` - design rationale, boundaries, and source anchors.

## Integrity Boundary

The skill must not say that misconduct, fraud, fabrication, or falsification is proven. It uses an `R0` to `R4` research-integrity risk scale:

- `R0`: no material issue found in supplied materials
- `R1`: completeness or documentation gap
- `R2`: reviewable inconsistency or weak evidence pattern
- `R3`: material concern needing source-data or author clarification
- `R4`: direct contradiction in supplied internal materials

Public-material-only review is capped below `R4` unless direct internal contradiction is available. Weak statistical patterns alone are capped below major concern levels.

Detectors only emit candidates with `risk_suggestion`. Final risk levels are assigned only by the calibrator as `calibrated_risk_level`, after source strength, material completeness, disclosure context, benign explanations, and mode-specific caps are applied.

## Install The Skill

Clone the repository, then copy or symlink the skill into your Codex skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill/biomed-research-integrity-auditor" ~/.codex/skills/biomed-research-integrity-auditor
```

If the symlink already exists, remove or update it intentionally.

## Run The Eval Harness

Run the default non-LLM audit pipeline on a package:

```bash
python3 scripts/audit_package.py evals/cases/case_004 --output-dir audit_outputs/case_004
```

The orchestrator inventories the package, runs detector scripts, validates detector JSON with `schemas/detector_output.schema.json`, joins context for disclosed reuse, applies `schemas/risk_rules.yaml`, validates calibrated findings, and writes an audit report plus `AUDIT_JSON_SUMMARY.json`.
Schema validation requires `jsonschema`; if it is unavailable, the pipeline fails closed instead of falling back to partial contract checks.
If no detector can run on the supplied package, the pipeline emits an explicit `audit_coverage_gap` R1 finding rather than treating the package as clean.
If an individual detector exits non-zero or writes invalid JSON, the pipeline preserves other detector outputs and emits a `detector_execution_failure` R1 finding for the failed module.
The calibrator accepts detector-candidate payloads only; legacy hand-written findings are rejected as inputs.
Risk-rule keys are validated, including mode-specific `missing_source_data_max` caps and `report_as: positive_evidence` routing for R0 traceability candidates.

The pipeline is provenance-aware: figure-panel similarity to a declared raw/source image is reported as positive traceability evidence, while unmapped figure-to-raw similarity is capped as an `R1` traceability gap rather than an `R3` image-reuse concern.
A declared figure-to-figure same-field/same-membrane relationship cannot clear a verifiable whole-image near-duplicate; that pair is reported as an unverifiable `manifest_conflict` requiring raw records, so an author-written manifest line cannot silently suppress a real duplicate.
The JSON summary includes both risk findings and machine-readable positive provenance, so clean traceability can be tested separately from unresolved gaps.
Every report and `AUDIT_JSON_SUMMARY` also includes an `audit_coverage` block (modules executed, modules not run, image panels screened, unreadable image files, detector failures, and a scope note), so an empty finding list within scope is not mistaken for a verified-correct manuscript.
The image pipeline also includes a conservative local patch screen that exports evidence crops for cross-image region reuse and same-image copy-move candidates. Patch similarity remains a detector candidate: declared traceability and same-field/channel relationships are excluded before risk calibration, and `R4` still requires a direct contradiction tag.
The statistics pipeline screens CSV, TSV, and XLSX source-data tables. Legacy `.xls` files may be inventoried as source material, but they are not treated as supported detector input.
The text pipeline includes a package-internal overlap screen for supplied manuscript, supplementary, draft, thesis, preprint, and lab-prior-paper text. The default orchestrator can also run privacy-aware external phrase-search triage with query/result provenance. It is not a web-scale plagiarism search; findings remain section-aware overlap candidates and must be calibrated against disclosure, citation, and journal-policy context.

Structured figure assembly manifests are preferred when available:

```csv
figure_panel,source_record,relation_type,modality,notes
figures/Figure_1A_control.png,raw_images/acquisition_A001.png,declared_derived_from,microscopy,control representative image
```

Manifest precedence is `assembly_manifest.csv` or `.yaml`, then parsed text manifests, then filename-derived figure-source maps.

Create prompts for blind testing:

```bash
python3 evals/run_eval.py generate-prompts
```

Run each prompt against an agent that has access to the skill and the target `cases/case_XXX` package, then save its report as:

```text
evals/outputs/case_001.md
evals/outputs/case_002.md
...
```

Each report must end with one fenced JSON block labeled `AUDIT_JSON_SUMMARY`. Score the outputs:

```bash
python3 evals/run_eval.py score
```

The scorecard is written to `evals/scorecards/`.

A persisted Codex-orchestrated eval run is archived at
[`evals/llm_runs/2026-06-30-codex-orchestrated/`](evals/llm_runs/2026-06-30-codex-orchestrated/).
It scored 30/30 synthetic cases with 0 boundary violations and 0 risk-cap violations. This is
evidence that the current harness was executed and retained; it is not an independent third-party
blinded LLM validation.

Run the non-LLM detector baseline:

```bash
python3 evals/run_script_baseline.py --case case_004
python3 evals/run_script_baseline.py --case case_010
python3 evals/run_script_baseline.py --case case_020
python3 evals/run_script_baseline.py --case case_026
```

Run the true-PDF benchmark:

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py
```

This benchmark verifies that a true binary PDF with compressed machine-readable text is extracted before package-internal text-overlap screening, while still confirming the expected text is not visible as raw PDF bytes.

Run the scanned-PDF OCR benchmark when OCR runtime dependencies are available:

```bash
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py
```

This benchmark creates an image-only PDF and verifies that OCR text can feed the package-internal text-overlap detector. Local `make validate` skips it if `tesseract`, PyMuPDF, or pytesseract are unavailable; CI installs `tesseract-ocr` and runs this benchmark without `--skip-if-unavailable`, making OCR a required gate for pushes and pull requests.

Run the real-image benchmark:

```bash
python3 benchmarks/real_image/run_real_image_benchmark.py
```

This benchmark uses a downscaled public-domain National Cancer Institute microscopy image to test duplicate detection on real image texture rather than hand-drawn synthetic shapes.
It also generates a 16-bit TIFF microscopy-derived pair to verify that image detectors normalize high-bit-depth grayscale inputs before hashing.

Run an explicit external literature/library phrase search:

```bash
python3 detectors/text/external_literature_search.py <package_dir> --provider europepmc --output external_literature_candidates.json
```

The default audit orchestrator also accepts `--external-literature-provider auto|none|fixture|europepmc|crossref`. `auto` uses a package fixture when present, runs Europe PMC in `external_public_material` mode, and stays offline for private internal audits unless a provider is explicitly requested. External search is a candidate-finding aid against Europe PMC, Crossref, or a fixture file, not a plagiarism database or verdict.

CI also asserts key script-baseline audit outputs against `evals/ground_truth/` with:

```bash
python3 evals/assert_audit_outputs.py --outputs-root audit_outputs
```

## Regenerate Synthetic Cases

The generated cases are already committed. To regenerate them:

```bash
python3 -m pip install -r requirements.txt
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

## Blind-Testing Note

The `ground_truth/` directory is included so the harness is reproducible. A tested agent should only receive the case package path and must not read `ground_truth/`, `outputs/`, `scorecards/`, or `prompts/`. For stricter evaluation, copy the target case package into an isolated workspace and keep the answer key outside the agent's accessible directory.

## Current Limitations

- Local patch and same-image copy-move detection are single-package only; they do not search across papers or external image corpora.
- Default text overlap screening is package-internal, with privacy-aware external phrase-search triage available through the orchestrator; it does not perform exhaustive plagiarism-database coverage or a plagiarism verdict.
- True PDF intake supports machine-readable text and OCR-capable scanned PDFs when OCR runtime dependencies are available; figure/caption extraction remains limited.
- Image intake now normalizes high-bit-depth grayscale TIFF-style inputs, but broad validation on multi-frame/Z-stack/channel microscopy corpora remains future work.
- Statistical screening checks p-value range/validity, SD/SEM/n consistency, integer-count feasibility, and weak forensic patterns. Weak digit/rounding screens require at least 8 comparable values by default, and integer-count feasibility requires n >= 6 while respecting reported precision. It does not perform Benford-style first-digit distribution analysis or p-value clustering/distribution tests; those remain manual statistical checks and are not implemented as detectors.
- Public-material review remains capped by missing source/raw records and must not be treated as a misconduct verdict.

## License

MIT. See `LICENSE`.
