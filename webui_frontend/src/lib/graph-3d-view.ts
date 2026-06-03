import type { GraphEdge, GraphNode, Position3, RouteCandidateSet, RouteGraph } from '../types/route-graph'

export type CanvasDisplayMode = '2d' | '3d'
export type Graph3DZLayerMode = 'recorded' | 'groupNormalized'

const DEFAULT_GROUP_COLOR = '#334155'
const EDGE_GROUP_COLOR_META_KEY = 'group_color'
const EDGE_KIND_BRIDGE = 'bridge'
const EDGE_KIND_META_KEY = 'edge_kind'

export type CanvasViewStateLike = {
  rotationQuadrants: number
  flipHorizontal: boolean
  flipVertical: boolean
}

export type Graph3DSceneMetrics = {
  centerX: number
  centerY: number
  baseZ: number
  sceneScale: number
}

export type ScenePoint3 = {
  x: number
  y: number
  z: number
}

export type Graph3DGrouping = {
  nodeGroupLookup: Map<string, string>
  groupAverageZLookup: Map<string, number>
  groupColors: string[]
}

function average(values: number[]) {
  if (!values.length) {
    return 0
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function normalizeHexColor(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const text = value.trim()
  if (!/^#?[0-9a-f]{6}$/i.test(text)) {
    return null
  }
  return (text.startsWith('#') ? text : `#${text}`).toUpperCase()
}

function edgeKind(edge: GraphEdge) {
  return edge.meta?.[EDGE_KIND_META_KEY] === EDGE_KIND_BRIDGE ? EDGE_KIND_BRIDGE : 'group'
}

function edgeGroupColor(edge: GraphEdge) {
  if (edgeKind(edge) === EDGE_KIND_BRIDGE) {
    return null
  }
  return normalizeHexColor(edge.meta?.[EDGE_GROUP_COLOR_META_KEY]) ?? DEFAULT_GROUP_COLOR
}

function readCandidateNodeGroupLookup(candidateSet: RouteCandidateSet | null) {
  const lookup = new Map<string, string>()
  const rawLookup = candidateSet?.meta?.node_group_lookup_v1
  if (!rawLookup || typeof rawLookup !== 'object' || Array.isArray(rawLookup)) {
    return lookup
  }
  for (const [nodeId, rawColor] of Object.entries(rawLookup)) {
    const color = normalizeHexColor(rawColor)
    if (color) {
      lookup.set(nodeId, color)
    }
  }
  return lookup
}

function readCandidateGroupAverageZLookup(candidateSet: RouteCandidateSet | null) {
  const lookup = new Map<string, number>()
  const rawLookup = candidateSet?.meta?.group_average_z_lookup_v1
  if (!rawLookup || typeof rawLookup !== 'object' || Array.isArray(rawLookup)) {
    return lookup
  }
  for (const [rawColor, rawValue] of Object.entries(rawLookup)) {
    const color = normalizeHexColor(rawColor)
    const z = Number(rawValue)
    if (color && Number.isFinite(z)) {
      lookup.set(color, z)
    }
  }
  return lookup
}

function completeGroupAverageZLookup(
  graph: RouteGraph | null,
  nodeGroupLookup: ReadonlyMap<string, string>,
  providedAverageZLookup: ReadonlyMap<string, number>,
) {
  const averageZLookup = new Map(providedAverageZLookup)
  const groupedZValues = new Map<string, number[]>()
  for (const node of graph?.nodes ?? []) {
    const groupColor = nodeGroupLookup.get(node.id)
    if (!groupColor || averageZLookup.has(groupColor)) {
      continue
    }
    const values = groupedZValues.get(groupColor) ?? []
    values.push(Number(node.position[2]) || 0)
    groupedZValues.set(groupColor, values)
  }
  for (const [groupColor, values] of groupedZValues) {
    if (values.length) {
      averageZLookup.set(groupColor, average(values))
    }
  }
  return averageZLookup
}

function deriveGraphGrouping(graph: RouteGraph | null): Graph3DGrouping {
  const nodeGroupCandidates = new Map<string, Set<string>>()
  const nodeGroupLookup = new Map<string, string>()
  const groupAverageZLookup = new Map<string, number>()
  const groupZValues = new Map<string, number[]>()

  for (const node of graph?.nodes ?? []) {
    nodeGroupCandidates.set(node.id, new Set())
  }

  for (const edge of graph?.edges ?? []) {
    const color = edgeGroupColor(edge)
    if (!color) {
      continue
    }
    nodeGroupCandidates.get(edge.from)?.add(color)
    nodeGroupCandidates.get(edge.to)?.add(color)
  }

  for (const node of graph?.nodes ?? []) {
    const candidates = nodeGroupCandidates.get(node.id)
    if (!candidates || candidates.size !== 1) {
      continue
    }
    const color = [...candidates][0]
    if (!color) {
      continue
    }
    nodeGroupLookup.set(node.id, color)
    const zValues = groupZValues.get(color) ?? []
    zValues.push(Number(node.position[2]) || 0)
    groupZValues.set(color, zValues)
  }

  for (const [color, zValues] of groupZValues) {
    groupAverageZLookup.set(color, average(zValues))
  }

  return {
    nodeGroupLookup,
    groupAverageZLookup,
    groupColors: [...groupAverageZLookup.keys()].sort(),
  }
}

export function resolveGraph3DGrouping(
  graph: RouteGraph | null,
  candidateSet: RouteCandidateSet | null,
): Graph3DGrouping {
  const candidateNodeGroupLookup = readCandidateNodeGroupLookup(candidateSet)
  if (candidateNodeGroupLookup.size) {
    const groupAverageZLookup = completeGroupAverageZLookup(
      graph,
      candidateNodeGroupLookup,
      readCandidateGroupAverageZLookup(candidateSet),
    )
    return {
      nodeGroupLookup: candidateNodeGroupLookup,
      groupAverageZLookup,
      groupColors: [...new Set([...candidateNodeGroupLookup.values(), ...groupAverageZLookup.keys()])].sort(),
    }
  }

  return deriveGraphGrouping(graph)
}

export function computeGraph3DSceneMetrics(
  graph: RouteGraph | null,
  nodePositions: ReadonlyMap<string, Position3>,
): Graph3DSceneMetrics {
  const nodes = graph?.nodes ?? []
  if (!nodes.length) {
    return {
      centerX: 0,
      centerY: 0,
      baseZ: 0,
      sceneScale: 1,
    }
  }

  const xs = nodes.map((node) => Number(node.position[0]) || 0)
  const ys = nodes.map((node) => Number(node.position[1]) || 0)
  const zs = nodes.map((node) => Number(nodePositions.get(node.id)?.[2] ?? node.position[2]) || 0)
  const spanX = Math.max(...xs) - Math.min(...xs)
  const spanY = Math.max(...ys) - Math.min(...ys)

  return {
    centerX: (Math.min(...xs) + Math.max(...xs)) / 2,
    centerY: (Math.min(...ys) + Math.max(...ys)) / 2,
    baseZ: average(zs),
    sceneScale: 120 / Math.max(spanX, spanY, 1),
  }
}

export function resolveGraph3DNodePositions(
  graph: RouteGraph | null,
  candidateSet: RouteCandidateSet | null,
  zLayerMode: Graph3DZLayerMode,
): Map<string, Position3> {
  const positions = new Map<string, Position3>()
  const nodes = graph?.nodes ?? []
  if (!nodes.length) {
    return positions
  }

  const grouping = zLayerMode === 'groupNormalized' ? resolveGraph3DGrouping(graph, candidateSet) : null
  for (const node of nodes) {
    if (zLayerMode === 'groupNormalized') {
      const groupColor = grouping?.nodeGroupLookup.get(node.id)
      const groupAverageZ = groupColor ? grouping?.groupAverageZLookup.get(groupColor) : null
      positions.set(node.id, [
        Number(node.position[0]) || 0,
        Number(node.position[1]) || 0,
        Number(groupAverageZ ?? node.position[2]) || 0,
      ])
      continue
    }

    positions.set(node.id, [
      Number(node.position[0]) || 0,
      Number(node.position[1]) || 0,
      Number(node.position[2]) || 0,
    ])
  }
  return positions
}

export function applyCanvasViewToGraphXY(
  position: Pick<GraphNode, 'position'> | Position3,
  metrics: Pick<Graph3DSceneMetrics, 'centerX' | 'centerY'>,
  canvasViewState: CanvasViewStateLike,
): { x: number; y: number } {
  const rawPosition = Array.isArray(position) ? position : position.position
  let dx = (Number(rawPosition[0]) || 0) - metrics.centerX
  let dy = (Number(rawPosition[1]) || 0) - metrics.centerY
  const normalizedRotation = ((Math.round(canvasViewState.rotationQuadrants) % 4) + 4) % 4

  if (normalizedRotation === 1) {
    ;[dx, dy] = [-dy, dx]
  } else if (normalizedRotation === 2) {
    ;[dx, dy] = [-dx, -dy]
  } else if (normalizedRotation === 3) {
    ;[dx, dy] = [dy, -dx]
  }

  if (canvasViewState.flipHorizontal) {
    dx = -dx
  }
  if (canvasViewState.flipVertical) {
    dy = -dy
  }

  return { x: dx, y: dy }
}

export function projectGraphPositionToScene(
  position: Position3,
  metrics: Graph3DSceneMetrics,
  canvasViewState: CanvasViewStateLike,
  zExaggeration: number,
): ScenePoint3 {
  const transformed = applyCanvasViewToGraphXY(position, metrics, canvasViewState)
  return {
    x: transformed.x * metrics.sceneScale,
    y: ((Number(position[2]) || 0) - metrics.baseZ) * metrics.sceneScale * zExaggeration,
    z: -transformed.y * metrics.sceneScale,
  }
}
