// Domain types for the self-audit webapp.
// Field names mirror the JSON artifacts written by scripts/audit_package.py
// (see schemas/*.schema.json). Many fields are optional because different
// detectors and modes produce different shapes.

export type Language = "zh" | "en";
export type AuditStatus = "queued" | "running" | "completed" | "failed";
export type RiskLevel = "R0" | "R1" | "R2" | "R3" | "R4";
export type Theme = "light" | "dark";

export interface ManifestRow {
  figure_panel: string;
  source_record: string;
  relation_type: string;
  modality?: string;
  notes?: string;
}

export interface AssemblyManifestInventory {
  path: string | null;
  rows: ManifestRow[];
  row_count: number;
  warnings?: string[];
}

export interface PackageInventory {
  package_path: string;
  exists: boolean;
  folders: Record<string, boolean>;
  files_by_role: Record<string, string[]>;
  file_counts: Record<string, number>;
  assembly_manifest: AssemblyManifestInventory;
  relation_types: string[];
  scope_note: string;
}

export interface PipelineSummary {
  overall_risk?: string;
  finding_count?: number;
  positive_provenance_count?: number;
  candidate_count?: number;
  [key: string]: unknown;
}

export interface AuditJob {
  audit_id: string;
  status: AuditStatus;
  mode: string;
  domains: string;
  external_literature_provider: string;
  package_path: string;
  output_dir: string;
  created_at: number;
  updated_at: number;
  returncode: number | null;
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
  detector_failures?: string[];
  audit_coverage_gap?: boolean;
  external_literature_provider?: string | null;
  scope_note?: string;
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
}
