import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const appVue = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const canvasStageVue = readFileSync(new URL('../src/components/CanvasStage.vue', import.meta.url), 'utf8')
const graph3DPreviewVue = readFileSync(new URL('../src/components/Graph3DPreview.vue', import.meta.url), 'utf8')
const autoPlanJobComposable = readFileSync(
  new URL('../src/composables/useAutoPlanJob.ts', import.meta.url),
  'utf8',
)

function assertContainsInOrder(source: string, snippets: string[]) {
  let cursor = 0
  for (const snippet of snippets) {
    const nextIndex = source.indexOf(snippet, cursor)
    assert.notEqual(nextIndex, -1, `Missing snippet after offset ${cursor}: ${snippet}`)
    cursor = nextIndex + snippet.length
  }
}

test('graph UI autosave persists planner group auto-plan and export input buckets', () => {
  assertContainsInOrder(appVue, [
    '() => currentGraphPath.value',
    '() => JSON.stringify(buildPlannerInputsPersistencePayload())',
    '() => JSON.stringify(buildGroupInputsPersistencePayload())',
    '() => JSON.stringify(buildAutoPlanInputsPersistencePayload())',
    '() => JSON.stringify(buildExportInputsPersistencePayload())',
    'scheduleGraphUiStateAutosave()',
  ])

  assertContainsInOrder(appVue, [
    'await updateGraphUiState({',
    'graph: graphPath',
    'planner_inputs: buildPlannerInputsPersistencePayload()',
    'group_inputs: buildGroupInputsPersistencePayload()',
    'auto_plan_inputs: buildAutoPlanInputsPersistencePayload()',
    'export_inputs: buildExportInputsPersistencePayload()',
  ])
})

test('candidate table keeps single range toggle and select-all selection paths wired', () => {
  assertContainsInOrder(appVue, [
    'function handleCandidateRowClick(candidateId: string, event: MouseEvent)',
    'if (event.shiftKey)',
    'selectCandidateRowRange(candidateId)',
    'if (event.metaKey || event.ctrlKey)',
    'toggleCandidateRowSelection(candidateId)',
    'selectOnlyCandidateRow(candidateId)',
  ])

  assertContainsInOrder(appVue, [
    'function handleCandidateTableKeydown(event: KeyboardEvent)',
    "event.key.toLowerCase() !== 'a'",
    'event.preventDefault()',
    'event.stopPropagation()',
    'selectAllCandidateRows()',
  ])
})

test('mission config payload carries export geometry and smoothing fields', () => {
  assertContainsInOrder(appVue, [
    'buildMissionConfigRequestPayload as buildMissionConfigRequestPayloadPure',
    'function buildMissionConfigRequestPayload()',
    'return buildMissionConfigRequestPayloadPure(exportForm, DEFAULT_SMOOTHING_INPUTS)',
  ])
})

test('3d toolbar exposes group normalization and group focus controls only in 3d mode', () => {
  assertContainsInOrder(canvasStageVue, [
    "v-if=\"canvasDisplayMode === '3d'\"",
    'groupNormalizedZLayerEnabled',
    "emit('toggle-group-normalized-z-layer')",
    '分组归一化',
  ])

  assertContainsInOrder(canvasStageVue, [
    'function handleGroupFocusChange(event: Event)',
    "emit('set-graph3d-group-focus'",
    'class="group-switch-chip"',
    'aria-label="3D 分组显示"',
  ])

  assertContainsInOrder(appVue, [
    'const graph3DGroupFocusColor = ref<string | null>(null)',
    ':graph3d-group-focus-color="graph3DGroupFocusColor"',
    '@set-graph3d-group-focus="setGraph3DGroupFocusColor"',
    ':group-focus-color="graph3DGroupFocusColor"',
  ])
})

test('3d viewport controls use independent camera lock state and 2d-style minimap panel', () => {
  assertContainsInOrder(appVue, [
    'const graph3DViewportLocked = ref(false)',
    'const GRAPH_3D_VIEWPORT_LOCK_STORAGE_KEY',
    'function setGraph3DViewportLockState(',
    'function toggleGraph3DViewportLock()',
  ])

  assertContainsInOrder(appVue, [
    ':camera-locked="graph3DViewportLocked"',
    '@toggle-camera-lock="toggleGraph3DViewportLock"',
  ])

  assertContainsInOrder(graph3DPreviewVue, [
    'class="graph-3d-controls"',
    'class="graph-3d-minimap"',
    'minimapModel.edges',
    'minimapModel.nodes',
    'class="graph-3d-controls__buttons"',
    '@click="zoomIn"',
    '@click="zoomOut"',
    '@click="resetCamera()"',
    "emit('toggle-camera-lock')",
  ])

  assertContainsInOrder(graph3DPreviewVue, [
    'const CAMERA_FIT_DISTANCE_SCALE = 0.54',
    'distance = (sphere.radius / Math.sin(fov / 2)) * CAMERA_FIT_DISTANCE_SCALE',
  ])
})

test('auto-plan job recovery validates graph identity before resuming status', () => {
  assertContainsInOrder(autoPlanJobComposable, [
    'export function useAutoPlanJob',
    'storageKey: string',
    'pollIntervalMs: number',
    'function readStoredAutoPlanJobs()',
    'function writeStoredAutoPlanJobs(jobMap: Record<string, number>)',
    'window.localStorage.setItem(storageKey, JSON.stringify(jobMap))',
    'function getStoredAutoPlanJobId(graphPath?: string | null)',
    'function clearStoredAutoPlanJobId(graphPath?: string | null)',
  ])

  assertContainsInOrder(autoPlanJobComposable, [
    'function scheduleAutoPlanPoll(jobId: number, graphPath: string)',
    'clearAutoPlanPollTimer()',
    'window.setTimeout(() => {',
    'void poll(jobId, graphPath)',
    'pollIntervalMs',
  ])

  assertContainsInOrder(appVue, [
    'useAutoPlanJob({',
    'storageKey: AUTO_PLAN_STORAGE_KEY',
    'pollIntervalMs: AUTO_PLAN_POLL_INTERVAL_MS',
    'async function restoreAutoPlanJobForGraph(graphPath: string)',
    'const storedJobId = getStoredAutoPlanJobId(graphPath)',
    'const status = await fetchAutoPlanJob(storedJobId)',
    'if (status.graph !== graphPath)',
    'clearStoredAutoPlanJobId(graphPath)',
    'handleAutoPlanJobStatus(status, { recovered: true })',
    'return status.state',
  ])
})
