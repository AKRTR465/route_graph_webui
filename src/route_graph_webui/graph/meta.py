from __future__ import annotations


NODE_Z_PREPROCESS_MODE = "mean_all_recorded_nodes"
NODE_SAMPLE_RADIUS_META_KEY = "node_sample_radius"

EDGE_KIND_META_KEY = "edge_kind"
EDGE_KIND_GROUP = "group"
EDGE_KIND_BRIDGE = "bridge"
EDGE_GROUP_COLOR_META_KEY = "group_color"

GRAPH_GROUP_CONFIGS_META_KEY = "group_configs_v1"
GRAPH_BRIDGE_STYLE_META_KEY = "bridge_style_v1"
GROUP_CONFIG_LABEL_KEY = "label"
GROUP_CONFIG_TEXT_KEYS = (
    "altitude_mode",
    "fixed_z",
    "altitude_offset",
    "node_sample_radius",
    "takeoff_landing_relative_z",
    "takeoff_landing_step_distance",
)

GRAPH_GUI_EXPORT_INPUTS_META_KEY = "graph_gui_export_inputs_v1"
GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY = "graph_gui_auto_plan_inputs_v1"
GRAPH_GUI_WEBUI_INPUTS_META_KEY = "graph_gui_webui_inputs_v1"
GRAPH_GUI_CANVAS_VIEW_META_KEY = "graph_gui_canvas_view_v1"
GRAPH_GUI_CANVAS_VIEW_BOOL_KEYS = ("flip_horizontal", "flip_vertical")
GRAPH_GUI_CANVAS_VIEW_DEFAULTS = {
    "rotation_quadrants": 0,
    "flip_horizontal": False,
    "flip_vertical": False,
}

DEFAULT_GROUP_COLOR = "#334155"
DEFAULT_BRIDGE_COLOR = "#F97316"

EDGE_KINDS = (EDGE_KIND_GROUP, EDGE_KIND_BRIDGE)
GRAPH_GUI_META_KEYS = (
    GRAPH_GUI_EXPORT_INPUTS_META_KEY,
    GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
    GRAPH_GUI_WEBUI_INPUTS_META_KEY,
    GRAPH_GUI_CANVAS_VIEW_META_KEY,
)


__all__ = [
    "DEFAULT_BRIDGE_COLOR",
    "DEFAULT_GROUP_COLOR",
    "EDGE_GROUP_COLOR_META_KEY",
    "EDGE_KIND_BRIDGE",
    "EDGE_KIND_GROUP",
    "EDGE_KIND_META_KEY",
    "EDGE_KINDS",
    "GRAPH_BRIDGE_STYLE_META_KEY",
    "GRAPH_GROUP_CONFIGS_META_KEY",
    "GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY",
    "GRAPH_GUI_CANVAS_VIEW_BOOL_KEYS",
    "GRAPH_GUI_CANVAS_VIEW_DEFAULTS",
    "GRAPH_GUI_CANVAS_VIEW_META_KEY",
    "GRAPH_GUI_EXPORT_INPUTS_META_KEY",
    "GRAPH_GUI_META_KEYS",
    "GRAPH_GUI_WEBUI_INPUTS_META_KEY",
    "GROUP_CONFIG_LABEL_KEY",
    "GROUP_CONFIG_TEXT_KEYS",
    "NODE_SAMPLE_RADIUS_META_KEY",
    "NODE_Z_PREPROCESS_MODE",
]
