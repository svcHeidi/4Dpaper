# Niederer Example

This is the single shipped example workspace for the first public release.

It contains:

- `main.qmd`: one minimal manuscript using one interactive 4D figure
- `data/niederer/niederer.vtk.series`: a compact 8-step surface export of the
  Niederer slab benchmark

Run it with Docker from the repository root:

```bash
cp .env.example .env
FOURD_WORKSPACE=./examples/niederer docker compose up
```

Then open `http://localhost:5006` and compile `main.qmd` from the dashboard.
