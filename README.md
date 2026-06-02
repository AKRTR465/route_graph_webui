# route_graph_webui

本目录是 Route Graph WebUI 的源码包。根 README 只保留启动、开发、离线运行包和常用检查命令；更细的格式和工具说明见 `docs/`。

## 文档入口

- `docs/README.md`：文档索引。
- `docs/schema/graph-json.md`：graph JSON schema 简要说明。
- `docs/operations/optional-tools.md`：media / mission 可选工具说明。
- `webui_frontend/README.md`：前端工程脚本和环境变量。
- `TODO.md`：执行清单。

## 目录约定

建议在本 README 所在的 `route_graph_webui/` 目录下执行命令。

常用运行态目录：

- `data/graphs`：graph JSON。
- `data/plans`：候选集和 plan。
- `data/missions`：导出的 mission。
- `data/previews`：预览图。

运行态数据目录由 `ROUTE_GRAPH_WEBUI_DATA_DIR` 指定。未指定时，源码开发默认使用本目录下的 `data/`；离线运行包通过 `start.bat` 默认使用用户可写目录，也可提前设置 `ROUTE_GRAPH_WEBUI_DATA_DIR` 覆盖。

旧拼写兼容集中在 `spelling_compat.py`：`ROUTE_GARPH_DIR`、`route_garph`、`phtots` 只作为只读 fallback 保留到 `2026-12-31`。新写入只使用 `ROUTE_GRAPH_WEBUI_DATA_DIR`、`photos` 和正确拼写的 graph creator。

## 干净机器启动

后端运行依赖：

```powershell
python -m pip install -r requirements-runtime.txt
```

前端依赖和构建：

```powershell
npm --prefix webui_frontend ci
npm --prefix webui_frontend run build
```

启动离线式 WebUI：

```powershell
start.bat
```

`start.bat` 会检查 Python、端口占用和 `webui_frontend/dist/index.html`，然后启动后端并用 `/api/health` 做 readiness check。

常用环境变量：

- `ROUTE_GRAPH_WEBUI_HOST`：后端监听地址，默认 `127.0.0.1`。
- `ROUTE_GRAPH_WEBUI_PORT`：后端端口，默认 `8000`。
- `ROUTE_GRAPH_WEBUI_DATA_DIR`：运行态数据目录。
- `ROUTE_GRAPH_WEBUI_PYTHON`：指定 Python 可执行文件。
- `ROUTE_GRAPH_WEBUI_ALLOW_LAN=1`：显式允许局域网调试。
- `ROUTE_GRAPH_WEBUI_CORS_ORIGINS`：覆盖允许的 CORS origins。

WebUI 是本地写文件工具，不应暴露到公网。

## 源码开发

安装开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
npm --prefix webui_frontend ci
```

启动开发模式：

```powershell
start_dev.bat
```

`start_dev.bat` 会检查 Python、Node、npm 和默认端口，启动后端 reload 模式和 Vite dev server。前端请求默认走 Vite `/api` proxy；如果后端 host/port 改了，可设置 `VITE_API_BASE` 或依赖脚本注入的默认值。

## 离线运行包和源码包

源码包保留：

- 后端和核心业务 Python 源码、`tests/`、`README.md`、`docs/`、`requirements*.txt`。
- `webui_frontend/package*.json` 和前端源码。
- 样例图 `data/graphs/*.json`。

源码包排除：

- `webui_frontend/node_modules/`、`webui_frontend/dist/`。
- 运行态输出：`data/plans/`、`data/missions/`、`data/previews/`、`data/logs/`、`data/webui_state.json`。
- `__pycache__/` 和 `tools/archive/`。

离线运行包必须额外包含：

- 已构建的 `webui_frontend/dist/`。
- 启动脚本和 `registered_env_ids.json`。
- 至少一个必要样例 graph，例如 `data/graphs/DowntownWest.json`。

离线运行包不需要 Node，也不包含 `node_modules/` 或运行态输出。

## 常用命令

后端测试和契约：

```powershell
python -B -m pytest tests -q -p no:cacheprovider
python -B tools\sync_api_schema.py --check
python -B tools\sync_graph_meta.py --check
```

前端检查：

```powershell
npm --prefix webui_frontend test
npm --prefix webui_frontend run test:collect
npm --prefix webui_frontend run typecheck
npm --prefix webui_frontend run lint
npm --prefix webui_frontend run format
npm --prefix webui_frontend run build
```

常用 CLI 入口：

```powershell
python graph_record.py --help
python graph_editor.py --help
python route_planner.py --help
python mission_export.py --help
python graph_gui.py --help
python visualize_graph.py --help
```

可选 media 工具需要额外依赖：

```powershell
python -m pip install -r requirements-media.txt
```

