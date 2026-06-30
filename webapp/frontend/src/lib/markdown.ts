// Markdown rendering for audit reports. Reports are produced by the local
// pipeline (trusted source) but we still sanitize on principle. Reports use
// headings, GFM tables, blockquotes, and fenced code blocks (sometimes with
// non-standard language tags like `json AUDIT_JSON_SUMMARY`, which marked
// tolerates).

import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: false });

export function renderMarkdown(md: string): string {
  if (!md) return "";
  const raw = marked.parse(md, { async: false }) as string;
  return DOMPurify.sanitize(raw, { ADD_ATTR: ["target"] });
}
