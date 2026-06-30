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
        <Metric label="Images" value={coverage.image_panels_screened ?? 0} />
        <Metric label="Unreadable" value={coverage.image_files_unreadable ?? 0} />
        <Metric label="Tables" value={coverage.source_tables_screened ?? 0} accent />
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
    </section>
  );
}
