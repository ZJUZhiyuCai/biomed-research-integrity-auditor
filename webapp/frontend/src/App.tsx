import { FormEvent, useEffect, useMemo, useState } from "react";
import { FileText, Play, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";

type Language = "zh" | "en";
type AuditStatus = "queued" | "running" | "completed" | "failed";

interface AuditJob {
  audit_id: string;
  status: AuditStatus;
  mode: string;
  domains: string;
  external_literature_provider: string;
  package_path: string;
  output_dir: string;
  created_at: number;
  updated_at: number;
  returncode: number | null;
  error: string | null;
  stdout_tail: string;
  stderr_tail: string;
  pipeline_summary?: {
    overall_risk?: string;
    finding_count?: number;
    positive_provenance_count?: number;
  } | null;
}

interface SummaryPayload {
  audit: AuditJob;
  audit_summary: Record<string, any>;
  coverage: Record<string, any>;
  calibrated_findings: { findings?: Array<Record<string, any>> };
  pipeline_summary: Record<string, any>;
}

const labels = {
  zh: {
    title: "生物医药研究诚信自查",
    privacy: "本地运行: 绑定 127.0.0.1，默认不上传材料；外部检索需显式选择。",
    packagePath: "材料目录",
    run: "开始审计",
    refresh: "刷新",
    history: "历史",
    mode: "模式",
    domains: "领域",
    provider: "外部检索",
    coverage: "审计覆盖",
    executed: "已执行",
    notExecuted: "未执行",
    findings: "风险登记",
    traceability: "正向溯源证据",
    missing: "缺失材料",
    report: "Markdown 报告",
    noSelection: "选择一次审计或输入材料目录开始。",
    noFindings: "当前 artifact 中没有校准 finding。",
    required: "待补材料",
    action: "建议动作",
    benign: "可能解释",
    evidence: "证据",
    delete: "删除",
    scopeNote: "无发现只代表当前材料与模块范围内未检出候选，不是正确性证明。",
    allRisks: "全部风险"
  },
  en: {
    title: "Biomedical Research Integrity Self-Audit",
    privacy: "Local run: bound to 127.0.0.1, no upload by default; network checks are opt-in.",
    packagePath: "Package path",
    run: "Run Audit",
    refresh: "Refresh",
    history: "History",
    mode: "Mode",
    domains: "Domains",
    provider: "External search",
    coverage: "Audit Coverage",
    executed: "Executed",
    notExecuted: "Not Executed",
    findings: "Risk Register",
    traceability: "Positive Provenance Evidence",
    missing: "Missing Materials",
    report: "Markdown Report",
    noSelection: "Select an audit or enter a package path to start.",
    noFindings: "No calibrated findings are present in the current artifact.",
    required: "Required Materials",
    action: "Recommended Action",
    benign: "Benign Explanations",
    evidence: "Evidence",
    delete: "Delete",
    scopeNote: "No findings only means no candidates within supplied scope; it is not proof of correctness.",
    allRisks: "All risks"
  }
};

const riskOptions = ["all", "R0", "R1", "R2", "R3", "R4"];

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<T>;
}

