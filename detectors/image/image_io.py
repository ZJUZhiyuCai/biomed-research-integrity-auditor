"""Image loading helpers for biomedical detector inputs."""

from __future__ import annotations

from typing import Any


HIGH_BIT_DEPTH_MODES = {"I;16", "I;16B", "I;16L", "I;16N", "I", "F"}


def normalized_rgb(img: Any) -> Any:
    """Return an 8-bit RGB image while preserving contrast from high-bit-depth inputs."""
    try:
        img.seek(0)
    except Exception:  # noqa: BLE001 - single-frame images do not support seek.
        pass
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
