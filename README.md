# Biomedical Research Self-Audit Assistant

[中文说明](README.zh-CN.md)

A local-first tool that helps biomedical research teams check their manuscript package for internal consistency before submission — figures, raw images, source data, statistics, text overlap, and traceability records.

It is **not** a fraud detector. It never concludes that misconduct occurred. Instead, it produces evidence-backed risk findings, lists what materials are missing, and queues concrete actions for the team to resolve — all in neutral language.

> **The one rule:** "no issue found" means *nothing was flagged within the supplied materials and the current detector scope*. It never means the work is proven correct.

Under the hood: a local **CLI**, a local-first **web app**, a Codex **skill**, and a scriptable detector pipeline.

---

## Who is this for

| You are… | Start here |
| --- | --- |
| An **author** running a pre-submission self-audit | [`docs/self-audit-guide.md`](docs/self-audit-guide.md) and [Quick start](#quick-start) below |
| A **reviewer or integrity office** triaging concerns | [Quick start](#quick-start), then [`docs/response-to-concern-guide.md`](docs/response-to-concern-guide.md) and the external/response modes in [`docs/architecture.md`](docs/architecture.md) |
| A **developer or evaluator** | [How it works](#how-it-works) and [For developers and evaluators](#for-developers-and-evaluators) |

---

## Quick start

Requires Python 3.10+.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

For a repeatable deployment that also links commands into `~/.local/bin`:

```bash
python3.11 scripts/install_local_commands.py
# or
make install-local
```

This installs `biomed-audit`, `biomed-audit-diff`, `biomed-audit-web`, and `biomed-self-audit-webapp`. Make sure `~/.local/bin` is on your `PATH`.

### Run your first audit

```bash
biomed-audit examples/minimal_package --scan-profile quick --output-dir audit_outputs/minimal
biomed-audit examples/full_presubmission_package --output-dir audit_outputs/full
```

If `python3` already points to 3.10+, use `python3` instead of `python3.11`. Without installing console scripts, use `python scripts/audit_package.py ...` with the same arguments.

### Audit your own package

```bash
biomed-audit /path/to/my_package --output-dir audit_outputs/my_package
```

The default mode is `--mode internal_presubmission`. Also available: `external_public_material` and `response_to_concern`.

**Authors:** the [self-audit guide](docs/self-audit-guide.md) walks through preparing materials, running the audit, and reading the report — including which conclusions you may *not* draw.

**Responding to a journal/reviewer concern:** use the [response-to-concern guide](docs/response-to-concern-guide.md) and keep the language evidence-based and neutral.

### What each run produces

**The report** (human-facing):

- `audit-report.md` — bilingual Markdown report: Quick Read, submission-readiness status, action queue, coverage, materials needed, finding cards, technical appendix.

**Structured evidence** (machine-readable):

- `AUDIT_JSON_SUMMARY.json` — the same findings in JSON form.
- `coverage.json`, `calibrated_findings.json`, per-detector outputs — supporting detail.
- `audit_snapshot.json`, `file_hash_manifest.json` — exact package version reviewed (SHA-256).
- `claim_coverage.json` / `.csv` — claim-to-evidence coverage (when `claim_manifest.csv` is supplied).
- `methodology_checklist.json` / `.csv` — readiness prompts for ARRIVE, CONSORT, ICMJE, MIFlowCyt, omics.
- `writing_readiness.json` / `.csv` — language/submission prep prompts (does not affect R0–R4).

**Team workflow**:

- `unresolved_actions.csv`, `resolved_actions.csv`, `accepted_with_reason.csv` — action trackers.
- `correction_plan.md` / `.csv` — pre-submission correction-plan tracker.
- `submission_qc_packet/` — a leave-behind packet containing the report, coverage, trackers, verified traceability, file hashes, and an author sign-off template.

---

## How it works

The pipeline separates *finding candidates* from *risk decisions*, so no single component can inflate a result:

```text
material intake → structured extraction → provenance graph → detectors
→ contextual join → risk calibration → evidence ledger → bilingual human report
```

- **Detectors** emit candidates with evidence and locations — never a final risk level.
- **Provenance builders** model files and declared figure-to-raw relationships.
- **Context joiners** add disclosure, source availability, and provenance context.
- **The calibrator** is the only component that assigns `calibrated_risk_level`, applying source strength, completeness, disclosure, benign explanations, and mode-specific caps.
- **The reporter** renders calibrated findings in neutral bilingual language and rejects uncalibrated input.

`scripts/audit_package.py` orchestrates the full flow. See [`docs/architecture.md`](docs/architecture.md) for the complete design.

---

## The R0–R4 risk scale

Every finding is placed on a five-level scale. Even the highest level is not a misconduct verdict.

| Level | Meaning | Typical action |
| --- | --- | --- |
| `R0` | No issue found (within scope) | State what was screened and what is missing |
| `R1` | Completeness or documentation gap | Add raw/source records and re-run |
| `R2` | Reviewable reporting concern or weak statistical pattern | Fix method/legend/supplement |
| `R3` | Material concern needing source data or author explanation | Provide raw records and explain |
| `R4` | Direct contradiction inside the supplied materials | Pause and reconcile before submitting |

Two guardrails: public-material-only review caps below `R4` unless a direct contradiction exists; weak statistical patterns alone cannot reach higher levels.

---

## Audit modes and options

### Scan profiles

Use `--scan-profile` to control speed and depth:

| Profile | Use case | What changes |
| --- | --- | --- |
| `quick` | First-pass drag-and-check | Fast source/text/global-image screens; skips local-patch deep image screening and external phrase search. |
| `standard` | Default pre-submission QC | Balanced detector set; exports submission QC packet. |
| `deep` | Focused recheck or response-to-concern | Stricter image similarity thresholds; records deep-profile parameters in coverage. |

### Claim-to-evidence manifest

For a stronger review, add `claim_manifest.csv` at the package root (or pass `--claim-manifest`). Each row links a manuscript claim to its evidence chain:

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

The report then includes a **Claim Coverage** section — this is a completeness view, not a claim that the science is true.

### Re-audit diff

After fixing gaps, compare two audit outputs:

```bash
biomed-audit-diff audit_outputs/v1 audit_outputs/v2 \
  --output audit_outputs/v2/re_audit_diff.json \
  --csv audit_outputs/v2/re_audit_diff.csv
```

Or pass `--compare-to audit_outputs/v1` during the second run. The diff reports changes in risk counts, missing materials, traceability, unresolved actions, and claim-evidence gaps.

### Local web app

One-command launcher from a source checkout:

```bash
make run
```

It creates `.venv`, installs dependencies, builds the frontend (when `npm` is available), starts the app on `127.0.0.1:8765`, and opens your browser. If the port is already in use, it opens the existing app.

Manual setup for development:

```bash
cd webapp/frontend && npm install && npm run build && cd ../..
biomed-audit-web
```

The web app wraps the same pipeline as the CLI, keeps Audit Coverage visible, and provides local package-prep tools for folder layout and `assembly_manifest.csv` creation. See [`webapp/README.md`](webapp/README.md).

Source-checkout fallback: `python -m webapp`.

---

## What makes results trustworthy

- **Separation of duties.** Detectors only suggest; the calibrator decides. Every finding must come from a schema-validated detector candidate.
- **Provenance-aware calibration.** A figure matching its declared raw is positive traceability evidence. But a self-declared manifest line cannot suppress a real duplicate — if two panels are declared "same source" yet detected as whole-image near-duplicates, the pipeline reports a `manifest_conflict` requiring raw records.
- **No silent "clean."** Every report carries an `audit_coverage` block listing which modules ran, which did not, how many panels were screened, and how many files were unreadable. An empty finding list is never presented as a verified-correct manuscript.
- **Fail-closed contracts.** Schema validation is required — the pipeline stops rather than silently degrading. A budget-limited detector yields an explicit `audit_coverage_gap` (R1); a crashed detector yields `detector_execution_failure` (R1) while preserving other modules.
- **Risk caps match evidence.** Weak statistical patterns cap at R2; completeness gaps at R1; public-material triage at R3; R4 requires a tagged direct contradiction.

---

## Scope and limitations

### Image screening

Image, local-patch, and same-image copy-move detection work within a single package only — they do not search across papers or external corpora. The detectors do not cover arbitrary-angle rotation, perspective warps, elastic deformation, substantial rescaling, splice forensics (JPEG ghost, CFA/noise inconsistency), or lighting/shadow inconsistency. Reports explicitly state this boundary.

For large packages, local-patch screening uses runtime tile/comparison budgets. If a budget is reached, the report records an R1 coverage gap and recommends a focused deep scan.

### Statistical screening

Covers SD/SEM/n consistency, p-value range, integer-count feasibility, and sample-gated weak distributional prompts (Benford-style first-digit ≥ 30 values, p-value clustering ≥ 20 values, digit/rounding ≥ 8 values, integer-count n ≥ 6). These weak screens use minimum sample-size gates and are automated triage only when those gates are met — they are not standalone evidence.

### Text, reference, and PDF

Text overlap screening is package-internal; optional external phrase search is triage, not exhaustive plagiarism coverage. Reference checking is opt-in and limited to DOI/reference metadata prompts via Crossref-style lookups. True-PDF intake handles machine-readable text and OCR-capable scanned PDFs; figure/caption extraction is limited. Public-material review is capped by missing source records and must never be read as a misconduct verdict.

---

## Repository layout

| Path | Purpose |
| --- | --- |
| `skill/biomed-research-integrity-auditor/` | Installable Codex skill (instructions, templates, references, helper scripts). |
| `scripts/audit_package.py` | Default contract-first orchestrator. |
| `scripts/submission_qc.py`, `scripts/compare_audit_runs.py` | Submission QC packet and re-audit diff helpers. |
| `detectors/` | Candidate detectors (image, statistics, text) — emit evidence, not verdicts. |
| `calibrators/` | Risk-cap and evidence-strength calibration, contract validation. |
| `provenance/` | Resource-graph builders separating expected traceability from reuse risk. |
| `schemas/` | JSON/YAML contracts for detector output, risk rules, source-data expectations. |
| `examples/` | Runnable example packages (`minimal_package/`, `full_presubmission_package/`). |
| `docs/self-audit-guide.md` | Non-developer guide to materials and report reading. |
| `docs/response-to-concern-guide.md` | Neutral workflow for journal/reviewer/public concern responses. |
| `docs/architecture.md`, `docs/design-notes.md` | Pipeline architecture and design rationale. |
| `evals/` | Synthetic packages, eval harness, and ground truth. |
| `benchmarks/` | True-PDF, scanned-PDF OCR, real-image regression, and PPPR public-concern benchmarks. |
| `webapp/` | Local FastAPI + React/Vite self-audit UI wrapping the CLI artifacts. |

---

## For developers and evaluators

### Run the audit on a synthetic case

```bash
biomed-audit evals/cases/case_004 --output-dir audit_outputs/case_004
```

### Non-LLM detector baseline

Isolates detector/calibration behavior from any LLM:

```bash
python3 evals/run_script_baseline.py --case case_004
```

Check outputs against ground truth:

```bash
python3 evals/assert_audit_outputs.py --outputs-root audit_outputs
```

### Blind evaluation harness

Generate prompts, run them against an agent with access to the skill and a single case package, save reports to `evals/outputs/`, then score:

```bash
python3 evals/run_eval.py generate-prompts
python3 evals/run_eval.py score          # scorecards land in evals/scorecards/
```

The harness rewards restraint as much as recall: over-claiming, ignoring benign explanations, exceeding risk caps, or using verdict language all count as failures.

**Blind-testing rule:** the tested agent must only receive the case package path — never `ground_truth/`, `outputs/`, `scorecards/`, or `prompts/`. For strict evaluation, isolate the case in a separate workspace.

### Archived eval run

A persisted run at [`evals/llm_runs/2026-06-30-codex-orchestrated/`](evals/llm_runs/2026-06-30-codex-orchestrated/): 30/30 synthetic cases passed, 0 boundary violations, 0 risk-cap violations. This shows the harness was executed and retained — it is not an independent third-party validation, and does not measure real-manuscript performance.

### Public-concern benchmark

`benchmarks/pppr_integrity_benchmark/` contains a post-publication concern benchmark scaffold with a real public-data smoke runner. PubPeer is treated as discovery metadata, Crossref/Retraction Watch as publication-status metadata, PMC Open Access as a permitted article source, and ORI samples as image unit cases. It is intentionally not a PubPeer scraper and does not store comments or non-OA article files.

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py --output-root tmp/pppr_public_smoke
python3 benchmarks/pppr_integrity_benchmark/scripts/build_rwdb_index.py --help
python3 benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py --help
```

Current baseline: [`benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json`](benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json) — 2 public cases, 0 violations, 13 ORI images screened, `finding_level_recall: 1.0` for detector-scope labels. ORI same-section overlap and low-contrast copy-move samples are retained as `scope_gap` labels for future work.

Read [`docs/benchmarking_with_pubpeer_and_rwdb.md`](docs/benchmarking_with_pubpeer_and_rwdb.md) and [`docs/data_ethics_and_legal_boundaries.md`](docs/data_ethics_and_legal_boundaries.md) before building real cases.

### Other benchmarks

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py        # compressed machine-text PDF extraction
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py  # image-only PDF OCR (needs tesseract/PyMuPDF/pytesseract)
python3 benchmarks/real_image/run_real_image_benchmark.py    # real public-domain microscopy + 16-bit TIFF
```

`make validate` skips the scanned-PDF benchmark when OCR runtime is missing; CI installs `tesseract-ocr` and runs it as a required gate.

### External literature phrase search

Off by default for private audits:

```bash
python3 detectors/text/external_literature_search.py <package_dir> --provider europepmc --output external_literature_candidates.json
```

The orchestrator flag `--external-literature-provider auto|none|fixture|europepmc|crossref` uses a package fixture when present, queries Europe PMC in `external_public_material` mode, and stays offline for private audits unless you request a provider. Results are candidates for manual review — never a plagiarism verdict.

### Regenerate synthetic cases

Cases are committed; regenerate deterministically with:

```bash
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

---

## Release and install options

### Release artifacts

```bash
make release-artifacts
```

Builds the frontend, Python wheel/sdist, source bundle, and SHA-256 manifest under `dist/release/`. GitHub Actions templates are at `packaging/github-workflows/`; enabling them requires a maintainer token with workflow permission. PyPI and Homebrew publication require maintainer credentials; see [`packaging/README.md`](packaging/README.md).

### Install as a Codex skill

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill/biomed-research-integrity-auditor" ~/.codex/skills/biomed-research-integrity-auditor
```

---

## License

MIT. See [`LICENSE`](LICENSE).
