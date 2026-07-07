# Local Self-Audit Web App

V0.6.2 is a local-first web wrapper around the existing audit pipeline. It does not replace
`scripts/audit_package.py`, and it does not reinterpret risk. The backend runs the CLI in a
background subprocess and the UI reads the artifacts the CLI writes.

## Run

From a source checkout, the shortest path is:

```bash
make run
```

This creates or reuses `.venv`, installs Python dependencies and the editable package, builds the
React frontend when `npm` is available, starts the local app on `127.0.0.1:8765`, and opens your
browser. If a local server is already running on that port, it opens the existing app.

Manual setup remains available for development or troubleshooting:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
cd webapp/frontend
npm install
npm run build
cd ../..
```

Start the local app:

```bash
biomed-audit-web
```

Open `http://127.0.0.1:8765`. The app stores local run artifacts under
`audit_outputs/webapp/`.

If your `python3` already points to Python 3.10+, you can use `python3` instead
of `python3.11`. Source-checkout fallback: `python -m webapp`.

For frontend development, run the API and Vite separately:

```bash
biomed-audit-web --no-browser
cd webapp/frontend
npm run dev
```

## V0.6.2 Scope

Included:

- Local FastAPI backend bound to `127.0.0.1`.
- Background jobs that invoke `scripts/audit_package.py`.
- JSON API for audit status, `AUDIT_JSON_SUMMARY.json`, `coverage.json`,
  `calibrated_findings.json`, `pipeline_summary.json`, Markdown reports, submission-QC artifact
  paths, and evidence crops.
- Path traversal protection for evidence serving and guarded zip-package extraction.
- React/Vite report viewer with audit coverage, R0-R4 register, positive provenance evidence,
  missing materials, evidence images, local history, delete, and Chinese/English labels.
- Scan-profile selection (`quick`, `standard`, `deep`) wired through to the CLI. Quick runs are
  explicitly marked as narrower-scope runs when expensive deep image screening is skipped.
- Local audit jobs invoke the CLI with `--execution-mode parallel`, so independent intake and
  detector workstreams run concurrently while calibration and report assembly stay serialized.
- Package prep tools: inspect a local package, create the recommended folder scaffold, and write
  `figure_assembly/assembly_manifest.csv` rows for declared figure-to-source relationships.
- Claim-manifest prep tools: write package-root `claim_manifest.csv` rows that link manuscript
  claims to source data, raw records, analysis code, and protocols. These rows support claim
  coverage only and do not prove that claims are true.
- Filename-based starter suggestions for package-prep manifests. These suggestions reduce typing
  for likely figure/source links and claim drafts, including simple zero-padding and separator
  differences such as `Fig 02-A` versus `F2A`, but they are not saved automatically and remain
  declarations requiring audit cross-checks when saved. When filename matching finds multiple
  equally plausible records, the app shows a material-prep warning and does not draft a row.
- PPTX slide text, speaker notes, and shape alt text with explicit figure/source paths are surfaced
  in Package Prep and may seed editable `assembly_manifest.csv` and claim drafts through the same
  structure intake that writes `pptx_structure.json`; they remain declaration aids, not verified
  provenance.
- Prism PZFX graph/table hints are surfaced in Package Prep and may seed editable graph-to-source
  drafts; they remain manifest-preparation hints, not verified provenance.
- Machine-readable PDF captions are surfaced in Package Prep and may seed editable claim drafts
  with figure/table labels and page locations; they do not create source/raw links by themselves.
- DOCX caption-styled figure/table text and Word table-like blocks are surfaced in Package Prep
  through the same structure intake that writes `docx_structure.json`, and may seed editable
  claim drafts; they do not create source/raw links by themselves. If a DOCX contains comments,
  tracked revisions, or embedded objects/media, Package Prep shows a warning because those layers
  are not read as body/caption/table evidence.
- XLSX workbook sheet/header metadata is surfaced in Package Prep through the same structure
  intake that writes `xlsx_structure.json`; figure/table-like sheet labels may seed editable
  claim drafts. This is material-prep metadata, not statistical validation or verified provenance.
- Package-prep guardrails: bounded directory inventory, visible scan warnings, package-relative
  path checks, relation/source-role validation, and CSV formula-injection escaping before manifest
  rows are written.
- CLI-generated submission-QC artifacts are available in each audit output directory, including
  `audit_snapshot.json`, `claim_coverage.*`, `unresolved_actions.csv`, and `submission_qc_packet/`.
- The report view surfaces claim coverage, unresolved action trackers, re-audit diffs, QC-packet
  download links, correction-plan trackers, external image-review handoff rows, and a separate
  Writing & Submission Readiness panel.
- Re-audit diff cards show fixed/new/persisted findings plus resolved, newly missing, and still
  missing materials; these are remediation-tracking views, not pass/fail status.
- Action tracker rows can be edited locally with owner, status, note, accepted-reason, and
  attachment fields. Users can type a local follow-up pointer or upload a file into that audit's
  `submission_qc_packet/attachments/` folder; the tracker stores the packet-relative reference and
  mirrors it in correction-plan exports. Attachments are team follow-up material, not external
  verification or pass/fail signals.
- Each action row surfaces copy-ready neutral inquiry and material-request templates when the
  CLI generated them, so teams can ask for clarification or source records without changing the
  calibrated audit result.
- Image-review handoff rows are linked to action-tracker rows when `source_finding_id` is available,
  so teams can see the current owner/status/attachment reference next to the external-review route.
- Image-review tracker rows can be edited locally with reviewer, review status, tool/method,
  result note, and attachment reference or upload. The update is written back to the QC packet CSVs;
  it is still a team follow-up record, not external validation by itself.

Not included yet:

- Inline editing/persistence of correction-plan rows inside the browser.
- Full citation-integrity/retraction-database coverage beyond opt-in Crossref-style DOI metadata prompts.
- Grammar/language checking engines.
- A signed desktop application.

Those remain future product features rather than current webapp behavior.

## Integrity Boundary

The UI must preserve the same boundary as the CLI:

- no misconduct/fraud/verdict language;
- no PASS/FAIL or score;
- no merged writing-quality score;
- always show audit coverage and missing scope;
- render positive provenance as evidence to inspect, not as proof that the manuscript is correct;
- treat assembly-manifest rows as declarations that the pipeline still cross-checks against
  supplied images, source data, and raw records.

## Package Prep Notes

The package-prep inventory is intentionally bounded. If a path contains more than the local file
limit or deeply nested folders, the API returns `inventory_warnings` and asks you to choose a
narrower package directory. This is a coverage warning for preparation, not an integrity finding.

Manifest relation types are constrained before writing:

- `declared_derived_from` may point to `raw_images/` or `source_data/`.
- `same_field_different_channel` may point to another `figures/` panel or a `raw_images/` file.
- `same_membrane_reprobe` may point to another `figures/` panel or a `raw_images/` file.
