# 4Dpapers Agent Notes

`CLAUDE.md` is the detailed machine-readable reference for coding agents working
inside this repository.

`agents.yaml` contains curated agent role metadata that may be exposed to the app
only when the server is started with:

```bash
FOURD_EXPOSE_AGENTS=1
```

When enabled, the app serves that metadata at `/api/agents`. The generic file
browser and `/api/file` endpoint intentionally hide `AGENTS.md`, `CLAUDE.md`,
and `agents.yaml` so internal guidance is not exposed accidentally.
