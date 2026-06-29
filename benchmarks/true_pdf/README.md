# True-PDF Benchmark Starter

This benchmark records a known boundary: most synthetic eval packages use text files with a `.pdf` suffix, while real manuscript PDFs are binary containers with encoded content streams.

`generate_true_pdf_benchmark.py` creates a tiny valid PDF whose page text is stored in a compressed stream. The expected text is also present in a supplied lab-prior-paper text file, so a future PDF extraction stage should be able to create a package-internal text-overlap candidate.

Current expected behavior:

- detect the file as a true binary PDF;
- do not treat raw PDF bytes as extracted manuscript text;
- record an explicit "PDF text extraction is not implemented" gap;
- continue screening non-PDF text in the same package.

Run:

```bash
python3 benchmarks/true_pdf/run_true_pdf_benchmark.py
```

This is a benchmark starter, not a PDF extraction implementation.
