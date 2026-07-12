# BRIA-Bench Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first independently testable BRIA-Bench release: a frozen case registry, auditable pipeline runner, normalized observations, location-aware matching, reliability/performance metrics, regression-track import, reviewer packet, and offline CI report.

**Architecture:** BRIA-Bench is a separate package under `benchmarks/bria_bench/`. A source manifest resolves to a frozen manifest with package hashes; runner adapters produce a common run-result contract; normalized observations are matched one-to-one against annotations; metrics and Markdown are generated only from schema-valid frozen artifacts. Existing synthetic evals enter through a regression adapter and are explicitly excluded from headline accuracy.

**Tech Stack:** Python 3.10+, JSON Schema Draft 2020-12, `psutil` for process-tree telemetry, existing audit CLI, `unittest`, Make, GitHub Actions.

---

## Scope Boundary

This plan implements the Week 1 benchmark core from the approved design. It does not implement the online DeepSeek baseline, the full 24-case blinded test set, final bilingual reviewer reports, GitHub Pages, or the usability study. Those are separate implementation plans built on the contracts created here.

## File Map

Create these focused modules:

- `benchmarks/bria_bench/__init__.py`: package version and public imports.
- `benchmarks/bria_bench/contracts.py`: schema loading and validation only.
- `benchmarks/bria_bench/registry.py`: source-manifest loading, safe path resolution, case expansion, and freeze verification.
- `benchmarks/bria_bench/hashing.py`: deterministic package tree hashes.
- `benchmarks/bria_bench/runtime.py`: subprocess execution, timeout handling, process-tree telemetry, and resumable result writes.
- `benchmarks/bria_bench/normalize.py`: convert audit artifacts to common observations and technical-failure records.
- `benchmarks/bria_bench/matching.py`: issue-family, location, and risk matching with one-to-one assignment.
- `benchmarks/bria_bench/metrics.py`: aggregate detection, reliability, boundary, and performance metrics without a composite score.
- `benchmarks/bria_bench/report.py`: deterministic technical Markdown generated from metrics JSON.
- `benchmarks/bria_bench/legacy_regression.py`: adapt the 30 existing eval cases without treating them as blinded accuracy data.
- `benchmarks/bria_bench/generate_dev_cases.py`: generate six deterministic, redistributable development cases.
- `benchmarks/bria_bench/reviewer_packet.py`: export blind annotation forms without detector output.
- `benchmarks/bria_bench/cli.py`: `freeze`, `run`, `evaluate`, `report`, and `reviewer-packet` commands.
- `benchmarks/bria_bench/schemas/*.schema.json`: manifest, annotation, observation, run-result, and metrics contracts.
- `benchmarks/bria_bench/benchmark_manifest.source.json`: source registry for the regression collection and six development smoke cases.
- `benchmarks/bria_bench/benchmark_manifest.json`: generated frozen registry committed with hashes.
- `benchmarks/bria_bench/annotations/dev/*.json`: explicit development labels only.
- `benchmarks/bria_bench/results/.gitkeep`: generated local run destination.
- `benchmarks/bria_bench/README.md`: honest usage and track-boundary documentation.
- `tests/test_bria_bench.py`: unit and integration tests for the new package.

Modify:

- `pyproject.toml`: add a `benchmark` optional dependency and `bria-bench` console command.
- `requirements.txt` and `requirements-lock.txt`: include `psutil` in contributor/CI installs.
- `Makefile`: add benchmark freeze, smoke, run, evaluate, and report targets.
- `.gitignore`: ignore generated BRIA-Bench run directories while retaining frozen summaries.
- `.github/workflows/validate.yml`: run the offline smoke benchmark.
- `CHANGELOG.md`: document the new benchmark core without claiming blinded validation is complete.

### Task 1: Create Contracts And Schema Validation

**Files:**
- Create: `benchmarks/bria_bench/__init__.py`
- Create: `benchmarks/bria_bench/contracts.py`
- Create: `benchmarks/bria_bench/schemas/benchmark_manifest.schema.json`
- Create: `benchmarks/bria_bench/schemas/annotation.schema.json`
- Create: `benchmarks/bria_bench/schemas/observation.schema.json`
- Create: `benchmarks/bria_bench/schemas/run_result.schema.json`
- Create: `benchmarks/bria_bench/schemas/metrics.schema.json`
- Create: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing schema tests**

Add a `BriaBenchContractTests` class that verifies every schema loads, a minimal valid payload passes, and unknown top-level keys fail:

