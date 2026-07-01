# 4Dpapers

A browser-based editor for scientific papers with interactive 3D simulation figures.

Write Quarto Markdown, embed VTK/OpenFOAM/FEA data as live WebGL figures, and export the paper to HTML or PDF from one local Docker app.

## Features

- Interactive 3D figures for simulation and mesh data
- Field switching for scalar arrays such as `U`, `p`, `T`, or `Vm`
- Time animation for multi-step datasets
- Synchronized multi-panel figure layouts
- HTML and PDF export
- Optional AI sidebar and signed HTML output

Supported formats include `.foam`, `.vtu`, `.vtp`, `.pvd`, `.vtk`, `.exo`, `.xdmf`, `.cgns`, `.stl`, `.obj`, `.ply`, `.case`, `.msh`, `.med`, `.inp`, and Plotly `.json`.

## Quick Start

Requirements: Docker.

```bash
cp .env.example .env
docker compose up
```

Open:

```bash
http://localhost:5006
```

The current directory is mounted as the paper workspace. If it does not contain a paper yet, 4Dpapers creates a starter Quarto project.

## Use The Prebuilt Image

```bash
IMAGE=ghcr.io/svcheidi/4dpaper:latest docker compose up
```

Or run without Compose:

```bash
docker run -d \
  --name 4dpapers \
  -p 5006:5006 \
  -v /path/to/your/project:/workspace \
  --env-file .env \
  ghcr.io/svcheidi/4dpaper:latest
```

## Embed A Figure

Papers are Quarto Markdown files (`.qmd`). Put simulation data under `data/`, then use a shortcode:

```markdown
{{< 4d-image
  id="fig-aorta"
  src="data/aorta.foam"
  field="U"
  fields="U,p"
  time="last"
  caption="Velocity magnitude"
>}}
```

Compile from the dashboard, or call:

```bash
curl -X POST http://localhost:5006/api/compile
```

## Project Layout

```text
your-project/
├── main.qmd
├── sections/
├── data/
├── media/
├── references.bib
├── _quarto.yml
├── state/      # generated runtime state
└── _output/    # compiled HTML/PDF
```

## Configuration

Copy `.env.example` to `.env` and edit only what you need.

Common variables:

| Variable | Purpose |
|---|---|
| `PORT` | Dashboard port, default `5006` |
| `FOURD_API_KEY` | Optional API key for dashboard/API access |
| `FOURD_ALLOWED_ORIGIN` | Allowed browser origin for CORS |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Enable AI providers |
| `OLLAMA_URL` | Local Ollama chat endpoint |

For any network-accessible deployment, set a strong `FOURD_API_KEY` and set `FOURD_ALLOWED_ORIGIN` to the exact dashboard origin. Leaving `FOURD_API_KEY` empty is for local single-user use only.

## More Documentation

- [Docker deployment guide](DOCKER_DEPLOYMENT.md)
- [Environment variable template](.env.example)
- [GitHub Actions image publishing workflow](.github/workflows/docker-publish.yml)
- [Agent and format reference](AGENTS.md)

## Troubleshooting

| Symptom | Try |
|---|---|
| Dashboard does not load | `docker compose logs -f` |
| Fields are missing | Check that `fields="..."` matches the data arrays exactly |
| Mesh is too simplified | Add `decimate="none"` to the shortcode |
| XDMF fails | Keep the companion `.h5` file next to the `.xdmf` |
| Volume permission error | Check host folder permissions |

## License

4Dpapers is source-available under a dual-license model:

- Free for non-commercial research and educational use
- Paid commercial license required for company/internal commercial use

See [LICENSE.md](LICENSE.md).
