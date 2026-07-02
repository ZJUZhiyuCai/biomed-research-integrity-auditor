import { expect, test } from "@playwright/test";

const audit = {
  audit_id: "audit-smoke-1",
  status: "completed",
  mode: "internal_presubmission",
  scan_profile: "standard",
  domains: "wetlab,animal,cell",
  external_literature_provider: "none",
  reference_check_provider: "none",
  package_path: "/tmp/example-package",
  output_dir: "/tmp/example-output",
  created_at: 1_700_000_000,
  updated_at: 1_700_000_100,
  returncode: 0,
  error: null,
  stdout_tail: "",
  stderr_tail: "",
  pipeline_summary: {
    overall_risk: "R1",
    candidate_count: 1,
    finding_count: 0,
    positive_provenance_count: 2
  }
};

const summary = {
  pipeline_summary: audit.pipeline_summary,
  coverage: {
    modules_executed: [
      "image_similarity",
      "statistics_consistency",
      "writing_submission_readiness"
    ],
    modules_not_executed: ["external literature phrase search (offline)"],
    image_panels_screened: 2,
    image_files_unreadable: 0,
    source_tables_screened: 1,
    detector_failures: [],
    audit_coverage_gap: false,
    scope_note:
      "No automated screen proves the work correct; this is a scoped review of supplied materials."
  },
  claim_coverage: {
    supplied: true,
    claims_declared: 3,
    claims_with_source_data: 2,
    claims_with_raw_records: 1,
    claims_with_analysis_code: 1,
    claims_with_protocol_link: 1,
    claims_with_unresolved_evidence_gap: 1,
    scope_note: "Claim coverage is based only on the supplied manifest."
  },
  action_trackers: {
    unresolved: [
      {
        action_id: "A-001",
        action_category: "provide_materials",
        owner: "author",
        required_action: "Attach the raw microscopy source file.",
        status: "unresolved",
        attachment_reference: "",
        neutral_inquiry_template:
          "Could the responsible owner provide the raw microscopy file for this action? This is a documentation request, not a conclusion about intent or responsibility.",
        material_request_template:
          "Please add or link the raw microscopy source file needed to resolve this action."
      }
    ],
    resolved: [],
    accepted_with_reason: []
  },
  correction_plan: [
    {
      finding_id: "A-001",
      risk: "R1",
      required_correction: "Attach the raw microscopy source file.",
      owner: "author",
      evidence_after_correction: "",
      attachment_reference: "source_data/Fig1_raw.tif",
      status: "unresolved",
      source_action_id: "A-001"
    }
  ],
  re_audit_diff: {
    scope_note: "Compared with the selected previous audit output.",
    overall_risk: { previous: "R2", current: "R1" },
    missing_material_count: { previous: 3, current: 1 },
    material_changes: {
      resolved_count: 2,
      new_count: 1,
      persisted_count: 1,
      resolved: ["source data", "protocol"],
      new: ["raw multichannel acquisition"],
      persisted: ["raw images"]
    },
    positive_provenance_count: { previous: 0, current: 2 },
    unresolved_action_count: { previous: 4, current: 1 },
    claim_evidence_gaps: { previous: 2, current: 1 }
  },
  submission_qc_packet: {
    available: true,
    files: [
      "README.md",
      "audit_snapshot.json",
      "unresolved_actions.csv",
      "writing_readiness.json"
    ],
    image_review_packet: {
      available: true,
      candidate_count: 1,
      external_handoff_count: 1,
      external_tool_handoff_csv: "image_review_packet/external_tool_handoff.csv",
      external_tool_handoff_guide: "image_review_packet/EXTERNAL_TOOL_HANDOFF.md",
      tracker_csv: "image_review_packet/image_review_tracker.csv",
      handoff_rows: [
        {
          handoff_item_id: "IMG-HANDOFF-0001",
          review_item_id: "IMG-REV-0001",
          source_finding_id: "BIOMED-PKG-0003",
          priority: "priority_review",
          finding_type: "keypoint_geometric_match",
          risk_level: "R3",
          candidate_files: "figures/Fig1A.png; figures/Fig4C.png",
          recommended_tool_route:
            "ImageTwin/Proofig or local feature-match review for rotated, resized, cropped, or perspective-shifted similarity",
          review_question:
            "Does an external image-review tool or manual feature review support an expected explanation for this relationship?",
          data_governance_note:
            "Check institutional, journal, patient/privacy, and collaborator rules before uploading images or raw records to any external service.",
          review_status: "unresolved",
          reviewer: "image_specialist",
          external_tool_or_method: "ImageTwin manual review",
          review_result_note: "pending local review",
          attachment_reference: "external_reviews/Fig1A_Fig4C.pdf",
          linked_action_id: "A-001",
          linked_action_status: "unresolved",
          linked_action_owner: "author",
          linked_action_attachment_reference: "source_data/Fig1_raw.tif"
        }
      ]
    }
  },
  writing_readiness: {
    scope: "writing_submission_readiness_only",
    overall_status: "review_needed",
    scope_note:
      "Writing readiness is an author workflow aid and is separate from R0-R4 integrity risk calibration.",
    checks: [
      { check_id: "references_present", status: "ready_for_manual_review" },
      { check_id: "doi_review", status: "manual_review_required" }
    ]
  },
  audit_summary: {
    audit_mode: "internal_presubmission",
    materials_reviewed: ["manuscript", "source_data"],
    materials_missing: [],
    overall_risk: "R1",
    misconduct_verdict_present: false,
    risk_caps_applied: [],
    positive_provenance: [
      {
        provenance_id: "PV-1",
        relation_type: "source_image_for_panel",
        figure_panel: "figures/Fig1A.png",
        source_record: "raw_images/Fig1A.tif",
        evidence_source: "assembly_manifest.csv",
        risk_effect: "expected_traceability"
      }
    ],
    traceability_gaps: [],
    findings: [],
    methodology_checklist: {
      requested_domains: ["wetlab"],
      totals: {
        modules_requested: 1,
        checks_ready_for_manual_review: 1,
        checks_partial_supporting_materials: 0,
        checks_missing_supporting_materials: 0,
        checks_not_requested: 0
      },
      modules: [],
      boundary_note: "Methodology checklist entries require author review."
    }
  },
  calibrated_findings: { findings: [] }
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ json: {} });
  });
  await page.route("**/api/audits", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { audits: [audit] } });
      return;
    }
    await route.fulfill({ json: audit });
  });
  await page.route("**/api/audits/audit-smoke-1", async (route) => {
    await route.fulfill({ json: audit });
  });
  await page.route("**/api/audits/audit-smoke-1/summary", async (route) => {
    await route.fulfill({ json: summary });
  });
  await page.route("**/api/audits/audit-smoke-1/report.md", async (route) => {
    await route.fulfill({
      contentType: "text/markdown",
      body: "# Human Review Report\n\n## Audit Coverage\n\nScoped review only."
    });
  });
});

