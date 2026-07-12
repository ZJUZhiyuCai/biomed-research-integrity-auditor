# Changelog

## Unreleased

### Added
- Formal BRIA-Bench `independent_blinded` review tooling: sealed-test eligibility gates, two
  independently permuted reviewer packets, immutable private form locks, mapping-free agreement
  comparison, presence/comment Cohen's kappa where defined, disagreement-only third-party
  adjudication, ambiguity retention, and hash-bound final annotation generation. Public/demo cases,
  prefilled answers, administrative cues, duplicate reviewer identities, and unadjudicated
  disagreements fail closed; no independent result is claimed until human forms are completed.
- Blinded headline metrics now require a frozen finalization proof bound to the package,
  annotation, reviewer, resolution, and adjudication hashes. Headline finding recall now requires
  location as well as issue compatibility; unmatched reviewer comments count against location and
  risk-range agreement. Release artifact construction rejects symlink, hardlink, and unstable-file
  inputs rather than following them into public archives.
- Provider-neutral OpenAI-compatible BRIA-Bench direct-LLM baseline with a current DeepSeek
  `deepseek-v4-flash` configuration, three separately identified live repeats, prompt-locked
  offline fixtures, strict JSON parsing, private response caching, token/latency/cost telemetry,
  and an explicit external-data-transfer opt-in. The text-only model records image pixels as an
  unexecuted modality and uses the same normalized-observation matcher as the full pipeline.
- Direct-LLM benchmark hardening now removes expected-outcome cues from dev manuscripts, sends only
  a hash-verified no-symlink package snapshot, locks fixtures and cache entries to the complete API
  request, disables HTTP redirects, rejects repository/package/output cache overlap, validates the
  returned model and repeat identity, exposes model-reported coverage gaps to the common matcher,
  and prevents synthetic fixture runs from becoming headline-eligible.
- BRIA-Bench integration commands and docs: `make benchmark-smoke` now runs the six controlled dev
  fixtures offline with the full adapter and a 60-second per-case timeout, while manual full
  benchmark targets use all 36 public fixtures under `tmp/bria_bench_runs`. Public docs now state
  that the current corpus has no test split, no completed blinded result, zero headline-eligible
  cases, and no real-manuscript validation claim.
- Audit publication is now transactional: each output directory has a single-writer lock, detector
  artifacts are built in a sibling staging directory, failed runs preserve the previous audit, and
  successful runs atomically replace generated files while retaining unrelated user files.
- Image evidence now records working and source coordinate spaces. Multi-frame global screening
  skips ordinary within-stack frame comparisons, reports the frame cap as an R1 coverage gap, and
  presentation-derived PDF/PPTX copies are not misreported as independent cross-context reuse.
- XLSX statistical and pseudoreplication intake can locate a real header row below workbook title
  lines. Column relationship screens now require at least eight paired values and use a
  multiplicity-adjusted correlation threshold.
- Submission-QC HTML now renders Markdown tables and lists, while the PDF uses searchable CJK text;
  both human derivatives omit the machine JSON appendix and point readers to its separate file.
- Portable local parallel workstreams are now the default audit execution mode. Independent intake
  and detector workstreams run concurrently, write `workstreams.json`, and surface the effective
  execution mode in coverage, pipeline summaries, and human reports; `--execution-mode sequential`
  remains available for debugging and constrained machines.
- Lu/Xiongbin Lu public-concern benchmark subset with reference-only public status/location labels,
  a local runner that downloads permitted public materials into `tmp/`, and a committed run summary
  that contains no third-party article materials or PubPeer comments.
- Image detectors can now screen an output-local package that includes presentation-layer images
  exported from PDF/PPTX/Keynote/PSD intake artifacts. Reports disclose those derived images as
  screening inputs only, not raw records or provenance proof.
- Local patch / same-image copy-move screening now cuts exported composite figures into image-like
  subpanels before deep scanning, preserves the original figure path for provenance calibration,
  and reports skipped chart/text/axis presentation regions in audit coverage.
- Local patch / same-image copy-move screening now suppresses sparse chart/text/axis/blank
  presentation tiles in exported figure panels before tile comparison, and reports the suppression
  in audit coverage as a false-positive control rather than a clean result.
- Statistical screening now compares row-oriented source tables for preserved decimal digits and
  integer-offset patterns across paired treatment/group rows, while keeping the result capped as a
  weak R2 triage signal.
- Public supplementary source tables such as `MOESM*.xlsx` are now included in statistical
  screening even when they are supplied outside `source_data/`; pseudoreplication still requires
  an explicit `source_data/` package folder.
- Local webapp hardening: explicit local-development CORS allowlist, bounded concurrent audit
  starts, and per-file zip extraction that avoids `extractall` while preserving zip-slip and
  symlink rejection.
