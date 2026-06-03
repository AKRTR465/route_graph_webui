# Graph JSON Format

Graph files use the `route-graph` format. The backend only reads this format; legacy
`schema_version` graph files are not supported at runtime.

Graph files live under the active data directory's `graphs` folder. Repository examples
live under `data/examples/graphs`.

## Top Level

Required fields:

- `format`: must be `route-graph`.
- `format_version`: must be `1`.
- `id`: stable graph id.
- `name`: display and export name.
- `coordinate_system`: object describing coordinates. Current bundled graphs use
  `{ "type": "cartesian", "axes": ["x", "y", "z"], "unit": "cm" }`.
- `nodes`: list of graph nodes.
- `edges`: list of graph edges.

Optional fields:

- `properties`: project-neutral graph attributes.
- `extensions`: namespaced project-specific data.

## Nodes

Each node contains:

- `id`: stable node id.
- `label`: display name.
- `position`: `[x, y, z]`.
- `tags`: string tags.
- `properties`: project-neutral node attributes.
- `extensions`: namespaced node-specific data.

UAV data is stored under `extensions.uav`, for example:

- `yaw_hint_deg`
- `sample_radius`

## Edges

Each edge contains:

- `id`: stable edge id.
- `source` / `target`: endpoint node ids.
- `directed`: whether the edge is one-way. `false` means bidirectional.
- `enabled`: whether planners may use the edge.
- `metrics`: optional numeric values such as `length` and `cost`.
- `properties`: project-neutral edge attributes.
- `extensions`: namespaced edge-specific data.

When `metrics` is omitted, route planning resolves edge cost at runtime from endpoint XY
distance. Missing metrics is not a graph format error.

## Extensions

Project-specific fields must live under a namespace in `extensions`.

- `extensions.uav.env_id`: runtime environment id when needed.
- `extensions.uav.default_altitude`: default route altitude when needed.
- `extensions.route_graph_webui`: WebUI grouping, bridge style, and saved UI state.

Unknown extension namespaces are preserved when loading and saving.

## Validation

Base graph validation is intentionally structural:

- JSON root must be an object.
- `format` must be `route-graph`.
- `format_version` must be `1`.
- `id` and `name` must be non-empty strings.
- `coordinate_system` must be an object.
- `nodes` and `edges` must be arrays.
- Node ids must be non-empty and unique.
- Node positions must contain exactly three finite numbers.
- Edge ids must be non-empty and unique.
- Edge `source` and `target` must reference existing nodes.
- Self-loop edges are invalid.
- `directed` and `enabled`, when present, must be booleans.
- `properties` and `extensions`, when present, must be objects.
- `metrics`, when present, must be an object with finite numeric values.

Color groups, bridge semantics, edge intersections, isolated nodes, and UAV-specific
export rules are domain checks, not base graph format checks.
