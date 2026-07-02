# 2026-06-30 Archived Synthetic Eval Scorecard

This archived run records a 30-case synthetic package scorecard generated with the default package-audit orchestrator, then scored with `evals/run_eval.py`.

Result:

- Total cases: 30
- Passed: 30
- Failed: 0
- Boundary violations: 0
- Risk cap violations: 0

How to reproduce the scorecard locally:

```bash
python3 scripts/audit_package.py evals/cases/case_XXX --mode <mode-from-ground-truth> --output-dir tmp/eval_work/case_XXX --case-id case_XXX
mkdir -p tmp/eval_reports
cp tmp/eval_work/case_XXX/audit-report.md tmp/eval_reports/case_XXX.md
python3 evals/run_eval.py score --outputs-dir tmp/eval_reports --scorecards-dir evals/llm_runs/2026-06-30-codex-orchestrated/scorecards
```

Limitations:

- This is not an independently blinded external LLM run.
- Reports were produced through the default deterministic audit orchestrator.
- Per-case generated reports are not committed because local audit reports can contain machine-specific paths.
- The archive demonstrates current harness/orchestrator behavior and boundary compliance; it does not validate performance on real-world manuscripts.
