// Missing materials register plus the list of materials that were reviewed
// (materials_reviewed existed in AUDIT_JSON_SUMMARY.json but was unrendered).

import { PackageCheck, PackageX } from "lucide-react";
import type { AuditSummary } from "../types";
import type { Labels } from "../i18n";
import { SectionTitle } from "./primitives";

export function MissingMaterialsPanel({
  summary,
  t
}: {
  summary: AuditSummary;
  t: Labels;
}) {
  const missing = summary.materials_missing || [];
  const reviewed = summary.materials_reviewed || [];

  return (
    <section className="panel">
      <SectionTitle title={t.missing} icon={<PackageX size={18} aria-hidden="true" />} />
      <div className="compact-list">
        {missing.length === 0 ? (
          <span className="muted">—</span>
        ) : (
          missing.map((row, i) => {
            const isStr = typeof row === "string";
            const obj = isStr ? null : (row as Record<string, unknown>);
            return (
              <div className="compact-row" key={i}>
                <strong>
                  {isStr ? row : String(obj?.material || obj?.path || "material")}
                </strong>
                <span>
                  {isStr ? "" : String(obj?.reason || obj?.status || "")}
                </span>
              </div>
            );
          })
        )}
      </div>

      {reviewed.length > 0 && (
        <div className="reviewed-block">
          <h4 className="list-block-title">
            <PackageCheck size={14} aria-hidden="true" /> {t.reviewed}
          </h4>
          <ul className="reviewed-list">
            {reviewed.map((material, i) => (
              <li key={i} className="mono">
                {material}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
