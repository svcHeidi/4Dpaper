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

Supported source formats for manually authored shortcodes include `.foam`, `.vtu`, `.vtp`, `.pvd`, `.vtk`, `.exo`, `.xdmf`, `.cgns`, `.stl`, `.obj`, `.ply`, `.case`, `.msh`, `.med`, `.inp`, and Plotly `.json`.

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

By default, Compose mounts `./workspace` as the paper workspace. If that folder does not contain a paper yet, 4Dpapers creates a starter Quarto project.

To edit an existing paper:

```bash
FOURD_WORKSPACE=/path/to/your/project docker compose up
```

For the best editing workflow, open the same host folder in your IDE while Docker runs the app. The IDE edits `/path/to/your/project`; 4Dpapers sees it as `/workspace` inside the container.

To run the included example manuscript:

```bash
FOURD_WORKSPACE=./examples/niederer docker compose up
```

The shipped example is a standalone Niederer slab workspace with one manuscript
(`main.qmd`) and one committed dataset at
`data/niederer/niederer.vtk.series`, so it renders from a clean clone.

## Use The Prebuilt Image

```bash
IMAGE=ghcr.io/4dpapers/4dpapers:latest docker compose up
```

Or run without Compose:

```bash
docker run -d \
  --name 4dpapers \
  -p 5006:5006 \
  -v /path/to/your/project:/workspace \
  --env-file .env \
  ghcr.io/4dpapers/4dpapers:latest
```

## Single-Host Production Deployment

The supported first remote deployment shape is a single-tenant Docker host with
Caddy terminating HTTPS in front of the 4Dpapers app container.

```bash
cp .env.production.example .env.production
$EDITOR .env.production
docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d
```

That bundle:

- binds the app itself to `127.0.0.1:5006`
- serves the public site through Caddy on ports `80/443`
- keeps `FOURD_API_KEY` enabled for browser/API access
- drops the app process to an unprivileged user after startup
- uses the same env file for Compose substitution and container runtime env

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

The dashboard's built-in figure upload modal is currently scoped to OpenFOAM
case folders. Other supported source formats can still be used by placing the
data under `data/` and writing the shortcode manually.

## Use With An IDE

Recommended workflow:

```text
IDE agent: edits paper/source files on the host
Docker: runs the 4Dpapers runtime and Quarto render
Browser: previews and interacts with figures
```

Run runtime commands inside the container:

```bash
docker compose exec 4dpapers quarto render main.qmd --to html
docker compose logs -f 4dpapers
```

See [Using 4Dpapers with an IDE](docs/ide-workflow.md).

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
| `FOURD_WORKSPACE` | Host paper folder mounted at `/workspace` by Docker Compose |
| `FOURD_API_KEY` | Optional API key for dashboard/API access |
| `FOURD_ALLOWED_ORIGIN` | Allowed browser origin for CORS |
| `FOURD_EXPOSE_AGENTS` | Set to `1` to expose optional in-app assistant personas |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Enable AI providers |
| `OLLAMA_URL` | Local Ollama chat endpoint |

For any network-accessible deployment, set a strong `FOURD_API_KEY` and set `FOURD_ALLOWED_ORIGIN` to the exact dashboard origin. The current first-deployment auth model is single-tenant: the browser stores the deployment key locally and mirrors it into a same-origin cookie so preview iframes and downloads work. Serve it over HTTPS and do not treat this as multi-user auth.

## More Documentation

- [Docker deployment guide](docs/docker-deployment.md)
- [Using 4Dpapers with an IDE](docs/ide-workflow.md)
- [Environment variable template](.env.example)
- [Production environment template](.env.production.example)
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