```python
class BriaBenchContractTests(unittest.TestCase):
    def test_manifest_contract_accepts_minimal_source_case(self) -> None:
        payload = {
            "schema_version": "1.0.0",
            "benchmark_id": "bria-bench-dev",
            "benchmark_version": "0.1.0",
            "cases": [{
                "case_id": "dev_001",
                "track": "blinded_challenge",
                "split": "dev",
                "package_path": "cases/dev_001",
                "annotation_path": "annotations/dev/dev_001.json",
                "mode": "internal_presubmission",
                "scan_profile": "quick",
                "redistributable": True,
                "license": "CC0-1.0",
            }],
        }
        validate_contract("benchmark_manifest.schema.json", payload)

    def test_manifest_contract_rejects_unknown_top_level_key(self) -> None:
        payload = {"schema_version": "1.0.0", "benchmark_id": "x", "benchmark_version": "0.1.0", "cases": [], "score": 99}
        with self.assertRaises(ContractError):
            validate_contract("benchmark_manifest.schema.json", payload)
```

- [ ] **Step 2: Run the tests and verify the import/schema failure**

Run:

```bash
.venv/bin/python -m unittest tests.test_bria_bench.BriaBenchContractTests -v
```

Expected: FAIL because `benchmarks.bria_bench.contracts` and schemas do not exist.

- [ ] **Step 3: Implement schema validation**

Use one validator entrypoint and reject additional properties in every benchmark-owned schema:

```python
SCHEMA_ROOT = Path(__file__).with_name("schemas")

class ContractError(ValueError):
    pass

def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / name
    if path.parent != SCHEMA_ROOT or not path.is_file():
        raise ContractError(f"Unknown BRIA-Bench schema: {name}")
    return json.loads(path.read_text(encoding="utf-8"))

def validate_contract(name: str, payload: Any) -> None:
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        location = ".".join(str(part) for part in errors[0].path) or "<root>"
        raise ContractError(f"{name}:{location}: {errors[0].message}")
```

The manifest schema must enumerate tracks (`regression`, `blinded_challenge`, `public_realism`, `public_concern`, `robustness_scale`), splits (`dev`, `test`, `reference`), modes, and scan profiles. The annotation schema must require `case_id`, `negative_control`, `review_status`, and `expected_observations`; `review_status` is one of `controlled_ground_truth`, `independent_pending`, `independent_adjudicated`, or `ambiguous`. Each observation supports `recall_label`, `coverage_gap`, `negative_guardrail`, or `reference_only`, plus issue family, location, risk range, benign explanations, and required materials. Apply prohibited-key constraints to the top level and nested annotation objects so keys named `misconduct`, `fraud`, `fake`, or `guilty` are rejected.

- [ ] **Step 4: Run contract tests**

Run the same unittest command. Expected: PASS.

- [ ] **Step 5: Commit the contract layer**

```bash
git add benchmarks/bria_bench tests/test_bria_bench.py
git commit -m "feat: add BRIA-Bench data contracts"
```

### Task 2: Add Deterministic Hashing And Frozen Registry

**Files:**
- Create: `benchmarks/bria_bench/hashing.py`
- Create: `benchmarks/bria_bench/registry.py`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing registry tests**

Cover deterministic hashes, symlink rejection, path traversal rejection, and frozen-hash mismatch:

```python
def test_tree_hash_is_stable_and_content_sensitive(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "b.txt").write_text("beta\n", encoding="utf-8")
        (root / "a.txt").write_text("alpha\n", encoding="utf-8")
        first = hash_tree(root)
        self.assertEqual(first, hash_tree(root))
        (root / "a.txt").write_text("changed\n", encoding="utf-8")
        self.assertNotEqual(first, hash_tree(root))

def test_registry_rejects_package_path_escape(self) -> None:
    case = valid_case(package_path="../private")
    with self.assertRaisesRegex(RegistryError, "escapes benchmark root"):
        resolve_case_paths(BENCH_ROOT, case)

def test_verify_frozen_case_rejects_hash_mismatch(self) -> None:
    case = valid_case(expected_sha256="0" * 64)
    with self.assertRaisesRegex(RegistryError, "hash mismatch"):
        verify_frozen_case(BENCH_ROOT, case)
```

- [ ] **Step 2: Run registry tests and verify failure**

Expected: FAIL because hashing and registry functions are undefined.

- [ ] **Step 3: Implement deterministic tree hashing**

Hash each relative POSIX path, a NUL separator, file length, file bytes, and a record separator. Reject symlinks rather than following them:

```python
def hash_tree(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file() or path.is_symlink())
    for path in files:
        if path.is_symlink():
            raise HashingError(f"Symlink is not allowed in frozen benchmark package: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\xff")
    return digest.hexdigest()
```

- [ ] **Step 4: Implement registry load, freeze, and verify**

`resolve_inside(root, value)` must call `Path.resolve()`, require `resolved.is_relative_to(root.resolve())`, and reject symlinks in every path component. `freeze_manifest()` must add `expected_sha256` for every package and `frozen_at` supplied by the caller; deterministic tests pass a fixed timestamp. `load_manifest(require_frozen=True)` must require `frozen_at` plus every case hash and verify the annotation file exists without reading sealed annotations during `run`.

- [ ] **Step 5: Run registry tests**

