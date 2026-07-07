# Niederer Example

This is the single shipped example workspace for the first public release.

It contains:

- `main.qmd`: one compact manuscript covering `4d-image`, `4d-panel`,
  `4d-timeseries`, and `4d-graph`
- `data/niederer/niederer.vtk.series`: a compact 8-step surface export of the
  Niederer slab benchmark
- `data/plots/niederer_signal.json`: a small Plotly JSON graph fixture
- `PREVIEW.md`: git-visible screenshots and preview instructions

Run it with Docker from the repository root:

```bash
cp .env.example .env
FOURD_WORKSPACE=./examples/niederer docker compose up
```

Then open `http://localhost:5006` and compile `main.qmd` from the dashboard.
