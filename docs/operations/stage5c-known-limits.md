# Stage 5C Known Limits And Next Optimizations

Stage 5C closed the low-risk utility/performance pass and final release validation. The items below are intentionally recorded as known limits rather than being mixed into the final low-risk patch.

## 已知限制

- `RouteGraph.node_map` / `edge_map` caching or reusable graph context is not implemented yet. The graph objects remain mutable, so a cache needs invalidation rules before it can be safe.
- `route_planner` parent pointer traceback optimization is not implemented yet. The current path expansion keeps existing candidate ordering and filtering semantics; a parent pointer rewrite needs focused equivalence tests.
- `auto_route_planner` Dijkstra/endpoint-distance caching is not implemented yet. Endpoint distance now reuses shared geometry helpers, but Dijkstra reuse should be handled as a separate planner performance change.
- `validate_graph` now buckets edge intersection checks by group color. A spatial index is deferred until a large-graph performance pass needs it and can prove identical validation results.
- `tools/mission/mission_repair.py` still keeps its local `_interpolate_segment` behavior because it rounds generated repair points and raises repair-specific `GraphSchemaError` messages. A later cleanup can wrap shared `geometry.interpolate_segment_3d` while preserving that rounding/error contract.
- `npm outdated` is clean after applying Wanted in-range updates and upgrading the dev-only `@types/node` package to 25.x. This changes TypeScript Node declarations only and does not change the runtime Node version.

## 下一轮优化项

- Add a safe cache/context layer for `RouteGraph.node_map` and `edge_map`, with mutation/invalidation tests.
- Prototype parent pointer search in `route_planner` behind ordering/selection equivalence tests.
- Add `auto_route_planner` Dijkstra and endpoint-distance caches only after confirming they do not alter pair scoring, sorting, or progress accounting.
- Revisit a spatial index for `validate_graph` only if group-color bucketing is insufficient on large maps.
- Consolidate mission repair interpolation after pinning its rounding behavior in tests.
- Revisit Node runtime support separately if the project later decides to require Node 25 at runtime.
