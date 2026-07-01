# Source-Data Templates

These YAML files are human review templates for common biomedical source-data exports. They are not loaded as automatic detector contracts by the current audit pipeline.

Use them when preparing source tables or reviewing whether a package has enough columns for manual follow-up. Automated statistics screening still runs on CSV/TSV/XLSX tables through `skill/biomed-research-integrity-auditor/scripts/stats_consistency_check.py` and `detectors/stats/pseudoreplication_screen.py`.

Current templates:

- `animal_tumor_volume.schema.yaml`
- `flow_percentages.schema.yaml`
- `qpcr.schema.yaml`
- `western_blot_densitometry.schema.yaml`
