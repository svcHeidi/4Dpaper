# Experimental PDF 3D (U3D/PRC + media9)

This repository now supports an experimental PDF 3D mode that can target a
single figure (default: `fig-vm`) and emit a LaTeX include snippet compatible
with `media9`.

## What is generated

When enabled, pre-render attempts to generate:

- `state/figures/<id>.u3d` or `state/figures/<id>.prc` (interactive 3D asset)
- `state/figures/<id>.pdf3d.tex` (LaTeX snippet for PDF embedding)

The shortcode layer uses `<id>.pdf3d.tex` for PDF output when present; otherwise
it falls back to the existing PNG figure.

## Enable

Set environment variables before `quarto render`:

```bash
export FOURDPAPER_PDF3D_EXPERIMENTAL=1
export FOURDPAPER_PDF3D_TARGET_ID=fig-vm
export FOURDPAPER_PDF3D_FORMAT=auto   # auto | u3d | prc
```

## Configure converters

Conversion from mesh to U3D/PRC requires external tools. Provide command
templates with `{input}` and `{output}` placeholders:

```bash
export FOURDPAPER_U3D_CONVERTER_CMD='assimp export {input} {output}'
# Optional PRC converter:
# export FOURDPAPER_PRC_CONVERTER_CMD='your-prc-tool {input} {output}'
```

If no converter succeeds, the system writes a PNG-only TeX fallback and PDF
rendering remains functional.

## Media9 and reader compatibility

- `media9` availability depends on LaTeX toolchain setup.
- Interactive PDF 3D support varies by viewer (best support is typically Adobe
  Acrobat desktop).
- Non-supporting viewers will still show the poster image fallback.
