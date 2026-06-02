from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from graph_schema import RouteCandidateSet, candidate_to_plan
from mission_export import MissionExportOptions, export_candidate_set_missions, export_mission


def mission_export_options(
    request: MissionExportOptions | Mapping[str, Any] | None,
) -> MissionExportOptions:
    if isinstance(request, MissionExportOptions):
        return request
    return MissionExportOptions.from_mapping(request)


def mission_export_kwargs(
    request: MissionExportOptions | Mapping[str, Any] | None,
) -> dict[str, Any]:
    return mission_export_options(request).to_mission_kwargs()


def build_mission_preview(
    candidate_set: RouteCandidateSet,
    *,
    candidate_id: str,
    export_config: MissionExportOptions | Mapping[str, Any] | None,
) -> dict[str, Any]:
    plan = candidate_to_plan(candidate_set, candidate_id)
    return export_mission(
        plan,
        output_path=None,
        **mission_export_kwargs(export_config),
    )


def export_candidate_missions(
    candidate_set: RouteCandidateSet,
    output_dir: Path,
    *,
    candidate_ids: list[str] | None,
    export_config: MissionExportOptions | Mapping[str, Any] | None,
) -> dict[str, Any]:
    return export_candidate_set_missions(
        candidate_set,
        output_dir,
        candidate_ids=candidate_ids,
        **mission_export_kwargs(export_config),
    )


__all__ = [
    "build_mission_preview",
    "export_candidate_missions",
    "mission_export_kwargs",
    "mission_export_options",
]
