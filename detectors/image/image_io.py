"""Image loading helpers for biomedical detector inputs."""

from __future__ import annotations

from typing import Any


HIGH_BIT_DEPTH_MODES = {"I;16", "I;16B", "I;16L", "I;16N", "I", "F"}
DEFAULT_MAX_FRAMES = 64


def normalized_rgb_frame(img: Any) -> Any:
    """Return an 8-bit RGB image while preserving contrast for the current frame."""
    if img.mode in HIGH_BIT_DEPTH_MODES:
        gray = img.convert("F")
        low, high = gray.getextrema()
        if high is None or low is None or high <= low:
            from PIL import Image

            return Image.new("RGB", img.size, (0, 0, 0))
        scale = 255.0 / (high - low)
        from PIL import ImageMath

        eval_image_math = ImageMath.unsafe_eval if hasattr(ImageMath, "unsafe_eval") else ImageMath.eval
        scaled = eval_image_math('convert((a - low) * scale, "L")', a=gray, low=low, scale=scale)
        return scaled.convert("L").convert("RGB")
    return img.convert("RGB")


def normalized_rgb(img: Any) -> Any:
    """Return an 8-bit RGB image from the first frame while preserving contrast."""
    try:
        img.seek(0)
    except Exception:  # noqa: BLE001 - single-frame images do not support seek.
        pass
    return normalized_rgb_frame(img)


def iter_normalized_frames(img: Any, max_frames: int = DEFAULT_MAX_FRAMES) -> list[tuple[str, Any]]:
    """Return normalized frames from a single or multi-frame image.

    The frame label is empty for single-frame files and ``#frameNNNN`` for
    multi-frame files so downstream detectors can keep frame-level provenance.
    """

    try:
        from PIL import ImageSequence
    except Exception:  # noqa: BLE001 - Pillow always provides this in normal installs.
        return [("", normalized_rgb(img))]

    n_frames = int(getattr(img, "n_frames", 1) or 1)
    if n_frames <= 1:
        return [("", normalized_rgb(img))]

    frames: list[tuple[str, Any]] = []
    for idx, frame in enumerate(ImageSequence.Iterator(img)):
        if idx >= max_frames:
            break
        frames.append((f"#frame{idx:04d}", normalized_rgb_frame(frame.copy())))
    return frames