Expected: PASS, including hash mismatch and path escape cases.

- [ ] **Step 6: Commit frozen-registry support**

```bash
git add benchmarks/bria_bench/hashing.py benchmarks/bria_bench/registry.py tests/test_bria_bench.py
git commit -m "feat: freeze BRIA-Bench case registries"
```

### Task 3: Add Process-Tree Telemetry And Failure-Preserving Runner

**Files:**
- Create: `benchmarks/bria_bench/runtime.py`
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-lock.txt`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Add failing runtime tests**

Test success, non-zero exit, timeout, child-process RSS, and atomic result output:

```python
def test_run_monitored_records_nonzero_exit_without_raising(self) -> None:
    result = run_monitored([sys.executable, "-c", "import sys; sys.exit(7)"], ROOT, timeout_seconds=5)
    self.assertEqual(result.status, "process_error")
    self.assertEqual(result.returncode, 7)
    self.assertGreater(result.elapsed_seconds, 0)

def test_run_monitored_times_out_and_stops_process_tree(self) -> None:
    result = run_monitored([sys.executable, "-c", "import time; time.sleep(30)"], ROOT, timeout_seconds=0.2)
    self.assertEqual(result.status, "timeout")
    self.assertTrue(result.timed_out)

def test_atomic_json_preserves_previous_file_on_serialization_error(self) -> None:
    path = self.temp_dir / "result.json"
    path.write_text('{"status":"old"}\n', encoding="utf-8")
    with self.assertRaises(TypeError):
        write_json_atomic(path, {"bad": object()})
    self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "old")
```

- [ ] **Step 2: Run runtime tests and verify failure**

Expected: FAIL because `runtime.py` is absent.

- [ ] **Step 3: Add benchmark dependency**

Add:

```toml
[project.optional-dependencies]
benchmark = [
  "psutil>=5.9,<8"
]
```

Keep existing optional groups unchanged. Add `psutil>=5.9,<8` to `requirements.txt`, then regenerate the lock using:

```bash
.venv/bin/python -m piptools compile --no-annotate --output-file=requirements-lock.txt --strip-extras requirements.txt
```

If `piptools` is absent, install it into the development environment only and rerun the exact command; do not hand-edit transitive lock entries.

- [ ] **Step 4: Implement monitored execution**

Use `subprocess.Popen(start_new_session=True)`, poll every 50 ms, and sum RSS/CPU across the root process plus recursive children. On timeout terminate children, wait one second, then kill survivors. Return a dataclass with `status`, `returncode`, `elapsed_seconds`, `cpu_seconds`, `peak_rss_bytes`, `timed_out`, `stdout_tail`, and `stderr_tail`. Never raise for process failure; raise only for invalid runner configuration.

Write results through a sibling temporary file followed by `os.replace()`:

```python
def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
```

- [ ] **Step 5: Run runtime tests and dependency preflight**

Run:

```bash
.venv/bin/python -m unittest tests.test_bria_bench.BriaBenchRuntimeTests -v
.venv/bin/python -c "import psutil; print(psutil.__version__)"
```

Expected: tests PASS and a supported psutil version prints.

- [ ] **Step 6: Commit telemetry support**

```bash
git add benchmarks/bria_bench/runtime.py pyproject.toml requirements.txt requirements-lock.txt tests/test_bria_bench.py
git commit -m "feat: record BRIA-Bench process telemetry"
```

### Task 4: Normalize Audit Outputs And Technical Failures

**Files:**
- Create: `benchmarks/bria_bench/normalize.py`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing normalization tests**

Use temporary `AUDIT_JSON_SUMMARY.json`, `coverage.json`, and `pipeline_summary.json` fixtures. Assert that findings become stable observations, detector failures are separate technical records, local paths are removed, and forbidden language is detected:

```python
def test_normalize_audit_output_separates_findings_and_failures(self) -> None:
    write_audit_fixture(self.output_dir, findings=[{
        "finding_id": "F-1",
        "risk_level": "R2",
        "finding_type": "whole-column additive shift",
        "location": "Figure_3.xlsx#Sheet1:control<->treated",
        "evidence_type": "weak_forensic_triage_signal",
        "recommended_action": "Re-run the source calculation.",
    }], detector_failures=["image.local_patch: detector_execution_failure"])
    normalized = normalize_audit_output("dev_001", self.output_dir)
    self.assertEqual(normalized["observations"][0]["issue_family"], "statistics_or_numeric")
    self.assertEqual(normalized["technical_failures"][0]["module"], "image.local_patch")
    self.assertNotIn(str(self.output_dir), json.dumps(normalized))
