PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
SKILL_DIR := skill/biomed-research-integrity-auditor
EVAL_DIR := evals
BRIA_BENCH_DIR := benchmarks/bria_bench
BRIA_BENCH_MANIFEST := $(BRIA_BENCH_DIR)/benchmark_manifest.json
BRIA_BENCH_SOURCE_MANIFEST := $(BRIA_BENCH_DIR)/benchmark_manifest.source.json
BRIA_BENCH_SMOKE_DIR := tmp/bria_bench_smoke
BRIA_BENCH_RUNS_DIR := tmp/bria_bench_runs

.PHONY: run preflight validate install-local frontend-smoke release-artifacts regenerate-evals prompts score true-pdf-benchmark scanned-pdf-benchmark real-image-benchmark pppr-public-smoke benchmark-freeze benchmark-smoke benchmark benchmark-report

run:
	$(PYTHON) scripts/run_local_webapp.py

preflight:
	$(PYTHON) scripts/environment_preflight.py --require-webapp

validate:
	$(PYTHON) scripts/environment_preflight.py --require-webapp
	cd webapp/frontend && (test -d node_modules || npm ci)
	cd webapp/frontend && npm run build
	$(PYTHON) -m py_compile scripts/*.py scripts/pipeline/*.py provenance/*.py benchmarks/*/*.py benchmarks/*/scripts/*.py $(EVAL_DIR)/run_eval.py $(EVAL_DIR)/run_script_baseline.py $(EVAL_DIR)/generate_synthetic_cases.py $(EVAL_DIR)/assert_audit_outputs.py $(SKILL_DIR)/scripts/*.py detectors/image/*.py detectors/stats/*.py detectors/text/*.py calibrators/*.py webapp/*.py webapp/backend/*.py tests/*.py
	$(PYTHON) -m mypy calibrators/ provenance/ detectors/ --ignore-missing-imports
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) benchmarks/true_pdf/run_true_pdf_benchmark.py --output-dir tmp/true_pdf_benchmark
	$(PYTHON) benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py --output-dir tmp/scanned_pdf_benchmark --skip-if-unavailable
	$(PYTHON) benchmarks/real_image/run_real_image_benchmark.py --output-dir tmp/real_image_benchmark
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

install-local:
	$(PYTHON) scripts/install_local_commands.py

frontend-smoke:
	cd webapp/frontend && npm run build
	cd webapp/frontend && npm run smoke

release-artifacts:
	cd webapp/frontend && npm ci
	cd webapp/frontend && npm run build
	$(PYTHON) -m pip install --upgrade build
	rm -rf build *.egg-info dist/release
	rm -f dist/biomed_research_integrity_auditor-*.whl dist/biomed_research_integrity_auditor-*.tar.gz
	$(PYTHON) -m build
	$(PYTHON) scripts/build_release_artifacts.py

regenerate-evals:
	$(PYTHON) $(EVAL_DIR)/generate_synthetic_cases.py
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

prompts:
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

score:
	$(PYTHON) $(EVAL_DIR)/run_eval.py score

true-pdf-benchmark:
	$(PYTHON) benchmarks/true_pdf/run_true_pdf_benchmark.py --output-dir tmp/true_pdf_benchmark

scanned-pdf-benchmark:
	$(PYTHON) benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py --output-dir tmp/scanned_pdf_benchmark

real-image-benchmark:
	$(PYTHON) benchmarks/real_image/run_real_image_benchmark.py --output-dir tmp/real_image_benchmark

pppr-public-smoke:
	$(PYTHON) benchmarks/pppr_integrity_benchmark/scripts/run_public_smoke_benchmark.py --output-root tmp/pppr_public_smoke

benchmark-freeze:
	$(PYTHON) -m benchmarks.bria_bench.cli freeze --source $(BRIA_BENCH_SOURCE_MANIFEST) --output $(BRIA_BENCH_MANIFEST) --frozen-at 2026-07-11T00:00:00Z

benchmark-smoke:
	rm -rf $(BRIA_BENCH_SMOKE_DIR)
	mkdir -p $(BRIA_BENCH_SMOKE_DIR)
	$(PYTHON) -m benchmarks.bria_bench.cli run --manifest $(BRIA_BENCH_MANIFEST) --runs-dir $(BRIA_BENCH_SMOKE_DIR) --split dev --adapter full --timeout-seconds 60
	$(PYTHON) -m benchmarks.bria_bench.cli evaluate --manifest $(BRIA_BENCH_MANIFEST) --runs-dir $(BRIA_BENCH_SMOKE_DIR) --split dev --output $(BRIA_BENCH_SMOKE_DIR)/metrics.json
	$(PYTHON) -m benchmarks.bria_bench.cli report --metrics $(BRIA_BENCH_SMOKE_DIR)/metrics.json --output $(BRIA_BENCH_SMOKE_DIR)/REPORT.md

benchmark:
	mkdir -p $(BRIA_BENCH_RUNS_DIR)
	$(PYTHON) -m benchmarks.bria_bench.cli run --manifest $(BRIA_BENCH_MANIFEST) --runs-dir $(BRIA_BENCH_RUNS_DIR) --adapter full --timeout-seconds 900
	$(PYTHON) -m benchmarks.bria_bench.cli evaluate --manifest $(BRIA_BENCH_MANIFEST) --runs-dir $(BRIA_BENCH_RUNS_DIR) --output $(BRIA_BENCH_RUNS_DIR)/metrics.json

benchmark-report:
	mkdir -p $(BRIA_BENCH_RUNS_DIR)
	$(PYTHON) -m benchmarks.bria_bench.cli evaluate --manifest $(BRIA_BENCH_MANIFEST) --runs-dir $(BRIA_BENCH_RUNS_DIR) --output $(BRIA_BENCH_RUNS_DIR)/metrics.json
	$(PYTHON) -m benchmarks.bria_bench.cli report --metrics $(BRIA_BENCH_RUNS_DIR)/metrics.json --output $(BRIA_BENCH_RUNS_DIR)/REPORT.md
