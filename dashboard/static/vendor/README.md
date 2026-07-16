# Vendored browser dependencies

These third-party assets are bundled so the dashboard renders with **no network
access** (air-gapped / egress-restricted containers). They were previously loaded
from CDNs; see `CHANGELOG.md` (0.1.2). All are redistributed under permissive
licenses. Do not edit the minified files — re-vendor from the upstream source
instead.

| Asset | Version | Source | License |
|-------|---------|--------|---------|
| Tailwind CSS (Play CDN standalone build, `forms` + `container-queries` plugins) | v3.4.x | https://github.com/tailwindlabs/tailwindcss | MIT |
| CodeMirror 5 (core + `markdown`/`yaml` modes, `material-darker` theme, `show-hint` addon) | 5.65.2 | https://github.com/codemirror/codemirror5 | MIT |
| Phosphor Icons (duotone, fill, bold weights) | 2.1.2 | https://github.com/phosphor-icons/web | MIT |
| Outfit (400, 500, 600) | Google Fonts | https://fonts.google.com/specimen/Outfit | SIL Open Font License 1.1 |
| JetBrains Mono (400, 500) | Google Fonts | https://fonts.google.com/specimen/JetBrains+Mono | SIL Open Font License 1.1 |

MathJax and the polyfill.io shim were **removed** (unused) rather than vendored.
