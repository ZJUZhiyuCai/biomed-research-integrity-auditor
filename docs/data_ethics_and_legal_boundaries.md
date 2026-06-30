# Data Ethics And Legal Boundaries

This project treats post-publication discussion data as a discovery signal, not a misconduct
verdict. Benchmark builders must follow these boundaries.

## PubPeer

Use PubPeer only through permitted channels, such as approved API access, small-scale manual
curation, or user-supplied URLs. Do not scrape the site, build a searchable copy of comments, copy
comment text into this repository, deanonymize users, or produce author/institution rankings.

Allowed benchmark fields:

- DOI / PMID / PMCID;
- PubPeer URL;
- comment count or timeline metadata when permitted;
- manually assigned issue categories;
- labels derived from the article's public materials.

Not allowed in a public dataset:

- PubPeer comment text;
- user identifiers beyond public URLs;
- downloaded PubPeer images;
- labels asserting misconduct, fraud, intent, or guilt.

## Retraction Watch / Crossref

Crossref Retraction Watch data can be used as publication-status metadata. It is article-level
metadata, not figure-level truth. A retraction reason can help stratify cases but does not identify
which image tile, row, or paragraph a detector should find unless a human label links it to public
evidence.

## PMC Open Access

Use official PMC Open Access channels and record the license per article. Do not redistribute a PDF,
figure, supplement, or XML file unless its license allows that use. If license status is unclear,
publish reconstruction scripts and metadata only.

## ORI Samples

ORI forensic image samples can be used as image-forensics unit tests. They should not be treated as
post-publication article-level benchmark cases unless the case context and reuse terms are clear.

## Negative / Comparison Cases

Never call controls "clean papers". Use:

```text
matched papers with no known public concern at snapshot date
```

Record the snapshot date and matching criteria. Absence of a PubPeer/RWDB signal is not proof that
the article has no issue.

## Public Release Rules

Public releases may include:

- identifiers;
- source URLs;
- license metadata;
- manually authored labels;
- scripts to reconstruct packages;
- PMC OA files only when license permits redistribution.

Public releases must not include:

- PubPeer comment text;
- non-OA PDFs or figures;
- private source/raw records;
- personal or institutional rankings;
- misconduct/fraud/guilt labels.
