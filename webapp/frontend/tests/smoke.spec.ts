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
        status: "unresolved"
      }
    ],
    resolved: [],
    accepted_with_reason: []
  },
  re_audit_diff: {
    scope_note: "Compared with the selected previous audit output.",
    overall_risk: { previous: "R2", current: "R1" },
    missing_material_count: { previous: 3, current: 1 },
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
    ]
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
  await expect(page.getByRole("heading", { name: "Re-audit Diff" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "QC Packet" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Writing & Submission Readiness" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Download QC Packet/i })).toHaveAttribute(
    "href",
    "/api/audits/audit-smoke-1/submission-qc-packet.zip"
  );

  const visibleText = (await page.locator("body").innerText()).toLowerCase();
  expect(visibleText).not.toMatch(/\b(pass|fail|fraud|verdict|score)\b/);
});
