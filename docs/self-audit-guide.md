# Self-Audit Guide

A practical, non-developer guide to running a pre-submission research-integrity self-audit
on your own manuscript package.

This tool helps you **organize evidence and surface risks** before submission. It does
**not** decide misconduct, and it does **not** prove a paper is correct. Read the
[boundary](#what-this-tool-is-and-is-not) section first.

---

## The one rule to remember

> **"No issue found" is not the same as "proven correct".**

The auditor only checks what you give it, with a limited set of automated detectors. A clean
report means *nothing was flagged within the supplied materials and the current detector
scope*. It never means the study is verified or the figures are guaranteed authentic. Every
report includes an **Audit Coverage** section that states exactly what was and was not
checked. Always read it.

---

## What this tool is and is not

**It is:**

- A pre-submission checklist and evidence organizer.
- An automated screen for: image near-duplicates and same-image copy-move, figure-to-raw
  traceability, numeric/statistical consistency in summary tables, and package-internal text
  overlap.
- A neutral report generator using an `R0`-`R4` risk scale.

**It is not:**

- A misconduct, fraud, fabrication, or plagiarism detector or verdict.
- A web-scale plagiarism database search.
- An automated methodology-compliance decision. ARRIVE / CONSORT / ICMJE / MIFlowCyt / omics
  accession review is organized as a structured manual-readiness checklist.
- A replacement for human review by you, your co-authors, or the journal.

If the report ever reads like an accusation, you are misreading it. Use neutral language such
as "integrity concern requiring explanation" and "materials are insufficient to resolve this".

---

## Step 1: Prepare your materials

Put your materials in one folder, using this layout. You do not need every folder; include
what you have. More complete packages can be checked more thoroughly.

```text
my_package/
├── manuscript.pdf              your manuscript (PDF or text)
├── supplementary/              supplementary files
├── figures/                    the figure panels as shown in the paper (PNG/JPG/TIFF)
├── raw_images/                 the original/uncropped acquisitions the figures came from
├── figure_assembly/
│   └── assembly_manifest.csv   declares which raw file each figure panel came from
├── source_data/                the numbers behind the figures (CSV / TSV / XLSX)
├── protocols/                  sample maps, methods notes, batch records
├── statistics_code/            analysis notes or scripts
└── claim_manifest.csv          optional: links each manuscript claim to evidence files
```

### The assembly manifest (strongly recommended)

If you provide `figure_assembly/assembly_manifest.csv`, the tool can confirm that each figure
panel matches the raw file you declare it came from, and report that as **positive
traceability evidence** instead of a possible reuse concern. Format:

```csv
figure_panel,source_record,relation_type,modality,notes
figures/Figure_1A.png,raw_images/acquisition_001.png,declared_derived_from,microscopy,exported from raw 001
```

A manifest line is a *claim*, not proof. The tool cross-checks it: a declared
"same field / same channel" relationship between two figure panels that are actually
whole-image duplicates is reported as a `manifest_conflict`, not cleared. So you cannot make a
real duplicate disappear by writing a manifest line.

### The claim manifest (recommended for submission QC)

If you provide `claim_manifest.csv`, the report includes **Claim Coverage**: how many manuscript
claims have links to source data, raw records, analysis code, and protocols. Format:

```csv
claim_id,claim_text,manuscript_location,figure_or_table,source_data,raw_record,analysis_code,protocol,owner,status
C001,"Treatment increases signal intensity",Results p.4,Fig1A,source_data/Fig1.csv,raw_images/acq_001.tif,statistics_code/fig1.ipynb,protocols/microscopy.md,first_author,ready
```

Claim coverage is only a completeness check. It does not say whether the claim is true.

---

## Step 2: Install and run

Use a Python 3.10+ interpreter, then install the project in editable mode so
the `biomed-audit` command is available:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Run the audit (internal pre-submission mode is the default):

```bash
biomed-audit /path/to/my_package --output-dir audit_outputs/my_package
```

If your `python3` already points to Python 3.10+, you can use `python3` instead
of `python3.11`. Source-checkout fallback:
`python scripts/audit_package.py /path/to/my_package --output-dir audit_outputs/my_package`.

Outputs land in `audit_outputs/my_package/`:

- `audit-report.md` — the bilingual human-readable report.
- `AUDIT_JSON_SUMMARY.json` — a machine-readable summary.
- `coverage.json`, `calibrated_findings.json`, and detector outputs — supporting detail.
- `audit_snapshot.json` / `file_hash_manifest.json` — file hashes for the exact package version reviewed.
- `claim_coverage.json` / `claim_coverage.csv` — claim-to-evidence coverage when `claim_manifest.csv` is supplied.
- `methodology_checklist.json` / `methodology_checklist.csv` — supporting-material readiness prompts for manual methodology review.
- `submission_qc_packet/` — a leave-behind packet with unresolved actions, verified traceability,
  missing materials, file hashes, claim coverage, methodology checklist, and an author sign-off template.

---

## Step 3: Try the bundled examples first

Two ready-made example packages let you see a real report in a few minutes. They are teaching
samples with synthetic images — not real data.

### Minimal example (fastest)

```bash
biomed-audit examples/minimal_package --output-dir audit_outputs/minimal
```

What to expect: overall risk **R1**, no findings, and a **Materials Needed / 需要补充的材料**
table (figures, raw images, protocols, etc.) because the package is intentionally tiny. The Audit Coverage
section shows that statistics and text screening ran, image screening was skipped (no images),
external search stayed offline, and methodology readiness is only a manual checklist. This is
the honest "small scope, can't conclude much" result.

### Full pre-submission example (realistic layout)

```bash
biomed-audit examples/full_presubmission_package --output-dir audit_outputs/full
```

What to expect: overall risk **R1**, **two positive-traceability links** (each figure panel
confirmed against its declared raw acquisition, shown under "Verified Traceability Evidence"),
two declared claims with source/raw/code/protocol coverage, no risk findings, and a short Materials Needed list. This is the honest "clean within scope,
with verified traceability, but not a complete audit" result.

> Regenerate the example images with `python3 examples/generate_example_assets.py` (optional;
> the images are already committed so the examples run as-is).

---

## Step 4: Read the report

The report is bilingual by default. Read the human Markdown sections first; use the final
`AUDIT_JSON_SUMMARY` block only when another tool needs machine-readable data.

| Section | What it tells you |
| --- | --- |
| **Quick Read / 快速结论** | The top-level risk, number of candidate findings, materials reviewed, missing categories, and the reminder that no findings is not proof of correctness. Start here. |
| **Scope / 范围** | The mode, case ID, and package root. |
| **Audit Coverage / 本次检查覆盖** | Which detector modules ran, which did not, image panels screened, unreadable image files, detector failures, and the scope note. Use this to know what was actually checked. |
| **Claim Coverage / 声明-证据覆盖** | Claim-to-evidence completeness when `claim_manifest.csv` is supplied. This is not claim correctness. |
| **Materials Needed / 需要补充的材料** | Expected material categories that were not found, each as a completeness gap. |
| **Verified Traceability Evidence / 已验证可追溯证据** | Figure-to-raw links the tool confirmed as positive provenance evidence. |
| **Risk Register / 风险登记** | One row per candidate finding with level, module, location, and type. |
| **Findings / Evidence Ledger / 发现项与证据台账** | Human-readable finding cards: observation, why it matters, evidence summary, benign explanations, materials needed, and recommended action. |
| **Action Checklist / 下一步清单** | The practical follow-up list, sorted by risk and missing materials. |
| **Technical Appendix / 技术附录** | Compact technical details plus pointers to `calibrated_findings.json` and detector outputs. |
| **Audit JSON Summary / 机器可读摘要** | The same audit summary in one machine-readable fenced JSON block. |

### The R0-R4 risk scale, in plain language

| Level | Meaning | What to do |
| --- | --- | --- |
| **R0** | No issue found in the supplied materials (within scope). | State scope and what is missing. Not a clean bill of health. |
| **R1** | Completeness gap — something needed to check the claim is missing. | Add the raw/source records and re-run. |
| **R2** | Minor reporting concern, or a weak statistical signal. | Fix the method/legend/supplement; document. |
| **R3** | Integrity concern that needs explanation; benign explanations exist. | Provide raw records and clarify before submission. |
| **R4** | Direct conflict inside the supplied materials. | Pause and resolve internally before submitting. |

Even **R4 is not a misconduct verdict.** It means two supplied things directly contradict each
other and must be reconciled.

---

## Step 5: What you may and may not conclude

**You may:**

- Use the report to find missing materials, fix reporting, and add raw/source records.
- Treat R3/R4 as "must explain or correct before submission".
- Quote the neutral findings to your co-authors as quality-control items.

**You may not:**

- Conclude that anyone committed misconduct, fraud, fabrication, or plagiarism.
- Treat a clean (R0/R1) report as proof the study is correct or the figures are authentic.
- Treat a missing-material gap as evidence of wrongdoing.
- Use the report publicly as an accusation.

For raising a question with a co-author, use neutral phrasing, for example: "Could we add the
uncropped blot and sample map so the relationship between this panel and its raw record is
documented?"

---

## Frequently confusing results

**"It says `figure assembly` is missing, but I included `assembly_manifest.csv`."**
The Materials Needed row named *figure assembly* refers to assembly/design project files
(PowerPoint, Photoshop, Illustrator, etc.). Your structured CSV/YAML manifest is still read and
used by the tool — look at the **Verified Traceability Evidence** section, which lists the
figure-to-raw links it confirmed from your manifest. This is exactly why you should read the
whole report, not just the Materials Needed list.

**"Overall risk is R1 but there are no findings."**
R1 here comes from missing materials, not from a detected problem. Add the missing records and
re-run to narrow the scope of what is unchecked.

**"My 16-bit TIFF / multi-channel images didn't all get screened."**
Image support is improving but limited. Check the Audit Coverage section for `image panels
screened` and `image files that could not be read`. Unreadable files are reported, never
silently dropped — but they are not screened.

**"It didn't catch an obvious problem."**
The automated detectors are a screen, not a guarantee. Coverage is intentionally honest about
this. Combine the tool with manual review of `methodology_checklist.json` / `.csv` and the
deeper reference notes in `skill/biomed-research-integrity-auditor/references/`.

---

## After the audit

1. Resolve every R4, and explain or correct every R3, before submission.
2. Add raw/source records for the R1 completeness gaps you can close.
3. Work through `methodology_checklist.csv`: "materials supplied" means ready for human review,
   not compliant. Add missing protocol, ethics, registration, FCS, accession, or analysis-code
   records where needed.
4. Keep `AUDIT_JSON_SUMMARY.json` with your submission records as a quality-control trail.

A complete self-audit is **automated screening + your manual review of raw/source records +
methodology checklist items** — not the tool alone.
