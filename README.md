# Biomedical Research Integrity Auditor

[中文说明](README.zh-CN.md)

A tool that helps you **screen a biomedical manuscript package for research-integrity risks
before submission** — and organizes the evidence into a calm, neutral, bilingual report
that humans can read before machines parse the JSON.

It is **not** a "paper fraud detector." It never decides that misconduct, fraud, fabrication,
or plagiarism occurred. Instead it surfaces evidence-backed risks, lists benign explanations,
flags missing materials, and recommends next actions — using an `R0`–`R4` risk scale and
neutral language throughout.

Under the hood it is three things: an installable Codex **skill**, a scriptable **detector
pipeline**, and a **blind-evaluation harness**.

> 中文简介：这是一个面向生物医药论文和研究材料的"研究诚信风险审计器"。它不判定作者造假，也不输出
> 学术不端结论，而是帮助作者、审稿人或机构内部团队做投稿前自查和外部公开材料的风险分级。

---

## What it does and what it does not

**It does:**

- Screen figures for image near-duplicates and same-image copy-move.
- Cross-check declared figure-to-raw traceability and record positive provenance evidence.
- Record an audit snapshot with file hashes, optional claim-to-evidence coverage, and a submission QC packet.
- Check numeric/statistical consistency in source or summary tables (SD/SEM/n, p-value range, integer counts).
- Screen package-internal text overlap, with optional external phrase-search triage.
- Produce a bilingual human-readable report with a Quick Read, coverage, materials needed,
  finding cards, action checklist, technical appendix, and an `R0`–`R4` risk register.

**It does not:**

- Decide misconduct, fraud, fabrication, falsification, or plagiarism.
- Prove a manuscript is correct or its figures authentic.
- Run a web-scale plagiarism database search.
- Auto-check methodology/reporting standards (ARRIVE / CONSORT / ICMJE / MIFlowCyt / omics accessions are guided **manual** checklists).

> **The one rule to remember:** "no issue found" only means *nothing was flagged within the
> supplied materials and the current detector scope* — never that the work is proven correct.

---

## Who is this for

