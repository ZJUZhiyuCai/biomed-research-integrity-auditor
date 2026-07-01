// Full-screen evidence viewer. Keyboard: Esc closes, ←/→ navigates; Tab stays inside the dialog.

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { evidenceUrl } from "../api";
import type { Labels } from "../i18n";

export function EvidenceLightbox({
  auditId,
  images,
  index,
  t,
  onClose,
  onIndex
}: {
  auditId: string;
  images: string[];
  index: number;
  t: Labels;
  onClose: () => void;
  onIndex: (i: number) => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight")
        onIndex(Math.min(index + 1, images.length - 1));
      if (event.key === "ArrowLeft") onIndex(Math.max(index - 1, 0));
      if (event.key === "Tab") {
        const focusable = Array.from(
          dialogRef.current?.querySelectorAll<HTMLElement>(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          ) || []
        ).filter((item) => !item.hasAttribute("disabled"));
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [index, images.length, onClose, onIndex]);

  const current = images[index];
  if (!current) return null;

  return (
    <div
      className="lightbox"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={t.lightboxViewer}
      ref={dialogRef}
    >
      <div className="lightbox-bar">
        <span className="lightbox-count">
          {index + 1} / {images.length}
        </span>
        <button
          ref={closeButtonRef}
          className="icon-button"
          onClick={onClose}
          aria-label={t.lightboxClose}
        >
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <div
        className="lightbox-stage"
        onClick={(event) => event.stopPropagation()}
      >
        <img
          className="lightbox-image"
          src={evidenceUrl(auditId, current)}
          alt={current}
        />
        {images.length > 1 && (
          <p className="lightbox-hint">← →</p>
        )}
      </div>
    </div>
  );
}
