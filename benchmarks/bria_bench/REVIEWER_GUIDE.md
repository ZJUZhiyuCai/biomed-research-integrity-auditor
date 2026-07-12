# BRIA-Bench Reviewer Guide

## Scope Boundary

This packet has `packet_scope` set to `workflow_demo_only`. The current 36 public fixtures can test packet mechanics and reviewer usability, but they are not independent blinded evidence and must not support a blinded headline claim. The package SHA-256 values are public and joinable to the published fixture tree. Administrative `PACKAGE_NOTE` material can also cue workflow state.

A future independent evaluation requires a sealed private corpus, manifest, and hash index. Those records must remain sealed until forms are locked, and corpus identifiers and answer annotations must remain outside every reviewer packet. Independent results require the process below with two independent reviewers.

## Publication Recovery

The exporter publishes the external mapping before the packet directory and never overwrites either target. If packet publication fails after the mapping is committed, an intentional mapping-only state may remain: the mapping exists at its external path while the packet target is absent. Keep that mapping external and protected with mode `0600`.

To rerun, either delete the mapping and reuse the original absent targets, or retain it as a recovery record and choose a new absent mapping path. Confirm that the packet target is absent before the rerun; atomic no-replace publication still applies.

## Independent Review

Two independent reviewers examine the supplied materials separately. Neither reviewer has access to the other reviewer's forms. Each reviewer records direct observations, where they occur, why they matter scientifically, plausible benign explanations, material needed to resolve uncertainty, and a proportionate next action.

Use one row per observation. `presence` is `present`, `absent`, or `insufficient_materials`. Use `major` or `minor` only for a present observation; use `materials_request` when materials are insufficient. A present observation needs a specific location and narrative. An absent response is the sole row in its form.

Review the supplied record, not presumed motives. Do not infer intent or author behavior. Keep uncertainty visible and distinguish an observed feature from an explanation that still needs supporting material.

After both forms are locked, an external adjudicator resolves disagreements against the supplied materials and records the resolution outside the original forms. Forms must not be revised to manufacture agreement.