- Documentation now calls out the local webapp's single-trusted-user security boundary, clarifies
  `requirements.txt` versus Python 3.11 `requirements-lock.txt`, and makes Chinese onboarding
  links more visible.
- Regression tests now cover webapp CORS behavior, safe zip extraction, concurrent-audit limits,
  and report-language guardrails against accusation-style phrases.
- YAML-backed extension detector registry (`schemas/detector_registry.yaml`) for contributed
  detectors that already emit the detector-output contract, with a CLI switch to disable
  extension loading when reproducibility requires a fixed built-in detector set.
- Python 3.11 `requirements-lock.txt` for reproducible dependency installs and deployment/debugging audits.
- README data-locality/privacy statements clarifying that package contents stay local by default
  and optional external checks are opt-in metadata/query calls.
- CLI package intake now emits an R1 package-guardrail coverage gap for symlinks,
  unreadable entries, and resource-limit overages; symlinks are skipped rather than
  followed or hashed, and resource-heavy image screening is explicitly marked as not run.
- Human reports now use a PI/co-author first-page order: Quick Read, Scope, Must Resolve,
  and Materials Needed appear before workflow status, the full action queue, coverage,
  finding cards, and technical appendices.
- Weak splice-forensics triage now includes a conservative CFA-like chroma-grid prompt
  alongside ELA/JPEG residual and noise-map prompts. The new signal remains capped as
  weak R2 triage and is explicitly not sensor-pattern authentication.
- Weak splice-forensics triage now also includes a multi-quality JPEG-ghost recompression
  profile prompt for exported JPEG panels. It remains an R2-capped review prompt and is
  explicitly not robust JPEG-ghost analysis.
- Webapp package-prep filename suggestions now normalize simple zero-padding and separator
  differences, so messy names such as `Fig 02-A` and `F2A` can seed draft manifest rows when
  the match is unique. Suggestions remain unsaved typing aids until reviewed.
- Webapp package prep now surfaces ambiguous filename matches as material-prep warnings instead
  of silently skipping them or choosing one candidate. Ambiguous figure/source matches still do
  not create draft manifest rows until a user selects the correct record.
- DOCX structure intake now records review-layer warnings when Word comments, tracked revisions,
  or embedded objects/media are present. These warnings are surfaced in audit coverage, reports,
  and the webapp Package Prep panel without copying comment text or embedded object contents.
- PPTX structure intake now reads speaker notes and shape alt text in addition to visible slide
  text. Explicit figure/source paths found in those layers can seed assembly-manifest drafts and
  provenance context, while remaining declarations that require pipeline cross-checks.
- DOCX manuscript/protocol intake for package-internal text screening and writing-readiness checks.
  The extractor reads WordprocessingML body paragraphs, caption-styled paragraphs, and table cell
  text without adding a runtime dependency. Unreadable DOCX files now emit an R1 text-extraction
  coverage gap instead of being silently treated as unsupported or clean.
- Best-effort DOCX structure intake via `docx_structure.json`. The audit pipeline now records
  body paragraphs, caption-like paragraphs, and Word tables as a stable material-prep artifact
  for claim-manifest drafting; comments, track changes, embedded objects, and provenance remain
  outside this artifact's scope.
- PPTX figure-assembly text intake for explicit traceability links. When `figure_assembly/*.pptx`
  slide text contains both a figure-panel path and a raw/source-data path, the provenance parser
  records a lower-confidence expected-traceability edge and preserves the slide as evidence.
- Best-effort PPTX slide text/path structure intake via `pptx_structure.json`. The audit pipeline
  now records slide text paragraphs, package-relative path mentions, and explicit figure/source
  path pairs as a stable material-prep artifact for assembly-manifest drafting; this does not
  inspect slide geometry or prove provenance.
- Best-effort PPTX embedded-image intake via `pptx_embedded_images.json` and
  `pptx_embedded_images/`. Raster images embedded in supplied PPTX assembly files are exported as
  presentation-layer artifacts for review; they are not raw/source records or provenance proof.
- Best-effort zip-based Keynote `.key` embedded-image intake via `key_embedded_images.json` and
  `key_embedded_images/`. Opaque assembly project containers such as `.ai`, `.indd`, and
  legacy `.ppt` now emit explicit R1 coverage gaps requiring panel exports and manual review.
- Best-effort PSD flattened-preview intake via `psd_preview_images.json` and
  `psd_preview_images/`. Decodable PSD files can now export presentation-layer previews for
  human intake review while layer/mask/history provenance remains an explicit coverage gap.
