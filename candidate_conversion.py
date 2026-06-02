from __future__ import annotations

if __package__ in {None, ""}:
    from graph_model import (
        GraphSchemaError,
        RouteCandidate,
        RouteCandidateSet,
        RouteEdgePass,
        RoutePlan,
        RouteSegment,
        clone_node_lookup,
    )
else:
    from .graph_model import (
        GraphSchemaError,
        RouteCandidate,
        RouteCandidateSet,
        RouteEdgePass,
        RoutePlan,
        RouteSegment,
        clone_node_lookup,
    )

def resolve_plan_edge_passes(plan: RoutePlan) -> list[RouteEdgePass]:
    if plan.edge_passes:
        return list(plan.edge_passes)

    edge_passes: list[RouteEdgePass] = []
    for segment_index, segment in enumerate(plan.segments):
        if segment.edge_passes:
            edge_passes.extend(segment.edge_passes)
            continue
        if len(segment.node_ids) != len(segment.edge_ids) + 1:
            raise GraphSchemaError(
                f"Segment `{segment.start_anchor}->{segment.end_anchor}` has inconsistent node_ids / edge_ids"
            )
        for local_index, edge_id in enumerate(segment.edge_ids, start=1):
            edge_passes.append(
                RouteEdgePass(
                    pass_index=len(edge_passes) + 1,
                    edge_id=edge_id,
                    from_node=segment.node_ids[local_index - 1],
                    to_node=segment.node_ids[local_index],
                    segment_index=segment_index,
                    local_index=local_index,
                )
            )
    return edge_passes


def _resolve_candidate_plan_anchor_nodes(
    candidate_set: RouteCandidateSet,
    candidate: RouteCandidate,
) -> list[str]:
    if candidate_set.anchor_nodes:
        return list(candidate_set.anchor_nodes)

    if candidate.segments:
        anchor_nodes = [str(candidate.segments[0].start_anchor)]
        anchor_nodes.extend(str(segment.end_anchor) for segment in candidate.segments)
        return anchor_nodes

    auto_start_node = str(candidate.meta.get("auto_start_node") or "").strip()
    auto_end_node = str(candidate.meta.get("auto_end_node") or "").strip()
    if auto_start_node and auto_end_node:
        if auto_start_node == auto_end_node:
            return [auto_start_node]
        return [auto_start_node, auto_end_node]

    if len(candidate.planned_nodes) == 1:
        return [str(candidate.planned_nodes[0])]

    return []


def candidate_to_plan(candidate_set: RouteCandidateSet, candidate_id: str | None = None) -> RoutePlan:
    if not candidate_set.candidates:
        raise GraphSchemaError("RouteCandidateSet contains no candidates")

    if candidate_id is None:
        selected_candidates = [candidate for candidate in candidate_set.candidates if candidate.selected]
        if len(selected_candidates) == 1:
            candidate = selected_candidates[0]
        elif selected_candidates:
            raise GraphSchemaError(
                "RouteCandidateSet has multiple selected candidates; specify `candidate_id` explicitly"
            )
        else:
            candidate = candidate_set.candidates[0]
    else:
        candidate = candidate_set.get_candidate(candidate_id)

    plan_meta = {
        **dict(candidate_set.meta),
        "graph_default_altitude": dict(candidate_set.meta).get("graph_default_altitude"),
        "candidate_id": candidate.candidate_id,
        "candidate_rank": int(candidate.rank),
        "selected": bool(candidate.selected),
        "candidate_meta": dict(candidate.meta),
    }

    return RoutePlan(
        env_id=candidate_set.env_id,
        graph_name=candidate_set.graph_name,
        anchor_nodes=_resolve_candidate_plan_anchor_nodes(candidate_set, candidate),
        planned_nodes=list(candidate.planned_nodes),
        segments=[RouteSegment.from_mapping(segment.to_dict()) for segment in candidate.segments],
        edge_passes=[RouteEdgePass.from_mapping(edge_pass.to_dict()) for edge_pass in candidate.edge_passes],
        total_length=float(candidate.total_length),
        node_lookup=clone_node_lookup(candidate_set.node_lookup),
        meta=plan_meta,
    )

__all__ = [
    "candidate_to_plan",
    "resolve_plan_edge_passes",
]
