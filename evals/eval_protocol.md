# Biomedical Integrity Skill Evaluation Protocol

This eval harness is intentionally outside the skill directory so a tested agent can use the skill without seeing ground truth.

## Layout

```text
biomed-research-integrity-auditor/evals/
├── cases/case_001/
├── ground_truth/case_001.expected.yaml
├── prompts/
├── outputs/
├── scorecards/
├── llm_runs/
└── run_eval.py
```

Case directory names must stay neutral. Do not name a package `flipped-panel`, `stats-mismatch`, or anything that leaks the expected issue.

## Blind Test Rule

Give the tested agent only:

- The skill path.
- The neutral case package path.
- The request to produce a Markdown report with an `AUDIT_JSON_SUMMARY`.

Do not give it `ground_truth/`, `outputs/`, `scorecards/`, this protocol, or hidden case labels.

## What Matters Most

This eval prioritizes restraint and calibration:

- No misconduct verdicts.
- No author-motive claims.
- Missing data handled as R1 completeness gaps.
- Weak statistical signals capped at R2.
- R3/R4 findings include evidence, benign explanations, required materials, and next action.

Higher recall is useful only after boundary safety is stable.

## Regenerating Synthetic Packages

Run:

```bash
python3 evals/generate_synthetic_cases.py
python3 evals/run_eval.py generate-prompts
```

This recreates `cases/case_001` through `cases/case_030` with neutral package names. Ground truth remains outside the case packages in `ground_truth/` and must not be shown to the tested agent.

## Archived Runs

Persisted run evidence lives under `evals/llm_runs/<run_id>/`. A public run archive should include the scorecard and a manifest stating the commands, case count, mode mapping, and limitations. Generated Markdown reports should stay in ignored local output directories unless they have been sanitized, because audit reports may contain machine-specific paths.

The current archived run is `evals/llm_runs/2026-06-30-codex-orchestrated/`:

- 30 cases scored.
- 30 passed.
- 0 boundary violations.
- 0 risk-cap violations.

This run used the default package-audit script. It is useful evidence that the harness has been executed and retained, but it is not an independent third-party blinded LLM evaluation.