- Basic GraphPad Prism `.pzfx` source-table intake for statistical screening. Plain XML PZFX tables
  with parseable columns can now feed the existing SD/SEM/n and weak-statistics checks; complex or
  unparseable Prism projects emit an R1 source-table extraction gap and still need CSV/XLSX exports.
- GraphPad Prism project intake now writes `prism_project_intake.json`, indexing parseable PZFX
  table/graph metadata and possible graph-to-table hints for manifest preparation. These hints are
  surfaced in coverage and reports as non-verified source-linkage aids, not provenance evidence.
- Flow cytometry FCS intake now writes `fcs_metadata_intake.json`, indexing event counts,
  channel/marker labels, cytometer fields, dates, and compensation-keyword presence for
  MIFlowCyt-oriented material review without validating gates, compensation, or population
  percentages.
- Best-effort PDF structure intake via `pdf_structure.json`. Machine-readable PDFs now contribute
  caption-like and table-like text blocks to audit coverage.
- Best-effort PDF embedded-image intake via `pdf_embedded_images.json` and `pdf_embedded_images/`.
  Raster images embedded in supplied PDFs are exported as presentation-layer artifacts for review;
  they are not raw/source records or provenance proof.
- Webapp package prep can now write package-root `claim_manifest.csv` rows, linking manuscript
  claims to source data, raw records, analysis code, and protocols while preserving the boundary
  that claim coverage is completeness tracking, not correctness proof.
- Webapp package prep now returns filename-based starter suggestions for `assembly_manifest.csv`
  rows and claim-manifest drafts, and can use Prism PZFX graph/table hints to seed editable
  graph-to-source drafts. Suggestions are typing aids only: they are not written until the user
  saves them, and saved rows remain declarations requiring pipeline cross-checks.
- Webapp package prep can use explicit figure/source paths found in PPTX slide text to seed
  editable `assembly_manifest.csv` and claim-manifest draft rows. PPTX slide text remains a
  declaration aid, not verified provenance.
- Webapp package prep can also use machine-readable PDF captions to seed editable claim-manifest
  draft rows with figure/table labels and manuscript page locations, while leaving source/raw
  evidence fields empty until the user links actual evidence files.
- Webapp package prep can use DOCX caption-styled figure/table text and Word table-like blocks
  to seed editable claim-manifest draft rows, again leaving source/raw evidence fields empty
  until the user links actual evidence files.
- Webapp package prep can summarize XLSX workbook sheet/header metadata and use
  figure/table-like sheet labels to seed editable claim-manifest drafts. These are
  material-prep hints only, not statistical validation or verified provenance.
- Best-effort XLSX workbook structure intake via `xlsx_structure.json`. The audit pipeline now
  records sheet names, headers, formula-cell counts, merged-cell ranges, hidden sheets, and
  figure/table-like labels for source-data and claim-manifest preparation; this is not
  statistical validation.
- Local patch / same-image copy-move screening now uses a NumPy-backed normalized
  cross-correlation path and records explicit tile/comparison budget limits. If
  a local image run is capped before all tile pairs are examined, the detector emits
  an R1 `audit_coverage_gap` rather than letting partial screening look complete.
- OpenCV ORB keypoint plus RANSAC homography screening for rotated, rescaled, cropped,
  or perspective-shifted image similarity candidates. Standard/deep scans run the new
  detector, reports summarize good matches/inliers/geometric estimates, and declared
  same-field/same-membrane matches are retained as R1 verification items instead of
  automatic clearance.
- Finding-derived action rows now include copy-ready neutral inquiry and material-request
  templates in the human report, `AUDIT_JSON_SUMMARY.json`, and action tracker CSVs so
  teams can request clarification or source records without implying intent or misconduct.
- Submission QC packets now include `audience_exports/` with editable PI, co-author, and
  journal/reviewer Markdown drafts generated from the neutral action queue.
- Re-audit comparison now writes `re_audit_diff.md`, tracks resolved/new/persisted missing
  materials, includes the Markdown diff in QC packets, and renders fixed/new/persisted lists
  in the web app.
- Action trackers now include an `attachment_reference` field so teams can record the local
  file path, folder, or link that supports a resolved or accepted action. This is a team
  follow-up reference, not uploaded evidence or an audit verdict. Correction-plan CSV/Markdown
  exports mirror the same reference for PI/co-author remediation tracking.
- The webapp can now save local follow-up attachments into
  `submission_qc_packet/attachments/` and write the packet-relative reference back to action
  tracker or image-review tracker rows. These files are local QC packet attachments, not detector
  evidence or external validation.
- The webapp Action Tracker now displays copy-ready neutral inquiry and material-request
  templates for each action row, making the finding-to-follow-up loop visible without opening
  raw CSV files.
