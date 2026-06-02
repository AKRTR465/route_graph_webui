# Route Graph WebUI Module Tree Refactor TODO

目标：把当前根目录平铺的 Python 模块整理为清晰的 `src/route_graph_webui/` 包结构，减少根目录噪音，并尽量砍掉旧的模块导入兼容负担。

本 TODO 只规划文件树重构，不要求在本轮直接移动代码。

## 0. 结论

- 采用 `src/` layout，Python 库代码进入 `src/route_graph_webui/`。
- 默认走“少兼容负担版”：
  - 保留前后端 API、graph/plan/mission 数据格式兼容。
  - 不长期保留根级模块 import 兼容，例如 `import graph_model`、`import graph_schema`、`import route_planner`。
  - 只短期保留少数用户可见 CLI 薄入口，且只作为命令入口，不作为库 API。
- 根目录最终只保留项目级文件：`README.md`、`pyproject.toml`、`docs/`、`tests/`、`webui_frontend/`、`data/examples/`、`scripts/`、`requirements/` 等。

## 1. 推荐目标树

```text
route_graph_webui/
  README.md
  pyproject.toml
  docs/
  tests/
  scripts/
    start.bat
    start_dev.bat
  requirements/
    runtime.txt
    dev.txt
    media.txt
  data/
    examples/
      graphs/
  webui_frontend/
  src/
    route_graph_webui/
      __init__.py
      resources/
        registered_env_ids.json
      graph/
        __init__.py
        model.py
        meta.py
        io.py
        validation.py
        grouping.py
        conversion.py
        versioning.py
        editor.py
        ui_state.py
        canvas_view.py
        edge_intent.py
      planning/
        __init__.py
        route_planner.py
        auto_route_planner.py
      mission/
        __init__.py
        io.py
      mission_export/
        __init__.py
        config.py
        group_context.py
        sampling.py
        smoothing.py
        exporter.py
      storage/
        __init__.py
        graph_store.py
        json_store.py
        spelling_compat.py
      runtime_support/
        __init__.py
        runtime.py
        env_registry.py
        bootstrap_paths.py
      shared/
        __init__.py
        geometry.py
        cli_args.py
        image_sequence.py
        time_utils.py
      cli/
        __init__.py
        graph_record.py
        graph_editor.py
        route_planner.py
        mission_export.py
        graph_gui.py
        visualize_graph.py
      apps/
        __init__.py
        workers/
          __init__.py
          route_generation.py
      backend/
        __init__.py
        server.py
        models.py
        routers/
        services/
      tools/
        __init__.py
        sync_api_schema.py
        sync_graph_meta.py
        media/
          __init__.py
          resample.py
          composed_video.py
        mission/
          __init__.py
          mission_repair.py
          takeoff_landing_repair.py
```

说明：

- 不建议新建名为 `runtime/` 的包，避免和当前 `runtime.py` 以及潜在第三方语义冲突；使用 `runtime_support/`。
- `mission_export/` 已经是包形态，迁移时优先保留内容边界，只调整到 `src/route_graph_webui/mission_export/`。
- `mission_io.py` 明确迁到 `src/route_graph_webui/mission/io.py`，供 export、repair、tools 共用；不再使用模糊的 `core/` 边界。
- `tools/sync_api_schema.py` 和 `tools/sync_graph_meta.py` 明确迁到 `src/route_graph_webui/tools/`，最终命令才使用 `python -m route_graph_webui.tools...`。
- `webui_frontend/` 继续保持前端独立工程。
- `data/` 只保留可版本化样例，运行态输出仍由 `ROUTE_GRAPH_WEBUI_DATA_DIR` 管理。
- `backend/routers/`、`backend/services/`、`tools/`、`resources/` 都必须有明确 package / package-data 策略；优先使用常规 `__init__.py` 包，资源用 `pyproject.toml` package-data 或 `importlib.resources`。
- 根目录当前的 `__init__.py` 必须在迁移末期删除或移动，否则会和 `src/route_graph_webui/` 发生包名阴影。
- `calculer.py` 当前未归类；默认策略是确认用途后迁到 `tools/mission/mission_stats.py`，无用途则删除。

## 2. 兼容策略

### 2.1 保留的数据/协议兼容

