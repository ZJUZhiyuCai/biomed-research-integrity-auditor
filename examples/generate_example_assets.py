#!/usr/bin/env python3
"""Generate deterministic image assets for the example self-audit packages.

These images are intentionally simple synthetic textures, not real microscopy.
They exist so a new user can run `scripts/audit_package.py` against a realistic
folder layout and see verified figure-to-raw traceability, completeness gaps, and
the audit-coverage section. Regenerate with:

    python3 examples/generate_example_assets.py

The committed PNGs let the examples run without this step.
"""

from __future__ import annotations

from pathlib import Path

EXAMPLES_ROOT = Path(__file__).resolve().parent
FULL_PACKAGE = EXAMPLES_ROOT / "full_presubmission_package"


def textured_image(seed: int, size: tuple[int, int] = (256, 256)):
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.new("RGB", size, (20 + seed % 18, 24, 30))
    draw = ImageDraw.Draw(img)
    for idx in range(110):
        x = (seed * 41 + idx * 33) % size[0]
        y = (seed * 47 + idx * 27) % size[1]
        radius = 3 + ((seed + idx) % 12)
        color = (
            45 + (seed * 13 + idx * 7) % 180,
            55 + (seed * 17 + idx * 11) % 170,
            60 + (seed * 19 + idx * 5) % 160,
        )
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    for idx in range(20):
        x0 = (seed * 7 + idx * 43) % size[0]
        y0 = (seed * 9 + idx * 31) % size[1]
        draw.line((x0, y0, (x0 + 61) % size[0], (y0 + 73) % size[1]), fill=(200, 200, 220), width=1)
    return img.filter(ImageFilter.GaussianBlur(0.3))


def save_png(path: Path, image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main() -> int:
    # Each figure panel is an exact export of its declared raw acquisition, so the
    # image detector confirms the manifest's declared figure-to-raw relationship and
    # reports it as positive traceability evidence rather than a reuse concern.
    microscopy = textured_image(101)
    blot = textured_image(202)

    save_png(FULL_PACKAGE / "figures" / "Figure_1A_microscopy.png", microscopy)
    save_png(FULL_PACKAGE / "raw_images" / "acquisition_001.png", microscopy.copy())

    save_png(FULL_PACKAGE / "figures" / "Figure_2A_blot.png", blot)
    save_png(FULL_PACKAGE / "raw_images" / "full_membrane_002.png", blot.copy())

    print(f"Wrote example image assets under {FULL_PACKAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
