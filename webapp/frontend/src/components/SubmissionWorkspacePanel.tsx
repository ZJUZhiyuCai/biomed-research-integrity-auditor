// Submission workspace: claim coverage, action tracker, re-audit diff,
// QC-packet downloads, and writing/submission readiness. Integrity Boundary:
// these readiness artifacts are never rendered as findings and never modify R0-R4.

import type React from "react";
import { ClipboardList, Download, FileArchive, GitCompare, PencilLine } from "lucide-react";
import { artifactUrl, qcPacketUrl } from "../api";
import type {
  ActionTrackerRow,
  ClaimCoverage,
  CorrectionPlanRow,
  ReAuditDiff,
  SubmissionQCPacket,
  WritingReadiness
} from "../types";
import type { Labels } from "../i18n";
import { EmptyState, Metric, SectionTitle } from "./primitives";

export function SubmissionWorkspacePanel({
  auditId,
  claimCoverage,
  actionRows,
  correctionRows,
  reAuditDiff,
  qcPacket,
  writingReadiness,
  t
}: {
  auditId: string;
  claimCoverage?: ClaimCoverage | null;
  actionRows: ActionTrackerRow[];
  correctionRows: CorrectionPlanRow[];
  reAuditDiff?: ReAuditDiff | null;
  qcPacket?: SubmissionQCPacket;
  writingReadiness?: WritingReadiness | null;
  t: Labels;
}) {
  return (
    <section className="panel submission-workspace">
      <SectionTitle
        title={t.submissionWorkspace}
        icon={<ClipboardList size={18} aria-hidden="true" />}
      />
      <p className="scope-line">{t.readinessBoundary}</p>
      <div className="submission-grid">
        <ClaimCoverageCard claimCoverage={claimCoverage} t={t} />
        <ActionTrackerCard auditId={auditId} rows={actionRows} t={t} />
        <CorrectionPlanCard auditId={auditId} rows={correctionRows} t={t} />
        <ReAuditDiffCard reAuditDiff={reAuditDiff} t={t} />
        <QCPacketCard auditId={auditId} qcPacket={qcPacket} t={t} />
        <WritingReadinessCard writingReadiness={writingReadiness} t={t} />
      </div>
    </section>
  );
}

function ClaimCoverageCard({
  claimCoverage,
  t
}: {
  claimCoverage?: ClaimCoverage | null;
  t: Labels;
}) {
  if (!claimCoverage) {
    return <MiniPanel title={t.claimCoverage}><EmptyState text={t.notExecutedYet} /></MiniPanel>;
  }
  return (
    <MiniPanel title={t.claimCoverage}>
      <div className="compact-metrics">
        <Metric label={t.claimsDeclared} value={claimCoverage.claims_declared ?? 0} />
        <Metric label={t.unresolvedClaimGaps} value={claimCoverage.claims_with_unresolved_evidence_gap ?? 0} accent />
      </div>
      <dl className="readiness-list">
        <Row label={t.sourceDataLinked} value={claimCoverage.claims_with_source_data ?? 0} />
        <Row label={t.rawRecordsLinked} value={claimCoverage.claims_with_raw_records ?? 0} />
        <Row label={t.analysisCodeLinked} value={claimCoverage.claims_with_analysis_code ?? 0} />
        <Row label={t.protocolLinked} value={claimCoverage.claims_with_protocol_link ?? 0} />
      </dl>
      {claimCoverage.scope_note && <p className="mini-note">{claimCoverage.scope_note}</p>}
    </MiniPanel>
  );
}