- 保留 graph JSON、candidate set、plan、mission JSON 的既有兼容读取策略。
- 保留 HTTP API path、请求/响应字段和前端契约。
- 保留 OpenAPI/前端生成 DTO 契约。
- 保留 `ROUTE_GRAPH_WEBUI_DATA_DIR` 运行态数据目录语义。
- 保留离线包读取 package resource 和样例 graph 的能力。
- 保留 legacy graph/mission 数据的迁移或 fallback，除非另开数据格式退役专项。

### 2.2 砍掉的模块兼容

目标是不再支持仓内或外部代码继续用根级裸 import：

- `import graph_model`
- `import graph_schema`
- `import graph_io`
- `import graph_validation`
- `import graph_grouping`
- `import candidate_conversion`
- `import graph_store`
- `import json_store`
- `import route_planner`
- `import auto_route_planner`
- `import runtime`
- `import env_registry`
- `import webui_common`
- `import edge_intent_service`
- `import mission_io`
- `import bootstrap_paths`
- `import spelling_compat`
- `import geometry`
- `import cli_args`
- `import image_sequence_utils`

迁移后仓内代码统一使用：

```python
from route_graph_webui.graph.model import RouteGraph
from route_graph_webui.planning.route_planner import generate_route_candidates
from route_graph_webui.storage.graph_store import resolve_graph_root
```

### 2.3 短期保留的命令入口

这些可以短期保留为 5-15 行薄 wrapper，方便用户过渡：

- `graph_record.py`
- `graph_editor.py`
- `route_planner.py`
- `mission_export.py`
- `graph_gui.py`
- `visualize_graph.py`

薄入口只允许调用新包里的 `main()`，不再承载业务逻辑，也不作为 import API。

### 2.4 建议删除的旧 wrapper

这些旧入口收益低，建议迁移到新模块命令后删除：

- `mission_repair.py`
- `resample.py`
- `composed_video.py`
- `route_generation_worker.py`
- `takeoff_landing_repair.py`：可保留一个迁移阶段，随后删除根级 wrapper。

对应新命令：

```powershell
python -m route_graph_webui.tools.mission.mission_repair
python -m route_graph_webui.tools.media.resample
python -m route_graph_webui.tools.media.composed_video
python -m route_graph_webui.apps.workers.route_generation
python -m route_graph_webui.tools.mission.takeoff_landing_repair
```

## 3. 阶段计划

### T00 基线与决策冻结

- [ ] 记录当前根级 `.py` 文件清单和 import 图。
- [ ] 明确当前根级 `__init__.py` 的删除时机，避免 `src/` layout 包名阴影。
- [ ] 明确 `calculer.py` 用途：迁移到 `tools/mission/mission_stats.py`，或确认无用途后删除。
- [ ] 明确 `mission_io.py` 归属为 `route_graph_webui.mission.io`。
- [ ] 记录当前测试基线：
  - `python -B -m pytest tests -q -p no:cacheprovider`
  - `python -B tools\sync_api_schema.py --check`
  - `python -B tools\sync_graph_meta.py --check`
  - `npm --prefix webui_frontend test`
  - `npm --prefix webui_frontend run typecheck`
- [ ] 明确本轮迁移策略：砍根级模块 import 兼容，只短期保留公开 CLI 薄入口。
- [ ] 决定是否同时引入 `pyproject.toml` 和 editable install。
- [ ] 决定根级 6 个 CLI 薄入口的运行前提：要求 `pip install -e .`，或 wrapper 内只允许极小 `PYTHONPATH` bootstrap。

验收：

- [ ] 基线命令全部通过。
- [ ] README 或 TODO 明确“少兼容负担版”的破坏性边界。

### T01 建立新包骨架

- [ ] 新增 `pyproject.toml`，配置 `src/` layout。
- [ ] 在 `pyproject.toml` 中声明 package-data，确保 `resources/registered_env_ids.json` 可被 wheel/离线包读取。
- [ ] 新建 `src/route_graph_webui/` 包骨架。
- [ ] 新建 `graph/`、`planning/`、`mission/`、`storage/`、`runtime_support/`、`shared/`、`cli/`、`apps/workers/`、`backend/`、`tools/` 包目录。
- [ ] 为 `backend/routers/`、`backend/services/`、`tools/media/`、`tools/mission/` 等子包补齐 `__init__.py`。
- [ ] 将 `registered_env_ids.json` 规划为 package resource：`src/route_graph_webui/resources/registered_env_ids.json`。
- [ ] 将 `tools/sync_api_schema.py`、`tools/sync_graph_meta.py` 规划进 `src/route_graph_webui/tools/`。
- [ ] 新增 package import smoke test，验证新 canonical import 可用。

