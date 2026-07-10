// Domain types for the self-audit webapp.
// Field names mirror the JSON artifacts written by scripts/audit_package.py
// (see schemas/*.schema.json). Many fields are optional because different
// detectors and modes produce different shapes.

export type Language = "zh" | "en";
export type AuditStatus = "queued" | "running" | "cancel_requested" | "completed" | "failed" | "canceled";
export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4";
export type Theme = "light" | "dark";

export interface ExamplePackage {
  id: string;
  label: string;
  description: string;
  path: string;
}

export interface HealthResponse {
  ok: boolean;
  version: string;
  runs_root: string;
  local_first: boolean;
  example_packages?: ExamplePackage[];
}

export interface ManifestRow {
  figure_panel: string;
  source_record: string;
  relation_type: string;
  modality?: string;
  notes?: string;
}

export interface ClaimManifestRow {
  claim_id: string;
  claim_text: string;
  manuscript_location?: string;
  figure_or_table?: string;
  source_data?: string;
  raw_record?: string;
  analysis_code?: string;
  protocol?: string;
  owner?: string;
  status?: string;
}

export interface AssemblyManifestInventory {
  path: string | null;
  rows: ManifestRow[];
  row_count: number;
  warnings?: string[];
}

export interface ClaimManifestInventory {
  path: string | null;
  rows: ClaimManifestRow[];
  row_count: number;
  warnings?: string[];
}

export interface ManifestSuggestionRow extends ManifestRow {
  suggestion_reason?: string;
}

export interface ClaimManifestSuggestionRow extends ClaimManifestRow {
  suggestion_reason?: string;
}

export interface PrismGraphTableSuggestion {
  source_pzfx: string;
  graph_id?: string;
  graph_title?: string;
  table_id?: string;
  table_title?: string;
  match_basis?: string;
  interpretation?: string;
}

export interface PdfCaptionSuggestion {
  caption_id?: string;
  path: string;
  page?: string;
  kind?: string;
  label?: string;
  text?: string;
  source_type?: string;
}

export interface PdfTableBlockSuggestion {
  block_id?: string;
  path: string;
  page?: string;
  row_count?: string;
  column_count_estimate?: string;
}

export interface PptxLinkSuggestion {
  figure_panel: string;
  source_record: string;
  evidence_source?: string;
  relation_type?: string;
  interpretation?: string;
}

export interface XlsxSheetSuggestion {
  source_xlsx: string;
  sheet_name: string;
  suggested_label?: string;
  header_row?: string;
  headers?: string[];
  data_rows_scanned?: string;
  row_scan_capped?: boolean;
  interpretation?: string;
}

export interface MaterialPrepSuggestions {
  assembly_rows: ManifestSuggestionRow[];
  claim_rows: ClaimManifestSuggestionRow[];
  prism_graph_table_links?: PrismGraphTableSuggestion[];
  prism_errors?: string[];
  pdf_captions?: PdfCaptionSuggestion[];
  pdf_table_like_blocks?: PdfTableBlockSuggestion[];
  pdf_errors?: string[];
  docx_captions?: PdfCaptionSuggestion[];
  docx_table_like_blocks?: PdfTableBlockSuggestion[];
  docx_warnings?: string[];
  docx_errors?: string[];
  pptx_links?: PptxLinkSuggestion[];
  pptx_warnings?: string[];
  xlsx_sheets?: XlsxSheetSuggestion[];
  xlsx_errors?: string[];
  filename_match_warnings?: string[];
  scope_note?: string;
}

export interface PackageInventory {
  package_path: string;
  exists: boolean;
  folders: Record<string, boolean>;
  files_by_role: Record<string, string[]>;
  file_counts: Record<string, number>;
  assembly_manifest: AssemblyManifestInventory;
  claim_manifest?: ClaimManifestInventory;
  relation_types: string[];
  relation_allowed_source_roles?: Record<string, string[]>;
  modality_options?: string[];
  claim_manifest_columns?: string[];
  claim_status_options?: string[];
  material_prep_suggestions?: MaterialPrepSuggestions;
  inventory_warnings?: string[];
  scan_limit_reached?: boolean;
  scan_limits?: {
    max_files?: number;
    max_depth?: number;
  };
  scope_note: string;
}

export interface PipelineSummary {
  overall_risk?: string;
  scan_profile?: string;
  finding_count?: number;
  positive_provenance_count?: number;
  candidate_count?: number;
  [key: string]: unknown;
}

