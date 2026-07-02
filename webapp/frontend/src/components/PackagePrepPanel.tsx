// Package preparation tools. These create local scaffolding and declaration
// manifests only; they do not validate or clear any integrity candidate.

import { useEffect, useMemo, useState } from "react";
import { FileSpreadsheet, FolderTree, GitBranchPlus, ListChecks, Plus, Save, Sparkles, Trash2 } from "lucide-react";
import type { ClaimManifestSuggestionRow, ClaimManifestRow, ManifestRow, PackageInventory } from "../types";
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
  onSaveClaimManifest: (rows: ClaimManifestRow[]) => Promise<void>;
}

const DEFAULT_MODALITIES = ["microscopy", "western_blot", "chart", "schematic", "other"] as const;

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

function sourceRole(path: string): string {
  if (path.startsWith("figures/")) return "figures";
  if (path.startsWith("raw_images/")) return "raw_images";
  if (path.startsWith("source_data/")) return "source_data";
  return "other";
}

function modalityLabel(t: Labels, value: string): string {
  if (Object.prototype.hasOwnProperty.call(t.modalityLabels, value)) {
    return t.modalityLabels[value as keyof Labels["modalityLabels"]];
  }
  return value;
}

function relationshipKey(row: Pick<ManifestRow, "figure_panel" | "source_record" | "relation_type">): string {
  return `${row.figure_panel}\u0000${row.source_record}\u0000${row.relation_type}`;
}

