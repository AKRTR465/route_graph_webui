from __future__ import annotations

import argparse
from pathlib import Path

from route_graph_webui.graph.editor import GraphEditor
from route_graph_webui.graph.io import load_graph
from route_graph_webui.graph.model import GraphSchemaError
from route_graph_webui.graph.validation import validate_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Edit and validate route_graph_webui graph JSON files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_edge = subparsers.add_parser("add-edge", help="Add a manual feasible edge")
    add_edge.add_argument("--graph", required=True)
    add_edge.add_argument("--from-node", required=True)
    add_edge.add_argument("--to-node", required=True)
    add_edge.add_argument("--edge-id")
    add_edge.add_argument("--weight", type=float)
    add_edge.add_argument("--one-way", action="store_true", help="Create a one-way edge")
    add_edge.add_argument("--disabled", action="store_true")
    add_edge.add_argument("--output")
    add_edge.add_argument("--allow-invalid", action="store_true")

    remove_edge = subparsers.add_parser("remove-edge", help="Remove an edge by id")
    remove_edge.add_argument("--graph", required=True)
    remove_edge.add_argument("--edge-id", required=True)
    remove_edge.add_argument("--output")
    remove_edge.add_argument("--allow-invalid", action="store_true")

    rename_node = subparsers.add_parser("rename-node", help="Rename a node")
    rename_node.add_argument("--graph", required=True)
    rename_node.add_argument("--node-id", required=True)
    rename_node.add_argument("--name", required=True)
    rename_node.add_argument("--output")
    rename_node.add_argument("--allow-invalid", action="store_true")

    set_tags = subparsers.add_parser("set-tags", help="Replace node tags")
    set_tags.add_argument("--graph", required=True)
    set_tags.add_argument("--node-id", required=True)
    set_tags.add_argument("--tags", nargs="*", default=[])
    set_tags.add_argument("--output")
    set_tags.add_argument("--allow-invalid", action="store_true")

    delete_node = subparsers.add_parser("delete-node", help="Delete a node and connected edges")
    delete_node.add_argument("--graph", required=True)
    delete_node.add_argument("--node-id", required=True)
    delete_node.add_argument("--output")
    delete_node.add_argument("--allow-invalid", action="store_true")

    recompute = subparsers.add_parser("recompute-weights", help="Recompute XY edge weights")
    recompute.add_argument("--graph", required=True)
    recompute.add_argument("--edge-id", nargs="*")
    recompute.add_argument("--output")
    recompute.add_argument("--allow-invalid", action="store_true")

    enable = subparsers.add_parser("enable-edge", help="Enable an edge")
    enable.add_argument("--graph", required=True)
    enable.add_argument("--edge-id", required=True)
    enable.add_argument("--output")
    enable.add_argument("--allow-invalid", action="store_true")

    disable = subparsers.add_parser("disable-edge", help="Disable an edge")
    disable.add_argument("--graph", required=True)
    disable.add_argument("--edge-id", required=True)
    disable.add_argument("--output")
    disable.add_argument("--allow-invalid", action="store_true")

    validate_cmd = subparsers.add_parser("validate", help="Validate graph structure")
    validate_cmd.add_argument("--graph", required=True)

    summary = subparsers.add_parser("summary", help="Print node/edge summary")
    summary.add_argument("--graph", required=True)
    return parser


def _save_and_report(
    editor: GraphEditor,
    output_path: str | Path,
    allow_invalid: bool,
    success_message: str | None = None,
) -> int:
    report = editor.validate()
    if not allow_invalid and not report.is_valid:
        raise GraphSchemaError(report.format_text())
    editor.save(output_path, allow_invalid=allow_invalid)
    if success_message:
        print(success_message)
    print(f"Saved graph to {Path(output_path).resolve()}")
    print(report.format_text())
    return 0 if report.is_valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        graph = load_graph(args.graph)
        report = validate_graph(graph)
        print(report.format_text())
        return 0 if report.is_valid else 1

    if args.command == "summary":
        graph = load_graph(args.graph)
        report = validate_graph(graph)
        enabled_edges = sum(1 for edge in graph.edges if edge.enabled)
        print(f"Graph: {graph.graph_name}")
        print(f"Environment: {graph.env_id}")
        print(f"Nodes: {len(graph.nodes)}")
        print(f"Edges: {len(graph.edges)} total / {enabled_edges} enabled")
        print(report.format_text())
        return 0 if report.is_valid else 1

    editor = GraphEditor.from_path(args.graph)
    output = args.output or args.graph
    allow_invalid = bool(getattr(args, "allow_invalid", False))

    try:
        if args.command == "add-edge":
            edge = editor.add_edge(
                args.from_node,
                args.to_node,
                edge_id=args.edge_id,
                weight=args.weight,
                enabled=not args.disabled,
                bidirectional=not args.one_way,
            )
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Added edge `{edge.id}`: {edge.from_node} -> {edge.to_node}",
            )

        if args.command == "remove-edge":
            edge = editor.remove_edge(args.edge_id)
            return _save_and_report(editor, output, allow_invalid, f"Removed edge `{edge.id}`")

        if args.command == "rename-node":
            editor.rename_node(args.node_id, args.name)
            return _save_and_report(editor, output, allow_invalid, f"Renamed node `{args.node_id}`")

        if args.command == "set-tags":
            editor.update_node_tags(args.node_id, args.tags)
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Updated tags for node `{args.node_id}`",
            )

        if args.command == "delete-node":
            editor.delete_node(args.node_id)
            return _save_and_report(
                editor,
                output,
                allow_invalid,
                f"Deleted node `{args.node_id}` and attached edges",
            )

        if args.command == "recompute-weights":
            editor.recompute_weights(args.edge_id)
            return _save_and_report(editor, output, allow_invalid, "Recomputed edge weights")

        if args.command == "enable-edge":
            editor.set_edge_enabled(args.edge_id, True)
            return _save_and_report(editor, output, allow_invalid, f"Enabled edge `{args.edge_id}`")

        if args.command == "disable-edge":
            editor.set_edge_enabled(args.edge_id, False)
            return _save_and_report(editor, output, allow_invalid, f"Disabled edge `{args.edge_id}`")
    except GraphSchemaError as exc:
        print(exc)
        return 1

    parser.error(f"Unhandled command: {args.command}")
    return 2


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
