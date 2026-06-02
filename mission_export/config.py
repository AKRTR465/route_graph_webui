from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from graph_schema import GraphSchemaError

DEFAULT_TURN_SMOOTHING_ENABLED = True
DEFAULT_CORNER_RADIUS = 900.0
DEFAULT_CORNER_MIN_ANGLE_DEG = 20.0
DEFAULT_U_TURN_THRESHOLD_DEG = 150.0
DEFAULT_U_TURN_TRANSITION_DISTANCE = 240.0
DEFAULT_CORNER_MAX_YAW_STEP_DEG = 2.0
DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG = 2.5
DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG = 15.0


def parse_bool_config(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise GraphSchemaError(f"`{field_name}` must be a boolean value")


def _optional_float(value: Any, *, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise GraphSchemaError(f"`{field_name}` must be numeric or empty") from exc


def _optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise GraphSchemaError(f"`{field_name}` must be an integer or empty") from exc


def _float_value(source: Mapping[str, Any], field_name: str, default: float) -> float:
    try:
        return float(source.get(field_name, default))
    except (TypeError, ValueError) as exc:
        raise GraphSchemaError(f"`{field_name}` must be numeric") from exc


@dataclass(frozen=True, slots=True)
class MissionExportOptions:
    step_distance: float = 60.0
    fps: float = 4.0
    altitude_mode: str = "fixed"
    fixed_z: float | None = None
    altitude_offset: float = 0.0
    takeoff_landing_relative_z: float | None = None
    takeoff_landing_step_distance: float | None = None
    node_sample_radius: float = 0.0
    random_seed: int | None = None
    turn_smoothing_enabled: bool = DEFAULT_TURN_SMOOTHING_ENABLED
    corner_radius: float = DEFAULT_CORNER_RADIUS
    small_turn_yaw_blend_threshold_deg: float = DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG
    corner_min_angle_deg: float = DEFAULT_CORNER_MIN_ANGLE_DEG
    u_turn_threshold_deg: float = DEFAULT_U_TURN_THRESHOLD_DEG
    u_turn_transition_distance: float = DEFAULT_U_TURN_TRANSITION_DISTANCE
    corner_max_yaw_step_deg: float = DEFAULT_CORNER_MAX_YAW_STEP_DEG
    u_turn_pivot_yaw_step_deg: float = DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None = None) -> "MissionExportOptions":
        source = dict(raw or {})
        altitude_mode = str(source.get("altitude_mode", "fixed")).strip() or "fixed"
        if altitude_mode not in {"fixed", "follow_nodes"}:
            raise GraphSchemaError("`altitude_mode` must be either `fixed` or `follow_nodes`")

        options = cls(
            step_distance=_float_value(source, "step_distance", 60.0),
            fps=_float_value(source, "fps", 4.0),
            altitude_mode=altitude_mode,
            fixed_z=_optional_float(source.get("fixed_z"), field_name="fixed_z"),
            altitude_offset=_float_value(source, "altitude_offset", 0.0),
            takeoff_landing_relative_z=_optional_float(
                source.get("takeoff_landing_relative_z"),
                field_name="takeoff_landing_relative_z",
            ),
            takeoff_landing_step_distance=_optional_float(
                source.get("takeoff_landing_step_distance"),
                field_name="takeoff_landing_step_distance",
            ),
            node_sample_radius=_float_value(source, "node_sample_radius", 0.0),
            random_seed=_optional_int(source.get("random_seed"), field_name="random_seed"),
            turn_smoothing_enabled=parse_bool_config(
                source.get("turn_smoothing_enabled", DEFAULT_TURN_SMOOTHING_ENABLED),
                field_name="turn_smoothing_enabled",
            ),
            corner_radius=_float_value(source, "corner_radius", DEFAULT_CORNER_RADIUS),
            small_turn_yaw_blend_threshold_deg=_float_value(
                source,
                "small_turn_yaw_blend_threshold_deg",
                DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG,
            ),
            corner_min_angle_deg=_float_value(
                source,
                "corner_min_angle_deg",
                DEFAULT_CORNER_MIN_ANGLE_DEG,
            ),
            u_turn_threshold_deg=_float_value(
                source,
                "u_turn_threshold_deg",
                DEFAULT_U_TURN_THRESHOLD_DEG,
            ),
            u_turn_transition_distance=_float_value(
                source,
                "u_turn_transition_distance",
                DEFAULT_U_TURN_TRANSITION_DISTANCE,
            ),
            corner_max_yaw_step_deg=_float_value(
                source,
                "corner_max_yaw_step_deg",
                DEFAULT_CORNER_MAX_YAW_STEP_DEG,
            ),
            u_turn_pivot_yaw_step_deg=_float_value(
                source,
                "u_turn_pivot_yaw_step_deg",
                DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG,
            ),
        )
        options.validate()
        return options

    def validate(self) -> None:
        if self.step_distance <= 0:
            raise GraphSchemaError("`step_distance` must be positive")
        if self.fps <= 0:
            raise GraphSchemaError("`fps` must be positive")
        if self.node_sample_radius < 0:
            raise GraphSchemaError("`node_sample_radius` must be non-negative")
        if self.takeoff_landing_relative_z is not None and self.takeoff_landing_relative_z < 0:
            raise GraphSchemaError("`takeoff_landing_relative_z` must be non-negative")
        if self.takeoff_landing_step_distance is not None and self.takeoff_landing_step_distance <= 0:
            raise GraphSchemaError("`takeoff_landing_step_distance` must be positive")
        if self.small_turn_yaw_blend_threshold_deg < 0:
            raise GraphSchemaError("`small_turn_yaw_blend_threshold_deg` must be non-negative")
        _validate_turn_smoothing_parameters(
            corner_radius=float(self.corner_radius),
            corner_min_angle_deg=float(self.corner_min_angle_deg),
            u_turn_threshold_deg=float(self.u_turn_threshold_deg),
            u_turn_transition_distance=float(self.u_turn_transition_distance),
            corner_max_yaw_step_deg=float(self.corner_max_yaw_step_deg),
            u_turn_pivot_yaw_step_deg=float(self.u_turn_pivot_yaw_step_deg),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "step_distance": float(self.step_distance),
            "fps": float(self.fps),
            "altitude_mode": self.altitude_mode,
            "fixed_z": None if self.fixed_z is None else float(self.fixed_z),
            "altitude_offset": float(self.altitude_offset),
            "takeoff_landing_relative_z": (
                None
                if self.takeoff_landing_relative_z is None
                else float(self.takeoff_landing_relative_z)
            ),
            "takeoff_landing_step_distance": (
                None
                if self.takeoff_landing_step_distance is None
                else float(self.takeoff_landing_step_distance)
            ),
            "node_sample_radius": float(self.node_sample_radius),
            "random_seed": None if self.random_seed is None else int(self.random_seed),
            "turn_smoothing_enabled": bool(self.turn_smoothing_enabled),
            "corner_radius": float(self.corner_radius),
            "small_turn_yaw_blend_threshold_deg": float(self.small_turn_yaw_blend_threshold_deg),
            "corner_min_angle_deg": float(self.corner_min_angle_deg),
            "u_turn_threshold_deg": float(self.u_turn_threshold_deg),
            "u_turn_transition_distance": float(self.u_turn_transition_distance),
            "corner_max_yaw_step_deg": float(self.corner_max_yaw_step_deg),
            "u_turn_pivot_yaw_step_deg": float(self.u_turn_pivot_yaw_step_deg),
        }

    def to_mission_kwargs(self) -> dict[str, Any]:
        return dict(self.to_mapping())

def _validate_turn_smoothing_parameters(
    *,
    corner_radius: float,
    corner_min_angle_deg: float,
    u_turn_threshold_deg: float,
    u_turn_transition_distance: float,
    corner_max_yaw_step_deg: float,
    u_turn_pivot_yaw_step_deg: float,
) -> None:
    if corner_radius <= 0:
        raise GraphSchemaError("`corner_radius` must be positive")
    if corner_min_angle_deg < 0 or corner_min_angle_deg >= 180:
        raise GraphSchemaError("`corner_min_angle_deg` must be in [0, 180)")
    if u_turn_threshold_deg <= corner_min_angle_deg or u_turn_threshold_deg > 180:
        raise GraphSchemaError(
            "`u_turn_threshold_deg` must be greater than `corner_min_angle_deg` and at most 180"
        )
    if u_turn_transition_distance <= 0:
        raise GraphSchemaError("`u_turn_transition_distance` must be positive")
    if corner_max_yaw_step_deg <= 0:
        raise GraphSchemaError("`corner_max_yaw_step_deg` must be positive")
    if u_turn_pivot_yaw_step_deg <= 0:
        raise GraphSchemaError("`u_turn_pivot_yaw_step_deg` must be positive")
__all__ = [
    "DEFAULT_CORNER_MAX_YAW_STEP_DEG",
    "DEFAULT_CORNER_MIN_ANGLE_DEG",
    "DEFAULT_CORNER_RADIUS",
    "DEFAULT_SMALL_TURN_YAW_BLEND_THRESHOLD_DEG",
    "DEFAULT_TURN_SMOOTHING_ENABLED",
    "DEFAULT_U_TURN_PIVOT_YAW_STEP_DEG",
    "DEFAULT_U_TURN_THRESHOLD_DEG",
    "DEFAULT_U_TURN_TRANSITION_DISTANCE",
    "MissionExportOptions",
    "parse_bool_config",
    "_float_value",
    "_optional_float",
    "_optional_int",
    "_validate_turn_smoothing_parameters",
]
