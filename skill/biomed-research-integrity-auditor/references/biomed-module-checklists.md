# Biomedical Audit Module Checklists

## 1. Package Completeness Audit

Inventory:

- Manuscript PDF or DOCX.
- Supplementary files.
- Source data tables.
- Final figures.
- Figure assembly files: PPTX, AI, PSD, INDD, SVG, editable PDF.
- Raw images: TIFF, CZI, ND2, LIF, OIB, OIR, SVS, VSI, PNG/JPEG exports.
- Raw numerical data: CSV, XLSX, instrument exports.
- Protocols, ELN/notebook pages, batch logs, sample maps.
- Statistical code.
- Ethics approval, IRB approval, animal protocol, clinical registration.
- Repository accessions and sample metadata.

Output a missing-materials matrix. Do not continue as if complete when source data are missing.

## 2. Figure-Source Traceability Audit

For each figure panel, ask:

- What claim does this panel support?
- What source data or raw image supports it?
- Is the panel present in source data with matching labels, units, groups, and n?
- Can graph values be recomputed from source data?
- Can representative images be traced to raw acquisition files?
- Are scale bars, magnification, channel labels, and exposure conditions documented?
- Are cropped blots accompanied by uncropped source images?
- Are assembly edits disclosed when needed?

## 3. Image Integrity Audit

Prioritize candidate detection for:

- Western blot and gel lanes.
- Microscopy, IF, IHC, histology, pathology.
- Wound-healing, migration, invasion, colony-formation images.
- Animal photographs.
- Flow cytometry plots.

Look for:

- Duplicate regions within or across panels.
- Rotation, flipping, resizing, contrast changes, or cropping of repeated regions.
- Clone/healing artifacts.
- Abrupt background changes.
- Undisclosed non-adjacent lane splicing.
- Loading control reuse across unrelated experiments.
- Scale bar inconsistencies.
- Same image described as different group, time point, cell line, tissue, or treatment.

Every image finding must identify coordinates, candidate files, method, and required raw materials.

## 4. Numerical and Statistical Consistency Audit

Prefer direct checks:

- Source data to graph values.
- Mean, SD, SEM, n internal consistency.
- P value roughly compatible with stated test.
- Figure labels and source-data group labels match.
- Biological vs technical replicate distinction.
- Animal, culture, field-of-view, and cell-count denominators.
- Multiple-testing correction where many comparisons are made.
- Exclusion and missing data consistency.

Weak triage checks:

- Terminal-digit patterns.
- Repeated decimals.
- Mechanical differences or ratios.
- Very small variance.
- P value clustering near thresholds.

Weak checks should not drive R4 findings.

## 5. Methodology and Compliance Audit

Animal:

- ARRIVE-style design, n rationale, exclusion, randomization, blinding, outcome, statistics, sex/age/strain, welfare, ethics.

Clinical:

- Registration, protocol, SAP, IRB, consent, outcomes, CONSORT flow, adverse events, data sharing.

Cell:

- Source, STR, mycoplasma, passage, antibody RRID, catalog/lot, controls.

Flow:

- FCS, workspace/gates, compensation, controls, instrument, software, denominator.

Omics:

- Accession, raw data/counts, metadata, batch, normalization, analysis code, multiple testing.
