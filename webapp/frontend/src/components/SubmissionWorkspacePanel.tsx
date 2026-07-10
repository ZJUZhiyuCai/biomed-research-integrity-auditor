// Submission workspace: claim coverage, action tracker, re-audit diff,
// QC-packet downloads, and writing/submission readiness. Integrity Boundary:
// these readiness artifacts are never rendered as findings and never modify R0-R4.

import { useState, type ReactNode } from "react";
import { ClipboardList, Copy, Download, FileArchive, GitCompare, Paperclip, PencilLine, Save } from "lucide-react";
import { artifactUrl, qcPacketUrl } from "../api";
import type {
  ActionTrackerRow,
  ActionTrackers,
  ClaimCoverage,
  CorrectionPlanRow,
  ImageReviewHandoffRow,
  ImageReviewPacketSummary,
  ReAuditDiff,
  SubmissionQCPacket,
  WritingReadiness
} from "../types";
import type { Labels } from "../i18n";
import { EmptyState, Metric, SectionTitle } from "./primitives";

export function SubmissionWorkspacePanel({
  auditId,
  claimCoverage,
  actionTrackers,
  correctionRows,
  reAuditDiff,
  qcPacket,
  writingReadiness,
  onActionUpdate,
  onImageReviewUpdate,
  onAttachmentUpload,
  t
}: {
  auditId: string;
  claimCoverage?: ClaimCoverage | null;
  actionTrackers?: ActionTrackers;
  correctionRows: CorrectionPlanRow[];
  reAuditDiff?: ReAuditDiff | null;
  qcPacket?: SubmissionQCPacket;
  writingReadiness?: WritingReadiness | null;
  onActionUpdate: (
    actionId: string,
    patch: Pick<ActionTrackerRow, "owner" | "status" | "human_note" | "accepted_with_reason" | "attachment_reference">
  ) => Promise<void>;
  onImageReviewUpdate: (
    reviewItemId: string,
    patch: Pick<ImageReviewHandoffRow, "reviewer" | "review_status" | "external_tool_or_method" | "review_result_note" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
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
        <ActionTrackerCard
          auditId={auditId}
          actionTrackers={actionTrackers}
          onActionUpdate={onActionUpdate}
          onAttachmentUpload={onAttachmentUpload}
          t={t}
        />
        <CorrectionPlanCard auditId={auditId} rows={correctionRows} t={t} />
        <ReAuditDiffCard reAuditDiff={reAuditDiff} t={t} />
        <ImageReviewHandoffCard
          auditId={auditId}
          imageReview={qcPacket?.image_review_packet}
          onImageReviewUpdate={onImageReviewUpdate}
          onAttachmentUpload={onAttachmentUpload}
          t={t}
        />
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
  actionTrackers,
  onActionUpdate,
  onAttachmentUpload,
  t
}: {
  auditId: string;
  actionTrackers?: ActionTrackers;
  onActionUpdate: (
    actionId: string,
    patch: Pick<ActionTrackerRow, "owner" | "status" | "human_note" | "accepted_with_reason" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
  t: Labels;
}) {
  const groups = [
    { key: "unresolved", title: t.unresolvedActions, rows: actionTrackers?.unresolved || [] },
    { key: "resolved", title: t.resolvedActions, rows: actionTrackers?.resolved || [] },
    { key: "accepted_with_reason", title: t.acceptedWithReason, rows: actionTrackers?.accepted_with_reason || [] }
  ];
  const unresolvedCount = groups[0].rows.length;
  const totalRows = groups.reduce((sum, group) => sum + group.rows.length, 0);

  return (
    <MiniPanel
      title={t.actionTracker}
      action={<a className="text-link" href={artifactUrl(auditId, "unresolved_actions.csv")}>{t.downloadCsv}</a>}
    >
      <div className="tracker-summary">
        <strong>{unresolvedCount}</strong>
        <span>{t.unresolvedActions}</span>
        <strong>{totalRows}</strong>
        <span>{t.trackedActions}</span>
      </div>
      {totalRows === 0 ? (
        <EmptyState text={t.notExecutedYet} />
      ) : (
        <div className="tracker-table-wrap">
          <table className="compact-table action-edit-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>{t.module}</th>
                <th>{t.action}</th>
                <th>{t.owner}</th>
                <th>{t.status}</th>
                <th>{t.note}</th>
                <th>{t.acceptedReason}</th>
                <th>{t.attachmentReference}</th>
                <th>{t.save}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                group.rows.length > 0 ? (
                  <ActionTrackerGroup
                    key={group.key}
                    title={group.title}
                    rows={group.rows}
                    onActionUpdate={onActionUpdate}
                    onAttachmentUpload={onAttachmentUpload}
                    t={t}
                  />
                ) : null
              ))}
            </tbody>
          </table>
        </div>
      )}
    </MiniPanel>
  );
}

