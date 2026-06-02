# Graph JSON Schema

Graph files live under the active data directory's `graphs` folder. Repository examples live under `data/examples/graphs`; on first startup, an empty runtime `graphs` folder is initialized from those examples. New writes include `schema_version`; old files without a version are migrated on read.

## Top Level

- `schema_version`: integer schema version. Current version is `1`.
- `env_id`: environment id used by runtime and export tools.
- `graph_name`: display and export name.
- `default_altitude`: optional default route altitude.
- `nodes`: list of graph nodes.
- `edges`: list of graph edges.
- `meta`: graph-level metadata for UI state, grouping, bridge style, and compatibility.

## Nodes

Each node contains:

- `id`: stable node id.
- `name`: display name.
- `position`: `[x, y, z]`.
- `yaw_hint`: optional yaw hint in degrees.
- `tags`: string tags.
- `meta`: node metadata, including optional sample radius overrides.

## Edges

Each edge contains:

- `id`: stable edge id.
- `from` / `to`: endpoint node ids.
- `weight`: edge length or route cost.
- `enabled`: whether planners may use the edge.
- `bidirectional`: whether the reverse direction is also allowed.
- `meta`: edge kind, group color, bridge metadata, and other UI metadata.

## Metadata Compatibility

Graph meta constants are sourced from `route_graph_webui.graph.meta` and synchronized to `webui_frontend/src/types/graph-meta.ts`.

Legacy `graph_gui_*` meta keys remain compatible for now. Legacy creator values beginning with `route_garph.` are accepted on read and normalized to `route_graph.` on new writes, preserving the original value in `legacy_creator`.

## Validation

Use:

```powershell
python -m route_graph_webui.cli.graph_editor validate --graph data/examples/graphs/DowntownWest.json
```

Validation checks duplicate edges, missing nodes, graph grouping constraints, same-color intersections, bridge exceptions, and schema field shapes.