```

- [ ] **Step 2: Run normalization tests and verify failure**

Expected: FAIL because normalizer functions do not exist.

- [ ] **Step 3: Implement stable observation normalization**

Define an ordered issue-family mapping for global image, local reuse, copy-move, keypoint geometry, statistics, text overlap, methodology/reporting, and material/coverage gaps. Preserve source finding IDs and exact location text. Produce separate arrays:

- `observations`
- `technical_failures`
- `reported_technical_failures`
- `boundary_violations`
- `contract_errors`

Scan the human report and JSON string values using the existing neutral-language boundary terms plus PASS/FAIL certificate language. Redact the package root, output root, home directory, and staging paths before writing normalized data.

- [ ] **Step 4: Validate normalized payload and run tests**

Call `validate_contract("observation.schema.json", payload)` before returning. Expected: all normalization tests PASS.

- [ ] **Step 5: Commit the normalizer**

```bash
git add benchmarks/bria_bench/normalize.py tests/test_bria_bench.py
git commit -m "feat: normalize BRIA-Bench audit observations"
```

### Task 5: Implement Location-Aware One-To-One Matching

**Files:**
- Create: `benchmarks/bria_bench/matching.py`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing matcher tests**

Cover exact issue/location matches, wrong panel rejection, generic “Figure” rejection, risk-band mismatch, and one observation not satisfying two labels:

```python
def test_matching_is_one_to_one(self) -> None:
    labels = [label("L1", "image_global_similarity", terms=["figure 1a"]), label("L2", "image_global_similarity", terms=["figure 1a"])]
    observations = [observation("O1", "image_global_similarity", "Figure 1A")]
    result = match_labels(labels, observations)
    self.assertEqual(len(result.matches), 1)
    self.assertEqual(len(result.unmatched_label_ids), 1)

def test_location_match_rejects_wrong_panel(self) -> None:
    expected = label("L1", "image_local_reuse", terms=["figure 3c"])
    actual = observation("O1", "image_local_reuse", "Figure 3D")
    self.assertFalse(label_observation_compatible(expected, actual).compatible)
```

- [ ] **Step 2: Run matcher tests and verify failure**

Expected: FAIL because matching functions are absent.

- [ ] **Step 3: Implement compatibility and maximum matching**

Normalize location tokens without discarding panel suffixes. Require exact issue-family match unless the annotation explicitly lists compatible families. Score files, figure/panel tokens, sheet/column terms, and coordinate overlap separately. A generic token such as `figure`, `panel`, `table`, or `sheet` cannot create compatibility by itself.

Build a bipartite adjacency list and use deterministic DFS augmenting paths so one observation satisfies at most one recall label:

```python
def maximum_cardinality_matching(edges: dict[int, list[int]], label_count: int) -> dict[int, int]:
    observation_to_label: dict[int, int] = {}

    def assign(label_index: int, visited: set[int]) -> bool:
        for observation_index in edges.get(label_index, []):
            if observation_index in visited:
                continue
            visited.add(observation_index)
            previous = observation_to_label.get(observation_index)
            if previous is None or assign(previous, visited):
                observation_to_label[observation_index] = label_index
                return True
        return False

    for label_index in range(label_count):
        assign(label_index, set())
    return {label_index: observation_index for observation_index, label_index in observation_to_label.items()}
```

Return match reasons and location components for auditability.

- [ ] **Step 4: Run matcher tests**

Expected: PASS for matching, panel distinction, risk-band, and one-to-one tests.

- [ ] **Step 5: Commit matcher**

```bash
git add benchmarks/bria_bench/matching.py tests/test_bria_bench.py
git commit -m "feat: match BRIA-Bench findings by issue and location"
```

### Task 6: Aggregate Separate Detection, Reliability, And Performance Metrics

**Files:**
- Create: `benchmarks/bria_bench/metrics.py`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing metric tests**

Build three in-memory run results: one matched positive, one clean negative, and one detector crash that the report fails to disclose. Assert exact fractions and absence of a composite score:

```python
def test_metrics_count_silent_failure_and_keep_dimensions_separate(self) -> None:
    result = aggregate_metrics(cases=[positive_hit(), negative_clean(), silent_detector_failure()])
    self.assertEqual(result["detection"]["expected_finding_recall"], 1.0)
    self.assertEqual(result["detection"]["negative_package_false_alert_rate"], 0.0)
    self.assertEqual(result["reliability"]["silent_failure_rate"], 1 / 3)
    self.assertNotIn("score", result)
    self.assertNotIn("overall_score", result)
```

- [ ] **Step 2: Run metric tests and verify failure**

Expected: FAIL because `aggregate_metrics` is absent.

- [ ] **Step 3: Implement metric denominators explicitly**

Each metric object must include `numerator`, `denominator`, and `value`. Use `None` when denominator is zero. Headline detection metrics must include only tracks and roles allowed by the frozen manifest:

- Regression: report assertion-met/assertion-not-met counts, never headline accuracy.
- Blinded challenge and public realism controlled cases: detection metrics.
- Public concern: localization coverage only.
- Robustness/scale: reliability and performance only.

Calculate p50/p95 with a deterministic nearest-rank function and preserve per-case values. Count a silent failure when runtime or normalized technical failures exist but `reported_technical_failures` does not contain a corresponding module.

- [ ] **Step 4: Validate metrics and run tests**

Validate against `metrics.schema.json`; expected tests PASS with exact numerator and denominator assertions.

- [ ] **Step 5: Commit metric aggregation**

```bash
git add benchmarks/bria_bench/metrics.py tests/test_bria_bench.py
git commit -m "feat: aggregate BRIA-Bench product metrics"
```

### Task 7: Build The Resumable Benchmark CLI

**Files:**
- Create: `benchmarks/bria_bench/cli.py`
- Modify: `benchmarks/bria_bench/__init__.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing CLI integration tests**

