import type { GraphEdge, GraphNode, RouteGraph } from '../types/route-graph'

export const UAV_EXTENSION_NAMESPACE = 'uav'
export const WEBUI_EXTENSION_NAMESPACE = 'route_graph_webui'

export function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

export function graphWebuiExtension(graph: RouteGraph | null | undefined): Record<string, unknown> {
  return objectRecord(objectRecord(graph?.extensions)[WEBUI_EXTENSION_NAMESPACE])
}

export function nodeUavExtension(node: GraphNode | null | undefined): Record<string, unknown> {
  return objectRecord(objectRecord(node?.extensions)[UAV_EXTENSION_NAMESPACE])
}

export function edgeWebuiExtension(edge: GraphEdge | null | undefined): Record<string, unknown> {
  return objectRecord(objectRecord(edge?.extensions)[WEBUI_EXTENSION_NAMESPACE])
}

export function nodeLabel(node: GraphNode): string {
  return node.label || node.id
}

export function nodeYawHint(node: GraphNode | null | undefined): number | null {
  const rawValue = nodeUavExtension(node).yaw_hint_deg
  return typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null
}

export function nodeSampleRadius(node: GraphNode | null | undefined): number | null {
  const rawValue = nodeUavExtension(node).sample_radius
  return typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null
}

export function edgeMetrics(edge: GraphEdge | null | undefined): Record<string, number> {
  return objectRecord(edge?.metrics) as Record<string, number>
}

export function edgeCost(edge: GraphEdge | null | undefined): number | null {
  const metrics = edgeMetrics(edge)
  const cost = metrics.cost
  if (typeof cost === 'number' && Number.isFinite(cost)) {
    return cost
  }
  const length = metrics.length
  return typeof length === 'number' && Number.isFinite(length) ? length : null
}

export function edgeBidirectional(edge: GraphEdge): boolean {
  return !edge.directed
}