export interface ClaimCoverage {
  supplied?: boolean;
  claim_manifest?: string | null;
  claims_declared?: number;
  claims_with_source_data?: number;
  claims_with_raw_records?: number;
  claims_with_analysis_code?: number;
  claims_with_protocol_link?: number;
  claims_with_unresolved_evidence_gap?: number;
  unresolved_claims?: Array<Record<string, unknown>>;
  warnings?: string[];
  scope_note?: string;
  [key: string]: unknown;
}

export interface ActionTrackerRow {
  action_id?: string;
  action_category?: string;
  risk_level?: string;
  action_type?: string;
  item?: string;
  location?: string;
  required_action?: string;
  owner?: string;
  status?: string;
  human_note?: string;
  accepted_with_reason?: string;
  attachment_reference?: string;
  neutral_inquiry_template?: string;
  material_request_template?: string;
  source?: string;
  [key: string]: string | undefined;
}

export interface ActionTrackers {
  unresolved?: ActionTrackerRow[];
  resolved?: ActionTrackerRow[];
  accepted_with_reason?: ActionTrackerRow[];
}

export interface AttachmentUploadResult {
  attachment_reference: string;
  artifact_path: string;
  filename: string;
  stored_filename: string;
  bytes: string;
  target_type: string;
  target_id: string;
}

export interface CorrectionPlanRow {
  finding_id?: string;
  risk?: string;
  required_correction?: string;
  owner?: string;
  evidence_after_correction?: string;
  attachment_reference?: string;
  status?: string;
  source_action_id?: string;
  [key: string]: string | undefined;
}

export interface ReAuditDiff {
  scope_note?: string;
  overall_risk?: { previous?: string | null; current?: string | null };
  risk_counts?: {
    previous?: Record<string, number>;
    current?: Record<string, number>;
  };
  missing_material_count?: { previous?: number; current?: number };
  positive_provenance_count?: { previous?: number; current?: number };
  unresolved_action_count?: { previous?: number; current?: number };
  claim_evidence_gaps?: { previous?: number | null; current?: number | null };
  finding_changes?: {
    fixed_count?: number;
    new_count?: number;
    persisted_count?: number;
    fixed?: Array<Record<string, unknown>>;
    new?: Array<Record<string, unknown>>;
    persisted?: Array<Record<string, unknown>>;
  };
  material_changes?: {
    resolved_count?: number;
    new_count?: number;
    persisted_count?: number;
    resolved?: string[];
    new?: string[];
    persisted?: string[];
  };
  [key: string]: unknown;
}

export interface ImageReviewHandoffRow {
  handoff_item_id?: string;
  review_item_id?: string;
  source_finding_id?: string;
  priority?: string;
  finding_type?: string;
  risk_level?: string;
  candidate_files?: string;
  evidence_files?: string;
  recommended_tool_route?: string;
  review_question?: string;
  supporting_context?: string;
  data_governance_note?: string;
  review_status?: string;
  reviewer?: string;
  external_tool_or_method?: string;
  review_result_note?: string;
  attachment_reference?: string;
  external_result_reference?: string;
  linked_action_id?: string;
  linked_action_status?: string;
  linked_action_owner?: string;
  linked_action_attachment_reference?: string;
  linked_action_bucket?: string;
  [key: string]: string | undefined;
}

export interface ImageReviewPacketSummary {
  available?: boolean;
  files?: string[];
  candidate_count?: number;
  external_handoff_count?: number;
  handoff_rows?: ImageReviewHandoffRow[];
  external_tool_handoff_csv?: string;
  external_tool_handoff_guide?: string;
  tracker_csv?: string;
}

export interface SubmissionQCPacket {
  available?: boolean;
  files?: string[];
  audience_exports?: Record<string, string>;
  image_review_packet?: ImageReviewPacketSummary;
  download_url?: string | null;
}