| You are… | Start here |
| --- | --- |
| An **author** running a pre-submission self-audit | [`docs/self-audit-guide.md`](docs/self-audit-guide.md) and the [Quick start](#quick-start) below |
| A **reviewer or integrity office** triaging concerns | [Quick start](#quick-start), then the external/response modes in [`docs/architecture.md`](docs/architecture.md) |
| A **developer or evaluator** | [How it works](#how-it-works) and [For developers and evaluators](#for-developers-and-evaluators) |

---

## Quick start

You need Python 3.10+ and the project dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run the audit on one of the bundled example packages and read the report it writes:

```bash
python3 scripts/audit_package.py examples/minimal_package --output-dir audit_outputs/minimal
python3 scripts/audit_package.py examples/full_presubmission_package --output-dir audit_outputs/full
```

Each run writes to the output directory:

- `audit-report.md` — the bilingual human-readable report (Quick Read, scope, coverage,
  materials needed, traceability evidence, finding cards, action checklist, technical appendix).
- `AUDIT_JSON_SUMMARY.json` — the same findings in machine-readable form.
- `coverage.json`, `calibrated_findings.json`, and per-detector outputs — supporting detail.
- `audit_snapshot.json` and `file_hash_manifest.json` — the exact package version reviewed, including SHA-256 hashes.
- `claim_coverage.json` / `claim_coverage.csv` — claim-to-evidence coverage when `claim_manifest.csv` is supplied.
- `submission_qc_packet/` — a leave-behind packet with the report, coverage, unresolved actions, verified traceability,
  missing materials, file hashes, claim coverage, and an author sign-off template.

To audit your own package, point the command at your folder and pick a mode
(`--mode internal_presubmission` is the default; `external_public_material` and
`response_to_concern` are also available):

```bash
python3 scripts/audit_package.py /path/to/my_package --output-dir audit_outputs/my_package
```

**Authors:** the [self-audit guide](docs/self-audit-guide.md) walks through how to lay out your
materials, run the audit, and read the report — including which conclusions you may not draw.

### Optional claim-to-evidence manifest

For a stronger pre-submission review, add `claim_manifest.csv` at the package root (or pass
`--claim-manifest /path/to/claim_manifest.csv`). Each row links a manuscript claim to source data,
raw records, analysis code, and protocol records:

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

The report then includes **Claim Coverage / 声明-证据覆盖** counts. This is a completeness view,
not a claim that the scientific conclusion is true.

### Re-audit diff

After fixing gaps, compare two audit outputs:

```bash
python3 scripts/compare_audit_runs.py audit_outputs/v1 audit_outputs/v2 \
  --output audit_outputs/v2/re_audit_diff.json \
  --csv audit_outputs/v2/re_audit_diff.csv
```

You can also pass `--compare-to audit_outputs/v1` to `scripts/audit_package.py` when running v2.
The diff reports changes in risk counts, missing materials, verified traceability, unresolved
actions, and claim-evidence gaps. It is not a pass/fail decision.

### Local web app (V0.5)

If you prefer a browser UI, build and launch the local self-audit app:

```bash
cd webapp/frontend && npm install && npm run build && cd ../..
python3 -m webapp
```

Then open `http://127.0.0.1:8765`. The web app is a thin local wrapper around
`scripts/audit_package.py`: it runs the same pipeline, reads the same artifacts, and keeps Audit
Coverage visible so "no findings" is not mistaken for a clean verdict. It also includes local
package-prep tools for creating the recommended folder layout and writing
`figure_assembly/assembly_manifest.csv` declarations before you run the audit. See
[`webapp/README.md`](webapp/README.md).

### Install the skill (optional)

To use it as a Codex skill, symlink it into your skills directory:

```bash
mkdir -p ~/.codex/skills
ln -s "$(pwd)/skill/biomed-research-integrity-auditor" ~/.codex/skills/biomed-research-integrity-auditor
```

---

## The R0–R4 risk scale

The tool never says "fraud" or "misconduct." It grades each finding on a five-level scale, and
even the highest level is not a verdict.

| Level | Meaning | Typical action |
| --- | --- | --- |
| `R0` | No issue found in the supplied materials (within scope) | State scope and what is missing |
| `R1` | Completeness or documentation gap | Add the raw/source records and re-run |
| `R2` | Reviewable reporting concern or weak statistical pattern | Fix the method/legend/supplement |
| `R3` | Material concern needing source data or author clarification | Provide raw records and explain |
| `R4` | Direct contradiction inside the supplied materials | Pause and reconcile before submitting |

Two guardrails keep the scale honest: public-material-only review is capped below `R4` unless a
direct internal contradiction exists, and weak statistical patterns alone cannot reach the
higher levels.

---

## How it works

The pipeline separates *finding candidates* from *deciding risk*, so no single component can
inflate a result:

```text
material intake → structured extraction → provenance graph → detectors
→ contextual join → risk calibration → evidence ledger → bilingual human report
```

- **Detectors** emit candidates with evidence and locations only — never a final risk level.
- **Provenance builders** model files and the figure-to-raw relationships you declare.
- **Context joiners** add disclosure, source-availability, and provenance context.
- **The calibrator** is the only component that assigns `calibrated_risk_level`, applying source
  strength, completeness, disclosure, benign explanations, and mode-specific caps.
- **The reporter** renders calibrated findings in neutral bilingual language, keeps the main
  Markdown body readable, and rejects uncalibrated input.

`scripts/audit_package.py` is the default orchestrator that runs this whole flow. See
[`docs/architecture.md`](docs/architecture.md) for the full design.

---

## What makes the results trustworthy

These are the design choices that keep the audit restrained, auditable, and harder to overstate:

- **Separation of duties.** Detectors only suggest; the calibrator decides. Legacy hand-written
  findings are rejected — every finding must come from a validated detector candidate.
- **Provenance-aware calibration.** A figure that matches its declared raw is reported as
  *positive traceability evidence*. But an author-written manifest line cannot bury a real
  duplicate: if two panels are declared "same field / same membrane" yet are detected as a
  whole-image near-duplicate, the pipeline reports a `manifest_conflict` requiring raw records.
- **No silent "clean."** Every report and `AUDIT_JSON_SUMMARY` carries an `audit_coverage` block
  listing which modules ran, which did not, how many image panels were screened, and how many
  image files were unreadable. An empty finding list within scope is never presented as a
  verified-correct manuscript.
- **Fail-closed contracts.** Detector, calibrated-finding, and summary outputs are schema-validated.
  If `jsonschema` is unavailable the pipeline stops rather than silently degrading. A package with
  no runnable detector yields an explicit `audit_coverage_gap` (R1), and a detector that crashes
  yields a `detector_execution_failure` (R1) while preserving the other modules' output.
- **Risk caps that match the evidence.** Weak statistical/forensic patterns cap at R2;
  completeness gaps at R1; public-material-only triage at R3; `R4` requires a tagged direct
  contradiction.

---

## Repository layout

| Path | Purpose |
| --- | --- |
| `skill/biomed-research-integrity-auditor/` | The installable Codex skill (instructions, templates, references, helper scripts). |
| `scripts/audit_package.py` | The default contract-first orchestrator for a package audit. |
| `scripts/submission_qc.py`, `scripts/compare_audit_runs.py` | Submission QC packet helpers and re-audit diff. |
| `detectors/` | Candidate detectors (image, statistics, text) that emit evidence, not verdicts. |
| `calibrators/` | Risk-cap and evidence-strength calibration, plus contract validation. |
| `provenance/` | Resource-graph builders that separate expected traceability from reuse risk. |
| `schemas/` | JSON/YAML contracts for detector output, risk rules, and source-data expectations. |
| `examples/` | Runnable example packages (`minimal_package/`, `full_presubmission_package/`). |
| `docs/self-audit-guide.md` | Non-developer guide to preparing materials and reading the report. |
| `docs/architecture.md`, `docs/design-notes.md` | Pipeline architecture and design rationale. |
| `evals/` | Neutral synthetic packages, the eval harness, and ground truth. |
| `benchmarks/` | True-PDF, scanned-PDF OCR, real-image regression benchmarks, and the PPPR public-concern benchmark scaffold. |
| `webapp/` | Local FastAPI + React/Vite self-audit UI that wraps the existing CLI artifacts. |

---

## For developers and evaluators

### Run the audit on a synthetic case

```bash
python3 scripts/audit_package.py evals/cases/case_004 --output-dir audit_outputs/case_004
```

### Non-LLM detector baseline

This delegates to the orchestrator and isolates detector/calibration behavior from any LLM:

```bash
python3 evals/run_script_baseline.py --case case_004
```

After baseline audit outputs have been generated, check them against `evals/ground_truth/`:

```bash
python3 evals/assert_audit_outputs.py --outputs-root audit_outputs
```

### Blind evaluation harness

Generate prompts, run them against an agent that has the skill and a single `cases/case_XXX`
package, save each report to `evals/outputs/case_XXX.md` (ending in one `AUDIT_JSON_SUMMARY`
block), then score:

```bash
python3 evals/run_eval.py generate-prompts
python3 evals/run_eval.py score          # scorecards land in evals/scorecards/
```

The harness rewards **restraint** as much as recall: a model fails by over-claiming, ignoring
benign explanations, exceeding risk caps, or using verdict language — not just by missing a risk.

### Public-concern benchmark

`benchmarks/pppr_integrity_benchmark/` contains a post-publication public concern benchmark scaffold
plus a tiny real public-data smoke runner. PubPeer is discovery metadata, Crossref/Retraction Watch
is publication-status metadata, PMC Open Access is a permitted article-material source, and ORI
samples are small image unit cases.

It is intentionally **not** a PubPeer scraper and does not store PubPeer comments or non-OA article
files. Start with:

```bash
python3 benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py --output-root tmp/pppr_public_smoke
python3 benchmarks/pppr_integrity_benchmark/scripts/build_rwdb_index.py --help
python3 benchmarks/pppr_integrity_benchmark/scripts/evaluate_audit_outputs.py --help
```

The current public smoke baseline is archived at
[`benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json`](benchmarks/pppr_integrity_benchmark/results/public_smoke_2026-06-30.json):
2 public cases ran, risk-cap and boundary-language violations were 0, 13 ORI public images were
screened, and 2/2 detector-scope ORI recall labels were hit (`finding_level_recall: 1.0`). ORI
same-section overlap and low-contrast copy-move samples are retained as `scope_gap` labels for
future detector work, not as clean/no-concern conclusions.

Read [`docs/benchmarking_with_pubpeer_and_rwdb.md`](docs/benchmarking_with_pubpeer_and_rwdb.md)
and [`docs/data_ethics_and_legal_boundaries.md`](docs/data_ethics_and_legal_boundaries.md) before
building any real cases.

**Blind-testing note:** the tested agent must receive only the case package path, never
`ground_truth/`, `outputs/`, `scorecards/`, or `prompts/`. For stricter evaluation, copy the case
into an isolated workspace and keep the answer key outside it.

### Archived eval run

A persisted run is kept at
[`evals/llm_runs/2026-06-30-codex-orchestrated/`](evals/llm_runs/2026-06-30-codex-orchestrated/):
30/30 synthetic cases passed with 0 boundary violations and 0 risk-cap violations. This shows the
harness was executed and retained — it is **not** an independent, third-party, blinded LLM
validation, and it does not measure performance on real manuscripts.

### Benchmarks

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py        # compressed machine-text PDF extraction
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py  # image-only PDF OCR (needs tesseract/PyMuPDF/pytesseract)
python3 benchmarks/real_image/run_real_image_benchmark.py    # real public-domain microscopy + 16-bit TIFF
```

`make validate` skips the scanned-PDF benchmark when the OCR runtime is missing; CI installs
`tesseract-ocr` and runs it as a required gate.

### External literature phrase search

Off by default for private audits. Run it explicitly, or let the orchestrator decide:

```bash
python3 detectors/text/external_literature_search.py <package_dir> --provider europepmc --output external_literature_candidates.json
```

The orchestrator's `--external-literature-provider auto|none|fixture|europepmc|crossref` uses a
package fixture when present, queries Europe PMC in `external_public_material` mode, and stays
offline for private internal audits unless you request a provider. Results are candidates for
manual review, never a plagiarism database or verdict.

### Regenerate synthetic cases

The cases are committed; regenerate them deterministically with:

```bash
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

---

## Limitations

- Image, local-patch, and same-image copy-move detection are single-package only; they do not
  search across papers or external image corpora.
- Text-overlap screening is package-internal; the optional external phrase search is triage, not
  exhaustive plagiarism-database coverage or a verdict.
- True-PDF intake handles machine-readable text and OCR-capable scanned PDFs; figure/caption
  extraction is limited.
- Image intake normalizes high-bit-depth grayscale TIFFs, but broad validation on
  multi-frame/Z-stack/channel microscopy remains future work.
- Statistical screening covers p-value range/validity, SD/SEM/n consistency, integer-count
  feasibility, and weak forensic patterns. Weak digit/rounding screens need at least 8 comparable
  values, and integer-count feasibility needs n ≥ 6 while respecting reported precision. It does
  **not** implement Benford-style first-digit analysis or p-value clustering/distribution tests —
  those remain manual checks.
- Public-material review is capped by missing source/raw records and must never be read as a
  misconduct verdict.

---

## License

MIT. See [`LICENSE`](LICENSE).
