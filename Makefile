PYTHON ?= python3
SKILL_DIR := skill/biomed-research-integrity-auditor
EVAL_DIR := evals

.PHONY: validate regenerate-evals prompts score true-pdf-benchmark scanned-pdf-benchmark real-image-benchmark pppr-public-smoke

validate:
	$(PYTHON) -m py_compile scripts/*.py provenance/*.py benchmarks/*/*.py benchmarks/*/scripts/*.py $(EVAL_DIR)/run_eval.py $(EVAL_DIR)/run_script_baseline.py $(EVAL_DIR)/generate_synthetic_cases.py $(EVAL_DIR)/assert_audit_outputs.py $(SKILL_DIR)/scripts/*.py detectors/image/*.py detectors/stats/*.py detectors/text/*.py calibrators/*.py webapp/*.py webapp/backend/*.py tests/*.py
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) benchmarks/true_pdf/run_true_pdf_benchmark.py --output-dir tmp/true_pdf_benchmark
	$(PYTHON) benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py --output-dir tmp/scanned_pdf_benchmark --skip-if-unavailable
	$(PYTHON) benchmarks/real_image/run_real_image_benchmark.py --output-dir tmp/real_image_benchmark
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

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
