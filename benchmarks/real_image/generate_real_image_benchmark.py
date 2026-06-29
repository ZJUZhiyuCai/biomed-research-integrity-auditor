#!/usr/bin/env python3
"""Generate a real-microscopy-image benchmark package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "benchmarks" / "real_image" / "assets" / "nci_cancer_cells_public_domain_640.jpg"
METADATA = ROOT / "benchmarks" / "real_image" / "asset_metadata.json"


def write_package(root: Path) -> dict:
    package = root / "real_image_001"
    package.mkdir(parents=True, exist_ok=True)
    (package / "figures").mkdir(exist_ok=True)
    (package / "raw_images").mkdir(exist_ok=True)

    with Image.open(ASSET) as img:
        base = img.convert("RGB")
        crop = base.crop((72, 44, 472, 344))
        duplicate = ImageOps.mirror(crop)
        negative = base.crop((180, 98, 580, 398))
        crop.save(package / "figures/Figure_Real_1A.jpg", quality=92)
        duplicate.save(package / "figures/Figure_Real_4D.jpg", quality=92)
        negative.save(package / "raw_images/source_context_real_negative.jpg", quality=92)

    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    (package / "real_image_source_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (package / "manuscript.pdf").write_text(
        "Results\n\nFigure Real 1A and Figure Real 4D are described as distinct microscopy panels. "
        "The benchmark image source is a public-domain National Cancer Institute microscopy image used only for detector validation.\n",
        encoding="utf-8",
    )

    expected = {
        "benchmark_id": "real_image_001",
        "package": str(package),
        "source_asset": str(ASSET.relative_to(ROOT)),
        "source_metadata": metadata,
        "expected_duplicate_pair": [
            "figures/Figure_Real_1A.jpg",
            "figures/Figure_Real_4D.jpg"
        ],
        "expected_transform": "flip_h",
        "expected_status": "real_image_global_duplicate_detected",
        "success_condition": (
            "The global image detector should identify a flipped duplicate pair derived from a real public-domain microscopy image."
        ),
    }
    (package / "expected_real_image_intake.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("tmp/real_image_benchmark/cases"))
    args = parser.parse_args()

    expected = write_package(args.output_dir.expanduser().resolve())
    print(json.dumps(expected, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
