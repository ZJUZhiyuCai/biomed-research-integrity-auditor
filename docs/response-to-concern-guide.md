# Response-To-Concern Guide / 关注回应指南

Use this mode when a journal, reviewer, reader, or post-publication forum asks about a figure, source table, image panel, statistical value, or text passage.

中文提示：当期刊、审稿人、读者或公开平台对图像、source data、统计值或文本提出疑问时，使用本流程。

## Boundary / 边界

- The audit helps organize evidence and gaps; it does not decide intent, responsibility, or misconduct.
- Treat every output as a candidate or completeness prompt until the original records are reviewed.
- Use neutral language: "we reviewed", "the supplied records show", "we could not verify from the supplied files", "we will correct/update".

## Package Layout / 材料目录

Start from the usual pre-submission package, then add a concern log:

```text
concern_response_package/
  manuscript/ or manuscript.pdf
  figures/
  raw_images/
  source_data/
  figure_assembly/
    assembly_manifest.csv
  protocols/
  concern_log.csv
```

Suggested `concern_log.csv` columns:

```csv
concern_id,source,manuscript_location,concern_text,related_files,owner,status,response_note
C001,journal email,Figure 2B,"possible duplicated region","figures/Figure_2B.png;raw_images/acq_2B.tif",figure_preparer,open,
```

## Run / 运行

Web app: choose `response_to_concern` mode and use `standard` or `deep` for image-focused questions.

CLI:

```bash
biomed-audit concern_response_package \
  --mode response_to_concern \
  --scan-profile deep \
  --output-dir audit_outputs/concern_response
```

## Read The Output / 如何读结果

Read in this order:

1. `START_HERE.md`
2. `audit-report.md`
3. `unresolved_actions.csv`
4. `verified_traceability.csv`
5. `calibrated_findings.json` only when you need the structured evidence payload.

For each concern, write down:

- What material was reviewed.
- Whether source/raw records support the explanation.
- What remains missing or unverifiable.
- Whether a correction, legend clarification, source-data upload, or replacement figure is needed.

## Response Drafting / 回应措辞

Use the template at:

`skill/biomed-research-integrity-auditor/templates/author-query-letter.md`

Keep the response factual:

- "The raw image for Figure 2B is supplied as ..."
- "The repeated region corresponds to the same field imaged in two channels, documented by ..."
- "We could not verify this from the submitted files; we are providing the missing source record ..."
- "We will update the legend/source data to clarify ..."

Avoid:

- Declaring misconduct or absence of misconduct.
- Claiming the tool has proven a figure correct.
- Hiding unresolved gaps behind a low risk band.