Invoke the CLI in subprocesses against a temporary one-case manifest. Test freeze, run, cache hit, hash change invalidation, evaluate, and report command exit codes. The fake audit command writes a minimal schema-valid audit output so the test does not run the full pipeline.

```python
def test_cli_run_resumes_only_when_case_and_runner_hash_match(self) -> None:
    first = run_cli("run", "--manifest", str(self.frozen_manifest), "--runs-dir", str(self.runs))
    second = run_cli("run", "--manifest", str(self.frozen_manifest), "--runs-dir", str(self.runs))
    self.assertEqual(first.returncode, 0)
    self.assertEqual(second.returncode, 0)
    summary = json.loads((self.runs / "run_summary.json").read_text(encoding="utf-8"))
    self.assertEqual(summary["cases"][0]["cache_status"], "reused")
```

- [ ] **Step 2: Run CLI tests and verify failure**

Expected: FAIL because no CLI exists.

- [ ] **Step 3: Implement subcommands**

Implement:

```text
bria-bench freeze --source ... --output ... --frozen-at ...
bria-bench run --manifest ... --runs-dir ... --adapter full --timeout-seconds 900
bria-bench evaluate --manifest ... --runs-dir ... --output ...
bria-bench report --metrics ... --output ...
bria-bench reviewer-packet --manifest ... --output-dir ... --mapping-output ...
```

`run` builds this full-pipeline command per case:

```python
[
    sys.executable,
    "scripts/audit_package.py",
    str(package_path),
    "--mode", case["mode"],
    "--scan-profile", case["scan_profile"],
    "--external-literature-provider", "none",
    "--case-id", case["case_id"],
    "--output-dir", str(case_output),
]
```

The cache key is SHA-256 over benchmark version, case hash, adapter name/version, command, Python version, package version, and relevant rules/schema file hashes. A cache hit requires a schema-valid run result and unchanged cache key. Write each case result atomically before continuing.

- [ ] **Step 4: Run CLI tests**

Expected: all freeze/run/resume/evaluate/report integration tests PASS.

- [ ] **Step 5: Commit CLI orchestration**

```bash
git add benchmarks/bria_bench/cli.py benchmarks/bria_bench/__init__.py pyproject.toml tests/test_bria_bench.py
git commit -m "feat: add resumable BRIA-Bench CLI"
```

### Task 8: Generate Deterministic Technical Reports

**Files:**
- Create: `benchmarks/bria_bench/report.py`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing report golden test**

Assert section order, explicit denominators, no composite score, regression exclusion language, public-concern boundary, and no local path:

```python
def test_technical_report_is_honest_and_reproducible(self) -> None:
    report = render_metrics_report(metrics_fixture())
    self.assertLess(report.index("## Detection and localization"), report.index("## Performance"))
    self.assertIn("3 / 4", report)
    self.assertIn("Regression cases are excluded from headline accuracy", report)
    self.assertIn("Public concern labels are localization references, not misconduct truth", report)
    self.assertNotIn("overall score", report.lower())
    self.assertNotIn(str(Path.home()), report)
```

- [ ] **Step 2: Run report test and verify failure**

Expected: FAIL because report renderer is absent.

- [ ] **Step 3: Implement deterministic Markdown**

Render in this fixed order:

1. Scope and benchmark version
2. Detection and localization
3. Reliability and safety
4. Performance and cost
5. Track boundaries
6. Case-level appendix
7. Reproduction command and hashes

Never infer prose from unavailable metrics. Render `not measured` when denominator is zero. Format every fraction as numerator, denominator, and percentage.

- [ ] **Step 4: Run report tests**

Expected: golden content tests PASS.

- [ ] **Step 5: Commit report generation**

```bash
git add benchmarks/bria_bench/report.py tests/test_bria_bench.py
git commit -m "feat: render BRIA-Bench technical reports"
```

### Task 9: Import The Existing 30 Cases As Regression-Only Data

**Files:**
- Create: `benchmarks/bria_bench/legacy_regression.py`
- Create: `benchmarks/bria_bench/benchmark_manifest.source.json`
- Create: `benchmarks/bria_bench/benchmark_manifest.json`
- Create: `benchmarks/bria_bench/annotations/dev/.gitkeep`
- Create: `benchmarks/bria_bench/results/.gitkeep`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing legacy import tests**