- Image review packets now include an editable `image_review_tracker.csv` so teams can record
  reviewer, status, ImageTwin/Proofig/manual-review method, result notes, and attachment
  references for each image candidate without treating the tracker as automated clearance.
- Image review packets now include `external_tool_handoff.csv` and `EXTERNAL_TOOL_HANDOFF.md`,
  turning calibrated image candidates into a practical ImageTwin/Proofig/manual-review handoff
  with recommended review route, review question, evidence references, and data-governance notes.
- The webapp Submission Workspace now surfaces the image-review handoff queue with links to the
  handoff CSV/guide, recommended external-review route, review question, and data-governance note.
- Image-review handoff rows are now linked back to action-tracker rows through `source_finding_id`,
  so the webapp can show the linked action status, owner, and attachment reference beside each
  external-review item.
- Image-review tracker rows can now be edited in the webapp. Updates to reviewer, review status,
  external tool/method, result note, and attachment reference are written back to
  `image_review_tracker.csv` and mirrored into the handoff CSV for packet downloads.
- The webapp re-audit diff now visualizes missing-material movement as resolved, newly missing,
  and still missing, matching the JSON/Markdown diff instead of showing only persisted gaps.
- Image metadata intake now writes `image_metadata.json` with frame/channel/Z/T and OME/TIFF
  hints for supplied images, surfaces multi-frame/channel/Z-stack coverage in reports, and
  carries the artifact into the submission QC packet.
- Same-field/different-channel manifest declarations are now checked against available
  frame/channel/OME metadata. Missing multichannel acquisition metadata emits an R1
  `channel_metadata_verification_gap`; present metadata is recorded as supporting context
  only, not as image-integrity clearance.
- Weak splice-forensics triage now writes `splice_forensics_candidates.json` for standard/deep
  image runs. The detector screens exported panels for localized ELA/JPEG residual and
  noise-map outlier prompts, caps them as weak R2 forensic signals, includes them in
  human reports and image-review packets, and keeps sensor-pattern authentication beyond
  weak CFA-like triage, robust JPEG ghost, and lighting/shadow analysis as explicit
  external/specialist-review boundaries.
- Submission QC packets now include `image_review_packet/` when image files are present.
  It organizes image candidate rows, image-file hashes, copied local-patch crop evidence,
  detector payloads, positive provenance, and data-governance notes for ImageTwin/Proofig
  or manual figure review without presenting the packet as an external-search result or verdict.
- Human reports and `AUDIT_JSON_SUMMARY.audit_coverage` now include an explicit image-screening
  boundary: automated checks performed, manipulation classes not covered by current image
  detectors, and the reminder that no image finding is not complete image-forensics clearance.
- CI/eval assertions now fail by default when an audit output contains an
  `audit.detector_failure` artifact or `detector_execution_failure` candidate, so missing runtime
  dependencies cannot silently turn required detector execution into a passing regression run.
- Unit tests now import runtime detector dependencies and image/text/stat detector modules directly,
  catching stale virtual environments that omit packages such as NumPy before end-to-end audit runs.

### Fixed
- Decimal-comma numeric parsing in the statistics detector: unambiguous European decimals such
  as `1,5` and `0,049` now parse as `1.5` and `0.049`; semicolon-delimited CSV exports are
  detected; ambiguous single-comma values such as `1,234` are left unparsed and reported as an
  R1 numeric-format coverage gap instead of being silently interpreted at the wrong magnitude.
- Contextual image joining now preserves local-patch coverage-gap candidates instead of treating
  them as similarity candidates with no edges and dropping them.
- Late pipeline failures no longer discard detector work: calibration failures now write a valid
  R1 partial `calibrated_findings.json`, and report-assembly failures write a bilingual fallback
  report with a valid `AUDIT_JSON_SUMMARY` rather than leaving users with no human-readable result.
- Webapp action-tracker status editing now uses the schema-level statuses
  (`unresolved`, `resolved`, `accepted_with_reason`, `false_positive`) and routes non-actionable
  items out of the unresolved tracker while keeping the QC packet in sync.

## v0.6.2 - Local Usability and Coverage Hardening

### Added
- User-facing safety hardening for human reports: Quick Read now surfaces open actions, unreadable
  image counts, modules not run, and detector activity (`raw candidates -> positive provenance ->
  findings`), while Submission Readiness explicitly states when open actions mean the package is
  not yet ready for a complete self-audit.
- Unreadable image files now generate an R1 `provide_materials` action and appear in the report's
  Materials Needed section, so corrupt or unsupported image exports cannot be mistaken for clean
  image screening.
- Plain-language module notes in Audit Coverage explain what each executed screening module did.
- Webapp overview counters now include unresolved actions, and the R-level pill has an inline
  scope explanation.
