import test from 'node:test'
import assert from 'node:assert/strict'

import {
  resolveCandidateKeepTargetIds,
  resolveCandidateRangeSelection,
  sortCandidateIdsByDisplayOrder,
} from '../src/lib/candidate-selection.ts'
import {
  clearStoredAutoPlanJobId,
  getStoredAutoPlanJobId,
  readStoredAutoPlanJobs,
  setStoredAutoPlanJobId,
} from '../src/lib/auto-plan-storage.ts'
import {
  buildMissionConfigRequestPayload,
  buildMissionGeometryInputsSnapshot,
  type ExportFormLike,
} from '../src/lib/mission-config.ts'
import { buildPreviewPathSegments, computeChevronGlyph } from '../src/lib/preview-path.ts'
import { transformGraphPoint } from '../src/lib/graph-view.ts'
import {
  applyCanvasViewToGraphXY,
  computeGraph3DSceneMetrics,
  projectGraphPositionToScene,
  resolveGraph3DGrouping,
  resolveGraph3DNodePositions,
  type CanvasViewStateLike,
} from '../src/lib/graph-3d-view.ts'
import { EDGE_GROUP_COLOR_META_KEY, EDGE_KIND_GROUP, EDGE_KIND_META_KEY } from '../src/types/graph-meta.ts'
import type { RouteCandidateSet, RouteGraph } from '../src/types/route-graph.ts'

function createMemoryStorage() {
  const values = new Map<string, string>()
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value)
    },
    removeItem: (key: string) => {
      values.delete(key)
    },
  }
}

const smoothingDefaults = {
  cornerRadius: '900',
  smallTurnYawBlendThresholdDeg: '15',
  cornerMinAngleDeg: '20',
  uTurnThresholdDeg: '150',
  uTurnTransitionDistance: '240',
  cornerMaxYawStepDeg: '2',
  uTurnPivotYawStepDeg: '2.5',
}

function createExportForm(overrides: Partial<ExportFormLike> = {}): ExportFormLike {
  return {
    stepDistance: '60',
    fps: '4',
    altitudeMode: 'fixed',
    fixedZ: '120',
    altitudeOffset: '0',
    takeoffLandingRelativeZ: '',
    takeoffLandingStepDistance: '',
    nodeSampleRadius: '0',
    randomSeed: '',
    turnSmoothingEnabled: true,
    cornerRadius: '450',
    smallTurnYawBlendThresholdDeg: '12',
    cornerMinAngleDeg: '10',
    uTurnThresholdDeg: '140',
    uTurnTransitionDistance: '180',
    cornerMaxYawStepDeg: '3',
    uTurnPivotYawStepDeg: '2.5',
    ...overrides,
  }
}

test('candidate selection sorts de-duplicates and builds ranges', () => {
  const lookup = new Map([
    ['C001', 0],
    ['C002', 1],
    ['C003', 2],
  ])

  assert.deepEqual(sortCandidateIdsByDisplayOrder(['C003', 'missing', 'C001', 'C003'], lookup), [
    'C001',
    'C003',
  ])
  assert.deepEqual(
    resolveCandidateRangeSelection(['C001', 'C002', 'C003'], lookup, 'C003', 'C001'),
    { ids: ['C001', 'C002', 'C003'], anchorId: 'C001' },
  )
  assert.deepEqual(resolveCandidateKeepTargetIds('C002', ['C001', 'C002'], new Set(['C001', 'C002']), null), [
    'C001',
    'C002',
  ])
})

test('auto plan storage normalizes stale values and updates graph jobs', () => {
  const storage = createMemoryStorage()
  storage.setItem('jobs', JSON.stringify({ graphA: '7', graphB: -1, graphC: 'bad' }))

  assert.deepEqual(readStoredAutoPlanJobs(storage, 'jobs'), { graphA: 7 })
  setStoredAutoPlanJobId(storage, 'jobs', 'graphB', 9)
  assert.equal(getStoredAutoPlanJobId(storage, 'jobs', 'graphB'), 9)
  clearStoredAutoPlanJobId(storage, 'jobs', 'graphA')
  assert.deepEqual(readStoredAutoPlanJobs(storage, 'jobs'), { graphB: 9 })
})