function App() {
  const [language, setLanguage] = useState<Language>("zh");
  const [audits, setAudits] = useState<AuditJob[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SummaryPayload | null>(null);
  const [report, setReport] = useState("");
  const [packagePath, setPackagePath] = useState("");
  const [mode, setMode] = useState("internal_presubmission");
  const [domains, setDomains] = useState("wetlab,animal,cell");
  const [provider, setProvider] = useState("auto");
  const [riskFilter, setRiskFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const t = labels[language];

  const selectedAudit = audits.find((audit) => audit.audit_id === selectedId) || null;

  async function loadAudits() {
    const payload = await api<{ audits: AuditJob[] }>("/api/audits");
    setAudits(payload.audits);
    if (!selectedId && payload.audits.length > 0) {
      setSelectedId(payload.audits[0].audit_id);
    }
  }

  async function loadSelected(auditId: string) {
    const job = await api<AuditJob>(`/api/audits/${auditId}`);
    setAudits((items) => [job, ...items.filter((item) => item.audit_id !== auditId)]);
    if (job.status === "completed") {
      const summary = await api<SummaryPayload>(`/api/audits/${auditId}/summary`);
      setDetail(summary);
      const reportResponse = await fetch(`/api/audits/${auditId}/report.md`);
      setReport(reportResponse.ok ? await reportResponse.text() : "");
    } else {
      setDetail(null);
      setReport("");
    }
  }

  useEffect(() => {
    loadAudits().catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    loadSelected(selectedId).catch((err) => setError(String(err)));
  }, [selectedId]);

  useEffect(() => {
    if (!selectedAudit || !["queued", "running"].includes(selectedAudit.status)) return;
    const timer = window.setInterval(() => {
      loadSelected(selectedAudit.audit_id).catch((err) => setError(String(err)));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedAudit?.audit_id, selectedAudit?.status]);

  async function runAudit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const job = await api<AuditJob>("/api/audits", {
      method: "POST",
      body: JSON.stringify({
        package_path: packagePath,
        mode,
        domains,
        external_literature_provider: provider
      })
    });
    setAudits((items) => [job, ...items]);
    setSelectedId(job.audit_id);
  }

  async function deleteAudit(auditId: string) {
    await api(`/api/audits/${auditId}`, { method: "DELETE" });
    setAudits((items) => items.filter((item) => item.audit_id !== auditId));
    if (selectedId === auditId) {
      setSelectedId(null);
      setDetail(null);
      setReport("");
    }
  }

  const findings = useMemo(() => {
    const rows: Array<Record<string, any>> = detail?.calibrated_findings?.findings || detail?.audit_summary?.findings || [];
    return rows.filter((finding: Record<string, any>) => {
      const risk = finding.calibrated_risk_level || finding.risk_level || "R0";
      return riskFilter === "all" || risk === riskFilter;
    });
  }, [detail, riskFilter]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row">
          <ShieldCheck size={22} aria-hidden="true" />
          <h1>{t.title}</h1>
        </div>
        <div className="privacy-banner">{t.privacy}</div>
        <div className="language-toggle" aria-label="Language">
          <button className={language === "zh" ? "active" : ""} onClick={() => setLanguage("zh")}>中</button>
          <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
        </div>

        <form className="run-form" onSubmit={runAudit}>
          <label>
            <span>{t.packagePath}</span>
            <input value={packagePath} onChange={(event) => setPackagePath(event.target.value)} placeholder="/Users/..." />
          </label>
          <label>
            <span>{t.mode}</span>
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="internal_presubmission">internal_presubmission</option>
              <option value="external_public_material">external_public_material</option>
              <option value="response_to_concern">response_to_concern</option>
            </select>
          </label>
          <label>
            <span>{t.domains}</span>
            <input value={domains} onChange={(event) => setDomains(event.target.value)} />
          </label>
          <label>
            <span>{t.provider}</span>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              <option value="auto">auto</option>
              <option value="none">none</option>
              <option value="fixture">fixture</option>
              <option value="europepmc">europepmc</option>
              <option value="crossref">crossref</option>
            </select>
          </label>
          <button className="primary-button" type="submit">
            <Play size={16} aria-hidden="true" />
            {t.run}
          </button>
        </form>

        <div className="history-header">
          <h2>{t.history}</h2>
          <button className="icon-button" onClick={() => loadAudits().catch((err) => setError(String(err)))} aria-label={t.refresh}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
        </div>
        <div className="audit-list">
          {audits.map((audit) => (
            <button
              key={audit.audit_id}
              className={`audit-list-item ${selectedId === audit.audit_id ? "selected" : ""}`}
              onClick={() => setSelectedId(audit.audit_id)}
            >
              <span className={`status-dot ${audit.status}`} />
              <span className="audit-name">{audit.audit_id}</span>
              <span className="audit-risk">{audit.pipeline_summary?.overall_risk || audit.status}</span>
            </button>
          ))}
        </div>
      </aside>

      <main className="workspace">
        {error && <div className="error-box">{error}</div>}
        {!selectedAudit && <EmptyState text={t.noSelection} />}
        {selectedAudit && (
          <>
            <header className="audit-header">
              <div>
                <p className="eyebrow">{selectedAudit.mode}</p>
                <h2>{selectedAudit.package_path}</h2>
              </div>
              <div className="header-actions">
                <span className={`status-pill ${selectedAudit.status}`}>{selectedAudit.status}</span>
                {selectedAudit.pipeline_summary?.overall_risk && (
                  <span className="risk-pill">{selectedAudit.pipeline_summary.overall_risk}</span>
                )}
                <button className="icon-button" onClick={() => loadSelected(selectedAudit.audit_id)} aria-label={t.refresh}>
                  <RefreshCw size={16} aria-hidden="true" />
                </button>
                {selectedAudit.status !== "running" && selectedAudit.status !== "queued" && (
                  <button className="icon-button danger" onClick={() => deleteAudit(selectedAudit.audit_id)} aria-label={t.delete}>
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                )}
              </div>
            </header>

            {selectedAudit.status === "failed" && (
              <section className="panel">
                <h3>Failure Log</h3>
                <pre>{selectedAudit.error || selectedAudit.stderr_tail || selectedAudit.stdout_tail}</pre>
              </section>
            )}

            {selectedAudit.status !== "completed" && selectedAudit.status !== "failed" && (
              <section className="panel">
                <h3>{selectedAudit.status}</h3>
                <pre>{selectedAudit.stdout_tail || selectedAudit.stderr_tail || "Waiting for pipeline output..."}</pre>
              </section>
            )}

            {detail && (
              <>
                <CoveragePanel coverage={detail.coverage} t={t} />
                <section className="two-column">
                  <TraceabilityPanel summary={detail.audit_summary} title={t.traceability} />
                  <MissingMaterialsPanel summary={detail.audit_summary} title={t.missing} />
                </section>
                <section className="panel">
                  <div className="section-title-row">
                    <h3>{t.findings}</h3>
                    <select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}>
                      {riskOptions.map((risk) => (
                        <option key={risk} value={risk}>{risk === "all" ? t.allRisks : risk}</option>
                      ))}
                    </select>
                  </div>
                  <p className="scope-line">{t.scopeNote}</p>
                  {findings.length === 0 && <EmptyState text={t.noFindings} />}
                  <div className="finding-list">
                    {findings.map((finding: Record<string, any>, index: number) => (
                      <FindingRow key={finding.finding_id || index} auditId={selectedAudit.audit_id} finding={finding} t={t} />
                    ))}
                  </div>
                </section>
                <section className="panel report-panel">
                  <div className="section-title-row">
                    <h3>{t.report}</h3>
                    <FileText size={18} aria-hidden="true" />
                  </div>
                  <pre>{report}</pre>
                </section>
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function CoveragePanel({ coverage, t }: { coverage: Record<string, any>; t: typeof labels["zh"] }) {
  const executed = coverage.modules_executed || [];
  const notExecuted = coverage.modules_not_executed || [];
  return (
    <section className="coverage-band">
      <div>
        <h3>{t.coverage}</h3>
        <p>{coverage.scope_note}</p>
      </div>
      <div className="coverage-metrics">
        <Metric label="Images" value={`${coverage.image_panels_screened || 0}`} />
        <Metric label="Unreadable" value={`${coverage.image_files_unreadable || 0}`} />
        <Metric label="Tables" value={`${coverage.source_tables_screened || 0}`} />
      </div>
      <div className="coverage-columns">
        <ListBlock title={t.executed} rows={executed} />
        <ListBlock title={t.notExecuted} rows={notExecuted} />
      </div>
    </section>
  );
}

function TraceabilityPanel({ summary, title }: { summary: Record<string, any>; title: string }) {
  const rows = summary.positive_provenance || [];
  return (
    <section className="panel">
      <h3>{title}</h3>
      <div className="compact-list">
        {rows.length === 0 && <span className="muted">None</span>}
        {rows.map((row: Record<string, any>, index: number) => (
          <div className="compact-row" key={row.provenance_id || index}>
            <strong>{row.figure_panel || row.left || row.source_path || "provenance"}</strong>
            <span>{row.source_record || row.right || row.target_path || row.relation_type}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function MissingMaterialsPanel({ summary, title }: { summary: Record<string, any>; title: string }) {
  const rows = summary.materials_missing || summary.traceability_gaps || [];
  return (
    <section className="panel">
      <h3>{title}</h3>
      <div className="compact-list">
        {rows.length === 0 && <span className="muted">None listed</span>}
        {rows.map((row: any, index: number) => (
          <div className="compact-row" key={index}>
            <strong>{typeof row === "string" ? row : row.material || row.path || "material"}</strong>
            <span>{typeof row === "string" ? "" : row.reason || row.status || ""}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function FindingRow({ auditId, finding, t }: { auditId: string; finding: Record<string, any>; t: typeof labels["zh"] }) {
  const risk = finding.calibrated_risk_level || finding.risk_level || "R0";
  const crops = extractEvidencePaths(finding);
  return (
    <article className="finding-row">
      <div className="finding-title">
        <span className={`risk-chip ${risk}`}>{risk}</span>
        <div>
          <h4>{finding.finding_type || finding.title || finding.finding_id}</h4>
          <p>{finding.location || finding.locations?.join(", ") || finding.evidence_type}</p>
        </div>
      </div>
      <div className="finding-grid">
        <DetailList title={t.benign} rows={finding.benign_explanations_considered || finding.benign_explanations || []} />
        <DetailList title={t.required} rows={finding.required_materials_to_resolve || finding.required_materials || []} />
        <DetailList title={t.action} rows={[finding.recommended_action].filter(Boolean)} />
      </div>
      {crops.length > 0 && (
        <div className="evidence-strip">
          <h5>{t.evidence}</h5>
          {crops.map((path) => (
            <img key={path} src={`/api/audits/${auditId}/evidence/${encodePath(path)}`} alt={path} />
          ))}
        </div>
      )}
    </article>
  );
}

function DetailList({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div>
      <h5>{title}</h5>
      <ul>
        {rows.length === 0 && <li className="muted">None listed</li>}
        {rows.map((row, index) => <li key={index}>{String(row)}</li>)}
      </ul>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ListBlock({ title, rows }: { title: string; rows: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      <ul>
        {rows.map((row) => <li key={row}>{row}</li>)}
      </ul>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

function extractEvidencePaths(value: any): string[] {
  const paths = new Set<string>();
  function visit(item: any) {
    if (!item) return;
    if (typeof item === "string") {
      const normalized = normalizeEvidencePath(item);
      if (normalized) paths.add(normalized);
      return;
    }
    if (Array.isArray(item)) {
      item.forEach(visit);
      return;
    }
    if (typeof item === "object") {
      Object.values(item).forEach(visit);
    }
  }
  visit(value.evidence);
  return Array.from(paths);
}

function normalizeEvidencePath(path: string): string | null {
  if (!/\.(png|jpg|jpeg|webp)$/i.test(path)) return null;
  const marker = "/evidence/";
  const markerIndex = path.indexOf(marker);
  if (markerIndex >= 0) return path.slice(markerIndex + marker.length);
  if (path.startsWith("evidence/")) return path.slice("evidence/".length);
  if (path.startsWith("local_patch/")) return path;
  return null;
}

function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export default App;
