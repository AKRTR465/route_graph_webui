from __future__ import annotations

import argparse
import sys

from route_graph_webui.storage.graph_store import PROJECT_ROOT

TARGET_PATH = PROJECT_ROOT / "webui_frontend" / "src" / "types" / "graph-meta.ts"


def _render() -> str:
    from route_graph_webui.graph import meta as graph_meta

    values = {
        "NODE_SAMPLE_RADIUS_META_KEY": graph_meta.NODE_SAMPLE_RADIUS_META_KEY,
        "EDGE_KIND_META_KEY": graph_meta.EDGE_KIND_META_KEY,
        "EDGE_KIND_GROUP": graph_meta.EDGE_KIND_GROUP,
        "EDGE_KIND_BRIDGE": graph_meta.EDGE_KIND_BRIDGE,
        "EDGE_GROUP_COLOR_META_KEY": graph_meta.EDGE_GROUP_COLOR_META_KEY,
        "GRAPH_GROUP_CONFIGS_META_KEY": graph_meta.GRAPH_GROUP_CONFIGS_META_KEY,
        "GRAPH_BRIDGE_STYLE_META_KEY": graph_meta.GRAPH_BRIDGE_STYLE_META_KEY,
        "GRAPH_GUI_EXPORT_INPUTS_META_KEY": graph_meta.GRAPH_GUI_EXPORT_INPUTS_META_KEY,
        "GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY": graph_meta.GRAPH_GUI_AUTO_PLAN_INPUTS_META_KEY,
        "GRAPH_GUI_WEBUI_INPUTS_META_KEY": graph_meta.GRAPH_GUI_WEBUI_INPUTS_META_KEY,
        "GRAPH_GUI_CANVAS_VIEW_META_KEY": graph_meta.GRAPH_GUI_CANVAS_VIEW_META_KEY,
        "DEFAULT_GROUP_COLOR": graph_meta.DEFAULT_GROUP_COLOR,
        "DEFAULT_BRIDGE_COLOR": graph_meta.DEFAULT_BRIDGE_COLOR,
    }
    lines = [
        f"export const {name} = '{value}' as const"
        for name, value in values.items()
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync graph meta constants to frontend TypeScript.")
    parser.add_argument("--check", action="store_true", help="Fail if the checked-in TypeScript is stale")
    args = parser.parse_args(argv)

    rendered = _render()
    if args.check:
        try:
            current = TARGET_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"Missing graph meta TypeScript file: {TARGET_PATH}", file=sys.stderr)
            return 1
        if current != rendered:
            print(
                "Graph meta TypeScript constants are stale. Run `python -m route_graph_webui.tools.sync_graph_meta`.",
                file=sys.stderr,
            )
            return 1
        return 0

    TARGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    TARGET_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {TARGET_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