test('mission config payload parses geometry and smoothing fields', () => {
  const form = createExportForm()
  assert.deepEqual(buildMissionGeometryInputsSnapshot(form), {
    step_distance: '60',
    fps: '4',
    altitude_mode: 'fixed',
    fixed_z: '120',
    altitude_offset: '0',
    takeoff_landing_relative_z: '',
    takeoff_landing_step_distance: '',
    node_sample_radius: '0',
    random_seed: '',
    turn_smoothing_enabled: true,
    corner_radius: '450',
    small_turn_yaw_blend_threshold_deg: '12',
    corner_min_angle_deg: '10',
    u_turn_threshold_deg: '140',
    u_turn_transition_distance: '180',
    corner_max_yaw_step_deg: '3',
    u_turn_pivot_yaw_step_deg: '2.5',
  })

  assert.deepEqual(buildMissionConfigRequestPayload(form, smoothingDefaults), {
    step_distance: 60,
    fps: 4,
    altitude_mode: 'fixed',
    fixed_z: 120,
    altitude_offset: 0,
    takeoff_landing_relative_z: null,
    takeoff_landing_step_distance: null,
    node_sample_radius: 0,
    random_seed: null,
    turn_smoothing_enabled: true,
    corner_radius: 450,
    small_turn_yaw_blend_threshold_deg: 12,
    corner_min_angle_deg: 10,
    u_turn_threshold_deg: 140,
    u_turn_transition_distance: 180,
    corner_max_yaw_step_deg: 3,
    u_turn_pivot_yaw_step_deg: 2.5,
  })
})

test('preview path and graph view helpers are deterministic', () => {
  assert.deepEqual(buildPreviewPathSegments([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }]), [
    'M 0 0 L 10 0',
    'M 10 0 L 10 10',
  ])
  assert.deepEqual(computeChevronGlyph({ x: 0, y: 0 }, { x: 10, y: 0 }, 0.5), {
    x: 5,
    y: 0,
    angle: 0,
  })
  assert.deepEqual(
    transformGraphPoint({ x: 2, y: 5 }, { rotationQuadrants: 1, flipHorizontal: true, flipVertical: false }),
    { x: 5, y: 2 },
  )
})

function createMinimal3DGraph(): RouteGraph {
  return {
    format: 'route-graph',
    format_version: 1,
    id: 'z_graph',
    name: 'z_graph',
    coordinate_system: { type: 'cartesian', axes: ['x', 'y', 'z'], unit: 'cm' },
    properties: {},
    nodes: [
      { id: 'A', label: 'A', position: [0, 0, 100], tags: [], properties: {}, extensions: {} },
      { id: 'B', label: 'B', position: [1000, 0, 300], tags: [], properties: {}, extensions: {} },
    ],
    edges: [
      {
        id: 'E001',
        source: 'A',
        target: 'B',
        metrics: { length: 1000, cost: 1000 },
        enabled: true,
        directed: false,
        properties: {},
        extensions: {
          route_graph_webui: { [EDGE_KIND_META_KEY]: EDGE_KIND_GROUP, [EDGE_GROUP_COLOR_META_KEY]: '#FF0000' },
        },
      },
    ],
    extensions: {},
  }
}

function createMinimalCandidateSet(): RouteCandidateSet {
  return {
    evaluation_version: 1,
    env_id: 'env',
    graph_name: 'z_graph',
    anchor_nodes: ['A', 'B'],
    candidates: [
      {
        candidate_id: 'C001',
        rank: 1,
        planned_nodes: ['A', 'B'],
        edge_passes: [
          {
            pass_index: 1,
            edge_id: 'E001',
            from_node: 'A',
            to_node: 'B',
            segment_index: 0,
            local_index: 1,
          },
        ],
        segments: [],
        total_length: 1000,
        selected: true,
        meta: {},
      },
    ],
    node_lookup: {
      A: { id: 'A', label: 'A', position: [0, 0, 200], tags: [], properties: {}, extensions: {} },
      B: { id: 'B', label: 'B', position: [1000, 0, 200], tags: [], properties: {}, extensions: {} },
    },
    selected_candidate_ids: ['C001'],
    meta: {
      node_group_lookup_v1: {
        A: '#FF0000',
        B: '#FF0000',
      },
      group_average_z_lookup_v1: {
        '#FF0000': 220,
      },
    },
  }
}

