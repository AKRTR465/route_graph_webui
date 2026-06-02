# Package Refactor T00/T01 Baseline

日期：2026-06-02

本记录只冻结 T00/T01 的可审查基线和决策；不代表后续模块已经迁移。

## 根级 Python 文件

当前根级 `.py` 文件清单：

```text
__init__.py
auto_route_planner.py
bootstrap_paths.py
calculer.py
candidate_conversion.py
cli_args.py
composed_video.py
edge_intent_service.py
env_registry.py
geometry.py
graph_canvas_view.py
graph_editor.py
graph_grouping.py
graph_gui.py
graph_io.py
graph_meta.py
graph_model.py
graph_record.py
graph_schema.py
graph_store.py
graph_ui_state.py
graph_validation.py
graph_versioning.py
image_sequence_utils.py
json_store.py
mission_export.py
mission_io.py
mission_repair.py
resample.py
route_generation_worker.py
route_planner.py
runtime.py
spelling_compat.py
takeoff_landing_repair.py
visualize_graph.py
webui_common.py
```

## 根级 import 图

用 AST 解析根级 `.py` 文件得到的根模块间 import 关系：

```text
auto_route_planner.py -> geometry, graph_schema, mission_export, route_planner
candidate_conversion.py -> graph_model
edge_intent_service.py -> graph_schema
graph_canvas_view.py -> graph_meta
graph_editor.py -> graph_schema, json_store
graph_grouping.py -> graph_meta, graph_model
graph_gui.py -> auto_route_planner, edge_intent_service, geometry, graph_canvas_view, graph_editor, graph_schema, graph_ui_state, mission_export, runtime, visualize_graph
graph_io.py -> graph_model, graph_validation, json_store
graph_model.py -> graph_versioning
graph_record.py -> graph_schema, runtime
graph_schema.py -> candidate_conversion, graph_grouping, graph_io, graph_meta, graph_model, graph_validation, graph_versioning
graph_store.py -> spelling_compat
graph_ui_state.py -> graph_meta, graph_schema
graph_validation.py -> candidate_conversion, geometry, graph_grouping, graph_meta, graph_model
graph_versioning.py -> spelling_compat
mission_export.py -> mission_export
mission_io.py -> graph_schema
route_generation_worker.py -> auto_route_planner, graph_schema, json_store, route_planner
route_planner.py -> cli_args, graph_schema, webui_common
runtime.py -> bootstrap_paths, env_registry, webui_common
visualize_graph.py -> graph_schema
webui_common.py -> graph_store, spelling_compat
```

## 冻结决策

- 采用 `src/` layout 和 editable install；新增 canonical package 为 `route_graph_webui`。
- `registered_env_ids.json` 先复制到 `src/route_graph_webui/resources/registered_env_ids.json` 并作为 package data 声明；根级原文件本阶段保留。
- 根级 `__init__.py` 本阶段不删除。删除时机冻结为 T09：所有业务模块完成迁移、仓内 import 已切到 `route_graph_webui.*`、根级 CLI 只剩允许的薄入口或已删除后，再删除，避免 parent path 下的包名阴影。
- 已观察到 pytest 在当前目录结构下会因根级 `__init__.py` 把仓库本身作为旧 `route_graph_webui` 包参与收集；T01 smoke test 因此用子进程验证 editable install，不提前修改 T02 的测试路径策略。
- `mission_io.py` 的目标归属冻结为 `route_graph_webui.mission.io`，供 export、repair、tools 共用。
- `calculer.py` 当前用途是 mission JSON frame-count statistics CLI；后续默认迁到 `route_graph_webui.tools.mission.mission_stats`。若主 agent 判定无用户价值，再在 T06/T09 删除。
- 破坏性边界采用“少兼容负担版”：保留 graph/plan/mission 数据格式、HTTP API 和前端契约兼容；不长期支持 `import graph_schema`、`import route_planner` 等根级裸 import。
- 短期公开 CLI 薄入口仍限定为 `graph_record.py`、`graph_editor.py`、`route_planner.py`、`mission_export.py`、`graph_gui.py`、`visualize_graph.py`。后续 wrapper 的运行前提是 `python -m pip install -e .`；如需 bootstrap，只允许极小 `PYTHONPATH` 处理，不承载业务逻辑。

## 本阶段验证记录

- `python -m pip install -e .`：通过。
- `python -m pip check`：通过。
- `python -c "import route_graph_webui"`：通过。
- `python -B -m pytest tests/test_package_skeleton.py -q -p no:cacheprovider`：通过。
- `python -B -m route_graph_webui.tools.sync_api_schema --check`：通过。
- `python -B -m route_graph_webui.tools.sync_graph_meta --check`：通过。
- `python -B -m pytest tests -q -p no:cacheprovider`：未通过，收集阶段 11 个错误；共同原因是现有 `bootstrap_paths.py` 在当前 workspace 中找不到完整项目根 markers：`gym_unrealcv`、`env_config.py`、`pyproject.toml`。该问题属于旧 runtime/project-root 前提，未在 T01 修改。
