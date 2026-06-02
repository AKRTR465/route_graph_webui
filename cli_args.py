from __future__ import annotations

import argparse
from typing import Any


def add_graph_argument(
    parser: argparse.ArgumentParser | argparse._ArgumentGroup,
    *,
    required: bool = True,
    help: str = "Path to graph JSON",
    **kwargs: Any,
) -> argparse.Action:
    return parser.add_argument("--graph", required=required, help=help, **kwargs)


def add_output_argument(
    parser: argparse.ArgumentParser | argparse._ArgumentGroup,
    *,
    required: bool = False,
    help: str = "Output path",
    **kwargs: Any,
) -> argparse.Action:
    return parser.add_argument("--output", required=required, help=help, **kwargs)


def add_mission_turn_smoothing_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_turn_smoothing_enabled: bool,
    default_corner_radius: float,
    default_small_turn_yaw_blend_threshold_deg: float,
    default_corner_min_angle_deg: float,
    default_u_turn_threshold_deg: float,
    default_u_turn_transition_distance: float,
    default_corner_max_yaw_step_deg: float,
    default_u_turn_pivot_yaw_step_deg: float,
) -> None:
    parser.add_argument(
        "--no-turn-smoothing",
        dest="turn_smoothing_enabled",
        action="store_false",
        help="Disable local corner smoothing and export the original polyline geometry",
    )
    parser.set_defaults(turn_smoothing_enabled=default_turn_smoothing_enabled)
    parser.add_argument("--corner-radius", type=float, default=default_corner_radius)
    parser.add_argument(
        "--small-turn-yaw-blend-threshold-deg",
        type=float,
        default=default_small_turn_yaw_blend_threshold_deg,
    )
    parser.add_argument("--corner-min-angle-deg", type=float, default=default_corner_min_angle_deg)
    parser.add_argument("--u-turn-threshold-deg", type=float, default=default_u_turn_threshold_deg)
    parser.add_argument("--u-turn-transition-distance", type=float, default=default_u_turn_transition_distance)
    parser.add_argument("--corner-max-yaw-step-deg", type=float, default=default_corner_max_yaw_step_deg)
    parser.add_argument("--u-turn-pivot-yaw-step-deg", type=float, default=default_u_turn_pivot_yaw_step_deg)


__all__ = [
    "add_graph_argument",
    "add_mission_turn_smoothing_arguments",
    "add_output_argument",
]
