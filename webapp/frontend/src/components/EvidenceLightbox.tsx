// Full-screen evidence viewer. Keyboard: Esc closes, ←/→ navigates.

import { useEffect } from "react";
import { X } from "lucide-react";
import { evidenceUrl } from "../api";

export function EvidenceLightbox({
  auditId,
  images,
  index,
  onClose,
  onIndex
}: {
  auditId: string;
  images: string[];
  index: number;
  onClose: () => void;
  onIndex: (i: number) => void;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowRight")
        onIndex(Math.min(index + 1, images.length - 1));
      if (event.key === "ArrowLeft") onIndex(Math.max(index - 1, 0));
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
      aria-label="Evidence viewer"
    >
      <div className="lightbox-bar">
        <span className="lightbox-count">
          {index + 1} / {images.length}
        </span>
        <button className="icon-button" onClick={onClose} aria-label="Close">
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