验收：

- [ ] `python -m pip install -e .` 可用。
- [ ] `python -m pip check` 通过。
- [ ] `python -c "import route_graph_webui"` 可用。
- [ ] 新包路径 smoke test 通过。

### T02 测试基础设施先切到包路径

- [ ] 修改 `tests/conftest.py`，不再把 `route_graph_webui/` 自身塞进 `sys.path`。
- [ ] 改为 editable install 或 `PYTHONPATH=src` 使用 `route_graph_webui.*`。
- [ ] 采用“随模块迁移同步改测试”的过渡策略；不新增长期 adapter，只允许短期 CLI wrapper。
- [ ] 重写 `tests/route_graph_test_helpers.py` 的裸 import。
- [ ] 将仓内测试的根级 import 批量改为新包路径。
- [ ] 删除或重写纯兼容断言：
  - `tests/test_graph_module_split.py` 中锁 `graph_schema` re-export / `__module__` 的断言。
  - `tests/test_stage4_backend_split.py` 中 mission export re-export 来源断言。
  - `tests/test_runtime_decoupling.py` 中裸模块 import 断言。

验收：

- [ ] `rg -n "^(from|import) (graph_|mission_export|route_planner|runtime|json_store|edge_intent_service|auto_route_planner|graph_store|graph_ui_state|graph_canvas_view|env_registry|composed_video|mission_io|bootstrap_paths|spelling_compat)\b" tests` 无非白名单命中。
- [ ] `python -B -m pytest tests/test_runtime_decoupling.py tests/test_graph_record_cli.py tests/test_cli_args.py -q -p no:cacheprovider` 通过。

### T03 迁移 shared/storage/runtime_support

- [ ] 移动 `geometry.py` 到 `shared/geometry.py`。
- [ ] 移动 `cli_args.py` 到 `shared/cli_args.py`。
- [ ] 移动 `image_sequence_utils.py` 到 `shared/image_sequence.py`。
- [ ] 拆 `webui_common.py`，将时间等轻量工具迁到 `shared/time_utils.py`。
- [ ] 移动 `graph_store.py`、`json_store.py`、`spelling_compat.py` 到 `storage/`。
- [ ] 移动 `runtime.py`、`env_registry.py`、`bootstrap_paths.py` 到 `runtime_support/`。
- [ ] 更新所有生产代码 import，不保留根级模块 import shim。
- [ ] `env_registry` 改用 `importlib.resources` 读取 `registered_env_ids.json`，不再假设资源一定在普通根目录文件路径。

验收：

- [ ] `tests/test_storage_contracts.py` 通过。
- [ ] `tests/test_shared_utils.py` 通过。
- [ ] `tests/test_env_registry_local.py` 通过。
- [ ] `rg -n "sys\.path\.insert" src tests scripts` 无非白名单命中。

### T04 迁移 graph core

- [ ] 移动 `graph_model.py` 到 `graph/model.py`。
- [ ] 移动 `graph_meta.py` 到 `graph/meta.py`。
- [ ] 移动 `graph_io.py` 到 `graph/io.py`。
- [ ] 移动 `graph_validation.py` 到 `graph/validation.py`。
- [ ] 移动 `graph_grouping.py` 到 `graph/grouping.py`。
- [ ] 移动 `candidate_conversion.py` 到 `graph/conversion.py`。
- [ ] 移动 `graph_versioning.py` 到 `graph/versioning.py`。
- [ ] 移动 `graph_editor.py` 的业务实现到 `graph/editor.py`，CLI 入口放 `cli/graph_editor.py`。
- [ ] 移动 `graph_ui_state.py` 到 `graph/ui_state.py`。
- [ ] 移动 `graph_canvas_view.py` 到 `graph/canvas_view.py`。
- [ ] 移动 `edge_intent_service.py` 到 `graph/edge_intent.py`。
- [ ] 删除 `graph_schema.py` facade，或将其改为新包内部的明确 schema 聚合模块，不再作为根级兼容层。