test('3d z layers default to recorded z and can switch to group normalized z from candidate meta', () => {
  const graph = createMinimal3DGraph()
  const candidateSet = createMinimalCandidateSet()

  const recordedPositions = resolveGraph3DNodePositions(graph, candidateSet, 'recorded')
  const groupNormalizedPositions = resolveGraph3DNodePositions(graph, candidateSet, 'groupNormalized')

  assert.deepEqual(recordedPositions.get('A'), [0, 0, 100])
  assert.deepEqual(recordedPositions.get('B'), [1000, 0, 300])
  assert.deepEqual(groupNormalizedPositions.get('A'), [0, 0, 220])
  assert.deepEqual(groupNormalizedPositions.get('B'), [1000, 0, 220])
})

test('3d group normalized layer falls back to graph-derived group averages without candidates', () => {
  const graph = createMinimal3DGraph()
  const grouping = resolveGraph3DGrouping(graph, null)
  const groupNormalizedPositions = resolveGraph3DNodePositions(graph, null, 'groupNormalized')

  assert.deepEqual(grouping.groupColors, ['#FF0000'])
  assert.deepEqual(groupNormalizedPositions.get('A'), [0, 0, 200])
  assert.deepEqual(groupNormalizedPositions.get('B'), [1000, 0, 200])
})

test('3d group normalized layer preserves conflicting and ungrouped node z', () => {
  const graph: RouteGraph = {
    format: 'route-graph',
    format_version: 1,
    id: 'group_conflict_graph',
    name: 'group_conflict_graph',
    coordinate_system: { type: 'cartesian', axes: ['x', 'y', 'z'], unit: 'cm' },
    properties: {},
    nodes: [
      { id: 'A', label: 'A', position: [0, 0, 100], tags: [], properties: {}, extensions: {} },
      { id: 'B', label: 'B', position: [100, 0, 300], tags: [], properties: {}, extensions: {} },
      { id: 'C', label: 'C', position: [200, 0, 500], tags: [], properties: {}, extensions: {} },
      { id: 'D', label: 'D', position: [300, 0, 700], tags: [], properties: {}, extensions: {} },
    ],
    edges: [
      {
        id: 'E_RED',
        source: 'A',
        target: 'B',
        metrics: { length: 100, cost: 100 },
        enabled: true,
        directed: false,
        properties: {},
        extensions: {
          route_graph_webui: { [EDGE_KIND_META_KEY]: EDGE_KIND_GROUP, [EDGE_GROUP_COLOR_META_KEY]: '#FF0000' },
        },
      },
      {
        id: 'E_BLUE',
        source: 'B',
        target: 'C',
        metrics: { length: 100, cost: 100 },
        enabled: true,
        directed: false,
        properties: {},
        extensions: {
          route_graph_webui: { [EDGE_KIND_META_KEY]: EDGE_KIND_GROUP, [EDGE_GROUP_COLOR_META_KEY]: '#0000FF' },
        },
      },
    ],
    extensions: {},
  }

  const groupNormalizedPositions = resolveGraph3DNodePositions(graph, null, 'groupNormalized')

  assert.deepEqual(groupNormalizedPositions.get('A'), [0, 0, 100])
  assert.deepEqual(groupNormalizedPositions.get('B'), [100, 0, 300])
  assert.deepEqual(groupNormalizedPositions.get('C'), [200, 0, 500])
  assert.deepEqual(groupNormalizedPositions.get('D'), [300, 0, 700])
})

test('3d route transform shares 2d quadrant and flip semantics without changing z', () => {
  const graph = createMinimal3DGraph()
  const positions = resolveGraph3DNodePositions(graph, null, 'recorded')
  const metrics = computeGraph3DSceneMetrics(graph, positions)
  const viewState: CanvasViewStateLike = {
    rotationQuadrants: 1,
    flipHorizontal: true,
    flipVertical: false,
  }

  assert.deepEqual(applyCanvasViewToGraphXY([502, 5, 300], metrics, viewState), { x: 5, y: 2 })

  const scenePoint = projectGraphPositionToScene([502, 5, 250], metrics, viewState, 4)
  assert.equal(scenePoint.x, 0.6)
  assert.equal(scenePoint.z, -0.24)
  assert.equal(scenePoint.y, 24)
})