Assert exactly 30 case IDs resolve, all are track `regression`, no regression case is headline eligible, and the frozen hash changes if a package changes:

```python
def test_legacy_collection_expands_to_regression_only_cases(self) -> None:
    cases = expand_legacy_regression(ROOT / "evals")
    self.assertEqual(len(cases), 30)
    self.assertTrue(all(case["track"] == "regression" for case in cases))
    self.assertTrue(all(case["headline_eligible"] is False for case in cases))
```

- [ ] **Step 2: Run legacy tests and verify failure**

Expected: FAIL because legacy adapter and manifest are absent.

- [ ] **Step 3: Implement explicit legacy conversion**

Read existing JSON-compatible YAML labels through `evals.run_eval.load_expected()`. Convert required finding types, risk ranges, location terms, benign-explanation terms, and required-material terms to annotation observations. Mark every converted observation with `evaluation_scope: regression_only` and preserve the source label path.

- [ ] **Step 4: Generate and verify the frozen manifest**

Run:

```bash
.venv/bin/python -m benchmarks.bria_bench.cli freeze \
  --source benchmarks/bria_bench/benchmark_manifest.source.json \
  --output benchmarks/bria_bench/benchmark_manifest.json \
  --frozen-at 2026-07-11T00:00:00Z
.venv/bin/python -m benchmarks.bria_bench.cli run \
  --manifest benchmarks/bria_bench/benchmark_manifest.json \
  --runs-dir tmp/bria_bench_smoke \
  --case case_001 --case case_004 --case case_008 \
  --adapter full --timeout-seconds 300
```

Expected: three successful case results, all identified as regression-only.

- [ ] **Step 5: Run legacy and smoke tests**

Expected: 30 cases resolve; three-case smoke run completes without headline accuracy fields.

- [ ] **Step 6: Commit regression integration**

```bash
git add benchmarks/bria_bench/benchmark_manifest.source.json benchmarks/bria_bench/benchmark_manifest.json benchmarks/bria_bench/annotations benchmarks/bria_bench/results benchmarks/bria_bench/legacy_regression.py tests/test_bria_bench.py
git commit -m "feat: register legacy evals as BRIA-Bench regression cases"
```

### Task 10: Generate Six Controlled Development Cases

**Files:**
- Create: `benchmarks/bria_bench/generate_dev_cases.py`
- Create: `benchmarks/bria_bench/cases/dev/`
- Create: `benchmarks/bria_bench/annotations/dev/dev_001_global_flip.json`
- Create: `benchmarks/bria_bench/annotations/dev/dev_002_independent_images.json`
- Create: `benchmarks/bria_bench/annotations/dev/dev_003_stats_shift.json`
- Create: `benchmarks/bria_bench/annotations/dev/dev_004_stats_independent.json`
- Create: `benchmarks/bria_bench/annotations/dev/dev_005_corrupt_image.json`
- Create: `benchmarks/bria_bench/annotations/dev/dev_006_manifest_laundering.json`
- Modify: `benchmarks/bria_bench/benchmark_manifest.source.json`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing deterministic-case tests**

Generate into two temporary roots and assert matching package hashes, six exact IDs, redistributable licensing, and schema-valid annotations:

```python
def test_dev_case_generation_is_deterministic(self) -> None:
    with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
        left = generate_dev_cases(Path(left_tmp))
        right = generate_dev_cases(Path(right_tmp))
        self.assertEqual([item["case_id"] for item in left], [item["case_id"] for item in right])
        self.assertEqual([hash_tree(Path(left_tmp) / item["case_id"]) for item in left], [hash_tree(Path(right_tmp) / item["case_id"]) for item in right])
        self.assertEqual(len(left), 6)
        self.assertTrue(all(item["redistributable"] and item["license"] == "CC0-1.0" for item in left))
```

- [ ] **Step 2: Run generation tests and verify failure**

Expected: FAIL because the generator and development cases do not exist.

- [ ] **Step 3: Implement the deterministic generator**

Use fixed seeds and no current timestamps. Generate these exact cases:

1. `dev_001_global_flip`: two figure files where one is a horizontal flip of the other; expected family `image_global_similarity`.
2. `dev_002_independent_images`: two independently seeded images with similar dimensions; negative guardrail with no R2+ image-reuse observation expected.
3. `dev_003_stats_shift`: eight paired control/treatment values with a constant `+10` shift; expected family `statistics_or_numeric`, risk range R1–R2.
4. `dev_004_stats_independent`: eight independently seeded decimal values; negative guardrail for relationship findings.
5. `dev_005_corrupt_image`: one valid PNG and one intentionally truncated PNG; expected `coverage_gap` for unreadable image disclosure.
6. `dev_006_manifest_laundering`: a whole-image duplicated/flip pair plus an assembly manifest falsely declaring `same_field_different_channel`; expected manifest-conflict observation and no positive-provenance clearance.