验收：

- [ ] `tests/test_graph_schema.py` 通过。
- [ ] `tests/test_graph_validation.py` 通过。
- [ ] `tests/test_graph_gui_color_groups.py` 通过。
- [ ] 新测试不再断言旧 `__module__`。

### T05 迁移 planning 与 worker

- [ ] 移动 `route_planner.py` 的业务实现到 `planning/route_planner.py`。
- [ ] 移动 `auto_route_planner.py` 到 `planning/auto_route_planner.py`。
- [ ] 移动 `route_generation_worker.py` 到 `apps/workers/route_generation.py`。
- [ ] 后端和 GUI worker 启动改成模块命令：
  - `python -m route_graph_webui.apps.workers.route_generation`
- [ ] 根级 `route_generation_worker.py` 删除。
- [ ] 根级 `route_planner.py` 若保留，只保留薄 CLI wrapper。

验收：

- [ ] `tests/test_route_planner.py` 通过。
- [ ] `tests/test_auto_route_planner.py` 通过。
- [ ] `tests/test_webui_api.py` 中 job 相关测试通过。
- [ ] `python -m route_graph_webui.cli.route_planner --help` 通过。

### T06 迁移 mission/export、tools 和 CLI

- [ ] 将 `mission_io.py` 移到 `src/route_graph_webui/mission/io.py`。
- [ ] 将 `mission_export/` 移入 `src/route_graph_webui/mission_export/`。
- [ ] 将 `graph_record.py` 业务实现移入 `cli/graph_record.py` 或 `apps/graph_record.py`。
- [ ] 将 `graph_gui.py` 业务实现移入 `cli/graph_gui.py` 或 `apps/graph_gui.py`。
- [ ] 将 `visualize_graph.py` 移入 `cli/visualize_graph.py`。
- [ ] 明确 `calculer.py` 的处置：迁到 `tools/mission/mission_stats.py` 并补命令说明，或删除。
- [ ] 将 `tools/sync_api_schema.py`、`tools/sync_graph_meta.py` 移入 `src/route_graph_webui/tools/`。
- [ ] 更新 sync 生成文件注释里的旧命令，改为 `python -m route_graph_webui.tools.sync_*`。
- [ ] 将 `tools/media/*` 移入 `src/route_graph_webui/tools/media/`。
- [ ] 将 `tools/mission/*` 移入 `src/route_graph_webui/tools/mission/`。
- [ ] 删除根级 optional wrapper：
  - `mission_repair.py`
  - `resample.py`
  - `composed_video.py`
  - `takeoff_landing_repair.py`（可在一个迁移阶段后删除）

验收：

- [ ] `python -m route_graph_webui.cli.graph_record --help` 通过。
- [ ] `python -m route_graph_webui.cli.graph_editor --help` 通过。
- [ ] `python -m route_graph_webui.cli.mission_export --help` 通过。
- [ ] `python -m route_graph_webui.cli.graph_gui --help` 通过。
- [ ] `python -m route_graph_webui.tools.media.resample --help` 通过。
- [ ] `python -B -m route_graph_webui.tools.sync_api_schema --check` 通过。
- [ ] `python -B -m route_graph_webui.tools.sync_graph_meta --check` 通过。
- [ ] `tests/test_graph_record_cli.py`、`tests/test_mission_export.py`、`tests/test_mission_repair.py` 通过。

### T07 迁移 backend 和启动脚本

- [ ] 将 `webui_backend/` 移入 `src/route_graph_webui/backend/`。
- [ ] 后端内部 import 全部改成 package import 或相对 import。
- [ ] `start.bat` / `start_dev.bat` 改为从根目录启动：
  - `"%PYTHON_EXE%" -m uvicorn route_graph_webui.backend.server:app --host ... --port ...`
- [ ] 不再 `cd webui_backend`。
- [ ] 如未安装 editable package，脚本显式设置并继承 `PYTHONPATH=%ROOT%src`。
- [ ] Windows bat 中所有路径变量加引号，继续支持 `ROUTE_GRAPH_WEBUI_PYTHON`。
- [ ] 端口检查继续显式成功退出，避免 `Get-NetTCPConnection` 空结果导致静默失败。
- [ ] 同步更新 `/api/health` readiness check。
- [ ] `BackgroundJobService` / GUI worker 启动改为 `sys.executable -m route_graph_webui.apps.workers.route_generation`，不再拼根级脚本路径。

