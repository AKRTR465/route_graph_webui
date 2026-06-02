export interface EdgeCreationGroupingState {
  nodeGroupLookup: Map<string, string>
  conflictingNodeIds: Set<string>
}

export interface EdgeCreationKinds {
  group: string
  bridge: string
}

export interface EdgeCreationIntent {
  edge_kind: string
  group_color: string | null
}

export function resolveEdgeCreationIntent(
  fromNodeId: string,
  toNodeId: string,
  grouping: EdgeCreationGroupingState,
  fallbackGroupColor: string | null,
  edgeKinds: EdgeCreationKinds,
): EdgeCreationIntent {
  if (
    grouping.conflictingNodeIds.has(fromNodeId) ||
    grouping.conflictingNodeIds.has(toNodeId)
  ) {
    throw new Error('存在归属多个颜色组的节点，请先调整相关边为桥接边。')
  }

  const groupA = grouping.nodeGroupLookup.get(fromNodeId) ?? null
  const groupB = grouping.nodeGroupLookup.get(toNodeId) ?? null
  if (groupA && groupB) {
    if (groupA === groupB) {
      return { edge_kind: edgeKinds.group, group_color: groupA }
    }
    return { edge_kind: edgeKinds.bridge, group_color: null }
  }
  if (groupA || groupB) {
    return { edge_kind: edgeKinds.group, group_color: groupA ?? groupB }
  }
  if (!fallbackGroupColor) {
    throw new Error('两个节点都尚未归组，请先从调色盘选择一个颜色。')
  }
  return { edge_kind: edgeKinds.group, group_color: fallbackGroupColor }
}
