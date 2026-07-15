# Contributing to 4Dpapers

Thank you for helping improve scientific publishing workflows.

## Before opening a change

Start with a Discussion for large features, new rendering architectures, or
new file-format promises. Small fixes and fixture-backed compatibility changes
can go directly to a pull request.

This repository is source-available under [LICENSE.md](LICENSE.md), not an
OSI-approved open-source license. By contributing, you agree that your
contribution can be distributed under the repository's current dual-license
model.

## Development checks

Use Python 3.11. Install the test dependencies, then run:

```bash
python -m pip install -r requirements-e2e.txt
python -m pytest -q
```

Quarto rendering must be tested inside the 4Dpapers Docker service, because the
repository extension resolves to `/app/_extensions` in that environment:

```bash
docker compose exec -T 4dpapers quarto render main.qmd --to html
```

Add a small redistributable fixture and regression test when changing a format
reader. Update `AGENTS.md` and the public evidence tier only after the new path
is repeatably tested.

## Pull requests

Keep changes focused, document user-visible behavior, and include the commands
you ran. Do not commit API keys, unpublished papers, generated `_output/`
folders, or proprietary datasets.
