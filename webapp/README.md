# Local Self-Audit Web App

V0.5 is a local-first web wrapper around the existing audit pipeline. It does not replace
`scripts/audit_package.py`, and it does not reinterpret risk. The backend runs the CLI in a
background subprocess and the UI reads the artifacts the CLI writes.

## Run

Install the Python package with a Python 3.10+ interpreter, then build the frontend:

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

## V0.5 Scope

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
- Package prep tools: inspect a local package, create the recommended folder scaffold, and write
  `figure_assembly/assembly_manifest.csv` rows for declared figure-to-source relationships.
- Package-prep guardrails: bounded directory inventory, visible scan warnings, package-relative
  path checks, and relation/source-role validation before manifest rows are written.
- CLI-generated submission-QC artifacts are available in each audit output directory, including
  `audit_snapshot.json`, `claim_coverage.*`, `unresolved_actions.csv`, and `submission_qc_packet/`.
- The report view surfaces claim coverage, unresolved action trackers, re-audit diffs, QC-packet
  download links, and a separate Writing & Submission Readiness panel.

Not included yet:

- Interactive editing of the correction-plan tracker inside the browser.
- Full citation-integrity/retraction-database coverage beyond opt-in Crossref-style DOI metadata prompts.
- Grammar/language checking engines.
- A signed desktop application.

Those remain P1/P2 features in [`docs/webapp-plan.md`](../docs/webapp-plan.md).

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