Every package includes a neutral `PACKAGE_NOTE.txt` and a short manuscript text. Use Pillow for generated images and `csv` for tables/manifests. Do not copy fixtures from the existing 30 regression cases.

- [ ] **Step 4: Write explicit development annotations**

Each annotation must contain `case_id`, `negative_control`, `review_status: controlled_ground_truth`, and `expected_observations`. Positive annotations include issue family, location terms, risk range, benign explanations, and required materials. Negative annotations contain a `negative_guardrail` observation naming the forbidden issue family rather than claiming the package is scientifically correct.

- [ ] **Step 5: Generate, freeze, and smoke-run the six cases**

```bash
.venv/bin/python -m benchmarks.bria_bench.generate_dev_cases --output benchmarks/bria_bench/cases/dev
.venv/bin/python -m benchmarks.bria_bench.cli freeze --source benchmarks/bria_bench/benchmark_manifest.source.json --output benchmarks/bria_bench/benchmark_manifest.json --frozen-at 2026-07-11T00:00:00Z
.venv/bin/python -m benchmarks.bria_bench.cli run --manifest benchmarks/bria_bench/benchmark_manifest.json --runs-dir tmp/bria_bench_dev --split dev --adapter full --timeout-seconds 300
```

Expected: six schema-valid case results; development metrics remain separate from future blinded-test headline metrics.

- [ ] **Step 6: Run generation and integration tests**

Expected: deterministic generation, annotation schema, negative-guardrail, and six-case smoke tests PASS.

- [ ] **Step 7: Commit development fixtures**

```bash
git add benchmarks/bria_bench/generate_dev_cases.py benchmarks/bria_bench/cases/dev benchmarks/bria_bench/annotations/dev benchmarks/bria_bench/benchmark_manifest.source.json benchmarks/bria_bench/benchmark_manifest.json tests/test_bria_bench.py
git commit -m "test: add BRIA-Bench controlled development cases"
```

### Task 11: Export Blind Reviewer Packets

**Files:**
- Create: `benchmarks/bria_bench/reviewer_packet.py`
- Create: `benchmarks/bria_bench/REVIEWER_GUIDE.md`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Write failing reviewer-packet tests**

Assert packets include only case materials, blank forms, anonymized IDs, hashes, and instructions. Detector output, expected labels, risk rules, local paths, and reviewer identities must be absent:

```python
def test_reviewer_packet_contains_no_detector_or_expected_output(self) -> None:
    packet = export_reviewer_packet(self.manifest, ["dev_001"], self.packet_dir)
    text = " ".join(path.read_text(encoding="utf-8", errors="ignore") for path in self.packet_dir.rglob("*") if path.is_file())
    self.assertNotIn("expected_observations", text)
    self.assertNotIn("detector", text.lower())
    self.assertNotIn(str(ROOT), text)
    self.assertEqual(packet["cases"][0]["reviewer_case_id"], "BRIA-R001")
```

- [ ] **Step 2: Run reviewer tests and verify failure**

Expected: FAIL because reviewer packet exporter is absent.

- [ ] **Step 3: Implement reviewer packet export**

Copy package materials under randomized stable reviewer IDs derived from an explicit packet seed. Write one blank JSON form per case with only:

- `reviewer_case_id`
- `presence`: `present`, `absent`, or `insufficient_materials`
- `comment_class`: `major`, `minor`, or `materials_request`
- `locations`
- `observation`
- `scientific_relevance`
- `benign_explanations`
- `required_materials`
- `recommended_action`

Write `packet_manifest.json` with reviewer case ID, source package hash, and annotation schema version. Do not include source case IDs in reviewer-facing files; require `--mapping-output` to point outside the packet directory, write the source-ID mapping there, and reject a mapping path inside the packet.

- [ ] **Step 4: Run reviewer-packet tests**

Expected: PASS, including privacy and output-leakage scans.

- [ ] **Step 5: Commit reviewer workflow**

```bash
git add benchmarks/bria_bench/reviewer_packet.py benchmarks/bria_bench/REVIEWER_GUIDE.md tests/test_bria_bench.py
git commit -m "feat: export blind BRIA-Bench reviewer packets"
```

### Task 12: Wire Make, CI, Ignore Rules, And Documentation

**Files:**
- Create: `benchmarks/bria_bench/README.md`
- Modify: `Makefile`
- Modify: `.gitignore`
- Modify: `.github/workflows/validate.yml`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_bria_bench.py`

- [ ] **Step 1: Add a failing command-surface test**

Read the Makefile and assert the expected targets exist. Run `bria-bench --help` and assert every approved subcommand appears.

- [ ] **Step 2: Add Make targets**

Add phony targets:

```make
BENCHMARK_FROZEN_AT ?= 2026-07-11T00:00:00Z