function ActionTrackerGroup({
  title,
  rows,
  onActionUpdate,
  onAttachmentUpload,
  t
}: {
  title: string;
  rows: ActionTrackerRow[];
  onActionUpdate: (
    actionId: string,
    patch: Pick<ActionTrackerRow, "owner" | "status" | "human_note" | "accepted_with_reason" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
  t: Labels;
}) {
  return (
    <>
      <tr className="action-group-row">
        <td colSpan={9}>
          {title} · {rows.length}
        </td>
      </tr>
      {rows.map((row) => (
        <ActionEditorRow
          key={row.action_id || row.required_action}
          row={row}
          onActionUpdate={onActionUpdate}
          onAttachmentUpload={onAttachmentUpload}
          t={t}
        />
      ))}
    </>
  );
}

function ActionEditorRow({
  row,
  onActionUpdate,
  onAttachmentUpload,
  t
}: {
  row: ActionTrackerRow;
  onActionUpdate: (
    actionId: string,
    patch: Pick<ActionTrackerRow, "owner" | "status" | "human_note" | "accepted_with_reason" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
  t: Labels;
}) {
  const [owner, setOwner] = useState(row.owner || "");
  const [status, setStatus] = useState(row.status || "unresolved");
  const [humanNote, setHumanNote] = useState(row.human_note || "");
  const [acceptedReason, setAcceptedReason] = useState(row.accepted_with_reason || "");
  const [attachmentReference, setAttachmentReference] = useState(row.attachment_reference || "");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const actionId = row.action_id || "";
  const neutralInquiry = row.neutral_inquiry_template || "";
  const materialRequest = row.material_request_template || "";
  const hasTemplates = Boolean(neutralInquiry || materialRequest);
  const normalizedStatus = status.toLowerCase();
  const acceptanceNeedsReason = ["accepted_with_reason", "false_positive"].includes(normalizedStatus);
  const resolutionNeedsEvidence = normalizedStatus === "resolved";
  const validationMessage = acceptanceNeedsReason && !(acceptedReason.trim() || humanNote.trim())
    ? t.actionAcceptanceReasonRequired
    : resolutionNeedsEvidence && !(humanNote.trim() || attachmentReference.trim())
      ? t.actionResolutionEvidenceRequired
      : "";

  function copyTemplate(value: string) {
    if (!value || !navigator.clipboard) return;
    void navigator.clipboard.writeText(value);
  }

  async function save() {
    if (!actionId) return;
    setSaving(true);
    try {
      await onActionUpdate(actionId, {
        owner,
        status,
        human_note: humanNote,
        accepted_with_reason: acceptedReason,
        attachment_reference: attachmentReference
      });
    } finally {
      setSaving(false);
    }
  }

  async function upload(file: File | undefined) {
    if (!actionId || !file) return;
    setUploading(true);
    try {
      const reference = await onAttachmentUpload("action", actionId, file);
      if (reference) setAttachmentReference(reference);
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <tr>
        <td className="mono">{row.action_id}</td>
        <td>{row.action_category || row.action_type}</td>
        <td>{row.required_action}</td>
        <td>
          <input className="compact-input" value={owner} onChange={(e) => setOwner(e.target.value)} aria-label={t.owner} />
        </td>
        <td>
          <select className="compact-input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t.status}>
            <option value="unresolved">{t.unresolved}</option>
            <option value="resolved">{t.resolved}</option>
            <option value="accepted_with_reason">{t.acceptedWithReason}</option>
            <option value="false_positive">{t.falsePositive}</option>
          </select>
        </td>
        <td>
          <input className="compact-input" value={humanNote} onChange={(e) => setHumanNote(e.target.value)} aria-label={t.note} aria-invalid={Boolean(validationMessage)} />
        </td>
        <td>
          <input className="compact-input" value={acceptedReason} onChange={(e) => setAcceptedReason(e.target.value)} aria-label={t.acceptedReason} aria-invalid={acceptanceNeedsReason && Boolean(validationMessage)} />
        </td>
        <td>
          <div className="attachment-cell">
            <input className="compact-input" value={attachmentReference} onChange={(e) => setAttachmentReference(e.target.value)} aria-label={t.attachmentReference} placeholder={t.attachmentPlaceholder} />
            <label className="file-inline-button">
              <Paperclip size={13} aria-hidden="true" />
              {uploading ? t.uploadingAttachment : t.uploadAttachment}
              <input
                type="file"
                onChange={(e) => void upload(e.target.files?.[0])}
                disabled={!actionId || uploading}
              />
            </label>
          </div>
        </td>
        <td>
          <button type="button" className="icon-button small" onClick={save} disabled={!actionId || saving || Boolean(validationMessage)} aria-label={t.save} title={validationMessage || t.save}>
            <Save size={14} aria-hidden="true" />
          </button>
        </td>
      </tr>
      {hasTemplates && (
        <tr className="action-template-row">
          <td colSpan={9}>
            <div className="action-template-grid">
              {neutralInquiry && (
                <TemplateSnippet
                  title={t.neutralInquiryTemplate}
                  body={neutralInquiry}
                  copyLabel={t.copyTemplate}
                  onCopy={() => copyTemplate(neutralInquiry)}
                />
              )}
              {materialRequest && (
                <TemplateSnippet
                  title={t.materialRequestTemplate}
                  body={materialRequest}
                  copyLabel={t.copyTemplate}
                  onCopy={() => copyTemplate(materialRequest)}
                />
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function TemplateSnippet({
  title,
  body,
  copyLabel,
  onCopy
}: {
  title: string;
  body: string;
  copyLabel: string;
  onCopy: () => void;
}) {
  return (
    <div className="action-template-card">
      <div className="action-template-title">
        <strong>{title}</strong>
        <button type="button" className="icon-button small" onClick={onCopy} aria-label={`${copyLabel}: ${title}`}>
          <Copy size={14} aria-hidden="true" />
        </button>
      </div>
      <p>{body}</p>
    </div>
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
                <th>{t.attachmentReference}</th>
                <th>{t.status}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.finding_id || row.source_action_id || row.required_correction}>
                  <td className="mono">{row.finding_id}</td>
                  <td>{row.risk}</td>
                  <td>{row.required_correction}</td>
                  <td>{row.attachment_reference || row.evidence_after_correction || ""}</td>
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
        <Row label={t.fixedFindings} value={reAuditDiff.finding_changes?.fixed_count ?? 0} />
        <Row label={t.newFindings} value={reAuditDiff.finding_changes?.new_count ?? 0} />
        <Row label={t.persistedFindings} value={reAuditDiff.finding_changes?.persisted_count ?? 0} />
        <Row label={t.missingMaterials} value={delta(reAuditDiff.missing_material_count)} />
        <Row label={t.resolvedMaterials} value={reAuditDiff.material_changes?.resolved_count ?? 0} />
        <Row label={t.newMissingMaterials} value={reAuditDiff.material_changes?.new_count ?? 0} />
        <Row label={t.stillMissingMaterials} value={reAuditDiff.material_changes?.persisted_count ?? 0} />
        <Row label="Traceability" value={delta(reAuditDiff.positive_provenance_count)} />
        <Row label="Actions" value={delta(reAuditDiff.unresolved_action_count)} />
        <Row label="Claim gaps" value={delta(reAuditDiff.claim_evidence_gaps)} />
      </dl>
      <div className="diff-lists">
        <DiffList title={t.fixedFindings} items={reAuditDiff.finding_changes?.fixed || []} />
        <DiffList title={t.newFindings} items={reAuditDiff.finding_changes?.new || []} />
        <DiffList title={t.persistedFindings} items={reAuditDiff.finding_changes?.persisted || []} persisted />
        <StringList title={t.resolvedMaterials} items={reAuditDiff.material_changes?.resolved || []} />
        <StringList title={t.newMissingMaterials} items={reAuditDiff.material_changes?.new || []} />
        <StringList title={t.stillMissingMaterials} items={reAuditDiff.material_changes?.persisted || []} />
      </div>
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
            {files.map((file) => (
              <li key={file} className="mono">
                <a href={artifactUrl(auditId, `submission_qc_packet/${file}`)}>{file}</a>
              </li>
            ))}
          </ul>
          {Object.entries(qcPacket.audience_exports || {}).length > 0 && (
            <>
              <p className="mini-note">Audience exports</p>
              <ul className="compact-file-list">
                {Object.entries(qcPacket.audience_exports || {}).map(([key, file]) => (
                  <li key={key} className="mono">
                    <a href={artifactUrl(auditId, `submission_qc_packet/${file}`)}>{file}</a>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      ) : (
        <EmptyState text={t.notExecutedYet} />
      )}
    </MiniPanel>
  );
}

function ImageReviewHandoffCard({
  auditId,
  imageReview,
  onImageReviewUpdate,
  onAttachmentUpload,
  t
}: {
  auditId: string;
  imageReview?: ImageReviewPacketSummary;
  onImageReviewUpdate: (
    reviewItemId: string,
    patch: Pick<ImageReviewHandoffRow, "reviewer" | "review_status" | "external_tool_or_method" | "review_result_note" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
  t: Labels;
}) {
  const rows = imageReview?.handoff_rows || [];
  const handoffCsv = imageReview?.external_tool_handoff_csv;
  const handoffGuide = imageReview?.external_tool_handoff_guide;
  return (
    <MiniPanel
      title={t.imageReviewHandoff}
      action={
        imageReview?.available ? (
          <span className="link-row">
            {handoffCsv && (
              <a className="text-link" href={artifactUrl(auditId, `submission_qc_packet/${handoffCsv}`)}>
                {t.openHandoffCsv}
              </a>
            )}
            {handoffGuide && (
              <a className="text-link" href={artifactUrl(auditId, `submission_qc_packet/${handoffGuide}`)}>
                {t.openHandoffGuide}
              </a>
            )}
          </span>
        ) : null
      }
    >
      {imageReview?.available ? (
        <>
          <div className="tracker-summary">
            <strong>{imageReview.external_handoff_count ?? rows.length}</strong>
            <span>{t.handoffItems}</span>
          </div>
          <p className="mini-note">{t.handoffBoundary}</p>
          {rows.length === 0 ? (
            <EmptyState text={t.noImageHandoff} />
          ) : (
            <div className="tracker-table-wrap">
              <table className="compact-table image-handoff-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>{t.module}</th>
                    <th>{t.reviewRoute}</th>
                    <th>{t.reviewQuestion}</th>
                    <th>{t.reviewStatus}</th>
                    <th>{t.linkedAction}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <ImageReviewEditorRows
                      key={row.handoff_item_id || row.source_finding_id || row.review_question}
                      row={row}
                      onImageReviewUpdate={onImageReviewUpdate}
                      onAttachmentUpload={onAttachmentUpload}
                      t={t}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {rows[0]?.data_governance_note && (
            <p className="mini-note">
              <strong>{t.dataGovernance}: </strong>
              {rows[0].data_governance_note}
            </p>
          )}
        </>
      ) : (
        <EmptyState text={t.noImageHandoff} />
      )}
    </MiniPanel>
  );
}

function ImageReviewEditorRows({
  row,
  onImageReviewUpdate,
  onAttachmentUpload,
  t
}: {
  row: ImageReviewHandoffRow;
  onImageReviewUpdate: (
    reviewItemId: string,
    patch: Pick<ImageReviewHandoffRow, "reviewer" | "review_status" | "external_tool_or_method" | "review_result_note" | "attachment_reference">
  ) => Promise<void>;
  onAttachmentUpload: (targetType: "action" | "image_review", targetId: string, file: File) => Promise<string>;
  t: Labels;
}) {
  const [reviewer, setReviewer] = useState(row.reviewer || "");
  const [reviewStatus, setReviewStatus] = useState(row.review_status || "unresolved");
  const [method, setMethod] = useState(row.external_tool_or_method || "");
  const [note, setNote] = useState(row.review_result_note || "");
  const [attachment, setAttachment] = useState(row.attachment_reference || row.external_result_reference || "");
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const reviewItemId = row.review_item_id || "";

  async function save() {
    if (!reviewItemId) return;
    setSaving(true);
    try {
      await onImageReviewUpdate(reviewItemId, {
        reviewer,
        review_status: reviewStatus,
        external_tool_or_method: method,
        review_result_note: note,
        attachment_reference: attachment
      });
    } finally {
      setSaving(false);
    }
  }

  async function upload(file: File | undefined) {
    if (!reviewItemId || !file) return;
    setUploading(true);
    try {
      const reference = await onAttachmentUpload("image_review", reviewItemId, file);
      if (reference) setAttachment(reference);
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <tr>
        <td className="mono">{row.handoff_item_id}</td>
        <td>
          <strong>{row.finding_type || row.source_finding_id}</strong>
          <span className="subtle-block">{row.priority || row.risk_level}</span>
        </td>
        <td>{row.recommended_tool_route}</td>
        <td>
          {row.review_question}
          {row.candidate_files && <span className="subtle-block mono">{row.candidate_files}</span>}
        </td>
        <td>{row.review_status || "unresolved"}</td>
        <td>
          {row.linked_action_id ? (
            <>
              <span className="mono">{row.linked_action_id}</span>
              <span className="subtle-block">
                {row.linked_action_status || "unresolved"}
                {row.linked_action_owner ? ` · ${row.linked_action_owner}` : ""}
              </span>
              {row.linked_action_attachment_reference && (
                <span className="subtle-block mono">{row.linked_action_attachment_reference}</span>
              )}
            </>
          ) : (
            <span className="subtle-block">—</span>
          )}
        </td>
      </tr>
      <tr className="action-template-row">
        <td colSpan={6}>
          <div className="image-review-edit-grid">
            <label>
              <span>{t.owner}</span>
              <input className="compact-input" value={reviewer} onChange={(e) => setReviewer(e.target.value)} aria-label={t.owner} />
            </label>
            <label>
              <span>{t.reviewStatus}</span>
              <select className="compact-input" value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)} aria-label={t.reviewStatus}>
                <option value="unresolved">{t.unresolved}</option>
                <option value="reviewed">{t.resolved}</option>
                <option value="accepted_with_reason">{t.acceptedWithReason}</option>
                <option value="needs_followup">{t.needsFollowup}</option>
              </select>
            </label>
            <label>
              <span>{t.externalMethod}</span>
              <input className="compact-input" value={method} onChange={(e) => setMethod(e.target.value)} aria-label={t.externalMethod} />
            </label>
            <label>
              <span>{t.reviewResult}</span>
              <input className="compact-input" value={note} onChange={(e) => setNote(e.target.value)} aria-label={t.reviewResult} />
            </label>
            <div className="field-label">
              <span>{t.attachmentReference}</span>
              <div className="attachment-cell">
                <input className="compact-input" value={attachment} onChange={(e) => setAttachment(e.target.value)} aria-label={t.attachmentReference} placeholder={t.attachmentPlaceholder} />
                <label className="file-inline-button">
                  <Paperclip size={13} aria-hidden="true" />
                  {uploading ? t.uploadingAttachment : t.uploadAttachment}
                  <input
                    type="file"
                    onChange={(e) => void upload(e.target.files?.[0])}
                    disabled={!reviewItemId || uploading}
                  />
                </label>
              </div>
            </div>
            <button type="button" className="icon-button small" onClick={save} disabled={!reviewItemId || saving} aria-label={t.save}>
              <Save size={14} aria-hidden="true" />
            </button>
          </div>
        </td>
      </tr>
    </>
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
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
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

function DiffList({
  title,
  items,
  persisted = false
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  persisted?: boolean;
}) {
  const visible = items.slice(0, 4);
  return (
    <div className="diff-list">
      <strong>{title}</strong>
      {visible.length === 0 ? (
        <p className="mini-note">None listed</p>
      ) : (
        <ul>
          {visible.map((item, index) => (
            <li key={`${String(item.finding_id || item.finding_key || index)}-${index}`}>
              <span className="mono">{String(item.finding_id || item.finding_key || "finding")}</span>
              {" "}
              <span>{String(item.location || "")}</span>
              {" "}
              <span className="mono">
                {persisted
                  ? `${String(item.previous_risk || "—")} → ${String(item.current_risk || "—")}`
                  : String(item.risk || "")}
              </span>
            </li>
          ))}
        </ul>
      )}
      {items.length > visible.length && <p className="mini-note">+{items.length - visible.length} more in JSON/Markdown diff</p>}
    </div>
  );
}

function StringList({ title, items }: { title: string; items: string[] }) {
  const visible = items.slice(0, 5);
  return (
    <div className="diff-list">
      <strong>{title}</strong>
      {visible.length === 0 ? (
        <p className="mini-note">None listed</p>
      ) : (
        <ul>
          {visible.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      {items.length > visible.length && <p className="mini-note">+{items.length - visible.length} more in Markdown diff</p>}
    </div>
  );
}
