# Independent Blinded Review Workflow / 独立盲评工作流

This coordinator workflow creates auditable labels from two locked independent reviews and, where needed, a third adjudicator. It does not prove that a reviewer is independent; the coordinator must recruit eligible reviewers, record conflicts outside Git, and keep identities separate from pseudonymous IDs.

本流程用于把两份锁定的独立复核表，以及必要时的第三人裁决，形成可审计标签。软件不能证明复核者真正独立；协调者仍须在 Git 之外完成招募、利益冲突记录和真实身份与匿名 ID 的隔离。

## Current Boundary / 当前边界

The public repository still has no formal `test` split and no completed independent result. The commands below are ready for a sealed private corpus; they must not be run on the 36 public workflow fixtures to create a headline claim.

当前公开仓库仍没有正式 `test` split，也没有已经完成的独立盲评结果。下列命令供仓库外的封存私有语料使用，不能把 36 个公开 workflow fixtures 包装成 headline 结果。

Every selected source case must be frozen with:

- `track: blinded_challenge`;
- `split: test`;
- `headline_eligible: false` before review;
- annotation `review_status: independent_pending`;
- an empty `expected_observations` array;
- no `reviewer_ids`, `adjudicator_id`, legacy answer contract, or `PACKAGE_NOTE` cue.

## 1. Export Two Packets / 导出两份盲包

Create two different 32-byte hexadecimal seeds and keep them in mode `0600`. Keep the packet directories, mappings, seeds, and private manifest outside the repository.

```bash
python -m benchmarks.bria_bench.cli reviewer-packet \
  --packet-scope independent_blinded \
  --manifest /private/sealed/benchmark_manifest.json \
  --case sealed_001 --case sealed_002 \
  --output-dir /private/review/packet-a \
  --mapping-output /private/review/mapping-a.json \
  --seed-file /private/review/seed-a

python -m benchmarks.bria_bench.cli reviewer-packet \
  --packet-scope independent_blinded \
  --manifest /private/sealed/benchmark_manifest.json \
  --case sealed_001 --case sealed_002 \
  --output-dir /private/review/packet-b \
  --mapping-output /private/review/mapping-b.json \
  --seed-file /private/review/seed-b
```

Give one packet to each reviewer. Reviewers must not see mappings, source IDs, seeds, tool or LLM output, detector configuration, or the other reviewer's forms.

## 2. Lock Completed Forms / 锁定复核表

Create pseudonymous ID files such as `BRIA-REV-A0000001`, with mode `0600`. Do not put names, emails, institutions, or contact details in these files.

```bash
python -m benchmarks.bria_bench.cli reviewer-lock \
  --packet-dir /private/review/packet-a \
  --reviewer-id-file /private/review/reviewer-a.id \
  --output-dir /private/review/locked-a \
  --locked-at 2026-07-12T10:00:00Z

python -m benchmarks.bria_bench.cli reviewer-lock \
  --packet-dir /private/review/packet-b \
  --reviewer-id-file /private/review/reviewer-b.id \
  --output-dir /private/review/locked-b \
  --locked-at 2026-07-12T10:05:00Z
```

Locking validates every form, re-hashes every supplied package, rejects privacy/accusation language and extra files, canonicalizes the forms, and publishes a new private directory without overwriting an earlier lock. Original forms are never edited by later stages.

## 3. Compare / 比较一致性

```bash
python -m benchmarks.bria_bench.cli reviewer-compare \
  --submission-a /private/review/locked-a \
  --submission-b /private/review/locked-b \
  --output-dir /private/review/comparison \
  --compared-at 2026-07-12T11:00:00Z
```

The comparison stage does not read either mapping or any answer annotation. It aligns the two independently permuted packets by the sealed package hash and reports raw presence, comment-class, location, and risk-range agreement. Cohen's kappa is reported only for nominal presence and comment-class units; constant marginals remain explicitly undefined.

## 4. Adjudicate Only Disagreements / 只裁决分歧

If `adjudication_template.json` contains cases, give the relevant packet materials and the two locked comments to a third reviewer. Copy the template to a new private file, set `status` to `completed`, use a distinct pseudonym such as `BRIA-ADJ-C0000003`, record the timestamp, and mark each case as `resolved` with complete final rows or `ambiguous` with a rationale. Keep the completed file in mode `0600`.

Do not revise either original reviewer submission to manufacture agreement. If the adjudicator cannot resolve the evidence, retain `ambiguous`.

## 5. Finalize / 冻结最终标签

```bash
python -m benchmarks.bria_bench.cli reviewer-finalize \
  --comparison /private/review/comparison/comparison.json \
  --submission-a /private/review/locked-a \
  --mapping-a /private/review/mapping-a.json \
  --submission-b /private/review/locked-b \
  --mapping-b /private/review/mapping-b.json \
  --manifest /private/sealed/benchmark_manifest.json \
  --adjudication /private/review/completed-adjudication.json \
  --output-dir /private/review/finalized \
  --frozen-at 2026-07-12T12:00:00Z \
  --benchmark-version 1.0.0
```

Omit `--adjudication` only when the comparison contains zero disagreements. Finalization is the first stage that reads private mappings. It verifies both locked submissions, both mappings, the frozen source manifest, package and pending-annotation hashes, then emits immutable final annotations plus an aggregate agreement summary. Unresolved cases receive `review_status: ambiguous` and remain ineligible for manifest promotion.

Before public release, independently review the finalization output, place approved annotations into the release corpus, and copy the scrubbed `finalization.json` to a versioned path such as `review_proofs/review_proof_v1.json`. For each promoted case, set `review_proof_path` to that file and set `headline_eligible: true` only for `independent_adjudicated` cases. `freeze` records `review_proof_sha256`; evaluation then verifies the proof's package hash, annotation hash, reviewer IDs, freeze time, resolution source, and any adjudicator before admitting the case to headline metrics. Archive the original private locks and never rewrite a published v1 test label after model or detector tuning.

## Never Commit / 严禁提交

- packet directories and seeds;
- reviewer mappings and real identity records;
- locked raw forms and comparison details;
- completed adjudication and private rationale;
- private source manifest or sealed cases before unsealing;
- API caches, local paths, tokens, or contact details.

Only intentionally scrubbed aggregate agreement, frozen release hashes, anonymous reviewer IDs, final public annotations, and versioned benchmark reports may enter a public release.
