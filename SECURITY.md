# Security Policy

This project processes untrusted local files such as ZIP packages, PDFs, DOCX/PPTX files, spreadsheets, images, and manuscript text. Security reports are welcome.

## Supported Versions

Security fixes target the current `main` branch and the latest tagged release, once releases are published.

## What To Report Privately

Please report security-sensitive issues privately when they involve:

- Path traversal, symlink escape, zip-slip, or archive extraction outside the selected package directory.
- Zip bombs, oversized-file denial of service, uncontrolled memory growth, or infinite processing loops.
- Unsafe parsing of PDFs, Office files, images, archives, or metadata.
- Webapp vulnerabilities on the local FastAPI/React interface, including unauthorized file access outside configured audit roots.
- Leaks of private manuscript contents, raw data, local filesystem paths, credentials, or uploaded attachments.
- Any bug that makes a failed detector appear as completed without an audit-coverage gap.

## How To Report

Use GitHub private vulnerability reporting if it is enabled for the repository. If it is not enabled, open a minimal public issue asking for a private security contact, but do not include exploit details, sample private manuscripts, raw images, patient data, credentials, or institution-identifying material.

Include:

- A short description of the issue.
- A minimal synthetic reproducer when possible.
- The affected command or webapp endpoint.
- Expected and actual behavior.
- Your environment: OS, Python version, Node version, and package version or commit.

## Handling Private Research Material

Do not attach real unpublished manuscripts, raw biomedical data, patient data, author names, institutional file paths, or non-public audit reports to public issues or pull requests. Create a synthetic package that demonstrates the same technical problem.

## Disclosure Expectations

Maintainers should acknowledge security reports promptly, avoid public disclosure before a fix is available, and credit reporters when requested and appropriate. Security fixes should preserve the project's integrity boundary: runtime failures and unsupported inputs must be reported as environment or audit-coverage gaps, not as scientific findings.