benchmark-freeze:
	$(PYTHON) -m benchmarks.bria_bench.cli freeze --source benchmarks/bria_bench/benchmark_manifest.source.json --output benchmarks/bria_bench/benchmark_manifest.json --frozen-at $(BENCHMARK_FROZEN_AT)

benchmark-smoke:
	$(PYTHON) -m benchmarks.bria_bench.cli run --manifest benchmarks/bria_bench/benchmark_manifest.json --runs-dir tmp/bria_bench_smoke --case case_001 --case dev_001_global_flip --case dev_005_corrupt_image --case dev_006_manifest_laundering --adapter full --timeout-seconds 300
	$(PYTHON) -m benchmarks.bria_bench.cli evaluate --manifest benchmarks/bria_bench/benchmark_manifest.json --runs-dir tmp/bria_bench_smoke --output tmp/bria_bench_smoke/metrics.json
	$(PYTHON) -m benchmarks.bria_bench.cli report --metrics tmp/bria_bench_smoke/metrics.json --output tmp/bria_bench_smoke/REPORT.md

benchmark:
	$(PYTHON) -m benchmarks.bria_bench.cli run --manifest benchmarks/bria_bench/benchmark_manifest.json --runs-dir tmp/bria_bench_runs --adapter full --timeout-seconds 900

benchmark-report:
	$(PYTHON) -m benchmarks.bria_bench.cli evaluate --manifest benchmarks/bria_bench/benchmark_manifest.json --runs-dir tmp/bria_bench_runs --output tmp/bria_bench_runs/metrics.json
	$(PYTHON) -m benchmarks.bria_bench.cli report --metrics tmp/bria_bench_runs/metrics.json --output tmp/bria_bench_runs/REPORT.md
```

Do not add `benchmark` to `validate`; add only `benchmark-smoke` after unit tests. This keeps CI bounded.

- [ ] **Step 3: Add CI and ignore rules**

Install the benchmark extra in CI with `python -m pip install -e '.[benchmark]'`. Add `make benchmark-smoke` after contract tests. Ignore `benchmarks/bria_bench/results/runs/`, reviewer packet exports, API caches, and local metrics; retain `.gitkeep`, frozen manifests, and explicitly named release summaries.

- [ ] **Step 4: Write honest README and changelog**

Document:

- the five tracks and which metrics each may support
- why the existing 30 cases are regression-only
- freeze and reproduce commands
- reviewer packet privacy boundary
- absence of a completed blinded headline result in this phase
- generated files and cache behavior
- how missing `psutil` is an environment blocker, not a scientific finding

- [ ] **Step 5: Run full verification**

Run:

```bash
.venv/bin/python -m unittest tests.test_bria_bench -v
make benchmark-smoke
make validate
git diff --check
git status --short
```

Expected: all BRIA-Bench tests PASS, smoke report is generated under `tmp/`, existing full validation passes, and no generated run/reviewer/API artifacts appear in Git status.

- [ ] **Step 6: Commit integration and docs**

```bash
git add Makefile .gitignore .github/workflows/validate.yml CHANGELOG.md benchmarks/bria_bench/README.md tests/test_bria_bench.py
git commit -m "feat: integrate BRIA-Bench offline smoke validation"
```

### Task 13: Phase-One Release Audit

**Files:**
- Modify only files required to fix findings from this audit.

- [ ] **Step 1: Verify spec coverage**

Create a temporary checklist mapping approved design sections 4, 5, 7, 10, 11, and 12 to implemented files and tests. Do not commit the temporary checklist.

- [ ] **Step 2: Verify public-tree privacy and licensing**

Run:

```bash
git grep -n -I -E '/Users/|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|API[_-]?KEY[[:space:]]*=' -- benchmarks/bria_bench docs || true
find benchmarks/bria_bench -type l -print
git status --short
```

Expected: no personal absolute path, email, key material, API secret, symlink, generated run, or reviewer identity is tracked.

- [ ] **Step 3: Verify benchmark-claim boundaries**

Search README, report fixtures, and generated smoke report for `fraud`, `misconduct confirmed`, `造假成立`, `PASS`, `FAIL`, `overall score`, and `accuracy`. Every hit must either be an explicit prohibition/technical test or be removed. Regression-track results must not render headline recall or false-alert claims.

- [ ] **Step 4: Run final clean verification**

```bash
rm -rf tmp/bria_bench_smoke tmp/bria_bench_runs
find . -path './.venv' -prune -o -type d -name __pycache__ -exec rm -rf {} +
git diff --check
git status --short --branch
.venv/bin/python -m unittest tests.test_bria_bench -v
```

Expected: tests PASS and the worktree contains only intentional source changes or is clean after the task commits.

- [ ] **Step 5: Record the phase-one milestone**

If the audit required fixes, commit them:

```bash
git add -A
git commit -m "fix: harden BRIA-Bench core release boundary"
```

If no fixes were required, do not create an empty commit. Record the final commit hash and test counts in the implementation handoff message.
