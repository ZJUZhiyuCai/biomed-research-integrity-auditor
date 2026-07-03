# Contributing

Thank you for helping improve Biomed Research Integrity Auditor. This project is a research-quality-control tool, not a misconduct detector, so contributions must preserve the integrity boundary as well as the code.

Please also follow `CODE_OF_CONDUCT.md` in issues, pull requests, reviews, and project discussions.

## Project Boundary

- Do not add language that concludes misconduct, fraud, fabrication, falsification, plagiarism, intent, or author guilt.
- Detector outputs must remain candidates. Final risk labels must come from calibration.
- Missing materials, detector failures, unsupported formats, and runtime limits are audit-coverage gaps, not evidence against authors.
- Reports should stay human-first, bilingual when user-facing, and neutral in tone.

## Development Setup

Requires Python 3.10+ and Node.js 20.19+ or 22.12+ for the local web UI.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e ".[webapp,ocr,dev]"
npm --prefix webapp/frontend ci
pre-commit install
make preflight PYTHON=.venv/bin/python
```

Before opening a PR, run `pre-commit run --all-files` and `PYTHON=.venv/bin/python make validate`.

Scanned-PDF OCR needs the `tesseract` binary on `PATH`. If it is unavailable, OCR coverage should be reported as unavailable rather than silently treated as screened.

## Validation

Run the same gate expected in CI:

```bash
PYTHON=.venv/bin/python make validate
```

For frontend-only changes:

```bash
npm --prefix webapp/frontend run build
```

Before committing, remove local run outputs and caches:

```bash
rm -rf tmp webapp/frontend/dist audit_outputs
find evals/prompts -type f ! -name '.gitkeep' -delete
find . -path './.venv' -prune -o -path './webapp/frontend/node_modules' -prune -o -name '__pycache__' -type d -exec rm -rf {} +
```

`audit_outputs/`, generated eval prompts, frontend `dist/`, virtual environments, and local caches must not be committed.

## Pull Requests

- Keep changes scoped to one concern.
- Include tests for detector, calibration, reporting, webapp, or packaging changes as appropriate.
- Update README/docs/skill instructions when user-visible behavior changes.
- Mention the validation command you ran in the PR description.
- For new detectors, document evidence strength, risk caps, benign explanations, runtime limits, and coverage-gap behavior.
- Do not include private manuscripts, raw data, institution names, user paths, or real audit outputs in fixtures or screenshots.

## Commit Messages

Use concise imperative messages, for example:

```text
Add manifest warning coverage
Harden webapp upload path checks
Document quick scan scope limits
```

## Reporting Problems

Use GitHub issues for ordinary bugs and feature requests. For security-sensitive issues, follow `SECURITY.md` and do not disclose exploit details or private research materials publicly.
