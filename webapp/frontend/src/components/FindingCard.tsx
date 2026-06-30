// A single finding: risk chip, type/location/module, benign explanations,
// required materials, recommended action, structured evidence metrics, and
// clickable evidence crops that open the lightbox.

import { useMemo } from "react";
import type { Finding } from "../types";
import type { Labels } from "../i18n";
import { ListBlock, RiskChip } from "./primitives";
import { extractEvidenceMetrics, extractEvidencePaths } from "../lib/evidence";
import { evidenceUrl } from "../api";

export function FindingCard({
  finding,
  t,
  auditId,
  onEvidence
}: {
  finding: Finding;
  t: Labels;
  auditId: string;
  onEvidence: (images: string[], index: number) => void;
}) {
  const risk = finding.calibrated_risk_level || finding.risk_level || "R0";
  const crops = useMemo(() => extractEvidencePaths(finding.evidence), [finding.evidence]);
  const metrics = useMemo(() => extractEvidenceMetrics(finding.evidence), [finding.evidence]);
  const title = finding.finding_type || finding.title || finding.finding_id || "—";
  const location =
    finding.location || finding.locations?.join(", ") || finding.evidence_type || "";

  return (
    <article className="finding-row">
      <header className="finding-title">
        <RiskChip risk={risk} />
        <div className="finding-heading">
          <h4>{title}</h4>
          {location && <p className="finding-location mono">{location}</p>}
        </div>
        {finding.module && <span className="module-chip mono">{finding.module}</span>}
        {finding.evidence_strength && (
          <span className="strength-chip">{finding.evidence_strength}</span>
        )}
      </header>

      <div className="finding-grid">
        <ListBlock
          title={t.benign}
          rows={finding.benign_explanations_considered || finding.benign_explanations || []}
        />
        <ListBlock
          title={t.required}
          rows={finding.required_materials_to_resolve || finding.required_materials || []}
        />
        <ListBlock
          title={t.action}
          rows={finding.recommended_action ? [finding.recommended_action] : []}
        />
      </div>

      {metrics.length > 0 && (
        <div className="evidence-metrics">
          <h5>{t.evidenceMetrics}</h5>
          <dl className="metric-grid">
            {metrics.map((m, i) => (
              <div key={i} className="metric-cell">
                <dt>{m.key}</dt>
                <dd className="mono">{m.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {crops.length > 0 && (
        <div className="evidence-strip">
          <h5>{t.evidence}</h5>
          <div className="evidence-thumbs">
            {crops.map((path, i) => (
              <button
                key={path}
                className="evidence-thumb"
                onClick={() => onEvidence(crops, i)}
                type="button"
              >
                <img src={evidenceUrl(auditId, path)} alt={path} loading="lazy" />
              </button>
            ))}
          </div>
        </div>
      )}

      {finding.note && <p className="finding-note">{finding.note}</p>}
    </article>
  );
}