export interface WritingReadiness {
  scope_note?: string;
  overall_status?: string;
  checks?: Array<Record<string, unknown>>;
  reference_checks?: Record<string, unknown>;
  language_checks?: Record<string, unknown>;
  submission_checks?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AuditJob {
  audit_id: string;
  status: AuditStatus;
  mode: string;
  scan_profile: string;
  domains: string;
  external_literature_provider: string;
  reference_check_provider?: string;
  package_path: string;
  output_dir: string;
  created_at: number;
  updated_at: number;
  returncode: number | null;
  process_pid?: number | null;
  error: string | null;
  stdout_tail: string;
  stderr_tail: string;
  pipeline_summary?: PipelineSummary | null;
}

export interface Coverage {
  modules_executed?: string[];
  modules_not_executed?: string[];
  image_panels_screened?: number;
  image_files_unreadable?: number;
  source_tables_screened?: number;
  source_table_files_attempted?: number;
  global_low_information_images_excluded?: number;
  global_low_information_image_files?: string[];
  multi_frame_screening_limits?: Array<Record<string, unknown>>;
  intra_stack_pairs_skipped?: number;
  prism_tables_indexed?: number;
  prism_graphs_indexed?: number;
  prism_possible_graph_table_links?: number;
  fcs_files_read?: number;
  fcs_files_unreadable?: number;
  fcs_total_events_reported?: number;
  fcs_parameters_indexed?: number;
  splice_forensics_images_screened?: number;
  splice_forensics_candidates?: number;
  channel_metadata_declarations_checked?: number;
  channel_metadata_verification_gaps?: number;
  psd_preview_images_extracted?: number;
  psd_preview_image_error_count?: number;
  detector_failures?: string[];
  audit_coverage_gap?: boolean;
  external_literature_provider?: string | null;
  scan_profile?: string;
  execution_mode?: string;
  parallel_workstreams_enabled?: boolean;
  workstream_count?: number;
  workstreams?: WorkstreamRecord[];
  workstream_scope_note?: string;
  scope_note?: string;
  [key: string]: unknown;
}

export interface WorkstreamRecord {
  phase?: string;
  name?: string;
  status?: string;
  elapsed_seconds?: number | null;
  output_count?: number | null;
  [key: string]: unknown;
}

export interface MethodologyCheck {
  check_id?: string;
  label_en?: string;
  label_zh?: string;
  status?: string;
  supporting_material_categories?: string[];
  supplied_material_categories?: string[];
  missing_material_categories?: string[];
  supplied_files?: Record<string, string[]>;
  recommended_action_en?: string;
  recommended_action_zh?: string;
  [key: string]: unknown;
}

export interface MethodologyModule {
  module_id?: string;
  label_en?: string;
  label_zh?: string;
  standard?: string;
  requested?: boolean;
  status?: string;
  checks?: MethodologyCheck[];
  [key: string]: unknown;
}

export interface MethodologyChecklist {
  requested_domains?: string[];
  modules?: MethodologyModule[];
  totals?: {
    modules_requested?: number;
    checks_ready_for_manual_review?: number;
    checks_partial_supporting_materials?: number;
    checks_missing_supporting_materials?: number;
    checks_not_requested?: number;
  };
  boundary_note?: string;
  boundary_note_zh?: string;
  [key: string]: unknown;
}

export interface Finding {
  finding_id?: string;
  finding_type?: string;
  title?: string;
  module?: string;
  location?: string;
  locations?: string[];
  evidence_type?: string;
  evidence?: unknown;
  evidence_strength?: string;
  calibrated_risk_level?: string;
  risk_level?: string;
  benign_explanations_considered?: string[];
  benign_explanations?: string[];
  required_materials_to_resolve?: string[];
  required_materials?: string[];
  recommended_action?: string;
  risk_caps_applied?: string[];
  requires_contextual_calibration?: boolean;
  note?: string;
  calibration_reason?: string;
  [key: string]: unknown;
}

export interface ProvenanceRow {
  provenance_id?: string;
  relation_type?: string;
  figure_panel?: string;
  source_record?: string;
  evidence_source?: string;
  risk_effect?: string;
  left?: string;
  right?: string;
  source_path?: string;
  target_path?: string;
  [key: string]: unknown;
}

export interface TraceabilityGap {
  gap_id?: string;
  finding_type?: string;
  risk_level?: string;
  location?: string;
  required_materials_to_resolve?: string[];
  [key: string]: unknown;
}

export interface AuditSummary {
  positive_provenance?: ProvenanceRow[];
  traceability_gaps?: TraceabilityGap[];
  materials_missing?: Array<string | Record<string, unknown>>;
  materials_reviewed?: string[];
  overall_risk?: string;
  // Integrity Boundary: the UI must never render verdict language. This flag
  // is consumed only as an implicit assertion; it is never shown to the user.
  misconduct_verdict_present?: boolean;
  risk_caps_applied?: string[];
  findings?: Finding[];
  audit_coverage?: Coverage;
  methodology_checklist?: MethodologyChecklist;
  claim_coverage?: ClaimCoverage;
  [key: string]: unknown;
}

export interface CalibratedFindings {
  findings?: Finding[];
  [key: string]: unknown;
}

export interface SummaryPayload {
  audit: AuditJob;
  audit_summary: AuditSummary;
  coverage: Coverage;
  calibrated_findings: CalibratedFindings;
  pipeline_summary: PipelineSummary;
  claim_coverage?: ClaimCoverage | null;
  action_trackers?: ActionTrackers;
  correction_plan?: CorrectionPlanRow[];
  re_audit_diff?: ReAuditDiff | null;
  submission_qc_packet?: SubmissionQCPacket;
  writing_readiness?: WritingReadiness | null;
}
