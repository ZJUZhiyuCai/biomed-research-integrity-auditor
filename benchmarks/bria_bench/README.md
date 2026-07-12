# BRIA-Bench

BRIA-Bench is a local, offline-by-default benchmark harness for the biomedical research integrity auditor. It freezes fixture package hashes, runs an adapter under monitored process control, evaluates normalized observations against sealed annotations, and renders technical metrics reports. External LLM baselines are separately gated, explicit opt-in runs.

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

## Freeze And Reproduce The Registry

The committed manifest uses a fixed freeze timestamp so package and annotation hashes can be regenerated deterministically:

```bash
make benchmark-freeze
git diff --exit-code -- benchmarks/bria_bench/benchmark_manifest.json
```

For a deliberately new benchmark release, supply its recorded UTC timestamp explicitly:

```bash
make benchmark-freeze BENCHMARK_FROZEN_AT=2026-07-11T00:00:00Z
```

Review and commit any resulting manifest change. Do not change the timestamp merely to refresh a file; it is part of the frozen benchmark identity. The smoke and full-run commands below reproduce execution from that committed manifest.

## Offline Smoke

```bash
make benchmark-smoke
```

The smoke target removes any previous `tmp/bria_bench_smoke` directory so every invocation executes fresh, then runs all dev cases with the `full` adapter and a 60 second timeout per case. It passes the same `--split dev` selection to both `run` and `evaluate`, writes only under that directory, and renders the evaluated metrics as a report.

Equivalent direct commands:

```bash
rm -rf tmp/bria_bench_smoke
mkdir -p tmp/bria_bench_smoke

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

## Direct LLM Baseline

The direct-LLM baseline uses a provider-neutral OpenAI-compatible producer and the same normalized-observation matcher as the full pipeline. CI remains offline:

```bash
make benchmark-llm-smoke
```

This target uses committed synthetic response fixtures locked to the current system/user prompt hashes and the canonical full request hash. Fixture token counts exercise telemetry plumbing, but fixture latency and cost are zero and are not DeepSeek API measurements. Synthetic fixture identity is visible in artifacts and reports and is hard-blocked from headline eligibility.

Descriptive registry case IDs remain runner metadata and cache identity only; they are not included in the model prompt, so names such as `stats_shift` or `global_flip` cannot leak the expected condition to the baseline.

The configured live baseline is DeepSeek `deepseek-v4-flash` in non-thinking JSON mode at temperature 0, with three separately identified repeats. DeepSeek V4 is text-only: the adapter extracts machine-readable text and records image pixels, embedded PDF/Office visual layers, image-only PDFs, and unsupported binary inputs as coverage gaps. Model-reported coverage gaps also enter the common observation/matching path as R1 limitations. It does not feed outputs from this project's image detectors to the LLM.

API settings were checked on 2026-07-12 against DeepSeek's official [OpenAI-compatible quick start](https://api-docs.deepseek.com/), [JSON output guide](https://api-docs.deepseek.com/guides/json_mode/), and [model/pricing table](https://api-docs.deepseek.com/quick_start/pricing/). Review those pages again before publishing cost comparisons because model aliases and prices can change.

Live runs send package-derived text to an external API and are therefore manual, explicit opt-in only:

```bash
export DEEPSEEK_API_KEY='set-this-in-your-shell-or-secret-manager'
export BRIA_BENCH_ALLOW_REMOTE_LLM=1
make benchmark-deepseek
```

Do not paste the key into a command, issue, log, fixture, result, or Git file. Before extraction, the adapter creates a bounded no-symlink package snapshot and verifies it against the frozen package hash. Live requests do not follow HTTP redirects. API responses are cached under the user cache directory (or `BRIA_BENCH_LLM_CACHE_DIR`) using private directory/file permissions; cache paths may not overlap the repository, input package, or producer output. Cache identity includes the canonical full request hash plus case, provider, endpoint, and repeat index. The three outputs remain under `tmp/bria_bench_deepseek_r1` through `r3` and are excluded from releases.

The pricing snapshot encoded in the adapters is dated 2026-07-12 and must be reviewed before a formal run. No live result is currently committed, and the current dev fixtures remain ineligible for headline accuracy.

## Reviewer Packets

Reviewer packets are currently `workflow_demo_only`. Public package hashes and reviewer-packet hashes are join keys to the public fixture tree, not sealed blinded identifiers. Use the packet flow to test mechanics and reviewer forms, not to claim independent evaluation.

The repository now also contains a fail-closed `independent_blinded` workflow for a future private `test` split: two separately permuted packet exports, immutable completed-form locks, mapping-free reviewer comparison, raw agreement and categorical kappa, disagreement-only adjudication, and final annotation generation. It refuses public/demo cases, prefilled answer labels, administrative cues, duplicate reviewer identities, changed hashes, and finalization without required adjudication. The existence of this workflow is not a completed independent result.

A blinded headline case must also bind `review_proof_path` and its frozen SHA-256. Evaluation rechecks the finalization record against the current package and annotation hashes; setting `headline_eligible: true` or hand-writing `independent_adjudicated` is insufficient. `expected_finding_recall` requires both issue-family and location compatibility; issue-only matches remain diagnostic for the separate localization denominator.

Coordinator commands and the bilingual privacy boundary are documented in [`INDEPENDENT_REVIEW_WORKFLOW.md`](INDEPENDENT_REVIEW_WORKFLOW.md). Reviewers receive the bilingual [`INDEPENDENT_REVIEWER_GUIDE.md`](INDEPENDENT_REVIEWER_GUIDE.md) inside each sealed packet.

Generated runs, reviewer packets, mapping files, API caches, local metrics, seeds, and identity artifacts are local/private outputs. They should remain ignored and outside source, wheel, and release archives unless an explicitly named release summary is intentionally added.
