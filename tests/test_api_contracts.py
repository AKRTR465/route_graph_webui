from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from route_graph_webui.backend import server as server_module
from route_graph_webui.planning.auto_route_planner import AutoPlanningConfig



class ApiContractTests(unittest.TestCase):
    def test_plan_request_rejects_extra_fields(self) -> None:
        client = TestClient(server_module.app)
        response = client.post(
            "/api/plan",
            json={
                "start_node": "A",
                "end_node": "B",
                "unexpected": True,
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_plan_request_rejects_out_of_range_values(self) -> None:
        client = TestClient(server_module.app)
        response = client.post(
            "/api/plan",
            json={
                "start_node": "A",
                "end_node": "B",
                "max_routes": 0,
            },
        )

        self.assertEqual(response.status_code, 422, response.text)

    def test_auto_planning_boolean_parser_handles_false_string(self) -> None:
        config = AutoPlanningConfig.from_mapping(
            {
                "prefer_connected_anchors": "false",
                "prefer_route_diversity": "0",
                "allow_reverse_direction_counterparts": "off",
            }
        )

        self.assertFalse(config.prefer_connected_anchors)
        self.assertFalse(config.prefer_route_diversity)
        self.assertFalse(config.allow_reverse_direction_counterparts)