- `make run` source-checkout launcher for non-developer local webapp use: it prepares `.venv`,
  installs dependencies, builds the frontend, starts the local server, and opens the browser.
- Assembly-manifest parser warnings now appear in Audit Coverage, Materials Needed, and the
  presubmission action queue instead of remaining only in `assembly_links.json`.
- Modality-aware panel routing for local patch / same-image copy-move screening: schematic and
  chart panels declared in `assembly_manifest.csv` are excluded from deep image screening, with
  explicit coverage records that exclusion is scope control rather than clearance. Legacy modality
  labels such as `blot`, `gel`, and `image` normalize to `western_blot` or `other`. Mixed modality
  declarations on the same panel default to deep scan with an explicit `modality_conflicts` record;
  only authoritative expected-traceability edges may control routing.
- Webapp manifest builder modality dropdown aligned to the canonical panel types.
- Scan profiles for the default audit entrypoint: `--scan-profile quick|standard|deep`.
  Quick runs skip expensive local-patch/copy-move deep image screening and external phrase search,
  and coverage records those scope limits explicitly.
- Presubmission action queue in the human report and `AUDIT_JSON_SUMMARY`, grouping follow-up
  work as must-resolve, missing-material, clarify/disclose, and low-priority review items.
- Team correction tracker exports: `resolved_actions.csv` and `accepted_with_reason.csv`, plus
  owner/status/human-note/accepted-reason fields in `unresolved_actions.csv`.
- Webapp scan-profile selection wired through to the local CLI backend.
- Product-facing console entry points: `biomed-audit`, `biomed-audit-diff`, and
  `biomed-audit-web`, while retaining existing script/module fallbacks.
- Expanded the public-data smoke benchmark to download all current ORI public image-forensics
  JPG samples, not just the original three-image subset.
- `evaluation_role` for PPPR finding labels, separating metric-bearing `recall_label` entries
  from `scope_gap` and `reference_only` records.
- A conservative low-contrast autocontrast probe for same-image copy-move screening, guarded by
  same-displacement tile clustering and positive/negative synthetic regression tests.
- Structured methodology/reporting-standard readiness output (`methodology_checklist.json` and
  `.csv`) covering wet-lab, animal, clinical, cell, flow, and omics manual-review prompts, with
  bilingual report and webapp panels.
- Separate Writing & Submission Readiness output (`writing_readiness.json` / `.csv`) for
  language placeholders, generic submission-file prompts, and opt-in DOI/reference metadata
  review. This module is rendered separately and is not merged into integrity findings.
- Webapp submission workspace surfaces claim coverage, unresolved action trackers, re-audit diffs,
  correction-plan trackers, QC-packet download links, and writing-readiness prompts.
- Frame-level screening for multi-frame TIFF-like image files in global near-duplicate and local
  patch/copy-move detectors.
- Sample-gated weak Benford-style first-digit and p-value-clustering prompts, capped as weak
  statistical triage signals.
- Release artifact tooling: `make release-artifacts`, `scripts/build_release_artifacts.py`,
  GitHub Release/frontend-smoke workflow templates, and Homebrew/macOS packaging templates.
- External literature search query provenance now records provider, query timestamp, result count,
  and per-query failure count for every executed external query.

### Changed
- Project version advanced to `0.6.2`.
- Structured assembly manifests now reject unsupported `relation_type` values with warnings instead
  of treating arbitrary strings as high-confidence expected traceability.
- The report no longer shows a misleading Quick Read row named `Coverage gap: no`; scope limits are
  represented as modules not run and detector activity instead.
- The report label for `figure_assembly` now refers to project files (`PPT/PS/AI`) rather than
  implying that an assembly manifest satisfies that category.
- Action Queue report tables now label owners as suggested owners.
- Human-facing CSV exports in the submission QC packet and webapp-created assembly manifests now
  neutralize spreadsheet formula-like cells, and webapp audit endpoints reject malformed audit IDs
  before filesystem lookup.
- Uploaded webapp zip packages now reject symlink members in addition to unsafe absolute or
  traversal paths.
- `evals/run_script_baseline.py` now runs all synthetic cases by default when neither `--case` nor
  `--package` is supplied, matching the downstream audit-output assertion workflow.
- Python support metadata now matches the documented and CI-tested requirement: Python 3.10+.
- The archived `public_smoke_2026-06-30` result now reports 13 ORI images screened, 2/2
  detector-scope ORI recall labels hit, and two retained ORI scope gaps for future
  same-section/low-contrast image recall work.
- Same-image copy-move screening preserves the existing luma path while applying the stricter
  displacement-cluster requirement only to low-contrast enhanced tiles.
