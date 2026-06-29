# Scanned-PDF OCR Benchmark

This benchmark creates an image-only PDF and checks whether the text detector can recover OCR text before package-internal overlap screening.

Run:

```bash
python3 benchmarks/scanned_pdf/run_scanned_pdf_benchmark.py
```

Requirements:

- PyMuPDF
- pytesseract
- the `tesseract` system binary

Local validation can skip this benchmark when OCR runtime dependencies are unavailable. Run this benchmark without `--skip-if-unavailable` when you want missing OCR runtime dependencies to fail the check.
