# BRIA-Bench

BRIA-Bench is an offline benchmark harness for the local biomedical research integrity auditor. It freezes fixture package hashes, runs an adapter under monitored process control, evaluates normalized observations against sealed annotations, and renders technical metrics reports.

## Current Public Corpus

The public registry currently contains 36 redistributable fixtures:

- 30 repository-authored synthetic legacy cases on the `regression` track and `reference` split.
- 4 first-party controlled development fixtures on the `blinded_challenge` track and `dev` split.
- 2 first-party controlled robustness fixtures on the `robustness_scale` track and `dev` split.

There is no public `test` split, no completed independent blinded result, and zero headline-eligible cases. The five-track contract supports `regression`, `blinded_challenge`, `public_realism`, `public_concern`, and `robustness_scale`, but only regression, controlled development/blinded-challenge, and robustness data are currently populated.

The 30 synthetic legacy cases are regression, reliability, and performance fixtures only. They are not real-manuscript validation. The 6 dev fixtures are controlled workflow cases for detector and pipeline behavior. They are also not real-manuscript validation.

Detection denominators are deliberately zero for the current public corpus. Metrics may still report reliability, runtime, output preservation, and regression-contract behavior, but detection metrics are not headline accuracy claims.

## Install

```bash
python -m pip install -e '.[benchmark]'
```

The benchmark extra installs `psutil`, which is required for process monitoring. Missing `psutil` is an environment failure and must never be interpreted as a scientific finding.

## Offline Smoke

```bash
make benchmark-smoke
```

The smoke target runs all dev cases with the `full` adapter, applies a 60 second timeout per case, and writes only under `tmp/bria_bench_smoke`. It passes the same `--split dev` selection to both `run` and `evaluate`, then renders the evaluated metrics as a report.

Equivalent direct commands:

```bash
python -m benchmarks.bria_bench.cli run \
  --manifest benchmarks/bria_bench/benchmark_manifest.json \
  --runs-dir tmp/bria_bench_smoke \
  --split dev \
  --adapter full \
  --timeout-seconds 60

python -m benchmarks.bria_bench.cli evaluate \
  --manifest benchmarks/bria_bench/benchmark_manifest.json \
  --runs-dir tmp/bria_bench_smoke \
  --split dev \
  --output tmp/bria_bench_smoke/metrics.json

python -m benchmarks.bria_bench.cli report \
  --metrics tmp/bria_bench_smoke/metrics.json \
  --output tmp/bria_bench_smoke/REPORT.md
```

Run artifacts and `run_summary.json` record technical execution, `metrics.json` is the machine-readable evaluation, and `REPORT.md` is the rendered technical metrics report. All of these smoke outputs remain under `tmp/bria_bench_smoke`.

## Manual Full Run

The full 36-case run is manual because it is slower and environment-sensitive:

```bash
make benchmark
make benchmark-report
```

Both targets use `tmp/bria_bench_runs` and do not pass split or case filters.

## Reviewer Packets

Reviewer packets are currently `workflow_demo_only`. Public package hashes and reviewer-packet hashes are join keys to the public fixture tree, not sealed blinded identifiers. Use the packet flow to test mechanics and reviewer forms, not to claim independent evaluation.

Generated runs, reviewer packets, mapping files, API caches, local metrics, seeds, and identity artifacts are local/private outputs. They should remain ignored and outside source, wheel, and release archives unless an explicitly named release summary is intentionally added.
