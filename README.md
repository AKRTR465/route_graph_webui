# route_graph_webui

Route Graph WebUI is a local WebUI and CLI toolkit for editing route graphs, planning UAV routes, and exporting replay-compatible mission JSON.

Run commands from this `route_graph_webui/` directory unless noted otherwise.

## Documentation

- `docs/README.md`: documentation index.
- `docs/schema/graph-json.md`: graph JSON format.
- `docs/operations/optional-tools.md`: optional media and mission repair tools.
- `docs/preview/`: development preview assets for frontend contour backgrounds.
- `webui_frontend/README.md`: frontend scripts and environment variables.
- `TODO.md`: staged refactor checklist.

## Runtime Data

Runtime data lives under `ROUTE_GRAPH_WEBUI_DATA_DIR`. In source development, the default is this repository's `data/` directory. In release/offline startup, `start.bat` defaults to a user-writable data directory unless `ROUTE_GRAPH_WEBUI_DATA_DIR` is set.

Runtime subdirectories:

- `graphs`: active graph JSON files.
- `plans`: candidate sets and plans.
- `missions`: exported mission JSON files.
- `previews`: generated preview images.
- `logs`, `progress`, `state`: runtime diagnostics and WebUI state.

Sample graphs are stored as repository examples under `data/examples/graphs/*.json`. On first startup, `ensure_data_directories()` creates the runtime data directories and copies those examples into an empty runtime `graphs` directory.

## Install

Runtime dependencies:

```powershell
python -m pip install -r requirements/runtime.txt
```

Editable install with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Optional media dependencies:

```powershell
python -m pip install -e ".[media]"
```

The equivalent requirements files are `requirements/dev.txt` and `requirements/media.txt`.

## Start

Build the frontend for offline-style startup:

```powershell
npm --prefix webui_frontend ci
npm --prefix webui_frontend run build
start.bat
```

`start.bat` checks Python, the backend port, and `webui_frontend/dist/index.html`, then starts:

```powershell
python -m uvicorn route_graph_webui.backend.server:app --host 127.0.0.1 --port 8000
```

Development startup:

```powershell
python -m pip install -e ".[dev]"
npm --prefix webui_frontend ci
start_dev.bat
```

`start_dev.bat` starts the package backend in reload mode and the Vite dev server. Both scripts set `PYTHONPATH=%ROOT%src` so they also work before an editable install.

Common environment variables:

- `ROUTE_GRAPH_WEBUI_HOST`: backend host, default `127.0.0.1`.
- `ROUTE_GRAPH_WEBUI_PORT`: backend port, default `8000`.
- `ROUTE_GRAPH_WEBUI_DATA_DIR`: runtime data directory.
- `ROUTE_GRAPH_WEBUI_PYTHON`: Python executable override.
- `ROUTE_GRAPH_WEBUI_ALLOW_LAN=1`: explicitly allow LAN-oriented local debugging.
- `ROUTE_GRAPH_WEBUI_CORS_ORIGINS`: comma-separated CORS origin override.

This is a local file-writing tool; do not expose it to the public internet.

## Common Commands

Backend tests and generated contract checks:

```powershell
python -B -m pytest tests -q -p no:cacheprovider
python -B -m route_graph_webui.tools.sync_api_schema --check
python -B -m route_graph_webui.tools.sync_graph_meta --check
```

Frontend checks:

```powershell
npm --prefix webui_frontend test
npm --prefix webui_frontend run test:collect
npm --prefix webui_frontend run typecheck
npm --prefix webui_frontend run lint
npm --prefix webui_frontend run format
npm --prefix webui_frontend run build
```

`npm audit` is an online security review command. It is useful before publishing but is not a hard gate for pure offline startup.

CLI entry points:

```powershell
python -m route_graph_webui.cli.graph_record --help
python -m route_graph_webui.cli.graph_editor --help
python -m route_graph_webui.cli.route_planner --help
python -m route_graph_webui.cli.mission_export --help
python -m route_graph_webui.cli.graph_gui --help
python -m route_graph_webui.cli.visualize_graph --help
```

Six root-level public CLI wrappers remain temporarily as transition entry points, but package module commands are the canonical form.

## Package And Offline Bundle

Python package metadata lives in `pyproject.toml`. Package resources include `route_graph_webui.resources/registered_env_ids.json`; keep that JSON covered by package data.

A source or offline bundle should include:

- `pyproject.toml`, `README.md`, `docs/`, `requirements/`, `start.bat`, and `start_dev.bat`.
- `src/route_graph_webui/`, including package resources.
- `data/examples/graphs/*.json`.
- `webui_frontend/package*.json`, frontend source, and for offline bundles the built `webui_frontend/dist/`.

Do not include runtime outputs in an offline bundle: runtime `graphs`, `plans`, `missions`, `previews`, `logs`, `progress`, `state`, `webui_state.json`, `node_modules`, or `__pycache__`.
