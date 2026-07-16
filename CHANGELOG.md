# Changelog

## 0.1.2 — Unreleased

Offline-hardening patch: the dashboard UI and PDF export now work with no
network access, which the first public build did not.

- Vendor every dashboard browser dependency — Tailwind, CodeMirror, the Phosphor
  icon font, and the Outfit / JetBrains Mono web fonts — instead of loading them
  from CDNs, so the editor renders correctly in air-gapped and egress-restricted
  containers. Drop the unused MathJax and polyfill.io includes.
- Make PDF export network-free: WeasyPrint no longer fetches remote assets by URL
  (set `FOURD_PDF_ALLOW_REMOTE=1` to opt back in), so a paper referencing an
  unreachable host can no longer hang the export silently. Shorten the render
  backstop timeout from 900s to 180s.
- Add real HTML-compile, standalone-HTML-export, and PDF-export regression tests
  that exercise the actual Quarto + WeasyPrint pipeline, plus an offline-assets
  guard, and run Quarto in CI so they execute on every pull request.

## 0.1.1 — 2026-07-15

Launch-hardening patch for the first public announcement.

- Replace the legacy writable-workspace Quick Export launcher with an opt-in
  isolated mode: read-only source, disposable workspace, and HTML-only output.
- Add `meshio` to the official image for the documented mesh readers.
- Render AI replies and workspace-controlled filenames as text to prevent
  same-origin HTML injection.
- Add a documentation link and AI data-handling notice to the dashboard.
- Add release test gating to the Docker publishing workflow.
- Replace the example-only Pages root with a responsive product landing page,
  embedded live figure, evidence-tiered format claims, and `/demo/` paper.
- Keep static papers interactive without calling dashboard-only camera and field
  persistence endpoints.
- Add security, support, contribution, citation, issue, and pull-request files.

## 0.1.0 — 2026-07-08

Initial tagged Docker release and Quarto-based interactive paper workflow.
