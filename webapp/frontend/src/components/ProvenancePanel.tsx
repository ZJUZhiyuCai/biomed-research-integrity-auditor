// Positive provenance evidence (to inspect, NOT proof of correctness — see
// scope note) plus traceability gaps shown as their own register rather than
// only as a missing-materials fallback.

import { Link2, Unlink } from "lucide-react";
import type { AuditSummary } from "../types";
import type { Labels } from "../i18n";
import { SectionTitle } from "./primitives";

export function ProvenancePanel({
  summary,
  t
}: {
  summary: AuditSummary;
  t: Labels;
}) {
  const rows = summary.positive_provenance || [];
  const gaps = summary.traceability_gaps || [];

  return (
    <section className="panel">
      <SectionTitle title={t.traceability} icon={<Link2 size={18} aria-hidden="true" />} />
      <div className="compact-list">
        {rows.length === 0 ? (
          <span className="muted">—</span>
        ) : (
          rows.map((row, i) => (
            <div className="compact-row" key={row.provenance_id || i}>
              <strong>
                {row.figure_panel || row.left || row.source_path || "provenance"}
              </strong>
              <span>
                {row.source_record || row.right || row.target_path || row.relation_type}
              </span>
            </div>
          ))
        )}
      </div>

      {gaps.length > 0 && (
        <div className="gaps-block">
          <h4 className="list-block-title">
            <Unlink size={14} aria-hidden="true" /> {t.gaps}
          </h4>
          <div className="compact-list">
            {gaps.map((gap, i) => (
              <div className="compact-row gap-row" key={gap.gap_id || i}>
                <strong className="mono">{gap.finding_type || gap.gap_id || "gap"}</strong>
                <span>
                  {gap.location || ""}
                  {gap.risk_level ? ` · ${gap.risk_level}` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
