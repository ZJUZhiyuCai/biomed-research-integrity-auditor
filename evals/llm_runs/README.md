# Archived Skill-Eval Runs

This directory stores reproducible scorecards and report outputs from agent-orchestrated skill evaluations.

These archives are not hidden answer keys and are not inputs to a tested agent. They are retained as evidence that a specific run was executed and scored. Each run directory should include:

- `run_manifest.json` describing the agent, commands, case count, and limitations.
- `outputs/case_XXX.md` reports produced during the run.
- `scorecards/scorecard.csv` and `scorecards/summary.md` from `evals/run_eval.py score`.

Important boundary: a Codex-orchestrated run is evidence of current skill/orchestrator behavior, not an independent third-party blinded LLM validation.