function ActionTrackerCard({
  auditId,
  rows,
  t
}: {
  auditId: string;
  rows: ActionTrackerRow[];
  t: Labels;
}) {
  return (
    <MiniPanel
      title={t.actionTracker}
      action={<a className="text-link" href={artifactUrl(auditId, "unresolved_actions.csv")}>{t.downloadCsv}</a>}
    >
      <div className="tracker-summary">
        <strong>{rows.length}</strong>
        <span>{t.unresolvedActions}</span>
      </div>
      {rows.length === 0 ? (
        <EmptyState text={t.notExecutedYet} />
      ) : (
        <div className="tracker-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>{t.module}</th>
                <th>{t.action}</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 8).map((row) => (
                <tr key={row.action_id || row.required_action}>
                  <td className="mono">{row.action_id}</td>
                  <td>{row.owner || row.action_category}</td>
                  <td>{row.required_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MiniPanel>
  );
}

function CorrectionPlanCard({
  auditId,
  rows,
  t
}: {
  auditId: string;
  rows: CorrectionPlanRow[];
  t: Labels;
}) {
  return (
    <MiniPanel
      title={t.correctionPlan}
      action={
        <span className="link-row">
          <a className="text-link" href={artifactUrl(auditId, "correction_plan.md")}>{t.downloadMd}</a>
          <a className="text-link" href={artifactUrl(auditId, "correction_plan.csv")}>{t.downloadCsv}</a>
        </span>
      }
    >
      <div className="tracker-summary">
        <strong>{rows.length}</strong>
        <span>{t.correctionItems}</span>
      </div>
      {rows.length === 0 ? (
        <EmptyState text={t.notExecutedYet} />
      ) : (
        <div className="tracker-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>{t.findingId}</th>
                <th>R</th>
                <th>{t.requiredCorrection}</th>
                <th>{t.status}</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 8).map((row) => (
                <tr key={row.finding_id || row.source_action_id || row.required_correction}>
                  <td className="mono">{row.finding_id}</td>
                  <td>{row.risk}</td>
                  <td>{row.required_correction}</td>
                  <td>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MiniPanel>
  );
}

function ReAuditDiffCard({
  reAuditDiff,
  t
}: {
  reAuditDiff?: ReAuditDiff | null;
  t: Labels;
}) {
  if (!reAuditDiff) {
    return <MiniPanel title={t.reAuditDiff} icon={<GitCompare size={15} aria-hidden="true" />}><EmptyState text={t.noReAuditDiff} /></MiniPanel>;
  }
  return (
    <MiniPanel title={t.reAuditDiff} icon={<GitCompare size={15} aria-hidden="true" />}>
      <dl className="readiness-list">
        <Row label="Overall R" value={`${reAuditDiff.overall_risk?.previous ?? "—"} → ${reAuditDiff.overall_risk?.current ?? "—"}`} />
        <Row label="Missing materials" value={delta(reAuditDiff.missing_material_count)} />
        <Row label="Traceability" value={delta(reAuditDiff.positive_provenance_count)} />
        <Row label="Actions" value={delta(reAuditDiff.unresolved_action_count)} />
        <Row label="Claim gaps" value={delta(reAuditDiff.claim_evidence_gaps)} />
      </dl>
      {reAuditDiff.scope_note && <p className="mini-note">{reAuditDiff.scope_note}</p>}
    </MiniPanel>
  );
}

function QCPacketCard({
  auditId,
  qcPacket,
  t
}: {
  auditId: string;
  qcPacket?: SubmissionQCPacket;
  t: Labels;
}) {
  const files = qcPacket?.files || [];
  return (
    <MiniPanel
      title={t.qcPacket}
      icon={<FileArchive size={15} aria-hidden="true" />}
      action={
        qcPacket?.available ? (
          <a className="text-link" href={qcPacketUrl(auditId)}>
            <Download size={13} aria-hidden="true" /> {t.downloadPacket}
          </a>
        ) : null
      }
    >
      {qcPacket?.available ? (
        <>
          <div className="tracker-summary">
            <strong>{files.length}</strong>
            <span>files</span>
          </div>
          <ul className="compact-file-list">
            {files.slice(0, 8).map((file) => (
              <li key={file} className="mono">
                <a href={artifactUrl(auditId, `submission_qc_packet/${file}`)}>{file}</a>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <EmptyState text={t.notExecutedYet} />
      )}
    </MiniPanel>
  );
}

function WritingReadinessCard({
  writingReadiness,
  t
}: {
  writingReadiness?: WritingReadiness | null;
  t: Labels;
}) {
  return (
    <MiniPanel title={t.writingReadiness} icon={<PencilLine size={15} aria-hidden="true" />}>
      {writingReadiness ? (
        <>
          <dl className="readiness-list">
            <Row label="Status" value={String(writingReadiness.overall_status || "review_needed")} />
            <Row label="Checks" value={(writingReadiness.checks || []).length} />
          </dl>
          {writingReadiness.scope_note && <p className="mini-note">{writingReadiness.scope_note}</p>}
        </>
      ) : (
        <EmptyState text={t.notExecutedYet} />
      )}
    </MiniPanel>
  );
}

function MiniPanel({
  title,
  icon,
  action,
  children
}: {
  title: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <article className="mini-panel">
      <header className="mini-panel-header">
        <h4>{icon}{title}</h4>
        {action}
      </header>
      {children}
    </article>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="mono">{value}</dd>
    </div>
  );
}

function delta(value?: { previous?: number | null; current?: number | null }): string {
  if (!value) return "—";
  return `${value.previous ?? "—"} → ${value.current ?? "—"}`;
}
