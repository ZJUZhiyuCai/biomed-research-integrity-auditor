PYTHON ?= python3
SKILL_DIR := skill/biomed-research-integrity-auditor
EVAL_DIR := evals

.PHONY: validate regenerate-evals prompts score

validate:
	$(PYTHON) -m py_compile scripts/*.py provenance/*.py $(EVAL_DIR)/run_eval.py $(EVAL_DIR)/run_script_baseline.py $(EVAL_DIR)/generate_synthetic_cases.py $(SKILL_DIR)/scripts/*.py detectors/image/*.py detectors/stats/*.py detectors/text/*.py calibrators/*.py tests/*.py
	$(PYTHON) -m unittest discover -s tests
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

regenerate-evals:
	$(PYTHON) $(EVAL_DIR)/generate_synthetic_cases.py
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

prompts:
	$(PYTHON) $(EVAL_DIR)/run_eval.py generate-prompts

score:
	$(PYTHON) $(EVAL_DIR)/run_eval.py score
