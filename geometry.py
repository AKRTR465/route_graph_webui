from __future__ import annotations

import math
from typing import Iterable


EPSILON = 1e-9


def normalize_angle_deg(angle: float) -> float:
    normalized = ((float(angle) + 180.0) % 360.0) - 180.0
    if normalized == -180.0:
        return 180.0
    return normalized


def distance_3d(a: Iterable[float], b: Iterable[float]) -> float:
    ax, ay, az = [float(value) for value in a]
    bx, by, bz = [float(value) for value in b]
    return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)


def interpolate_segment_3d(
    start_xyz: list[float],
    end_xyz: list[float],
    step_distance: float,
) -> list[list[float]]:
    dx = end_xyz[0] - start_xyz[0]
    dy = end_xyz[1] - start_xyz[1]
    dz = end_xyz[2] - start_xyz[2]
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    step_distance = float(step_distance)
    if step_distance <= 0:
        raise ValueError("`step_distance` must be positive")
    steps = max(1, int(math.ceil(distance / step_distance)))
    points = []
    for index in range(1, steps + 1):
        ratio = index / steps
        points.append(
            [
                start_xyz[0] + dx * ratio,
                start_xyz[1] + dy * ratio,
                start_xyz[2] + dz * ratio,
            ]
        )
    return points


def project_point_to_segment_2d(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> tuple[float, tuple[float, float]]:
    px, py = point
    ax, ay = segment_start
    bx, by = segment_end
    dx = bx - ax
    dy = by - ay
    segment_length_sq = (dx * dx) + (dy * dy)
    if segment_length_sq <= EPSILON:
        return 0.0, (ax, ay)
    projection_ratio = ((px - ax) * dx + (py - ay) * dy) / segment_length_sq
    projection_ratio = max(0.0, min(1.0, projection_ratio))
    closest_x = ax + (projection_ratio * dx)
    closest_y = ay + (projection_ratio * dy)
    return projection_ratio, (closest_x, closest_y)


def distance_point_to_segment_2d(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
) -> float:
    _, closest_point = project_point_to_segment_2d(point, segment_start, segment_end)
    return math.hypot(point[0] - closest_point[0], point[1] - closest_point[1])


def _orientation(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> float:
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)


def _on_segment(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> bool:
    return (
        min(ax, bx) - EPSILON <= cx <= max(ax, bx) + EPSILON
        and min(ay, by) - EPSILON <= cy <= max(ay, by) + EPSILON
    )


def segments_intersect_2d(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    ax1, ay1 = a1
    ax2, ay2 = a2
    bx1, by1 = b1
    bx2, by2 = b2

    o1 = _orientation(ax1, ay1, ax2, ay2, bx1, by1)
    o2 = _orientation(ax1, ay1, ax2, ay2, bx2, by2)
    o3 = _orientation(bx1, by1, bx2, by2, ax1, ay1)
    o4 = _orientation(bx1, by1, bx2, by2, ax2, ay2)

    if (o1 > 0 > o2 or o1 < 0 < o2) and (o3 > 0 > o4 or o3 < 0 < o4):
        return True
    if abs(o1) <= EPSILON and _on_segment(ax1, ay1, ax2, ay2, bx1, by1):
        return True
    if abs(o2) <= EPSILON and _on_segment(ax1, ay1, ax2, ay2, bx2, by2):
        return True
    if abs(o3) <= EPSILON and _on_segment(bx1, by1, bx2, by2, ax1, ay1):
        return True
    if abs(o4) <= EPSILON and _on_segment(bx1, by1, bx2, by2, ax2, ay2):
        return True
    return False


__all__ = [
    "EPSILON",
    "distance_3d",
    "distance_point_to_segment_2d",
    "interpolate_segment_3d",
    "normalize_angle_deg",
    "project_point_to_segment_2d",
    "segments_intersect_2d",
]
