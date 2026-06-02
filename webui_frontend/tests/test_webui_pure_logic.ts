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
