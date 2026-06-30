// Workspace: audit header with overview counters, live/failed logs, and the
// panel stack (coverage, provenance+missing, findings, report). Counters are
// neutral counts only — never a score or verdict.

import { RefreshCw, Trash2 } from "lucide-react";
import type { AuditJob, ManifestRow, PackageInventory, SummaryPayload } from "../types";
import type { Labels } from "../i18n";
import { CoveragePanel } from "./CoveragePanel";
import { FindingsPanel } from "./FindingsPanel";
import { ProvenancePanel } from "./ProvenancePanel";
import { MissingMaterialsPanel } from "./MissingMaterialsPanel";
import { ReportPanel } from "./ReportPanel";
import { PackagePrepPanel } from "./PackagePrepPanel";
import { MethodologyPanel } from "./MethodologyPanel";
import { SubmissionWorkspacePanel } from "./SubmissionWorkspacePanel";
import { WorkspaceSkeleton } from "./Skeleton";
import { EmptyState, StatusPill } from "./primitives";

interface WorkspaceProps {
  t: Labels;
  audit: AuditJob | null;
  detail: SummaryPayload | null;
  report: string;
  loading: boolean;
  error: string | null;
  packagePath: string;
  packageInventory: PackageInventory | null;
  packagePrepLoading: boolean;
  onInspectPackage: () => void;
  onScaffoldPackage: () => void;
  onSaveManifest: (rows: ManifestRow[]) => Promise<void>;
  onRefresh: () => void;
  onDelete: () => void;
  onEvidence: (images: string[], index: number) => void;
}

function statusLabel(t: Labels, status: string): string {
  const key = status as keyof Labels;
  return typeof t[key] === "string" ? (t[key] as string) : status;
}

export function Workspace(props: WorkspaceProps) {
  const { t, audit, detail, report, error } = props;

  if (!audit) {
    return (
      <main className="workspace">
        <PackagePrepPanel
          t={t}
          packagePath={props.packagePath}
          inventory={props.packageInventory}
          loading={props.packagePrepLoading}
          onInspect={props.onInspectPackage}
          onScaffold={props.onScaffoldPackage}
          onSaveManifest={props.onSaveManifest}
        />
        {error && <div className="error-box">{error}</div>}
        <EmptyState text={t.noSelection} />
      </main>
    );
  }

  const summary = detail?.pipeline_summary;
  const showCounters =
    summary &&
    (summary.candidate_count !== undefined ||
      summary.finding_count !== undefined ||
      summary.positive_provenance_count !== undefined);
  const loadingDetail = props.loading && !detail && audit.status === "completed";

  return (
    <main className="workspace">
      <PackagePrepPanel
        t={t}
        packagePath={props.packagePath}
        inventory={props.packageInventory}
        loading={props.packagePrepLoading}
        onInspect={props.onInspectPackage}
        onScaffold={props.onScaffoldPackage}
        onSaveManifest={props.onSaveManifest}
      />

      <header className="audit-header">
        <div className="audit-heading">
          <p className="eyebrow">{audit.mode} · {audit.scan_profile}</p>
          <h2 className="mono">{audit.package_path}</h2>
        </div>
        <div className="header-actions">
          <StatusPill status={audit.status} label={statusLabel(t, audit.status)} />
          {audit.pipeline_summary?.overall_risk && (
            <span className="risk-pill">{audit.pipeline_summary.overall_risk}</span>
          )}
          <button
            type="button"
            className="icon-button"
            onClick={props.onRefresh}
            aria-label={t.refresh}
          >
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          {audit.status !== "running" && audit.status !== "queued" && (
            <button
              type="button"
              className="icon-button danger"
              onClick={props.onDelete}
              aria-label={t.delete}
            >
              <Trash2 size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </header>

      {error && <div className="error-box">{error}</div>}

      {audit.status === "failed" && (
        <section className="panel">
          <h3>{t.failureLog}</h3>
          <pre className="log-pre">{audit.error || audit.stderr_tail || audit.stdout_tail}</pre>
        </section>
      )}

      {(audit.status === "queued" || audit.status === "running") && (
        <section className="panel live-panel">
          <h3>{statusLabel(t, audit.status)}</h3>
          <pre className="log-pre">{audit.stdout_tail || audit.stderr_tail || t.waiting}</pre>
        </section>
      )}

      {loadingDetail && <WorkspaceSkeleton />}

      {detail && !loadingDetail && (
        <>
          {showCounters && (
            <div className="overview-row">
              {summary!.candidate_count !== undefined && (
                <OverviewStat label={t.candidates} value={summary!.candidate_count} />
              )}
              {summary!.finding_count !== undefined && (
                <OverviewStat label={t.findingsCount} value={summary!.finding_count} />
              )}
              {summary!.positive_provenance_count !== undefined && (
                <OverviewStat label={t.provenance} value={summary!.positive_provenance_count} />
              )}
            </div>
          )}
          <CoveragePanel coverage={detail.coverage} t={t} />
          <SubmissionWorkspacePanel
            auditId={audit.audit_id}
            claimCoverage={detail.claim_coverage || detail.audit_summary?.claim_coverage}
            actionRows={detail.action_trackers?.unresolved || []}
            correctionRows={detail.correction_plan || []}
            reAuditDiff={detail.re_audit_diff}
            qcPacket={detail.submission_qc_packet}
            writingReadiness={detail.writing_readiness}
            t={t}
          />
          <MethodologyPanel checklist={detail.audit_summary?.methodology_checklist} t={t} />
          <section className="two-column">
            <ProvenancePanel summary={detail.audit_summary} t={t} />
            <MissingMaterialsPanel summary={detail.audit_summary} t={t} />
          </section>
          <FindingsPanel
            findings={detail.calibrated_findings?.findings || detail.audit_summary?.findings || []}
            t={t}
            auditId={audit.audit_id}
            onEvidence={props.onEvidence}
          />
          <ReportPanel report={report} t={t} />
        </>
      )}
    </main>
  );
}

function OverviewStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="overview-stat">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
