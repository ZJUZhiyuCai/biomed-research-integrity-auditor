// Thin API client. All endpoints are served by webapp/backend/app.py on the
// same origin (Vite proxies /api -> 127.0.0.1:8765 in dev; in production the
// FastAPI app mounts the built dist/). No contract changes here — we only
// consume existing endpoints, including the previously-unused zip upload.

import type { AuditJob, ManifestRow, PackageInventory, SummaryPayload } from "./types";

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

export interface CreateAuditInput {
  package_path: string;
  mode: string;
  scan_profile: string;
  domains: string;
  external_literature_provider: string;
}

export const listAudits = () => api<{ audits: AuditJob[] }>("/api/audits");

export const createAudit = (input: CreateAuditInput) =>
  api<AuditJob>("/api/audits", { method: "POST", body: JSON.stringify(input) });

export const getAudit = (id: string) => api<AuditJob>(`/api/audits/${id}`);

export const getSummary = (id: string) =>
  api<SummaryPayload>(`/api/audits/${id}/summary`);

export const deleteAudit = (id: string) =>
  api<{ deleted: string }>(`/api/audits/${id}`, { method: "DELETE" });

export const inspectPackage = (packagePath: string) =>
  api<{ inventory: PackageInventory }>("/api/packages/inspect", {
    method: "POST",
    body: JSON.stringify({ package_path: packagePath })
  });

export const scaffoldPackage = (packagePath: string) =>
  api<{ inventory: PackageInventory }>("/api/packages/scaffold", {
    method: "POST",
    body: JSON.stringify({ package_path: packagePath })
  });

export const saveAssemblyManifest = (packagePath: string, rows: ManifestRow[]) =>
  api<{ manifest_path: string; rows_written: number; inventory: PackageInventory }>(
    "/api/packages/assembly-manifest",
    {
      method: "POST",
      body: JSON.stringify({ package_path: packagePath, rows })
    }
  );

export async function getReport(id: string): Promise<string> {
  const response = await fetch(`/api/audits/${id}/report.md`);
  return response.ok ? await response.text() : "";
}

// multipart/form-data — do NOT set Content-Type; the browser sets the boundary.
export async function uploadZip(
  file: File,
  mode: string,
  scan_profile: string,
  domains: string,
  external_literature_provider: string
): Promise<AuditJob> {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  form.append("scan_profile", scan_profile);
  form.append("domains", domains);
  form.append("external_literature_provider", external_literature_provider);
  const response = await fetch("/api/audits/upload", { method: "POST", body: form });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json() as Promise<AuditJob>;
}

export function evidenceUrl(auditId: string, path: string): string {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  return `/api/audits/${auditId}/evidence/${encoded}`;
}