test("renders human-facing submission workspace without boundary-breaking language", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN" }).click();

  await expect(page.getByRole("heading", { name: "Submission Workspace" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Claim Coverage" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Action Tracker" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Correction Plan" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Attachment" })).toHaveCount(2);
  await expect(page.getByText("Neutral inquiry")).toBeVisible();
  await expect(page.getByText("Material request")).toBeVisible();
  await expect(page.getByText(/documentation request, not a conclusion about intent/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Re-audit Diff" })).toBeVisible();
  await expect(page.getByText("Resolved materials")).toHaveCount(2);
  await expect(page.getByText("New missing materials")).toHaveCount(2);
  await expect(page.getByText("Still missing materials")).toHaveCount(2);
  await expect(page.getByText("raw multichannel acquisition")).toBeVisible();
  await expect(page.getByRole("heading", { name: "External Image Review" })).toBeVisible();
  await expect(page.getByText("ImageTwin/Proofig or local feature-match review")).toBeVisible();
  await expect(page.getByText("Check institutional, journal, patient/privacy")).toBeVisible();
  await expect(
    page.locator(".image-handoff-table").getByRole("cell", { name: /A-001/ })
  ).toBeVisible();
  await expect(page.getByText("source_data/Fig1_raw.tif")).toHaveCount(2);
  await expect(page.locator('input[value="ImageTwin manual review"]')).toBeVisible();
  await expect(page.locator('input[value="external_reviews/Fig1A_Fig4C.pdf"]')).toBeVisible();
  await expect(page.getByRole("link", { name: /Open handoff CSV/i })).toHaveAttribute(
    "href",
    "/api/audits/audit-smoke-1/artifact/submission_qc_packet/image_review_packet/external_tool_handoff.csv"
  );
  await expect(page.getByRole("heading", { name: "QC Packet" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Writing & Submission Readiness" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Download QC Packet/i })).toHaveAttribute(
    "href",
    "/api/audits/audit-smoke-1/submission-qc-packet.zip"
  );
  await expect(page.getByRole("link", { name: /Download Markdown/i })).toHaveAttribute(
    "href",
    "/api/audits/audit-smoke-1/artifact/correction_plan.md"
  );

  const visibleText = (await page.locator("body").innerText()).toLowerCase();
  expect(visibleText).not.toMatch(/\b(pass|fail|fraud|verdict|score)\b/);
});

test("package prep exposes claim manifest creation controls", async ({ page }) => {
  await page.route("**/api/packages/inspect", async (route) => {
    await route.fulfill({
      json: {
        inventory: {
          package_path: "/tmp/example-package",
          exists: true,
          folders: {
            figures: true,
            raw_images: true,
            figure_assembly: true,
            source_data: true,
            protocols: true,
            statistics_code: true,
            supplementary: false,
            ethics_irb: false
          },
          files_by_role: {
            figures: ["figures/Fig1A.png"],
            raw_images: ["raw_images/Fig1A.tif"],
            figure_assembly: [],
            source_data: ["source_data/Fig1.csv"],
            protocols: ["protocols/microscopy.md"],
            statistics_code: ["statistics_code/fig1.ipynb"],
            supplementary: [],
            ethics_irb: [],
            other: []
          },
          file_counts: {
            figures: 1,
            raw_images: 1,
            figure_assembly: 0,
            source_data: 1,
            protocols: 1,
            statistics_code: 1,
            supplementary: 0,
            ethics_irb: 0,
            other: 0
          },
          assembly_manifest: { path: null, rows: [], row_count: 0, warnings: [] },
          claim_manifest: {
            path: "claim_manifest.csv",
            row_count: 1,
            warnings: [],
            rows: [
              {
                claim_id: "C-001",
                claim_text: "Treatment increases signal intensity.",
                manuscript_location: "Results p.4",
                figure_or_table: "Figure 1A",
                source_data: "source_data/Fig1.csv",
                raw_record: "raw_images/Fig1A.tif",
                analysis_code: "statistics_code/fig1.ipynb",
                protocol: "protocols/microscopy.md",
                owner: "first_author",
                status: "ready"
              }
            ]
          },
          relation_types: ["declared_derived_from"],
          relation_allowed_source_roles: { declared_derived_from: ["raw_images", "source_data"] },
          modality_options: ["microscopy", "other"],
          claim_manifest_columns: [
            "claim_id",
            "claim_text",
            "manuscript_location",
            "figure_or_table",
            "source_data",
            "raw_record",
            "analysis_code",
            "protocol",
            "owner",
            "status"
          ],
          claim_status_options: ["draft", "ready", "complete", "resolved", "needs_review"],
          inventory_warnings: [],
          scan_limit_reached: false,
          scan_limits: { max_files: 5000, max_depth: 12 },
          scope_note:
            "Assembly and claim manifest rows are audit material, not proof of correctness."
        }
      }
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "EN" }).click();
  await page.getByLabel("Package path").fill("/tmp/example-package");
  await page.getByRole("button", { name: "Inspect Package" }).click();

  await expect(page.getByRole("heading", { name: "Claim manifest" })).toBeVisible();
  await expect(page.getByText("claim_manifest.csv", { exact: true })).toBeVisible();
  await expect(page.getByText("Treatment increases signal intensity.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add Claim" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Write claim_manifest" })).toBeVisible();
});
