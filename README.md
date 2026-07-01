# 4Dpapers

**A browser-based authoring IDE for interactive scientific papers.**  
Write Quarto Markdown, embed live 3D simulation figures, compile to HTML or PDF — all inside Docker, no local Python setup required.

---

## What it does

4Dpapers is a self-contained web application that lets researchers write and publish papers with **interactive 3D figures** directly embedded in the document.

| Feature | Details |
|---|---|
| **Interactive 3D figures** | Embed VTK/OpenFOAM/FEA simulation results as live WebGL viewers |
| **Field switching** | Toggle between scalar fields (U, p, T...) inside the rendered figure |
| **Time animation** | Play button auto-appears for multi-timestep datasets |
| **Synchronized panels** | Multi-figure grids with optional shared camera |
| **Compile to HTML/PDF** | One-click export; PDF uses static screenshots |
| **AI sidebar** | Chat with OpenAI, Anthropic, or local Ollama about your paper |
| **Document signing** | Cryptographic signing of HTML output for trust verification |

**Supported data formats:** `.foam`, `.vtu`, `.vtp`, `.pvd`, `.vtk`, `.exo`, `.xdmf`, `.cgns`, `.stl`, `.obj`, `.ply`, `.case`, `.msh`, `.med`, `.inp`, `.json` (Plotly)

---

## Quick start with Docker

No Python installation required. Just Docker.

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Start the container (builds locally on first run)
docker compose up

# 3. Open the dashboard
open http://localhost:5006
```

Your project files are mounted from the current directory.  
The dashboard auto-initialises a template paper if the folder is empty.

---

## Using a prebuilt image from GHCR

Skip the local build — pull the image directly from GitHub Container Registry:

```bash
# Pull and run the latest image
IMAGE=ghcr.io/svcheidi/4dpaper:latest docker compose up

# Or pin to a specific release
IMAGE=ghcr.io/svcheidi/4dpaper:1.2.0 docker compose up
```

Images are published automatically on every push to `main` and on semver tags.

---

## Docker run (without compose)

```bash
docker run -d \
  --name 4dpapers \
  -p 5006:5006 \
  -v /path/to/your/project:/workspace \
  --env-file .env \
  ghcr.io/svcheidi/4dpaper:latest

open http://localhost:5006
```

---

## Environment variables

Copy `.env.example` to `.env` and fill in what you need:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5006` | Dashboard port |
| `FOURD_API_KEY` | _(empty)_ | Shared secret for API auth (leave empty for local use) |
| `FOURD_ALLOWED_ORIGIN` | `http://localhost:5006` | CORS origin |
| `OPENAI_API_KEY` | _(empty)_ | Enables OpenAI in AI sidebar |
| `ANTHROPIC_API_KEY` | _(empty)_ | Enables Claude in AI sidebar |
| `GEMINI_API_KEY` | _(empty)_ | Enables Gemini in AI sidebar |
| `OLLAMA_URL` | `http://host.docker.internal:11434/api/chat` | Local Ollama endpoint |
| `FOURD_SIGNING_PRIVATE_KEY_PATH` | _(empty)_ | Path to signing private key (inside container) |
| `FOURD_SIGNING_PUBLIC_KEY_PATH` | _(empty)_ | Path to signing public key (inside container) |

---

## Writing a paper

Papers are written in [Quarto Markdown](https://quarto.org) (`.qmd`).  
Use the built-in shortcodes to embed interactive figures.

### Single 3D figure

```
{{< 4d-image id="fig-aorta"
             src="data/aorta.foam"
             field="U"
             fields="U,p"
             time="last"
             caption="Blood velocity magnitude (m/s)" >}}
```

### Comparison grid

```
{{< 4d-panel id="comparison"
             layout="2x1"
             height="600px"
             camera="sync"
             src1="data/case_a.foam" id1="case-a" field1="U"
             src2="data/case_b.foam" id2="case-b" field2="U"
             caption="Left: baseline  Right: optimised" >}}
```

### Time-series plot

```
{{< 4d-timeseries id="ts-pressure"
                  src="data/probe_data.json"
                  caption="Pressure at probe point" >}}
```

Then compile from the dashboard or via the API:

```bash
curl -X POST http://localhost:5006/api/compile
```

---

## Project structure

```
your-project/            <- mounted at /workspace
├── main.qmd             <- root document
├── sections/            <- document sections
├── data/                <- simulation files (OpenFOAM cases, VTK, STL...)
├── media/               <- images, videos
├── references.bib       <- bibliography
├── _quarto.yml          <- Quarto configuration
├── state/               <- runtime-generated (camera states, figure assets)
└── _output/             <- compiled HTML / PDF
```

---

## Data shortcuts

For large datasets that live outside the project directory, define shortcuts in `_shortcuts.yml`:

```yaml
shortcuts:
  hpc_data:
    path: /mnt/hpc/projects/myproject
    description: HPC cluster outputs
```

Then reference them in shortcodes:

```
{{< 4d-image id="fig-sim" src="@hpc_data/run_42/case.foam" field="U" >}}
```

---

## Multiple projects

Run multiple instances on different ports:

```bash
# Paper 1
docker run -d --name paper1 -p 5006:5006 -v ~/projects/paper1:/workspace ghcr.io/svcheidi/4dpaper:latest

# Paper 2
docker run -d --name paper2 -p 5007:5006 -v ~/projects/paper2:/workspace ghcr.io/svcheidi/4dpaper:latest
```

---

## Document signing (optional)

Cryptographic signing of compiled HTML for trust verification:

```bash
# Generate a keypair
python scripts/generate_signing_keys.py \
  --private-key ~/4dpapers-keys/private.pem \
  --public-key  ~/4dpapers-keys/public.pem

# Set in .env
FOURD_SIGNING_KEYS_HOST_DIR=~/4dpapers-keys
FOURD_SIGNING_PRIVATE_KEY_PATH=/run/secrets/4dpapers/private.pem
FOURD_SIGNING_PUBLIC_KEY_PATH=/run/secrets/4dpapers/public.pem
```

---

## Building locally

```bash
docker build -t 4dpapers:local .
docker run -d -p 5006:5006 -v .:/workspace 4dpapers:local
```

---

## CI / GitHub Actions

Every push to `main` and every semver tag (`v1.2.3`) automatically builds and publishes a multi-platform image (`linux/amd64` + `linux/arm64`) to GHCR.

PRs trigger a build-only dry run (no push) to catch broken Dockerfiles before merge.

See [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) for the workflow definition.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard not loading | `docker compose logs -f` |
| Fields do not appear in viewer | Check `fields="U,p"` attribute matches exact field names in dataset |
| Mesh looks too simplified | Add `decimate="none"` to the shortcode |
| XDMF fails to load | Ensure the `.h5` companion file is co-located with the `.xdmf` |
| Permission denied on volume | `chmod 755 /path/to/project` on the host |
| Quarto not found | `docker exec 4dpapers quarto --version` |

---

## License

MIT