- Audit coverage now records the methodology readiness checklist as executed while still stating
  that ARRIVE/CONSORT/ICMJE/MIFlowCyt/omics compliance determinations require manual review.
- The `deep` scan profile now applies stricter image similarity parameters and records those
  thresholds in coverage.
- Source/wheel packaging metadata now includes schema, skill, template, and built webapp assets
  needed by the installed CLI entry points.

## v0.6.1 - Human Bilingual Reports and Public Smoke Benchmark

### Added
- Human-first bilingual Markdown reports from the CLI assembler, with a Quick Read, scope,
  audit coverage, claim coverage, materials-needed table, verified traceability evidence,
  risk register, finding cards, action checklist, technical appendix, integrity boundary,
  and the existing machine-readable `AUDIT_JSON_SUMMARY` block.
- Regression tests that assert reports are bilingual, readable without raw detector JSON in
  the main body, preserve exactly one `AUDIT_JSON_SUMMARY` block, and summarize image evidence
  with reader-facing metrics.
- PPPR/public-concern benchmark scaffold under `benchmarks/pppr_integrity_benchmark/`, including
  a dataset card, data-ethics boundaries, finding-level label schema, source/label manifests,
  and offline scripts for RWDB/Crossref normalization, PubPeer manifest normalization, PMC OA
  local-package assembly, matched-control metadata, benchmark running, and audit-output evaluation.
- Documentation for PubPeer/RWDB/PMC OA/ORI benchmark use that explicitly treats PubPeer as case
  discovery / weak public-concern metadata, not misconduct ground truth, and forbids scraping,
  comment redistribution, and clean-paper labels for controls.
- Public-data smoke benchmark runner for ORI public image samples plus PMC Open Access S3 packages,
  with local package generation, source manifests, split/label generation, auditor execution, and
  evaluation. The archived summary (`public_smoke_2026-06-30`) records compact public-data smoke
  metrics without storing third-party article or image files.

### Changed
- Project version advanced to `0.6.1`.
- The report assembler now treats the Markdown body as the human reading surface and keeps
  raw detector payloads in supporting JSON artifacts / the final machine-readable summary.
- `make validate` now compiles nested benchmark helper scripts.

## v0.6.0 - Submission QC Packet

### Added
- Submission-QC artifact foundation: `audit_snapshot.json` with package file hashes,
  `file_hash_manifest.json`, optional `claim_coverage.json` / `.csv` from `claim_manifest.csv`,
  root-level `missing_materials.csv`, `verified_traceability.csv`, `unresolved_actions.csv`,
  and a `submission_qc_packet/` leave-behind bundle with report HTML/PDF exports and an
  `author_signoff.yaml` template.
- Re-audit comparison support through `scripts/compare_audit_runs.py` and
  `scripts/audit_package.py --compare-to`, summarizing changes in risk counts, missing materials,
  verified traceability, unresolved actions, and claim-evidence gaps without pass/fail language.
- Machine-readable submission-QC templates for `claim_manifest.csv`, author sign-off, ARRIVE 2.0,
  ICMJE authorship/disclosure, Nature image integrity, and Nature data/code/material availability.
- Local web app package-prep tools: inspect recommended package folders, create the scaffold
  without overwriting supplied files, and write `figure_assembly/assembly_manifest.csv` declared
  figure-to-source rows with package-relative path and relation-type validation.
- Package inventory guardrails for the local web app and assembly-manifest parser: bounded file/depth
  scanning, symlink skips, inventory warnings, and stricter relation-type/source-role validation so
  package prep cannot silently scan an overly broad directory or write semantically incompatible
  manifest rows.
- 16-bit TIFF real-image benchmark coverage for microscopy-derived duplicate detection.
- Required CI OCR gate: GitHub Actions installs `tesseract-ocr` and runs the scanned-PDF benchmark without skip mode.
- Same-image copy-move screening in the local patch detector, including coordinate evidence crops and contextual calibration.
- Default-orchestrator external literature phrase-search integration with deterministic fixture auto-detection, external-public Europe PMC auto mode, query/result provenance, and R1 provider-gap reporting.
- Audit Coverage / scope reporting: every report and `AUDIT_JSON_SUMMARY` now records which modules executed, which were not run (including methodology compliance and offline external search), how many image panels were screened, how many image files were unreadable, and a scope note stating that no findings in a module is not a guarantee of correctness.
- User self-audit onboarding: `docs/self-audit-guide.md` (non-developer guide to preparing materials, running the audit, reading the report, and which conclusions are not permitted), two runnable example packages under `examples/` (`minimal_package/` and `full_presubmission_package/`) with a deterministic image generator, and entry-point links from the README, SKILL, and architecture docs. A regression test asserts both examples run, expose an Audit Coverage block, carry no misconduct verdict, and (for the full package) show verified figure-to-raw traceability.
- Archived Codex-orchestrated eval evidence under `evals/llm_runs/2026-06-30-codex-orchestrated/`: 30 synthetic cases scored, 30 passed, 0 boundary violations, and 0 risk-cap violations, with a manifest that states this is not an independent third-party blinded LLM run.