验收：

- [ ] `python -m uvicorn route_graph_webui.backend.server:app --host 127.0.0.1 --port 8000` 可启动。
- [ ] `start.bat` 可启动离线式 WebUI。
- [ ] `start_dev.bat` 可启动后端 reload 和 Vite。
- [ ] `tests/test_webui_api.py`、`tests/test_api_contracts.py` 通过。
- [ ] 新增或更新测试，断言后端和 GUI worker 使用 `-m route_graph_webui.apps.workers.route_generation`。
- [ ] `python -B -m route_graph_webui.tools.sync_api_schema --check` 通过。

### T08 整理 requirements、docs、data、发布包

- [ ] 新增 `requirements/` 目录，迁移：
  - `requirements-runtime.txt` -> `requirements/runtime.txt`
  - `requirements-dev.txt` -> `requirements/dev.txt`
  - `requirements-media.txt` -> `requirements/media.txt`
- [ ] 删除 `requirements-webui.txt`，或在一个迁移阶段后删除。
- [ ] 新增/更新 `pyproject.toml` extras：
  - `.[dev]`
  - `.[media]`
- [ ] 更新 README 所有命令为新模块命令。
- [ ] 更新 `docs/operations/optional-tools.md`，删除旧 wrapper 说明。
- [ ] 更新 `docs/schema/graph-json.md` 中的 CLI 示例。
- [ ] 更新 `webui_frontend/README.md` 中与后端路径、API base、启动方式相关的说明。
- [ ] 将 `registered_env_ids.json` 迁为 package resource。
- [ ] 将 `data/graphs/*.json` 迁到 `data/examples/graphs/`，运行态数据仍写入 `ROUTE_GRAPH_WEBUI_DATA_DIR`。
- [ ] 明确首次启动如何从 package/data examples 初始化或复制默认 graph 到运行态 `data/graphs`。
- [ ] 明确 `preview/` 是文档/开发资产还是运行资产；若是开发资产，移动到 `docs/preview/` 或 `webui_frontend/dev_preview/`。
- [ ] 明确 `npm audit` 是联网安全检查，不作为纯离线包启动硬门禁。
- [ ] 写清发布包/离线包清单：
  - package metadata / `pyproject.toml`
  - `src/route_graph_webui/resources/registered_env_ids.json`
  - `data/examples/graphs/*.json`
  - `webui_frontend/dist/`
  - `scripts/start*.bat`
  - 必要 requirements 或 wheel/editable install 说明。

验收：

- [ ] README 不再推荐 `python xxx.py` 旧命令，除短期保留的 6 个薄入口外。
- [ ] 发布包清单不包含根级业务 `.py` 平铺文件。
- [ ] 离线包仍包含 `webui_frontend/dist/` 和必要样例 graph。
- [ ] 干净环境 `python -m pip install -e ".[dev]"`、`python -m pip check` 通过。
- [ ] 临时 `ROUTE_GRAPH_WEBUI_DATA_DIR` 首次启动后能看到或复制样例 graph。

### T09 删除根级模块与最终门禁

- [ ] 删除根级库模块文件：
  - `__init__.py`
  - `bootstrap_paths.py`
  - `graph_model.py`
  - `graph_meta.py`
  - `graph_io.py`
  - `graph_validation.py`
  - `graph_grouping.py`
  - `candidate_conversion.py`
  - `graph_schema.py`
  - `graph_store.py`
  - `json_store.py`
  - `runtime.py`
  - `env_registry.py`
  - `webui_common.py`
  - `graph_ui_state.py`
  - `graph_canvas_view.py`
  - `edge_intent_service.py`
  - `auto_route_planner.py`
  - `route_generation_worker.py`
  - `geometry.py`
  - `cli_args.py`
  - `image_sequence_utils.py`
  - `mission_io.py`
  - `spelling_compat.py`
  - `calculer.py`
  - `resample.py`
  - `composed_video.py`
  - `mission_repair.py`
  - `takeoff_landing_repair.py`
