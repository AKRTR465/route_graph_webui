# route_graph_webui 中文说明

[English README](README.md)

Route Graph WebUI 是一个面向无人机任务的本地 WebUI 与 CLI 工具箱，用来编辑航线图、规划 UAV 路线，并导出可回放或可对接任务流程的 mission JSON。

默认情况下，它会在本机写入运行数据。除非只是做受控的局域网调试，否则不要把这个服务暴露到公网。

## 功能概览

- 编辑和管理 route graph JSON。
- 根据航线图生成候选航线和规划结果。
- 导出 mission JSON，并支持部分任务修复、统计和媒体辅助工具。
- 提供 FastAPI 后端和 Vue/Vite 前端 WebUI。
- 提供 Python 包模块形式的 CLI 入口，方便脚本化处理。

## 目录结构

- `src/route_graph_webui/`：Python 包源码，包含后端、图模型、规划、任务导出、存储和 CLI。
- `webui_frontend/`：Vue/Vite 前端工程。
- `data/examples/graphs/`：随仓库提供的示例航线图。
- `docs/`：补充文档、JSON schema、运维说明和审计记录。
- `requirements/`：运行、开发和可选媒体依赖。
- `tests/`：后端、图模型、规划和契约测试。
- `start.bat`：构建前端后使用的本地启动脚本。
- `start_dev.bat`：开发模式启动脚本，会同时启动后端和 Vite dev server。

## 环境要求

- Python 3.10 或更高版本。
- Node.js 和 npm，用于前端开发、测试和构建。
- Windows 下可以直接使用仓库里的 `.bat` 启动脚本。

以下命令默认都在项目根目录执行：

```powershell
Set-Location "F:\deeplearning\UAV\route_graph_webui"
```

## 安装

只安装后端运行依赖：

```powershell
python -m pip install -r requirements/runtime.txt
```

开发模式建议使用 editable install：

```powershell
python -m pip install -e ".[dev]"
```

需要媒体处理相关工具时安装可选依赖：

```powershell
python -m pip install -e ".[media]"
```

等价的 requirements 文件是 `requirements/dev.txt` 和 `requirements/media.txt`。

## 启动

### 普通本地启动

普通启动要求先构建前端：

```powershell
npm --prefix webui_frontend ci
npm --prefix webui_frontend run build
.\start.bat
```

`start.bat` 会检查 Python、后端端口和 `webui_frontend/dist/index.html`，然后启动：

```powershell
python -m uvicorn route_graph_webui.backend.server:app --host 127.0.0.1 --port 8000
```

启动成功后浏览器会打开 `http://127.0.0.1:8000/`。

### 开发模式启动

开发模式会启动后端 reload 和 Vite dev server：

```powershell
python -m pip install -e ".[dev]"
npm --prefix webui_frontend ci
.\start_dev.bat
```

默认前端地址是 `http://127.0.0.1:5173`，后端地址是 `http://127.0.0.1:8000`。

两个启动脚本都会设置 `PYTHONPATH=%ROOT%src`，因此在 editable install 之前也可以找到本地包源码。

## 运行数据

运行数据由 `ROUTE_GRAPH_WEBUI_DATA_DIR` 决定。

开发模式默认使用仓库内的 `data/` 目录。普通启动或离线包启动时，如果没有显式设置 `ROUTE_GRAPH_WEBUI_DATA_DIR`，`start.bat` 会优先使用用户可写目录，例如 `%LOCALAPPDATA%\RouteGraphWebUI\data`。

常见运行子目录：

- `graphs`：当前可编辑的航线图 JSON。
- `plans`：候选集合和规划结果。
- `missions`：导出的 mission JSON。
- `previews`：生成的预览图片。
- `logs`、`progress`、`state`：运行诊断信息和 WebUI 状态。

示例航线图位于 `data/examples/graphs/*.json`。首次启动时，`ensure_data_directories()` 会创建运行目录，并在运行时 `graphs` 目录为空时复制这些示例。

## 常用环境变量

- `ROUTE_GRAPH_WEBUI_HOST`：后端监听地址，默认 `127.0.0.1`。
- `ROUTE_GRAPH_WEBUI_PORT`：后端端口，默认 `8000`。
- `ROUTE_GRAPH_WEBUI_DATA_DIR`：运行数据目录。
- `ROUTE_GRAPH_WEBUI_PYTHON`：指定 Python 可执行文件。
- `ROUTE_GRAPH_WEBUI_ALLOW_LAN=1`：显式允许面向局域网的本地调试。
- `ROUTE_GRAPH_WEBUI_CORS_ORIGINS`：用逗号分隔的 CORS origin 覆盖值。
- `ROUTE_GRAPH_WEBUI_VITE_HOST`：Vite dev server 监听地址，默认 `127.0.0.1`。
- `VITE_API_BASE`：前端请求的后端基础地址；开发模式为空时使用 Vite `/api` 代理。

## 常用命令

后端测试和生成契约检查：

```powershell
python -B -m pytest tests -q -p no:cacheprovider
python -B -m route_graph_webui.tools.sync_api_schema --check
python -B -m route_graph_webui.tools.sync_graph_meta --check
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

`npm audit` 是联网安全审计命令，发布前可以跑，但不是离线启动的硬性门槛。

## CLI 入口

推荐使用 Python 包模块形式的 CLI：

```powershell
python -m route_graph_webui.cli.graph_record --help
python -m route_graph_webui.cli.graph_editor --help
python -m route_graph_webui.cli.route_planner --help
python -m route_graph_webui.cli.mission_export --help
python -m route_graph_webui.cli.graph_gui --help
python -m route_graph_webui.cli.visualize_graph --help
```

根目录级别的旧脚本包装器不再随包发布，以上包模块命令是支持的入口。

## 更多文档

- `docs/README.md`：文档索引。
- `docs/schema/graph-json.md`：graph JSON 格式说明。
- `docs/operations/optional-tools.md`：可选媒体和任务修复工具。
- `docs/preview/`：前端等高线背景的开发预览资源。
- `webui_frontend/README.md`：前端脚本和环境变量。

## 打包和离线包

Python 包元数据位于 `pyproject.toml`。包资源包含 `route_graph_webui.resources/registered_env_ids.json`，保持它在 package data 中。

源码包或离线包建议包含：

- `pyproject.toml`、`README.md`、`README.zh-CN.md`、`docs/`、`requirements/`、`start.bat`、`start_dev.bat`。
- `src/route_graph_webui/`，包括包资源。
- `data/examples/graphs/*.json`。
- `webui_frontend/package*.json`、前端源码；离线包还需要包含已构建的 `webui_frontend/dist/`。

不要把运行输出放进离线包，例如运行时 `graphs`、`plans`、`missions`、`previews`、`logs`、`progress`、`state`、`webui_state.json`、`node_modules` 或 `__pycache__`。
