# Packaging Notes

This project currently supports repeatable local command installation and GitHub
Release artifact generation. Registry publication remains a maintainer action.

## Local Commands

```bash
python3 scripts/install_local_commands.py
```

This creates an editable virtual environment and links:

- `biomed-audit`
- `biomed-audit-diff`
- `biomed-audit-web`
- `biomed-self-audit-webapp`

## Release Artifacts

```bash
make release-artifacts
```

The target builds the React frontend, builds Python wheel/sdist artifacts, and
writes a source bundle plus SHA256 manifest under `dist/release/`.

## GitHub Actions Templates

`github-workflows/` contains workflow templates for release artifact publishing and frontend
Playwright smoke testing. Copy them into `.github/workflows/` using a maintainer token with
workflow permission.

## Homebrew

`homebrew/biomed-research-integrity-auditor.rb.template` is a release-template
formula. Replace `OWNER`, `VERSION`, and `REPLACE_WITH_SHA256` after a tagged
GitHub Release is built.

## macOS Launcher

`macos/Biomed Self-Audit.command` is a tiny local helper for users who prefer a
double-click installation path. It installs command links; it is not a signed
desktop application.
