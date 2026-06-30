// Evidence helpers. Findings carry an `evidence` object whose shape varies
// per detector module:
//   - image similarity: { left, right, best_transform, best_hash_method,
//     best_hamming_distance, all_method_distances, threshold } with paths
//     like figures/Figure_3A.png (package-relative, NOT under evidence/).
//   - pseudoreplication: { file, group, biological_unit_count,
//     technical_unit_count, row_count, reported_n_appears_technical, ... }.
//   - local_patch_reuse: candidate evidence contains evidence_crops with
//     { crop_a, crop_b, side_by_side } written to <output>/evidence/local_patch/*.
//
// extractEvidencePaths pulls image paths that the backend can serve (those
// under evidence/ or local_patch/). extractEvidenceMetrics pulls the numeric
// / categorical fields for a structured metric card.

const IMAGE_RE = /\.(png|jpg|jpeg|webp)$/i;
const EVIDENCE_MARKER = "/evidence/";

export function normalizeEvidencePath(path: string): string | null {
  if (!IMAGE_RE.test(path)) return null;
  const markerIndex = path.indexOf(EVIDENCE_MARKER);
  if (markerIndex >= 0) return path.slice(markerIndex + EVIDENCE_MARKER.length);
  if (path.startsWith("evidence/")) return path.slice("evidence/".length);
  if (path.startsWith("local_patch/")) return path;
  return null;
}

export function encodePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

export function extractEvidencePaths(value: unknown): string[] {
  const paths = new Set<string>();
  function visit(item: unknown) {
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
      Object.values(item as Record<string, unknown>).forEach(visit);
    }
  }
  visit(value);
  return Array.from(paths);
}

export interface EvidenceMetric {
  key: string;
  value: string;
}

// Flatten a nested distances map (e.g. all_method_distances: {phash: 3, ...})
// into individual metric rows.
function flattenDistances(label: string, value: unknown, out: EvidenceMetric[]) {
  if (!value || typeof value !== "object") return;
  for (const [method, distance] of Object.entries(value as Record<string, unknown>)) {
    if (distance === null || distance === undefined) continue;
    out.push({ key: `${label} · ${method}`, value: String(distance) });
  }
}

export function extractEvidenceMetrics(evidence: unknown): EvidenceMetric[] {
  if (!evidence || typeof evidence !== "object") return [];
  const out: EvidenceMetric[] = [];
  for (const [key, value] of Object.entries(evidence as Record<string, unknown>)) {
    if (value === null || value === undefined) continue;
    if (typeof value === "string" && normalizeEvidencePath(value)) continue; // skip image paths
    if (Array.isArray(value) && key === "reported_n_basis_values") {
      out.push({ key: key.replace(/_/g, " "), value: value.join(", ") || "—" });
      continue;
    }
    if (typeof value === "object") {
      if (key === "all_method_distances") flattenDistances("distance", value, out);
      continue;
    }
    out.push({ key: key.replace(/_/g, " "), value: String(value) });
  }
  return out;
}
