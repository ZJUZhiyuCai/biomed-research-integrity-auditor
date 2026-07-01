// App: top-level state, data flow, polling, toasts, theme, lightbox.
// Integrity Boundary: no score/verdict/PASS-FAIL language anywhere.

import { useEffect, useMemo, useState } from "react";
import { ToastProvider, useToast } from "./components/Toast";
import { Sidebar } from "./components/Sidebar";
import { Workspace } from "./components/Workspace";
import { EvidenceLightbox } from "./components/EvidenceLightbox";
import {
  cancelAudit,
  createAudit,
  deleteAudit,
  getAudit,
  getHealth,
  getReport,
  getSummary,
  inspectPackage,
  listAudits,
  saveAssemblyManifest,
  scaffoldPackage,
  updateAction,
  uploadZip
} from "./api";
import { getLabels } from "./i18n";
import type { AuditJob, ExamplePackage, Language, ManifestRow, PackageInventory, SummaryPayload, Theme } from "./types";

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
  const [examplePackages, setExamplePackages] = useState<ExamplePackage[]>([]);
  const [mode, setMode] = useState("internal_presubmission");
  const [scanProfile, setScanProfile] = useState("standard");
  const [domains, setDomains] = useState("wetlab,animal,cell");
  const [provider, setProvider] = useState("auto");
  const [referenceProvider, setReferenceProvider] = useState("none");
  const [compareToAuditId, setCompareToAuditId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);
  const [packageInventory, setPackageInventory] = useState<PackageInventory | null>(null);
  const [packagePrepLoading, setPackagePrepLoading] = useState(false);

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
    selectedAudit?.status === "queued" ||
    selectedAudit?.status === "running" ||
    selectedAudit?.status === "cancel_requested";

  async function loadAudits() {
    setAuditsLoading(true);
    try {
      const payload = await listAudits();
      const auditList = payload.audits || [];
      setAudits(auditList);
      setSelectedId((current) => current ?? (auditList[0]?.audit_id ?? null));
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
    loadHealth();
  }, []);

  async function loadHealth() {
    try {
      const payload = await getHealth();
      setExamplePackages(payload.example_packages || []);
    } catch {
      setExamplePackages([]);
    }
  }

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

  async function startAuditForPath(path: string) {
    if (!path.trim()) {
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
        package_path: path,
        mode,
        scan_profile: scanProfile,
        domains,
        external_literature_provider: provider,
        reference_check_provider: referenceProvider,
        compare_to_audit_id: compareToAuditId || null
      });
      setAudits((items) => [job, ...items]);
      setSelectedId(job.audit_id);
      toast("success", t.runStarted);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  async function runAudit() {
    await startAuditForPath(packagePath);
  }

  async function handleRunExample(example: ExamplePackage) {
    setPackagePath(example.path);
    setPackageInventory(null);
    await startAuditForPath(example.path);
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
      const job = await uploadZip(file, mode, scanProfile, domains, provider, referenceProvider, compareToAuditId || null);
      setAudits((items) => [job, ...items]);
      setSelectedId(job.audit_id);
      toast("success", t.uploaded);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  function handlePackagePath(value: string) {
    setPackagePath(value);
    if (packageInventory && value.trim() !== packageInventory.package_path) {
      setPackageInventory(null);
    }
  }

  async function handleInspectPackage() {
    if (!packagePath.trim()) {
      toast("error", t.invalidPath);
      return;
    }
    setPackagePrepLoading(true);
    try {
      const payload = await inspectPackage(packagePath);
      setPackageInventory(payload.inventory);
      toast("success", t.packageInspected);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    } finally {
      setPackagePrepLoading(false);
    }
  }

  async function handleScaffoldPackage() {
    if (!packagePath.trim()) {
      toast("error", t.invalidPath);
      return;
    }
    setPackagePrepLoading(true);
    try {
      const payload = await scaffoldPackage(packagePath);
      setPackageInventory(payload.inventory);
      toast("success", t.scaffolded);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    } finally {
      setPackagePrepLoading(false);
    }
  }

  async function handleSaveManifest(rows: ManifestRow[]) {
    if (!packagePath.trim()) {
      toast("error", t.invalidPath);
      return;
    }
    try {
      const payload = await saveAssemblyManifest(packagePath, rows);
      setPackageInventory(payload.inventory);
      toast("success", t.manifestSaved);
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

  async function handleCancel() {
    if (!selectedAuditId) return;
    try {
      const job = await cancelAudit(selectedAuditId);
      setAudits((items) => [job, ...items.filter((i) => i.audit_id !== selectedAuditId)]);
      toast("success", t.cancelRequested);
    } catch (err) {
      setError(String(err));
      toast("error", String(err));
    }
  }

  async function handleActionUpdate(actionId: string, patch: Parameters<typeof updateAction>[2]) {
    if (!selectedAuditId) return;
    try {
      await updateAction(selectedAuditId, actionId, patch);
      const summary = await getSummary(selectedAuditId);
      setDetail(summary);
      toast("success", t.actionSaved);
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
      <a className="skip-link" href="#main-content">{t.skipToContent}</a>
      <Sidebar
        t={t}
        audits={audits}
        selectedId={selectedId}
        loading={auditsLoading}
        language={language}
        theme={theme}
        packagePath={packagePath}
        mode={mode}
        scanProfile={scanProfile}
        domains={domains}
        provider={provider}
        referenceProvider={referenceProvider}
        compareToAuditId={compareToAuditId}
        onLanguage={setLanguage}
        onTheme={setTheme}
        onSelect={setSelectedId}
        onRefresh={loadAudits}
        onPackagePath={handlePackagePath}
        onMode={setMode}
        onScanProfile={setScanProfile}
        onDomains={setDomains}
        onProvider={setProvider}
        onReferenceProvider={setReferenceProvider}
        onCompareToAuditId={setCompareToAuditId}
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
        packagePath={packagePath}
        examples={examplePackages}
        packageInventory={packageInventory}
        packagePrepLoading={packagePrepLoading}
        onInspectPackage={handleInspectPackage}
        onScaffoldPackage={handleScaffoldPackage}
        onSaveManifest={handleSaveManifest}
        onRunExample={handleRunExample}
        onRefresh={() => selectedAuditId && loadSelected(selectedAuditId)}
        onDelete={handleDelete}
        onCancel={handleCancel}
        onActionUpdate={handleActionUpdate}
        onEvidence={openEvidence}
      />
      {lightbox && (
        <EvidenceLightbox
          auditId={lightbox.auditId}
          images={lightbox.images}
          index={lightbox.index}
          t={t}
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
