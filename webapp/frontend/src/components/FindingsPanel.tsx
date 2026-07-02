// Risk register: R0–R4 + module filtering. Each finding card surfaces
// structured evidence metrics and clickable evidence crops.

import { useMemo, useState } from "react";
import { Filter } from "lucide-react";
import type { Finding } from "../types";
import type { Labels } from "../i18n";
import { EmptyState, SectionTitle } from "./primitives";
import { FindingCard } from "./FindingCard";

const RISK_OPTIONS = ["all", "R0", "R1", "R2", "R3", "R4"];
const RISK_ORDER: Record<string, number> = { R0: 0, R1: 1, R2: 2, R3: 3, R4: 4 };

export function FindingsPanel({
  findings,
  t,
  auditId,
  onEvidence
}: {
  findings: Finding[];
  t: Labels;
  auditId: string;
  onEvidence: (images: string[], index: number) => void;
}) {
  const [riskFilter, setRiskFilter] = useState("all");
  const [moduleFilter, setModuleFilter] = useState("all");

  const modules = useMemo(() => {
    const set = new Set<string>();
    findings.forEach((f) => {
      if (f.module) set.add(f.module);
    });
    return Array.from(set).sort();
  }, [findings]);

  const filtered = useMemo(
    () =>
      findings.filter((f) => {
        const risk = f.calibrated_risk_level || f.risk_level || "R0";
        const riskOk = riskFilter === "all" || risk === riskFilter;
        const modOk = moduleFilter === "all" || f.module === moduleFilter;
        return riskOk && modOk;
      }).sort((a, b) => {
        const riskA = RISK_ORDER[a.calibrated_risk_level || a.risk_level || "R0"] ?? 0;
        const riskB = RISK_ORDER[b.calibrated_risk_level || b.risk_level || "R0"] ?? 0;
        return riskB - riskA;
      }),
    [findings, riskFilter, moduleFilter]
  );

  return (
    <section className="panel">
      <SectionTitle
        title={t.findings}
        icon={<Filter size={18} aria-hidden="true" />}
        actions={
          <div className="filter-row">
            <select
              className="filter-select"
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              aria-label={t.allRisks}
            >
              {RISK_OPTIONS.map((risk) => (
                <option key={risk} value={risk}>
                  {risk === "all" ? t.allRisks : risk}
                </option>
              ))}
            </select>
            {modules.length > 0 && (
              <select
                className="filter-select"
                value={moduleFilter}
                onChange={(e) => setModuleFilter(e.target.value)}
                aria-label={t.module}
              >
                <option value="all">{t.allModules}</option>
                {modules.map((mod) => (
                  <option key={mod} value={mod}>
                    {mod}
                  </option>
                ))}
              </select>
            )}
          </div>
        }
      />
      <p className="scope-line">{t.scopeNote}</p>
      {filtered.length === 0 ? (
        <EmptyState text={t.noFindings} />
      ) : (
        <div className="finding-list">
          {filtered.map((finding, index) => (
            <FindingCard
              key={finding.finding_id || index}
              finding={finding}
              t={t}
              auditId={auditId}
              onEvidence={onEvidence}
            />
          ))}
        </div>
      )}
    </section>
  );
}