export function PackagePrepPanel({
  t,
  packagePath,
  inventory,
  loading,
  onInspect,
  onScaffold,
  onSaveManifest,
  onSaveClaimManifest
}: PackagePrepPanelProps) {
  const [rows, setRows] = useState<ManifestRow[]>([]);
  const [claimRows, setClaimRows] = useState<ClaimManifestRow[]>([]);
  const [figure, setFigure] = useState("");
  const [source, setSource] = useState("");
  const [relationType, setRelationType] = useState("declared_derived_from");
  const [modality, setModality] = useState("other");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [savingClaims, setSavingClaims] = useState(false);
  const [claimId, setClaimId] = useState("");
  const [claimText, setClaimText] = useState("");
  const [claimLocation, setClaimLocation] = useState("");
  const [claimFigureOrTable, setClaimFigureOrTable] = useState("");
  const [claimSourceData, setClaimSourceData] = useState("");
  const [claimRawRecord, setClaimRawRecord] = useState("");
  const [claimAnalysisCode, setClaimAnalysisCode] = useState("");
  const [claimProtocol, setClaimProtocol] = useState("");
  const [claimOwner, setClaimOwner] = useState("");
  const [claimStatus, setClaimStatus] = useState("draft");

  useEffect(() => {
    setRows(inventory?.assembly_manifest.rows || []);
    setClaimRows(inventory?.claim_manifest?.rows || []);
  }, [inventory]);

  const figures = inventory?.files_by_role.figures || [];
  const rawImages = inventory?.files_by_role.raw_images || [];
  const sourceData = inventory?.files_by_role.source_data || [];
  const analysisFiles = inventory?.files_by_role.statistics_code || [];
  const protocolFiles = inventory?.files_by_role.protocols || [];
  const claimStatusOptions = inventory?.claim_status_options?.length
    ? inventory.claim_status_options
    : ["draft", "ready", "complete", "resolved", "needs_review"];
  const modalityOptions = inventory?.modality_options?.length
    ? inventory.modality_options
    : [...DEFAULT_MODALITIES];
  const relationTypes = inventory?.relation_types?.length
    ? inventory.relation_types
    : ["declared_derived_from", "same_field_different_channel", "same_membrane_reprobe"];
  const allowedSourceRoles =
    inventory?.relation_allowed_source_roles?.[relationType] ||
    (relationType === "declared_derived_from"
      ? ["raw_images", "source_data"]
      : ["figures", "raw_images"]);
  const assemblySuggestions = inventory?.material_prep_suggestions?.assembly_rows || [];
  const claimSuggestions = inventory?.material_prep_suggestions?.claim_rows || [];
  const prismLinks = inventory?.material_prep_suggestions?.prism_graph_table_links || [];
  const prismErrors = inventory?.material_prep_suggestions?.prism_errors || [];
  const pdfCaptions = inventory?.material_prep_suggestions?.pdf_captions || [];
  const pdfErrors = inventory?.material_prep_suggestions?.pdf_errors || [];
  const docxCaptions = inventory?.material_prep_suggestions?.docx_captions || [];
  const docxWarnings = inventory?.material_prep_suggestions?.docx_warnings || [];
  const docxErrors = inventory?.material_prep_suggestions?.docx_errors || [];
  const pptxLinks = inventory?.material_prep_suggestions?.pptx_links || [];
  const pptxWarnings = inventory?.material_prep_suggestions?.pptx_warnings || [];
  const xlsxSheets = inventory?.material_prep_suggestions?.xlsx_sheets || [];
  const xlsxErrors = inventory?.material_prep_suggestions?.xlsx_errors || [];
  const filenameWarnings = inventory?.material_prep_suggestions?.filename_match_warnings || [];
  const prepSuggestionNote = inventory?.material_prep_suggestions?.scope_note || t.prepSuggestionBoundary;

  const sourceOptions = useMemo(
    () => [
      { label: "raw_images", files: rawImages },
      { label: "source_data", files: sourceData },
      { label: "figures", files: figures.filter((file) => file !== figure) }
    ].filter((group) => allowedSourceRoles.includes(group.label)),
    [allowedSourceRoles, figure, figures, rawImages, sourceData]
  );

  const selectedSourceOptions = useMemo(
    () => sourceOptions.flatMap((group) => group.files),
    [sourceOptions]
  );

  const sourceIsCompatible = !source || (
    allowedSourceRoles.includes(sourceRole(source)) &&
    source !== figure &&
    selectedSourceOptions.includes(source)
  );

  useEffect(() => {
    if (!sourceIsCompatible) setSource("");
  }, [sourceIsCompatible]);

  const canAddRelationship = Boolean(figure && source && sourceIsCompatible);
  const canAddClaim = Boolean(claimId.trim() && claimText.trim());

  const roleRows = useMemo(
    () =>
      ROLE_LABELS.map((role) => {
        const count = inventory?.file_counts[role] || 0;
        const preview = (inventory?.files_by_role[role] || []).slice(0, 3).join(", ");
        return (
          <span key={role}>
            <span className="mono">{role}</span>: {count}
            {preview ? <span className="muted"> · {preview}</span> : null}
          </span>
        );
      }),
    [inventory]
  );

  function addRow() {
    if (!canAddRelationship) return;
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

  function addSuggestedRelationships() {
    const existing = new Set(rows.map((row) => relationshipKey(row)));
    const additions = assemblySuggestions
      .filter((row) => !existing.has(relationshipKey(row)))
      .map(({ suggestion_reason: _suggestionReason, ...row }) => row);
    if (additions.length === 0) return;
    setRows((current) => [...current, ...additions]);
  }

  async function saveRows() {
    setSaving(true);
    try {
      await onSaveManifest(rows);
    } finally {
      setSaving(false);
    }
  }

  function addClaimRow() {
    if (!canAddClaim) return;
    setClaimRows((current) => [
      ...current,
      {
        claim_id: claimId.trim(),
        claim_text: claimText.trim(),
        manuscript_location: claimLocation.trim(),
        figure_or_table: claimFigureOrTable.trim(),
        source_data: claimSourceData,
        raw_record: claimRawRecord,
        analysis_code: claimAnalysisCode,
        protocol: claimProtocol,
        owner: claimOwner.trim(),
        status: claimStatus
      }
    ]);
    setClaimId("");
    setClaimText("");
    setClaimLocation("");
    setClaimFigureOrTable("");
    setClaimSourceData("");
    setClaimRawRecord("");
    setClaimAnalysisCode("");
    setClaimProtocol("");
  }

  function useClaimDraft(row: ClaimManifestSuggestionRow) {
    setClaimId(row.claim_id || "");
    setClaimText(row.claim_text || "");
    setClaimLocation(row.manuscript_location || "");
    setClaimFigureOrTable(row.figure_or_table || "");
    setClaimSourceData(row.source_data || "");
    setClaimRawRecord(row.raw_record || "");
    setClaimAnalysisCode(row.analysis_code || "");
    setClaimProtocol(row.protocol || "");
    setClaimOwner(row.owner || "");
    setClaimStatus(row.status || "draft");
  }

  async function saveClaimRows() {
    setSavingClaims(true);
    try {
      await onSaveClaimManifest(claimRows);
    } finally {
      setSavingClaims(false);
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
                rows={roleRows}
              />
              {(assemblySuggestions.length > 0 || claimSuggestions.length > 0 || prismLinks.length > 0 || pdfCaptions.length > 0 || docxCaptions.length > 0 || pptxLinks.length > 0 || xlsxSheets.length > 0) && (
                <div className="prep-suggestion-block">
                  <h4 className="list-block-title">
                    <Sparkles size={14} aria-hidden="true" />
                    {t.prepSuggestions}
                  </h4>
                  <p>{prepSuggestionNote}</p>
                  {pptxLinks.length > 0 && (
                    <div className="prism-hint-list">
                      <h5>{t.pptxPrepHints}</h5>
                      {pptxLinks.slice(0, 5).map((link, index) => (
                        <div className="prism-hint-row" key={`${link.figure_panel}:${link.source_record}:${index}`}>
                          <strong className="mono">{link.figure_panel}</strong>
                          <span className="mono">{link.source_record}</span>
                          <span className="mono">{link.evidence_source || "figure_assembly"}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {prismLinks.length > 0 && (
                    <div className="prism-hint-list">
                      <h5>{t.prismPrepHints}</h5>
                      {prismLinks.slice(0, 5).map((link, index) => (
                        <div className="prism-hint-row" key={`${link.source_pzfx}:${link.graph_id}:${index}`}>
                          <strong>{link.graph_title || link.graph_id || "Prism graph"}</strong>
                          <span>{link.table_title || link.table_id || t.sourceData}</span>
                          <span className="mono">{link.source_pzfx}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {xlsxSheets.length > 0 && (
                    <div className="prism-hint-list">
                      <h5>{t.xlsxPrepHints}</h5>
                      {xlsxSheets.slice(0, 5).map((sheet, index) => (
                        <div className="prism-hint-row" key={`${sheet.source_xlsx}:${sheet.sheet_name}:${index}`}>
                          <strong>{sheet.suggested_label || sheet.sheet_name}</strong>
                          <span>{(sheet.headers || []).slice(0, 5).join(", ") || t.sourceData}</span>
                          <span className="mono">{sheet.source_xlsx}#{sheet.sheet_name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {pdfCaptions.length > 0 && (
                    <div className="prism-hint-list">
                      <h5>{t.pdfCaptionHints}</h5>
                      {pdfCaptions.slice(0, 5).map((caption, index) => (
                        <div className="prism-hint-row" key={`${caption.caption_id}:${caption.path}:${index}`}>
                          <strong>{caption.label || caption.kind || "PDF caption"}</strong>
                          <span>{caption.text || t.claimText}</span>
                          <span className="mono">{caption.path}{caption.page ? ` p. ${caption.page}` : ""}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {docxCaptions.length > 0 && (
                    <div className="prism-hint-list">
                      <h5>{t.docxCaptionHints}</h5>
                      {docxCaptions.slice(0, 5).map((caption, index) => (
                        <div className="prism-hint-row" key={`${caption.caption_id}:${caption.path}:${index}`}>
                          <strong>{caption.label || caption.kind || "DOCX caption"}</strong>
                          <span>{caption.text || t.claimText}</span>
                          <span className="mono">{caption.path}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {(prismErrors.length > 0 || pdfErrors.length > 0 || docxWarnings.length > 0 || docxErrors.length > 0 || pptxWarnings.length > 0 || xlsxErrors.length > 0 || filenameWarnings.length > 0) && (
                <div className="inventory-warning-block">
                  <h4 className="list-block-title">{t.materialPrepWarnings}</h4>
                  <ul>
                    {prismErrors.slice(0, 4).map((warning, index) => (
                      <li key={`prism-${index}`}>{warning}</li>
                    ))}
                    {pdfErrors.slice(0, 4).map((warning, index) => (
                      <li key={`pdf-${index}`}>{warning}</li>
                    ))}
                    {docxWarnings.slice(0, 4).map((warning, index) => (
                      <li key={`docx-warning-${index}`}>{warning}</li>
                    ))}
                    {docxErrors.slice(0, 4).map((warning, index) => (
                      <li key={`docx-${index}`}>{warning}</li>
                    ))}
                    {pptxWarnings.slice(0, 4).map((warning, index) => (
                      <li key={`pptx-${index}`}>{warning}</li>
                    ))}
                    {xlsxErrors.slice(0, 4).map((warning, index) => (
                      <li key={`xlsx-${index}`}>{warning}</li>
                    ))}
                    {filenameWarnings.slice(0, 6).map((warning, index) => (
                      <li key={`filename-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
              {(inventory.inventory_warnings || []).length > 0 && (
                <div className="inventory-warning-block">
                  <h4 className="list-block-title">{t.inventoryWarnings}</h4>
                  <ul>
                    {(inventory.inventory_warnings || []).slice(0, 6).map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
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
              <div className="manifest-action-row">
                {assemblySuggestions.length > 0 && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={addSuggestedRelationships}
                  >
                    <Sparkles size={15} aria-hidden="true" />
                    {t.addSuggestedRelationships}
                  </button>
                )}
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
                <select value={modality} onChange={(e) => setModality(e.target.value)}>
                  {modalityOptions.map((value) => (
                    <option key={value} value={value}>{modalityLabel(t, value)}</option>
                  ))}
                </select>
              </label>
              <label className="relationship-notes">
                <span>{t.notes}</span>
                <input value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              <button
                type="button"
                className="primary-button relationship-add"
                onClick={addRow}
                disabled={!canAddRelationship}
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

          <div className="manifest-builder">
            <div className="manifest-heading">
              <div>
                <h4>
                  <ListChecks size={16} aria-hidden="true" />
                  {t.claimManifest}
                </h4>
                {inventory.claim_manifest?.path && (
                  <p className="muted">
                    {t.existingClaimManifest}: <span className="mono">{inventory.claim_manifest.path}</span>
                  </p>
                )}
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={saveClaimRows}
                disabled={savingClaims}
              >
                <Save size={15} aria-hidden="true" />
                {t.saveClaimManifest}
              </button>
            </div>
            <p className="scope-note">{t.claimManifestBoundary}</p>

            {claimSuggestions.length > 0 && (
              <div className="claim-suggestion-list">
                <h5>{t.claimDrafts}</h5>
                {claimSuggestions.slice(0, 6).map((row, index) => (
                  <div className="claim-suggestion-row" key={`${row.claim_id}:${row.figure_or_table}:${index}`}>
                    <div>
                      <strong className="mono">{row.claim_id}</strong>
                      <span className="mono">{row.figure_or_table}</span>
                      {row.suggestion_reason ? <small>{row.suggestion_reason}</small> : null}
                    </div>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => useClaimDraft(row)}
                    >
                      <Plus size={14} aria-hidden="true" />
                      {t.useClaimDraft}
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="claim-form">
              <label>
                <span>{t.claimId}</span>
                <input value={claimId} onChange={(e) => setClaimId(e.target.value)} placeholder="C-001" />
              </label>
              <label className="claim-text-field">
                <span>{t.claimText}</span>
                <input value={claimText} onChange={(e) => setClaimText(e.target.value)} />
              </label>
              <label>
                <span>{t.manuscriptLocation}</span>
                <input value={claimLocation} onChange={(e) => setClaimLocation(e.target.value)} placeholder="Results p. 6" />
              </label>
              <label>
                <span>{t.figureOrTable}</span>
                <input value={claimFigureOrTable} onChange={(e) => setClaimFigureOrTable(e.target.value)} placeholder="Figure 1A" />
              </label>
              <label>
                <span>{t.sourceData}</span>
                <select value={claimSourceData} onChange={(e) => setClaimSourceData(e.target.value)}>
                  <option value="">{t.optionalEvidence}</option>
                  {sourceData.map((file) => (
                    <option key={file} value={file}>{file}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.rawRecord}</span>
                <select value={claimRawRecord} onChange={(e) => setClaimRawRecord(e.target.value)}>
                  <option value="">{t.optionalEvidence}</option>
                  {[...rawImages, ...figures].map((file) => (
                    <option key={file} value={file}>{file}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.analysisCode}</span>
                <select value={claimAnalysisCode} onChange={(e) => setClaimAnalysisCode(e.target.value)}>
                  <option value="">{t.optionalEvidence}</option>
                  {analysisFiles.map((file) => (
                    <option key={file} value={file}>{file}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.protocol}</span>
                <select value={claimProtocol} onChange={(e) => setClaimProtocol(e.target.value)}>
                  <option value="">{t.optionalEvidence}</option>
                  {protocolFiles.map((file) => (
                    <option key={file} value={file}>{file}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>{t.owner}</span>
                <input value={claimOwner} onChange={(e) => setClaimOwner(e.target.value)} />
              </label>
              <label>
                <span>{t.status}</span>
                <select value={claimStatus} onChange={(e) => setClaimStatus(e.target.value)}>
                  {claimStatusOptions.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                className="primary-button claim-add"
                onClick={addClaimRow}
                disabled={!canAddClaim}
              >
                <Plus size={15} aria-hidden="true" />
                {t.addClaim}
              </button>
            </div>

            {claimRows.length === 0 ? (
              <p className="muted prep-empty">{t.noClaimRows}</p>
            ) : (
              <div className="manifest-table-wrap">
                <table className="manifest-table claim-table">
                  <thead>
                    <tr>
                      <th>{t.claimId}</th>
                      <th>{t.claimText}</th>
                      <th>{t.figureOrTable}</th>
                      <th>{t.sourceData}</th>
                      <th>{t.rawRecord}</th>
                      <th>{t.analysisCode}</th>
                      <th>{t.protocol}</th>
                      <th>{t.status}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {claimRows.map((row, index) => (
                      <tr key={`${row.claim_id}:${index}`}>
                        <td className="mono">{row.claim_id}</td>
                        <td>{row.claim_text}</td>
                        <td>{row.figure_or_table || "—"}</td>
                        <td className="mono">{row.source_data || "—"}</td>
                        <td className="mono">{row.raw_record || "—"}</td>
                        <td className="mono">{row.analysis_code || "—"}</td>
                        <td className="mono">{row.protocol || "—"}</td>
                        <td>{row.status || "draft"}</td>
                        <td>
                          <button
                            type="button"
                            className="icon-button danger"
                            onClick={() => setClaimRows((current) => current.filter((_, i) => i !== index))}
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