- [ ] 根级只允许保留项目文件、文档、脚本目录、前端目录、测试目录、样例数据目录，以及短期保留的 6 个 CLI 薄入口。
- [ ] 如仍保留 6 个 CLI 薄入口，确认每个文件只有 import main + exit main。
- [ ] 增加静态门禁，禁止仓内裸 import 和手工 `sys.path.insert` 回流。
- [ ] 增加旧目录/旧根模块不存在检查，避免迁移后残留 `webui_backend/`、根级库模块或旧 `tools` 入口。

静态门禁：

```powershell
rg -n "^(from|import) (graph_|mission_export|route_planner|runtime|json_store|edge_intent_service|auto_route_planner|graph_store|graph_ui_state|graph_canvas_view|env_registry|composed_video|mission_io|bootstrap_paths|spelling_compat)\b" tests src scripts
rg -n "sys\.path\.insert" tests src scripts
python -c "from pathlib import Path; forbidden=['__init__.py','graph_model.py','graph_schema.py','graph_store.py','json_store.py','runtime.py','env_registry.py','webui_common.py','route_generation_worker.py','mission_io.py','calculer.py']; remain=[p for p in forbidden if Path(p).exists()]; raise SystemExit('forbidden root files remain: '+repr(remain) if remain else 0)"
```

最终验收：

```powershell
python -m pip install -e ".[dev]"
python -m pip check
python -B -m pytest tests -q -p no:cacheprovider
python -B -m route_graph_webui.tools.sync_api_schema --check
python -B -m route_graph_webui.tools.sync_graph_meta --check
npm --prefix webui_frontend ci
npm --prefix webui_frontend test
npm --prefix webui_frontend run test:collect
npm --prefix webui_frontend run typecheck
npm --prefix webui_frontend run lint
npm --prefix webui_frontend run format
npm --prefix webui_frontend run build
npm --prefix webui_frontend audit --audit-level=moderate
```

手工烟雾：

```powershell
scripts\start.bat
scripts\start_dev.bat
python -m route_graph_webui.cli.graph_editor --help
python -m route_graph_webui.cli.route_planner --help
python -m route_graph_webui.cli.mission_export --help
python -m route_graph_webui.tools.media.resample --help
```

## 4. 风险清单

- `graph_gui.py` 体量最大，耦合 Tk UI、worker、graph/planning/export，建议晚迁。
- `route_generation_worker.py` 当前被后端和 GUI 以脚本路径启动，必须先切模块命令再删除根文件。
- `tests/test_graph_module_split.py`、`tests/test_stage4_backend_split.py`、`tests/test_runtime_decoupling.py` 当前保护旧兼容，需要主动重写。
- `webui_backend/server.py` 当前启动方式依赖 `cd webui_backend && uvicorn server:app`，迁移后必须改 start scripts。
- `registered_env_ids.json` 当前在根目录，被 `env_registry.py` 直接读取；迁移到 package resource 时要保留离线包可读性。
- `data/examples/graphs` 迁移后必须有首次运行初始化策略，否则新运行态目录可能无 graph 可选。
- `requirements-webui.txt` 删除前要确认 README、docs 和脚本不再引用。
- Windows 启动要覆盖路径含空格、PowerShell/CMD、端口空闲、端口占用、Vite 5173 占用、`start` 子进程环境继承。
- 不要把“模块 import 兼容退役”和“旧数据格式退役”混在同一阶段，后者需要单独迁移公告和数据迁移脚本。

## 5. 子 agent 研究摘要

- Gauss：建议把库代码和命令入口分开；少兼容版本可以砍掉根级模块 import 兼容，只保留必要可执行入口。
- Euclid：测试层当前大量保护旧裸 import 和 re-export；若要砍兼容，必须先改 tests/conftest、route_graph_test_helpers、compat-only 测试。
- Aristotle：CLI/tools/docs/start 边界建议转向 `python -m route_graph_webui...`；可删除 optional wrapper 和内部 worker 根入口，保留 6 个公开 CLI 薄入口作为过渡。
- Dewey/Pauli/Rawls 审查：方案方向通过，但补充要求覆盖根级 `__init__.py`、`calculer.py`、`mission_io.py`、`tools/sync_*`、package resource、Windows 启动和最终静态门禁。
