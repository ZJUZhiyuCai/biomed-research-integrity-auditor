// Package preparation tools. These create local scaffolding and declaration
// manifests only; they do not validate or clear any integrity candidate.

import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FolderTree, GitBranchPlus, Plus, Save, Trash2 } from "lucide-react";
import type { ManifestRow, PackageInventory } from "../types";
import type { Labels } from "../i18n";
import { ListBlock, SectionTitle } from "./primitives";

interface PackagePrepPanelProps {
  t: Labels;
  packagePath: string;
  inventory: PackageInventory | null;
  loading: boolean;
  onInspect: () => void;
  onScaffold: () => void;
  onSaveManifest: (rows: ManifestRow[]) => Promise<void>;
}

const ROLE_LABELS = [
  "figures",
  "raw_images",
  "source_data",
  "figure_assembly",
  "protocols",
  "statistics_code",
  "supplementary",
  "ethics_irb"
];

export function PackagePrepPanel({
  t,
  packagePath,
  inventory,
  loading,
  onInspect,
  onScaffold,
  onSaveManifest
}: PackagePrepPanelProps) {
  const [rows, setRows] = useState<ManifestRow[]>([]);
  const [figure, setFigure] = useState("");
  const [source, setSource] = useState("");
  const [relationType, setRelationType] = useState("declared_derived_from");
  const [modality, setModality] = useState("image");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRows(inventory?.assembly_manifest.rows || []);
  }, [inventory]);

  const figures = inventory?.files_by_role.figures || [];
  const rawImages = inventory?.files_by_role.raw_images || [];
  const sourceData = inventory?.files_by_role.source_data || [];
  const relationTypes = inventory?.relation_types?.length
    ? inventory.relation_types
    : ["declared_derived_from", "same_field_different_channel", "same_membrane_reprobe"];

  const sourceOptions = useMemo(
    () => [
      { label: "raw_images", files: rawImages },
      { label: "source_data", files: sourceData },
      { label: "figures", files: figures }
    ],
    [figures, rawImages, sourceData]
  );

  function addRow() {
    if (!figure || !source) return;
    setRows((current) => [
      ...current,
      {
        figure_panel: figure,
        source_record: source,
        relation_type: relationType,
        modality,
        notes
      }
    ]);
    setNotes("");
  }

  async function saveRows() {
    setSaving(true);
    try {
      await onSaveManifest(rows);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel prep-panel">
      <SectionTitle
        title={t.packagePrep}
        icon={<GitBranchPlus size={17} aria-hidden="true" />}
        actions={
          <div className="prep-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={onInspect}
              disabled={loading || !packagePath.trim()}
            >
              <FolderTree size={15} aria-hidden="true" />
              {t.inspectPackage}
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={onScaffold}
              disabled={loading || !packagePath.trim()}
            >
              <Plus size={15} aria-hidden="true" />
              {t.scaffoldPackage}
            </button>
          </div>
        }
      />
      <p className="scope-line">{t.packagePrepIntro}</p>
      <p className="scope-note">{inventory?.scope_note || t.manifestBoundary}</p>

      {!inventory ? (
        <p className="muted prep-empty">{t.noInventory}</p>
      ) : (
        <>
          <div className="prep-grid">
            <div>
              <h4 className="list-block-title">{t.packageStructure}</h4>
              <div className="folder-grid">
                {ROLE_LABELS.map((role) => {
                  const present = Boolean(inventory.folders[role]);
                  return (
                    <span key={role} className={`folder-chip${present ? " present" : " missing"}`}>
                      <span className="folder-dot" />
                      <span className="mono">{role}</span>
                      <span>{present ? t.presentFolder : t.missingFolder}</span>
                    </span>
                  );
                })}
              </div>
            </div>
            <div>
              <ListBlock
                title={t.detectedFiles}
                empty={t.emptyRole}
                rows={ROLE_LABELS.map((role) => {
                  const count = inventory.file_counts[role] || 0;
                  const preview = (inventory.files_by_role[role] || []).slice(0, 3).join(", ");
                  return (
                    <span>
                      <span className="mono">{role}</span>: {count}
                      {preview ? <span className="muted"> · {preview}</span> : null}
                    </span>
                  );
                })}
              />
            </div>
          </div>

          <div className="manifest-builder">
            <div className="manifest-heading">
              <div>
                <h4>
                  <FileSpreadsheet size={16} aria-hidden="true" />
                  {t.declaredRelationships}
                </h4>
                {inventory.assembly_manifest.path && (
                  <p className="muted">
                    {t.existingManifest}: <span className="mono">{inventory.assembly_manifest.path}</span>
                  </p>
                )}
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={saveRows}
                disabled={saving}
              >
                <Save size={15} aria-hidden="true" />
                {t.saveManifest}
              </button>
            </div>

            <div className="relationship-form">
              <label>
                <span>{t.figurePanel}</span>
                <select value={figure} onChange={(e) => setFigure(e.target.value)}>
                  <option value="">{t.chooseFigure}</option>
                  {figures.map((file) => (
                    <option key={file} value={file}>{file}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.sourceRecord}</span>
                <select value={source} onChange={(e) => setSource(e.target.value)}>
                  <option value="">{t.chooseSource}</option>
                  {sourceOptions.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.files.map((file) => (
                        <option key={`${group.label}:${file}`} value={file}>{file}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.relationType}</span>
                <select value={relationType} onChange={(e) => setRelationType(e.target.value)}>
                  {relationTypes.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.modality}</span>
                <input value={modality} onChange={(e) => setModality(e.target.value)} />
              </label>
              <label className="relationship-notes">
                <span>{t.notes}</span>
                <input value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              <button
                type="button"
                className="primary-button relationship-add"
                onClick={addRow}
                disabled={!figure || !source}
              >
                <Plus size={15} aria-hidden="true" />
                {t.addRelationship}
              </button>
            </div>

            {rows.length === 0 ? (
              <p className="muted prep-empty">{t.noManifestRows}</p>
            ) : (
              <div className="manifest-table-wrap">
                <table className="manifest-table">
                  <thead>
                    <tr>
                      <th>{t.figurePanel}</th>
                      <th>{t.sourceRecord}</th>
                      <th>{t.relationType}</th>
                      <th>{t.modality}</th>
                      <th>{t.notes}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${row.figure_panel}:${row.source_record}:${index}`}>
                        <td className="mono">{row.figure_panel}</td>
                        <td className="mono">{row.source_record}</td>
                        <td>{row.relation_type}</td>
                        <td>{row.modality || "—"}</td>
                        <td>{row.notes || "—"}</td>
                        <td>
                          <button
                            type="button"
                            className="icon-button danger"
                            onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                            aria-label={t.remove}
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
