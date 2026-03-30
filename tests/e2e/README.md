# Dashboard E2E tests (Playwright)

These tests start `panel serve` and drive Chromium headless. They are **off by default**.

## Setup

```bash
pip install -r requirements-e2e.txt
playwright install chromium
```

## Run

From the **same git tree** that contains `dashboard/app.py` (for example `.worktrees/panel-ide-3pane` under the main repo):

```bash
export PLAYWRIGHT_E2E=1
export FOURDPAPERS_DASHBOARD_ROOT="$PWD"
pytest ../../tests/e2e/test_dashboard_split.py -v
```

(Adjust the relative path to `tests/e2e` from your checkout; from `.worktrees/panel-ide-3pane` inside `4Dpapers`, use `../../tests/e2e/...`.)

If `dashboard/` is at the repository root and you run `pytest` from that root, you can omit `FOURDPAPERS_DASHBOARD_ROOT`.

`panel` is launched with the interpreter at `<4Dpapers>/.venv/bin/python` (three levels above `tests/e2e/`). Point that venv at a Python that has `panel` installed.
