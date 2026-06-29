# Real-Image Benchmark

This benchmark uses a downscaled public-domain National Cancer Institute microscopy image as a real-texture fixture.

Source metadata is recorded in `asset_metadata.json`. The generated package creates a known flipped duplicate pair and verifies that `detectors/image/global_near_duplicate.py` detects the expected edge.

Run:

```bash
python3 benchmarks/real_image/run_real_image_benchmark.py
```

This is a controlled regression benchmark, not a broad real-world image-forensics validation corpus.
