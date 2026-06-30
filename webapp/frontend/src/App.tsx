// App: top-level state, data flow, polling, toasts, theme, lightbox.
// Integrity Boundary: no score/verdict/PASS-FAIL language anywhere.

import { useEffect, useMemo, useState } from "react";
import { ToastProvider, useToast } from "./components/Toast";
import { Sidebar } from "./components/Sidebar";
import { Workspace } from "./components/Workspace";
import { EvidenceLightbox } from "./components/EvidenceLightbox";
import {
  createAudit,
  deleteAudit,
  getAudit,
  getReport,
  getSummary,
  listAudits,
  uploadZip
} from "./api";
import { getLabels } from "./i18n";
import type { AuditJob, Language, SummaryPayload, Theme } from "./types";

const THEME_KEY = "biomed-self-audit-theme";
const MAX_ZIP_BYTES = 250 * 1024 * 1024;

function getInitialTheme(): Theme {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

interface LightboxState {
  auditId: string;
  images: string[];
  index: number;
}

function AppInner() {
  const toast = useToast();
  const [language, setLanguage] = useState<Language>("zh");
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  const [audits, setAudits] = useState<AuditJob[]>([]);
  const [auditsLoading, setAuditsLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SummaryPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [report, setReport] = useState("");
  const [packagePath, setPackagePath] = useState("");
  const [mode, setMode] = useState("internal_presubmission");
  const [domains, setDomains] = useState("wetlab,animal,cell");
  const [provider, setProvider] = useState("auto");
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  const t = useMemo(() => getLabels(language), [language]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const selectedAudit = audits.find((a) => a.audit_id === selectedId) || null;
  const selectedAuditId = selectedAudit?.audit_id;
  const isLive =
    selectedAudit?.status === "queued" || selectedAudit?.status === "running";

  async function loadAudits() {
    setAuditsLoading(true);
    try {
      const payload = await listAudits();
      setAudits(payload.audits);
      setSelectedId((current) => current ?? (payload.audits[0]?.audit_id ?? null));
    } catch (err) {
      setError(String(err));
    } finally {
      setAuditsLoading(false);
    }
  }

  async function loadSelected(auditId: string) {
    setDetailLoading(true);
    try {
      const job = await getAudit(auditId);
      setAudits((items) => [job, ...items.filter((i) => i.audit_id !== auditId)]);
      if (job.status === "completed") {
        const [summary, reportText] = await Promise.all([
          getSummary(auditId),
          getReport(auditId)
        ]);
        setDetail(summary);
        setReport(reportText);
      } else {
        setDetail(null);
        setReport("");
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    loadAudits();
  }, []);

  useEffect(() => {
    if (selectedAuditId) loadSelected(selectedAuditId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAuditId]);

  useEffect(() => {
    if (!selectedAuditId || !isLive) return;
    const timer = window.setInterval(() => {
      loadSelected(selectedAuditId);
    }, 2000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAuditId, isLive]);

  async function runAudit() {
    if (!packagePath.trim()) {
      toast("error", t.invalidPath);
      return;
    }
    if (!domains.trim()) {
      toast("error", t.invalidDomains);
      return;
    }
    setError(null);
    try {
      const job = await createAudit({
        package_path: packagePath,
        mode,
        domains,
        external_literature_provider: provider
      });
      setAudits((items) => [job, ...items]);
      setSelectedId(job.audit_id);
      toast("success", t.runStarted);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  async function handleUpload(file: File) {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast("error", t.invalidZip);
      return;
    }
    if (file.size > MAX_ZIP_BYTES) {
      toast("error", t.invalidZip);
      return;
    }
    setError(null);
    try {
      const job = await uploadZip(file, mode, domains, provider);
      setAudits((items) => [job, ...items]);
      setSelectedId(job.audit_id);
      toast("success", t.uploaded);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  async function handleDelete() {
    if (!selectedAuditId) return;
    try {
      await deleteAudit(selectedAuditId);
      setAudits((items) => items.filter((i) => i.audit_id !== selectedAuditId));
      setSelectedId(null);
      setDetail(null);
      setReport("");
      toast("success", t.deleted);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  function openEvidence(images: string[], index: number) {
    if (!selectedAuditId || images.length === 0) return;
    setLightbox({ auditId: selectedAuditId, images, index });
  }

  return (
    <div className="app-shell">
      <Sidebar
        t={t}
        audits={audits}
        selectedId={selectedId}
        loading={auditsLoading}
        language={language}
        theme={theme}
        packagePath={packagePath}
        mode={mode}
        domains={domains}
        provider={provider}
        onLanguage={setLanguage}
        onTheme={setTheme}
        onSelect={setSelectedId}
        onRefresh={loadAudits}
        onPackagePath={setPackagePath}
        onMode={setMode}
        onDomains={setDomains}
        onProvider={setProvider}
        onRun={runAudit}
        onUpload={handleUpload}
      />
      <Workspace
        t={t}
        audit={selectedAudit}
        detail={detail}
        report={report}
        loading={detailLoading}
        error={error}
        onRefresh={() => selectedAuditId && loadSelected(selectedAuditId)}
        onDelete={handleDelete}
        onEvidence={openEvidence}
      />
      {lightbox && (
        <EvidenceLightbox
          auditId={lightbox.auditId}
          images={lightbox.images}
          index={lightbox.index}
          onClose={() => setLightbox(null)}
          onIndex={(i) =>
            setLightbox((prev) => (prev ? { ...prev, index: i } : null))
          }
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  );
}
