from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from route_graph_webui.storage import graph_store
from route_graph_webui.storage import json_store as _json_store

append_jsonl = _json_store.append_jsonl
consume_jsonl_text = _json_store.consume_jsonl_text
read_json = _json_store.read_json
write_json_atomic = _json_store.write_json_atomic


class StoragePathJsonTests(unittest.TestCase):
    def test_resolve_data_dir_uses_new_environment_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.dict(
                os.environ,
                {graph_store.ROUTE_GRAPH_WEBUI_DATA_DIR_ENV: temp_dir},
                clear=False,
            ):
                self.assertEqual(graph_store.resolve_data_dir(), Path(temp_dir).resolve())

    def test_legacy_route_garph_env_is_read_only_compat_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_root = Path(temp_dir) / "legacy"
            with mock.patch.dict(
                os.environ,
                {
                    graph_store.LEGACY_ROUTE_GARPH_DIR_ENV: str(legacy_root),
                    graph_store.ROUTE_GRAPH_WEBUI_DATA_DIR_ENV: "",
                },
                clear=False,
            ):
                with self.assertWarns(DeprecationWarning):
                    roots = graph_store.legacy_data_roots()

            self.assertIn((legacy_root / "data").resolve(), roots)

    def test_resolve_within_root_blocks_traversal_and_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "graphs"
            root.mkdir()
            with self.assertRaises(ValueError):
                graph_store.resolve_within_root(root, "../escape.json")

            outside = Path(temp_dir) / "outside.json"
            with self.assertRaises(ValueError):
                graph_store.resolve_within_root(root, outside)

            resolved = graph_store.resolve_within_root(root, "nested/example")
            self.assertEqual(resolved, (root / "nested" / "example.json").resolve())

    def test_json_atomic_write_leaves_existing_file_when_encoding_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            write_json_atomic(path, {"status": "old"})

            with self.assertRaises(TypeError):
                write_json_atomic(path, {"bad": object()})

            self.assertEqual(read_json(path), {"status": "old"})
            self.assertEqual(list(Path(temp_dir).glob("*.tmp")), [])

    def test_jsonl_messages_are_utf8_line_delimited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "progress.jsonl"
            append_jsonl(path, {"type": "progress", "message": "ready"})
            append_jsonl(path, {"type": "progress", "value": 2})

            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                self.assertIsInstance(json.loads(line), dict)

            messages, remainder = consume_jsonl_text("", text)
            self.assertEqual(remainder, "")
            self.assertEqual(messages[0]["message"], "ready")
            self.assertEqual(messages[1]["value"], 2)

    def test_sample_graphs_are_copied_into_empty_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            graph_store.copy_sample_graphs_if_needed(temp_dir)
            copied_graphs = sorted((Path(temp_dir) / "graphs").glob("*.json"))
            self.assertTrue(copied_graphs)
            self.assertTrue(any(path.name == "DowntownWest.json" for path in copied_graphs))
