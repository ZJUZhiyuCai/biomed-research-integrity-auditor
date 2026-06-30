// Small presentational primitives shared across panels.

import type { ReactNode } from "react";

export function Metric({
  label,
  value,
  accent
}: {
  label: string;
  value: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`metric${accent ? " metric--accent" : ""}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </div>
  );
}

export function ListBlock({
  title,
  rows,
  empty = "—"
}: {
  title: string;
  rows: ReactNode[];
  empty?: ReactNode;
}) {
  return (
    <div className="list-block">
      <h4 className="list-block-title">{title}</h4>
      {rows.length === 0 ? (
        <p className="muted list-empty">{empty}</p>
      ) : (
        <ul>
          {rows.map((row, i) => (
            <li key={i}>{row}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EmptyState({ text, icon }: { text: string; icon?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <p>{text}</p>
    </div>
  );
}

export function StatusPill({ status, label }: { status: string; label: string }) {
  return <span className={`status-pill ${status}`}>{label}</span>;
}

const RISK_RE = /^R[0-4]$/;

export function RiskChip({ risk }: { risk: string }) {
  const normalized = RISK_RE.test(risk) ? risk : "R0";
  return <span className={`risk-chip ${normalized}`}>{risk}</span>;
}

export function SectionTitle({
  title,
  icon,
  actions
}: {
  title: string;
  icon?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="section-title-row">
      <h3>
        {icon && <span className="section-icon">{icon}</span>}
        {title}
      </h3>
      {actions}
    </div>
  );
}
