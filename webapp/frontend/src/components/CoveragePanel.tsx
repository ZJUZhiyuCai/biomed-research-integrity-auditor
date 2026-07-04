// Audit coverage: scope note pinned on top, screening metrics, modules
// executed/not-executed, plus detector failures and coverage-gap flag
// (fields that existed in coverage.json but were previously unrendered).

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { Coverage } from "../types";
import type { Labels } from "../i18n";
import { ListBlock, Metric, SectionTitle } from "./primitives";

export function CoveragePanel({
  coverage,
  t
}: {
  coverage: Coverage;
  t: Labels;
}) {
  const executed = coverage.modules_executed || [];
  const notExecuted = coverage.modules_not_executed || [];
  const failures = coverage.detector_failures || [];
  const hasGap = coverage.audit_coverage_gap === true;
  const workstreams = coverage.workstreams || [];
  const executionMode = coverage.execution_mode === "parallel" ? t.parallelWorkstreams : t.sequentialFallback;
  const workstreamCount = coverage.workstream_count ?? workstreams.length;

  return (
    <section className="coverage-band">
      <div className="coverage-intro">
        <SectionTitle title={t.coverage} icon={<CheckCircle2 size={18} aria-hidden="true" />} />
        {coverage.scope_note && <p className="scope-note">{coverage.scope_note}</p>}
        {hasGap && (
          <div className="coverage-gap-flag">
            <AlertTriangle size={14} aria-hidden="true" /> {t.coverageGap}
          </div>
        )}
      </div>
      <div className="coverage-metrics">
        <Metric label={t.coverageImages} value={coverage.image_panels_screened ?? 0} />
        <Metric label={t.coverageUnreadable} value={coverage.image_files_unreadable ?? 0} />
        <Metric label={t.coverageTables} value={coverage.source_tables_screened ?? 0} accent />
        <Metric label={t.coveragePrismLinks} value={coverage.prism_possible_graph_table_links ?? 0} />
        <Metric label={t.coverageFcsFiles} value={coverage.fcs_files_read ?? 0} />
        <Metric label={t.coverageSpliceChecks} value={coverage.splice_forensics_images_screened ?? 0} />
        <Metric label={t.coverageSpliceSignals} value={coverage.splice_forensics_candidates ?? 0} />
        <Metric label={t.executionMode} value={executionMode} accent={coverage.parallel_workstreams_enabled === true} />
        <Metric label={t.workstreams} value={workstreamCount} />
        <Metric label={t.coverageChannelChecks} value={coverage.channel_metadata_declarations_checked ?? 0} />
        <Metric label={t.coverageChannelGaps} value={coverage.channel_metadata_verification_gaps ?? 0} />
        <Metric label={t.coveragePsdPreviews} value={coverage.psd_preview_images_extracted ?? 0} />
      </div>
      <div className="coverage-columns">
        <ListBlock title={t.executed} rows={executed} />
        <ListBlock title={t.notExecuted} rows={notExecuted} />
      </div>
      {failures.length > 0 && (
        <div className="coverage-failures">
          <h4 className="list-block-title">{t.detectorFailures}</h4>
          <ul>
            {failures.map((failure, i) => (
              <li key={i} className="mono">
                {failure}
              </li>
            ))}
          </ul>
        </div>
      )}
      {workstreams.length > 0 && (
        <div className="coverage-workstreams">
          <h4 className="list-block-title">{t.workstreams}</h4>
          <p className="muted coverage-workstream-note">{coverage.workstream_scope_note || t.workstreamBoundary}</p>
          <ul>
            {workstreams.map((item, i) => (
              <li key={`${item.phase || "phase"}-${item.name || i}`} className="workstream-row">
                <span className="mono">{item.phase || "stage"}</span>
                <strong>{item.name || "workstream"}</strong>
                <span>{item.status || "completed"}</span>
                <span className="mono">{item.elapsed_seconds ?? "—"}s</span>
                <span className="mono">{item.output_count ?? 0}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
