# Benign Explanations and Resolution Materials

Use this file before assigning R3 or R4. A plausible benign explanation does not eliminate a concern; it defines what materials can resolve it.

## Image Similarity

Possible benign explanations:

- Same loading control intentionally reused for samples run on the same membrane.
- Same membrane reprobed for a related target.
- Adjacent crop from one larger image.
- Shared representative image disclosed in legend.
- PDF compression or resizing artifact.
- Duplicate placeholder accidentally left during figure assembly.
- Supplementary figure repeats main figure intentionally.

Materials that resolve:

- Uncropped original image or full membrane.
- Acquisition metadata.
- Figure assembly file.
- Sample map and lane map.
- Lab notebook or ELN entry.
- Explicit figure legend disclosure.

## Graph and Source-Data Mismatch

Possible benign explanations:

- Graph uses normalized values while source table contains raw values.
- SEM vs SD confusion in label only.
- Rounding difference.
- Excluded sample documented elsewhere.
- Technical replicate averaged before biological replicate summary.
- Different batch or cohort not obvious from filename.

Materials that resolve:

- Analysis code or GraphPad/Prism file.
- Raw and normalized source tables.
- Exclusion log.
- Sample metadata.
- Statistical analysis plan.

## Statistical Pattern

Possible benign explanations:

- Instrument exports fixed decimal places.
- Background subtraction creates repeated offsets.
- Normalization to control creates fixed ratios.
- QC filtering truncates distribution.
- Small n makes patterns unstable.
- Baseline balancing due to randomization stratification.

Materials that resolve:

- Raw instrument export.
- Preprocessing code.
- QC rule documentation.
- Batch logs and sample map.

## Methodology Gap

Possible benign explanations:

- Details are in protocol or supplement not included in package.
- Journal word limits compressed method details.
- Legacy data predate current reporting standard.

Materials that resolve:

- Full protocol.
- Supplementary methods.
- Ethics/IRB/animal approval.
- Registry entry and protocol.
- Reagent and cell-line records.
