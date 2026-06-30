# Local Self-Audit Web App

V0.5 is a local-first web wrapper around the existing audit pipeline. It does not replace
`scripts/audit_package.py`, and it does not reinterpret risk. The backend runs the CLI in a
background subprocess and the UI reads the artifacts the CLI writes.

## Run

Install Python and frontend dependencies:

```bash
python3 -m pip install -r requirements.txt
cd webapp/frontend
npm install
npm run build
cd ../..
```

Start the local app:

```bash
python3 -m webapp
```

Open `http://127.0.0.1:8765`. The app stores local run artifacts under
`audit_outputs/webapp/`.

For frontend development, run the API and Vite separately:

```bash
python3 -m webapp --no-browser
cd webapp/frontend
npm run dev
```

## V0.5 Scope

Included:

- Local FastAPI backend bound to `127.0.0.1`.
- Background jobs that invoke `scripts/audit_package.py`.
- JSON API for audit status, `AUDIT_JSON_SUMMARY.json`, `coverage.json`,
  `calibrated_findings.json`, `pipeline_summary.json`, Markdown reports, and evidence crops.
- Path traversal protection for evidence serving and guarded zip-package extraction.
- React/Vite report viewer with audit coverage, R0-R4 register, positive provenance evidence,
  missing materials, evidence images, local history, delete, and Chinese/English labels.
- Package prep tools: inspect a local package, create the recommended folder scaffold, and write
  `figure_assembly/assembly_manifest.csv` rows for declared figure-to-source relationships.

Not included yet:

- Writing/submission-readiness module.
- PDF export.
- Network reference/DOI/retraction checks.
- Desktop packaging.

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
