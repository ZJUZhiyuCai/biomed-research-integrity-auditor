# Labeling Guide

## Core Rule

Label public, reproducible evidence. Do not label misconduct, intent, fraud, guilt, or author
character.

## Article-Level Labels

Use `labels/article_level_labels.csv` for article-level metadata:

- identifiers: DOI, PMID, PMCID;
- source: PubPeer, RWDB, Crossref, PMC OA, ORI;
- publication status: retracted, corrected, expression of concern, reinstated;
- public-concern status at snapshot date;
- license and OA status.

Article-level labels do not imply a detector should find a specific image or table issue.

## Finding-Level Labels

Use JSON Lines with one object per label. Required fields are documented in `labels.schema.json`.

Each label should answer:

1. What public material supports the observation?
2. Where is it located?
3. Which issue type is it?
4. Can it be verified from public materials alone?
5. What benign explanations remain possible?
6. What materials are needed to resolve it?
7. What risk range should the auditor produce under R0-R4 rules?

## Issue Types

Recommended values:

- `image_global_similarity`
- `image_local_reuse`
- `same_image_copy_move`
- `western_blot_or_gel`
- `microscopy_reuse`
- `statistics_or_numeric`
- `text_overlap`
- `reporting_gap`
- `methodological_concern`
- `publication_status`
- `metadata_status`

## Expected Risk

Use ranges when appropriate:

- `R1`
- `R2`
- `R2_or_R3`
- `R3`
- `R3_or_R4`

R4 should be reserved for direct contradiction inside supplied materials, not merely a PubPeer
comment or missing raw data.

## Adjudication

Use at least two annotators for release-grade labels:

- annotator A;
- annotator B;
- adjudicator for disagreements.

Record disagreement notes in `labels/adjudication_notes.md`.
