// Markdown report rendered to HTML (marked + DOMPurify). The original UI
// dumped raw markdown into a <pre>. Tables, blockquotes, fenced code, and
// headings are styled via .markdown-body in styles.css.

import { useMemo } from "react";
import { FileText } from "lucide-react";
import type { Labels } from "../i18n";
import { SectionTitle } from "./primitives";
import { renderMarkdown } from "../lib/markdown";

export function ReportPanel({ report, t }: { report: string; t: Labels }) {
  const html = useMemo(() => renderMarkdown(report), [report]);
  if (!report) return null;
  return (
    <section className="panel report-panel">
      <SectionTitle title={t.report} icon={<FileText size={18} aria-hidden="true" />} />
      <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
    </section>
  );
}
