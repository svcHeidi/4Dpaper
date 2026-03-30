# Experimental PDF 3D (U3D/PRC + media9)

This repository now supports an experimental PDF 3D mode that can target a
single figure (default: `fig-vm`) and emit a LaTeX include snippet compatible
with `media9`.

## What is generated

When enabled, pre-render attempts to generate:

- `state/figures/<id>.u3d` or `state/figures/<id>.prc` (interactive 3D asset)
- `state/figures/<id>.pdf3d.tex` (LaTeX snippet for PDF embedding)
- `state/figures/<id>.pdf3d-manifest.json` (route/size metadata for experiment comparison)

The shortcode layer uses `<id>.pdf3d.tex` for PDF output when present; otherwise
it falls back to the existing PNG figure.

## Enable

Set environment variables before `quarto render`:

```bash
export FOURDPAPER_PDF3D_EXPERIMENTAL=1
export FOURDPAPER_PDF3D_TARGET_ID=fig-vm
export FOURDPAPER_PDF3D_FORMAT=auto   # auto | u3d | prc
export FOURDPAPER_PDF3D_INTERMEDIATE=obj  # obj | ply
```

`FOURDPAPER_PDF3D_INTERMEDIATE` selects the temporary mesh artifact passed to the
converter pipeline:

- `obj` — current baseline path (`surface -> OBJ -> converter -> U3D/PRC`)
- `ply` — experimental path (`surface + field colors -> PLY -> converter -> U3D/PRC`)

When `ply` is selected, the pre-render hook exports a surface-only, vertex-colored
PLY using the active scalar field before invoking the configured converter.

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

## Logging

During pre-render, the PDF3D path now logs:

- the chosen output format (`u3d` / `prc`)
- the chosen intermediate artifact (`obj` / `ply`)
- the temporary intermediate file path handed to the converter
- the intermediate and final asset sizes when available

## Manifest output

Each successful PDF3D asset-generation attempt now writes a small manifest:

- `state/figures/<id>.pdf3d-manifest.json`

The manifest records:

- source figure id
- selected output format target order
- chosen intermediate artifact (`obj` / `ply`)
- intermediate artifact path and byte size
- final generated asset path and byte size

This is intended to make OBJ-vs-PLY comparison repeatable without changing the
media9 embedding path.

This makes it easier to compare converter behavior between OBJ and PLY
intermediates without changing the media9 embedding path.

## Media9 and reader compatibility

- `media9` availability depends on LaTeX toolchain setup.
- Interactive PDF 3D support varies by viewer (best support is typically Adobe
  Acrobat desktop).
- Non-supporting viewers will still show the poster image fallback.