### Changed
- Package manifest classification now respects the top-level recommended package directories before
  filename keyword heuristics, so `figure_assembly/assembly_manifest.csv` is no longer reported as
  a missing figure-assembly category while source-data files with `Figure_*` names remain source data.
- Project version advanced to `0.6.0`.
- Image detectors now normalize high-bit-depth grayscale inputs before hashing or tile screening, preserving contrast instead of relying on default PIL RGB conversion.
- The live skill, README, and architecture docs now describe same-image copy-move coverage and privacy-aware external literature search through `scripts/audit_package.py`.
- Implementation-boundary alignment for statistics: removed the `benford_style` and `p_value_clustering` caps from `schemas/risk_rules.yaml` because no detector emits them, and updated README, SKILL, architecture, and the module checklist to state explicitly that Benford-style first-digit analysis and p-value clustering/distribution tests are manual checks, not automated detector outputs. Only p-value range/validity is screened automatically.
- Statistical weak-signal calibration is more conservative for small samples: terminal-digit, rounding, precision, and digit-preservation screens now require at least 8 comparable values by default, and integer-count mean/SD/n feasibility checks require n >= 6 and respect reported mean/SD precision. Synthetic weak-statistics cases were updated so evals no longer depend on tiny-n triggers.

### Fixed
- Digit-preservation statistical screening now passes the shared-pair threshold explicitly instead of referencing an undefined name, restoring linear-transform/time-stratified synthetic detections after the small-sample threshold update.
- Detector JSON `errors` are now surfaced in `audit_coverage.detector_failures`, so a detector that emits a contract-valid payload with per-file errors is reported as partial coverage rather than silently appearing clean.
- Manifest suppression hardening: an author-declared figure-to-figure same-field/same-membrane relationship can no longer clear a verifiable whole-image near-duplicate. Such pairs are now flagged as an unverifiable `manifest_conflict` (R3) requiring raw-record review, instead of being downgraded to a positive-traceability completeness gap. Declared figure-to-raw/source links and genuine local-patch same-field pairs are unaffected.
- External literature phrase-search now reports an `external_literature_search_gap` R1 coverage finding whenever any query fails, even if other queries returned matches, so partial external coverage is never presented as complete.
- Statistical time-column detection no longer matches time tokens inside unrelated identifiers (for example `CD4`, `CD8`, `CD3`, `CD45`), preventing immunology/marker columns from being misread as longitudinal timepoints.
- SD-versus-SEM consistency screening now tolerates ordinary reporting precision: the mismatch tolerance accounts for the rounding half-ULP of the reported SD and SEM, so legitimately rounded summary tables are no longer flagged as SD/SEM contradictions while genuine large deviations still fire.

## v0.5.0 - Local Self-Audit Web App

### Added
- Local-first FastAPI backend under `webapp/backend` that launches `scripts/audit_package.py` as a background subprocess and serves the generated audit artifacts without recomputing risk.
- React/Vite report viewer under `webapp/frontend` with Audit Coverage, R0-R4 risk register, positive provenance evidence, missing-materials panel, evidence crop rendering, bilingual labels, local history, and delete support.
- `python3 -m webapp` launcher plus `biomed-self-audit-webapp` console entry point.
- Safe artifact serving for evidence crops, guarded zip-package extraction, and backend tests that assert the API preserves CLI artifact risk/coverage fields.
- Frontend polish for the local self-audit app: modular React components, local font assets, light/dark themes, Markdown report rendering with sanitization, zip drag/drop upload, toast feedback, evidence lightbox, module/risk filters, structured evidence metrics, traceability gaps, and materials-reviewed panels while preserving the no-verdict integrity boundary.

### Changed
- Project version advanced to `0.5.0`; README files now include the local web-app entry point.
- Web app font imports now use Latin-only IBM Plex subsets while keeping Chinese system-font fallbacks, reducing the offline frontend bundle without changing the typography model.

## v0.4.2 - OCR, Real-Image, and External-Search Benchmarks

### Added
- OCR fallback for image-only/scanned PDFs when PyMuPDF, pytesseract, and the tesseract binary are available.
- Scanned-PDF benchmark package and runner, with required mode for environments that provide the OCR runtime.
- Real-microscopy-image benchmark based on a public-domain National Cancer Institute image, replacing one purely toy benchmark path with a real image asset.
- External literature/library phrase-search detector with Europe PMC, Crossref, and fixture-backed CI modes.

