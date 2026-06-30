# Example Self-Audit Packages

Runnable teaching examples for first-time users. **These are synthetic teaching samples**
(the images are generated textures, not real microscopy), not real audits.

Read the full walkthrough in [`../docs/self-audit-guide.md`](../docs/self-audit-guide.md).

## Packages

- `minimal_package/` — the smallest runnable package (a manuscript text and one source-data
  table). Use it to confirm the tool runs and to see the Audit Coverage section. Expect overall
  risk `R1` with completeness gaps.
- `full_presubmission_package/` — a realistic pre-submission layout with figures, raw images, a
  structured `figure_assembly/assembly_manifest.csv`, source data, protocols, and analysis
  notes. It also includes `claim_manifest.csv` with two claim-to-evidence rows. Expect overall
  risk `R1`, two verified figure-to-raw traceability links, claim coverage with no unresolved
  claim-evidence gaps, and an honest Missing Materials list.

## Run

```bash
python3 scripts/audit_package.py examples/minimal_package --output-dir audit_outputs/minimal
python3 scripts/audit_package.py examples/full_presubmission_package --output-dir audit_outputs/full
```

## Regenerate the images (optional)

The PNGs are committed so the examples run as-is. To regenerate them deterministically:

```bash
python3 examples/generate_example_assets.py
```

## Remember

A clean result on these examples is **"nothing flagged within scope"**, not **"proven
correct"**. Always read the Audit Coverage section to see what was and was not checked.
