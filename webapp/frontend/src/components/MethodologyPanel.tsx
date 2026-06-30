// Methodology readiness: structured manual-review prompts from
// methodology_checklist.json. This is not an automated compliance decision.

import { ClipboardCheck } from "lucide-react";
import type { MethodologyCheck, MethodologyChecklist, MethodologyModule } from "../types";
import type { Labels } from "../i18n";
import { Metric, SectionTitle } from "./primitives";

function labelFor(moduleOrCheck: MethodologyModule | MethodologyCheck, zh: boolean): string {
  return String((zh ? moduleOrCheck.label_zh : moduleOrCheck.label_en) || moduleOrCheck.check_id || moduleOrCheck.module_id || "item");
}

function statusText(status: string | undefined, zh: boolean): string {
  const value = status || "";
  const labels: Record<string, [string, string]> = {
    manual_review_ready: ["Manual review ready", "可人工复核"],
    manual_review_limited: ["Manual review limited", "人工复核受限"],
    materials_supplied_manual_review_required: ["Materials supplied", "已有支撑材料"],
    partial_supporting_materials_manual_review_limited: ["Partial support", "部分支撑材料"],
    supporting_material_missing: ["Support missing", "缺少支撑材料"],
    not_requested: ["Not requested", "本次未请求"]
  };
  const pair = labels[value];
  if (!pair) return value.replace(/_/g, " ");
  return zh ? pair[1] : pair[0];
}

function checkRows(modules: MethodologyModule[]): MethodologyCheck[] {
  return modules
    .flatMap((module) =>
      (module.checks || [])
        .filter((check) =>
          check.status === "supporting_material_missing" ||
          check.status === "partial_supporting_materials_manual_review_limited"
        )
        .map((check) => ({ ...check, module_label_en: module.label_en, module_label_zh: module.label_zh }))
    )
    .slice(0, 8);
}

export function MethodologyPanel({
  checklist,
  t
}: {
  checklist?: MethodologyChecklist;
  t: Labels;
}) {
  if (!checklist) return null;
  const zh = t.title.includes("生物");
  const modules = (checklist.modules || []).filter((module) => module.requested);
  const gaps = checkRows(modules);
  const totals = checklist.totals || {};

  return (
    <section className="panel methodology-panel">
      <SectionTitle title={t.methodology} icon={<ClipboardCheck size={18} aria-hidden="true" />} />
      <p className="scope-note">{zh ? checklist.boundary_note_zh : checklist.boundary_note}</p>

      <div className="methodology-metrics">
        <Metric label={t.requestedModules} value={totals.modules_requested ?? modules.length} />
        <Metric label={t.readyReview} value={totals.checks_ready_for_manual_review ?? 0} accent />
        <Metric label={t.partialSupport} value={totals.checks_partial_supporting_materials ?? 0} />
        <Metric label={t.missingSupport} value={totals.checks_missing_supporting_materials ?? 0} />
      </div>

      {modules.length > 0 && (
        <div className="methodology-modules">
          {modules.map((module) => (
            <div className="methodology-module" key={module.module_id}>
              <strong>{labelFor(module, zh)}</strong>
              <span>{module.standard}</span>
              <em>{statusText(module.status, zh)}</em>
            </div>
          ))}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="methodology-gaps">
          <h4 className="list-block-title">{t.action}</h4>
          {gaps.map((check, i) => (
            <div className="methodology-gap-row" key={`${check.check_id}-${i}`}>
              <div>
                <strong>{labelFor(check, zh)}</strong>
                <span>{statusText(check.status, zh)}</span>
              </div>
              <p>{zh ? check.recommended_action_zh : check.recommended_action_en}</p>
              {check.missing_material_categories && check.missing_material_categories.length > 0 && (
                <code>{check.missing_material_categories.join(", ")}</code>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
