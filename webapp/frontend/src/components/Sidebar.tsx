// Sidebar: brand, privacy banner, language/theme toggle, run form (with
// zip drop-zone wired to POST /api/audits/upload), and audit history list.

import { useRef, useState, type DragEvent } from "react";
import { Moon, Play, RefreshCw, ShieldCheck, Sun, Upload } from "lucide-react";
import type { AuditJob, Language, Theme } from "../types";
import type { Labels } from "../i18n";
import { SidebarListSkeleton } from "./Skeleton";

interface SidebarProps {
  t: Labels;
  audits: AuditJob[];
  selectedId: string | null;
  loading: boolean;
  language: Language;
  theme: Theme;
  packagePath: string;
  mode: string;
  scanProfile: string;
  domains: string;
  provider: string;
  referenceProvider: string;
  compareToAuditId: string;
  onLanguage: (l: Language) => void;
  onTheme: (t: Theme) => void;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  onPackagePath: (v: string) => void;
  onMode: (v: string) => void;
  onScanProfile: (v: string) => void;
  onDomains: (v: string) => void;
  onProvider: (v: string) => void;
  onReferenceProvider: (v: string) => void;
  onCompareToAuditId: (v: string) => void;
  onRun: () => void;
  onUpload: (file: File) => void;
}

export function Sidebar(props: SidebarProps) {
  const { t } = props;
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) props.onUpload(file);
  }

  return (
    <aside className="sidebar">
      <div className="brand-row">
        <ShieldCheck size={22} aria-hidden="true" />
        <h1>{t.brand}</h1>
      </div>
      <div className="privacy-banner">{t.privacy}</div>

      <div className="toggle-row">
        <div className="language-toggle" role="group" aria-label="Language">
          <button
            type="button"
            className={props.language === "zh" ? "active" : ""}
            onClick={() => props.onLanguage("zh")}
          >
            中
          </button>
          <button
            type="button"
            className={props.language === "en" ? "active" : ""}
            onClick={() => props.onLanguage("en")}
          >
            EN
          </button>
        </div>
        <button
          type="button"
          className="theme-toggle"
          onClick={() => props.onTheme(props.theme === "dark" ? "light" : "dark")}
          aria-label={t.theme}
        >
          {props.theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
        </button>
      </div>

      <form
        className="run-form"
        onSubmit={(event) => {
          event.preventDefault();
          props.onRun();
        }}
      >
        <label>
          <span>{t.packagePath}</span>
          <input
            value={props.packagePath}
            onChange={(e) => props.onPackagePath(e.target.value)}
            placeholder={t.packagePathHint}
          />
        </label>
        <label>
          <span>{t.mode}</span>
          <select value={props.mode} onChange={(e) => props.onMode(e.target.value)}>
            <option value="internal_presubmission">{t.modeLabels.internal_presubmission}</option>
            <option value="external_public_material">{t.modeLabels.external_public_material}</option>
            <option value="response_to_concern">{t.modeLabels.response_to_concern}</option>
          </select>
        </label>
        <label>
          <span>{t.scanProfile}</span>
          <select value={props.scanProfile} onChange={(e) => props.onScanProfile(e.target.value)}>
            <option value="quick">{t.scanProfileLabels.quick}</option>
            <option value="standard">{t.scanProfileLabels.standard}</option>
            <option value="deep">{t.scanProfileLabels.deep}</option>
          </select>
        </label>
        <label>
          <span>{t.domains}</span>
          <input
            value={props.domains}
            onChange={(e) => props.onDomains(e.target.value)}
            placeholder={t.domainsHint}
          />
        </label>
        <label>
          <span>{t.provider}</span>
          <select value={props.provider} onChange={(e) => props.onProvider(e.target.value)}>
            <option value="auto">{t.providerLabels.auto}</option>
            <option value="none">{t.providerLabels.none}</option>
            <option value="fixture">{t.providerLabels.fixture}</option>
            <option value="europepmc">{t.providerLabels.europepmc}</option>
            <option value="crossref">{t.providerLabels.crossref}</option>
          </select>
        </label>
        <label>
          <span>{t.referenceProvider}</span>
          <select value={props.referenceProvider} onChange={(e) => props.onReferenceProvider(e.target.value)}>
            <option value="none">{t.referenceProviderLabels.none}</option>
            <option value="crossref">{t.referenceProviderLabels.crossref}</option>
          </select>
        </label>
        <label>
          <span>{t.compareTo}</span>
          <select value={props.compareToAuditId} onChange={(e) => props.onCompareToAuditId(e.target.value)}>
            <option value="">{t.noCompare}</option>
            {props.audits
              .filter((audit) => audit.status === "completed")
              .map((audit) => (
                <option key={audit.audit_id} value={audit.audit_id}>
                  {auditLabel(audit)}
                </option>
              ))}
          </select>
        </label>
        <button className="primary-button" type="submit">
          <Play size={16} aria-hidden="true" />
          {t.run}
        </button>
      </form>

      <div
        className={`upload-zone${dragging ? " is-dragging" : ""}`}
        role="button"
        tabIndex={0}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") fileRef.current?.click();
        }}
      >
        <Upload size={18} aria-hidden="true" />
        <span className="upload-label">{t.upload}</span>
        <span className="upload-hint">{t.uploadHint}</span>
        <input
          ref={fileRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) props.onUpload(file);
            e.target.value = "";
          }}
        />
      </div>

      <div className="history-header">
        <h2>{t.history}</h2>
        <button
          type="button"
          className="icon-button"
          onClick={props.onRefresh}
          aria-label={t.refresh}
        >
          <RefreshCw size={16} aria-hidden="true" />
        </button>
      </div>
      <div className="audit-list">
        {props.loading && props.audits.length === 0 ? (
          <SidebarListSkeleton />
        ) : (
          props.audits.map((audit) => (
            <button
              type="button"
              key={audit.audit_id}
              className={`audit-list-item${props.selectedId === audit.audit_id ? " selected" : ""}`}
              onClick={() => props.onSelect(audit.audit_id)}
            >
              <span className={`status-dot ${audit.status}`} />
              <span className="audit-name mono">{audit.audit_id}</span>
              <span className="audit-risk">{audit.pipeline_summary?.overall_risk || audit.status}</span>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}

function auditLabel(audit: AuditJob): string {
  const packageName = audit.package_path.split(/[\\/]/).filter(Boolean).pop() || audit.audit_id;
  const time = new Date(audit.created_at * 1000).toLocaleString();
  const risk = audit.pipeline_summary?.overall_risk || audit.status;
  return `${packageName} · ${time} · ${risk}`;
}
