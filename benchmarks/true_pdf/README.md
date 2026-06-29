# True-PDF Benchmark

This benchmark guards a real intake boundary: most synthetic eval packages use text files with a `.pdf` suffix, while real manuscript PDFs are binary containers with encoded content streams.

`generate_true_pdf_benchmark.py` creates a tiny valid PDF whose page text is stored in a compressed stream. The expected text is also present in a supplied lab-prior-paper text file, so the text-overlap detector should extract the PDF text and create a package-internal text-overlap candidate.

Current expected behavior:

- detect the file as a true binary PDF;
- do not treat raw PDF bytes as extracted manuscript text;
- extract compressed machine-readable PDF text;
- create an overlap candidate against the supplied prior text;
- continue screening non-PDF text in the same package.

Run:

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py
```

Scanned or image-only PDFs still require OCR; this benchmark covers machine-readable PDF text only.