### Changed
- Validation now runs the real-image benchmark and locally skips the scanned-PDF benchmark only when OCR runtime dependencies are unavailable.
- The scanned-PDF benchmark can be run in required mode by omitting `--skip-if-unavailable`.

## v0.4.1 - Intake and Reliability Hardening

### Added
- Machine-readable true-PDF text extraction for package-internal overlap screening, backed by a compressed-stream PDF fixture.
- Package-internal text overlap detector for manuscripts, supplements, prior drafts, thesis chapters, preprints, and lab-prior-paper folders.
- Section-aware text overlap risk calibration for methods boilerplate, disclosed thesis/preprint overlap, results overlap, and abstract/conclusion overlap.
- Synthetic text-overlap eval cases `case_025` through `case_030`, including methods boilerplate, disclosed thesis reuse, clean text, and prompt-injection controls.
- Script-baseline audit-output assertions for CI risk ranges and required finding tags.
- Explicit `audit_coverage_gap` R1 finding when no detector can run on a supplied package.
- Detector failure isolation: non-zero detector exits or invalid detector JSON now produce `detector_execution_failure` R1 findings while preserving other module outputs.
- XLSX source-data intake for statistical consistency and pseudoreplication screening.
- Release metadata guardrail requiring the `pyproject.toml` version to have a matching changelog entry.

### Changed
- Figure-to-figure `declared_derived_from` manifest rows no longer clear image-reuse findings as positive traceability.
- True binary PDFs are extracted as machine-readable text when possible instead of being skipped or read as raw UTF-8 bytes.
- Censored or bounded numeric values such as `<5`, `<=0.01`, `>10`, or `>=8` are no longer treated as exact observations in statistical forensic screens.
- The default audit pipeline now runs text overlap screening when supported text files are present.
- Contract validation now fails closed when `jsonschema` is unavailable instead of silently using a partial fallback.
- R3/R4 candidates missing benign explanations, resolving materials, or recommended actions are capped to R2 instead of having generic text auto-filled.
- Risk-rule configuration now rejects unsupported safety keys, applies external `missing_source_data_max`, and honors R0 `report_as: positive_evidence` routing without hiding mixed risk candidates.
- The risk calibrator now rejects legacy hand-written findings payloads; inputs must satisfy the detector-output contract.
- Source-data availability gates are aligned to supported detector inputs: CSV, TSV, and XLSX.
- CI key audit regressions now include local patch cases `case_020` through `case_024` and text-overlap cases `case_025` through `case_030`.

## v0.4.0 - Provenance-aware Local Patch Reuse Detection

### Added
- Provenance-aware local patch image reuse detector with evidence crop export.
- Local patch contextual calibration for cross-context figure reuse, declared traceability exclusions, and R1 unmapped figure-to-raw gaps.
- Synthetic cases `case_020` through `case_024` for local patch clone and negative-calibration scenarios.

## v0.3.2 - Release Hardening and Provenance Summaries

### Added
- GitHub Actions validation across Python 3.10, 3.11, and 3.12.
- Machine-readable `positive_provenance` and `traceability_gaps` in `AUDIT_JSON_SUMMARY`.
- Structured `figure_assembly/assembly_manifest.csv` and `.yaml` parsing, with CSV/YAML precedence over text manifests.
- Regression tests for risk-rule contextual tag coverage and structured manifest parsing.

### Changed
- `audit_outputs/` is ignored locally and uploaded as a CI artifact for key package regressions.

## v0.3.1 - Provenance-First Negative Calibration

### Added
- Provenance graph construction from package manifests, figure-source maps, and assembly manifests.
- Resource-node and provenance-edge contracts for package-level traceability.
- Provenance-aware contextual image calibration before risk capping.
- Positive traceability evidence reporting for declared figure-to-raw/source similarity.
- False-positive regression coverage for clean-control and prompt-injection packages.

### Changed
- `scripts/audit_package.py` now builds a provenance graph before image contextual joining.
- Declared figure-to-raw/source similarity is treated as `expected_traceability`, not image-reuse risk.
- Unmapped figure-to-raw/source similarity is capped as an `R1` traceability gap.

### Fixed
- Clean-control false positive where figure panels matching their own raw images could escalate to `R3`.
- Prompt-injection package image false positive caused by ordinary figure-to-raw similarity.

### Known Limitations
- Local patch single-package detection is not included in v0.3.2; it was added in v0.4.0.
- No text overlap, self-overlap, or plagiarism-style detector yet.
- No cross-paper image-reuse search.
- Synthetic eval packages still simplify image generation, PDF realism, and lab-record complexity.
