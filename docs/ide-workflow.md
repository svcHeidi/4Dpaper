# Using 4Dpapers With An IDE

4Dpapers is a Docker app for rendering and previewing scientific papers. For editing, debugging, and AI-assisted development, use an IDE on the host machine and let Docker provide the runtime.

## Mental Model

There are two paths for the same paper:

```text
Host machine:  /path/to/your/paper
Container:     /workspace
```

Docker Compose mounts the host paper folder into the container:

```yaml
volumes:
  - ${FOURD_WORKSPACE:-./workspace}:/workspace
```

That means:

- Your IDE opens the host folder.
- 4Dpapers reads and writes the same files inside the container at `/workspace`.
- Edits made in the IDE appear in the dashboard.
- Files created by the dashboard appear in the IDE.

## Recommended Workflow

Start the app with an existing paper workspace:

```bash
FOURD_WORKSPACE=/path/to/your/paper docker compose up
```

Open this folder in your IDE:

```text
/path/to/your/paper
```

Use the IDE agent for:

- editing `main.qmd`, sections, captions, and references
- writing or reviewing shortcodes
- inspecting `_shortcuts.yml`
- organizing `data/` and `media/`
- reviewing generated files
- running git operations

Use Docker for runtime checks:

```bash
docker compose exec 4dpapers quarto render main.qmd --to html
docker compose logs -f 4dpapers
docker compose ps
```

Use the browser dashboard for:

- previewing compiled output
- interacting with 3D figures
- changing camera/field state
- upload workflows
- exporting HTML/PDF

## IDE Agent vs In-App Assistant

Use an IDE agent for building or debugging 4Dpapers itself. It can read the repository, edit files, run tests, inspect Docker logs, and understand the source code.

The optional in-app assistant is for paper-author help only:

- choosing supported file formats
- writing captions
- explaining shortcodes
- troubleshooting missing fields
- suggesting visualization settings
- drafting methods or reproducibility notes

It is not intended to replace an IDE or source-code agent.

## In-App Assistant Flag

Agent persona metadata is hidden by default. Enable it only when you want the in-app assistant UI to expose curated paper-author personas:

```bash
FOURD_EXPOSE_AGENTS=1 docker compose up
```

When `FOURD_EXPOSE_AGENTS` is not set to `1`, `/api/agents` returns 404.

## Security Notes

For any network-accessible deployment:

- Set `FOURD_API_KEY`.
- Set `FOURD_ALLOWED_ORIGIN` to the exact dashboard origin.
- Treat shortcut configuration as trusted-admin behavior.
- Do not store private keys or secrets inside the paper workspace.
