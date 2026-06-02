<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type Ref } from 'vue'
import { Background } from '@vue-flow/background'
import { ControlButton, Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import {
  MarkerType,
  Position,
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge as FlowEdge,
  type EdgeMouseEvent,
  type Node as FlowNode,
  type NodeDragEvent,
  type NodeMouseEvent,
  type ViewportTransform,
  type XYPosition,
} from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

import TopologyNode from './components/TopologyNode.vue'
import AppHeader from './components/AppHeader.vue'
import StatusRibbon from './components/StatusRibbon.vue'
import CandidatePanel from './components/CandidatePanel.vue'
import CanvasStage from './components/CanvasStage.vue'
import EdgeInspector from './components/EdgeInspector.vue'
import ExportPanel from './components/ExportPanel.vue'
import GroupConfigPanel from './components/GroupConfigPanel.vue'
import NodeInspector from './components/NodeInspector.vue'
import PalettePanel from './components/PalettePanel.vue'
import RoutePlannerPanel from './components/RoutePlannerPanel.vue'

import {
  addEdge,
  exportMissions,
  fetchAutoPlanJob,
  fetchGraph,
  fetchGraphCatalog,
  fetchMissionPreview,
  generatePlan,
  moveNode,
  removeEdge,
  removeEdgeBetween,
  saveCandidateSet,
  startAutoPlanJob,
  updateCanvasView,
  updateEdge,
  updateGraphGroupConfig,
  updateGraphUiState,
  updateLastGraph,
  updateNode,
  validateGraph,
} from './lib/api'
import {
  normalizeOptionalHexColor,
  resolvePaletteBrushColor,
  resolvePaletteSelectionResult,
} from './lib/palette-selection'
import { resolveEdgeCreationIntent as resolveSharedEdgeCreationIntent } from './lib/edge-intent'
import { resolveNodePulseState } from './lib/node-pulse'
import { depthCardDirective, type DepthCardOptions } from './lib/depth-card'
import { useAutoPlanJob, useAutoPlanJobStatus } from './composables/useAutoPlanJob'
import { useGraphMutations } from './composables/useGraphMutations'
import { useGraphSelection } from './composables/useGraphSelection'
import { useGraphState } from './composables/useGraphState'
import { useGraphUiAutosave } from './composables/useGraphUiAutosave'
import { useMissionPreview } from './composables/useMissionPreview'
import { usePlannerForm } from './composables/usePlannerForm'
import {
  resolveCandidateKeepTargetIds as resolveCandidateKeepTargetIdsPure,
  resolveCandidateRangeSelection,
} from './lib/candidate-selection'
import {
  buildMissionConfigRequestPayload as buildMissionConfigRequestPayloadPure,
  buildMissionGeometryInputsSnapshot as buildMissionGeometryInputsSnapshotPure,
} from './lib/mission-config'
import type {
  AutoPlanJobStatus,
  GraphEdge,
  GraphEnvelope,
  GroupConfigInputsState,
  GraphNode,
  GraphSummary,
  GraphUiState,
  MissionPreviewStatus,
  MissionExportResponse,
  RouteCandidate,
  RouteCandidateSet,
  RouteGraph,
} from './types/route-graph'
import {
  DEFAULT_GROUP_COLOR,
  EDGE_GROUP_COLOR_META_KEY,
  EDGE_KIND_BRIDGE,
  EDGE_KIND_GROUP,
  EDGE_KIND_META_KEY,
  GRAPH_BRIDGE_STYLE_META_KEY,
  GRAPH_GROUP_CONFIGS_META_KEY,
  GRAPH_GUI_CANVAS_VIEW_META_KEY,
} from './types/graph-meta'

const { fitView, getViewport, zoomIn, zoomOut } = useVueFlow()
const vDepthCard = depthCardDirective
const trackingDepthCard = { mode: 'tracking' } as const satisfies DepthCardOptions
const subtleTrackingDepthCard = {
  mode: 'tracking',
  intensity: 'subtle',
  scale: 0.7,
} as const satisfies DepthCardOptions
const bannerDepthCard = { mode: 'tracking', intensity: 'subtle', scale: 0.30 } as const satisfies DepthCardOptions
const shadowOnlyDepthCard = { mode: 'shadow-only' } as const satisfies DepthCardOptions
const leftRailDepthTrackingEnabled = ref(true)
const leftRailDepthCard = computed<DepthCardOptions>(() =>
  leftRailDepthTrackingEnabled.value ? trackingDepthCard : shadowOnlyDepthCard,
)
const rightRailDepthTrackingEnabled = ref(true)
const rightRailDepthCard = computed<DepthCardOptions>(() =>
  rightRailDepthTrackingEnabled.value ? subtleTrackingDepthCard : shadowOnlyDepthCard,
)

type AnchorRole = 'start' | 'end' | 'via'
type AnchorChangeSource = 'gesture' | 'inspector' | 'planner' | 'reset'
type NodeGestureTracker = {
  nodeId: string
  timeoutId: number
}
type CanvasViewState = {
  rotationQuadrants: number
  flipHorizontal: boolean
  flipVertical: boolean
}
type PreviewChevronGlyph = {
  id: string
  x: number
  y: number
  angle: number
  tone: 'yellow' | 'black'
}
type PreviewPathSegment = {
  start: XYPosition
  dx: number
  dy: number
  length: number
  startDistance: number
  angleDeg: number
}
type PreviewPathMetrics = {
  segments: PreviewPathSegment[]
  totalLength: number
  glyphCount: number
  spacing: number
}
type CandidateDisplayRow = {
  id: string
  candidate: RouteCandidate
  displayRank: number
  startNode: string
  endNode: string
  frameCount: number | null
  edgePassCount: number
  repeatNodeCount: number
}
type AutoPlanRestoreOutcome = 'none' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out'

const AUTO_PLAN_POLL_INTERVAL_MS = 500
const AUTO_PLAN_STORAGE_KEY = 'route_graph_webui_auto_plan_jobs_v1'

const DEFAULT_SMOOTHING_INPUTS = {
  cornerRadius: '900',
  smallTurnYawBlendThresholdDeg: '15',
  cornerMinAngleDeg: '20',
  uTurnThresholdDeg: '150',
  uTurnTransitionDistance: '240',
  cornerMaxYawStepDeg: '2',
  uTurnPivotYawStepDeg: '2.5',
}

function createDefaultGroupConfigFormState() {
  return {
    altitudeMode: 'fixed' as 'fixed' | 'follow_nodes',
    fixedZ: '',
    altitudeOffset: '0',
    nodeSampleRadius: '0',
    takeoffLandingRelativeZ: '',
    takeoffLandingStepDistance: '',
  }
}

function createDefaultPlanFormState() {
  return {
    planningMode: 'manual' as 'manual' | 'auto',
    startNodeId: '',
    endNodeId: '',
    viaNodeIds: [] as string[],
    maxRoutes: 10,
    maxEdgePassFactor: 2.5,
    minTotalLength: '',
    maxTotalLength: '',
    minFrameCount: '',
    maxFrameCount: '',
    autoMaxOutputRoutes: '20',
    autoMaxRoutesPerPair: '3',
    autoMaxAnchorPairs: '100',
    autoDistancePerFrame: '1',
    autoMinFrameCount: '',
    autoMaxFrameCount: '',
    autoMinEndpointDistance: '0',
    autoMaxSearchStates: '50000',
    autoCoverageWeight: '1.0',
    autoDiversityWeight: '0.45',
    autoAnchorWeight: '0.35',
    autoReversePenaltyWeight: '0.2',
    autoNodeCoverageWeight: '0.2',
    autoEndpointReuseWeight: '0.2',
    autoAllowedRouteGroupColors: [] as string[],
    autoExcludedEndpointGroupColors: [] as string[],
    autoPreferConnectedAnchors: true,
    autoPreferRouteDiversity: true,
    autoAllowReverseDirectionCounterparts: true,
  }
}

function createDefaultExportFormState() {
  return {
    candidateSetFileName: '',
    missionsOutputDir: '',
    stepDistance: '60',
    fps: '4',
    altitudeMode: 'fixed' as 'fixed' | 'follow_nodes',
    fixedZ: '',
    altitudeOffset: '0',
    takeoffLandingRelativeZ: '',
    takeoffLandingStepDistance: '',
    nodeSampleRadius: '0',
    randomSeed: '',
    turnSmoothingEnabled: true,
    cornerRadius: DEFAULT_SMOOTHING_INPUTS.cornerRadius,
    smallTurnYawBlendThresholdDeg: DEFAULT_SMOOTHING_INPUTS.smallTurnYawBlendThresholdDeg,
    cornerMinAngleDeg: DEFAULT_SMOOTHING_INPUTS.cornerMinAngleDeg,
    uTurnThresholdDeg: DEFAULT_SMOOTHING_INPUTS.uTurnThresholdDeg,
    uTurnTransitionDistance: DEFAULT_SMOOTHING_INPUTS.uTurnTransitionDistance,
    cornerMaxYawStepDeg: DEFAULT_SMOOTHING_INPUTS.cornerMaxYawStepDeg,
    uTurnPivotYawStepDeg: DEFAULT_SMOOTHING_INPUTS.uTurnPivotYawStepDeg,
  }
}

const {
  graphCatalog,
  currentGraphPath,
  graphEnvelope,
  candidateSet,
  loadingGraph,
  validatingGraph,
  graph,
  graphSummary,
  groupEditorState,
  groupColorOptions,
  groupConfigLookup,
  availableGraphs,
  upsertGraphSummary: upsertGraphSummaryInState,
  applyGraphEnvelopeToState,
} = useGraphState()
const {
  selectedCandidateId,
  selectedCandidateRowIds,
  selectedCandidateRowIdSet,
  selectedNodeIds,
  primarySelectedNodeId,
  selectedNodeIdSet,
  selectedEdgeId,
  candidateRowSelectionAnchorId,
  candidateRowClickTimeoutId,
  clearCandidateRowClickTimer,
  setSelectedCandidateRows: setSelectedCandidateRowsInSelection,
} = useGraphSelection()
const nodeDragEnabled = ref(false)
const nodePositionBaseline = ref<Map<string, [number, number, number]>>(new Map())
const lastCandidateSavePath = ref('')
const lastExportSummary = ref<MissionExportResponse | null>(null)
const canvasScale = ref(0.02)
const canvasViewState = reactive<CanvasViewState>({
  rotationQuadrants: 0,
  flipHorizontal: false,
  flipVertical: false,
})

const savingNode = ref(false)
const resettingNodePosition = ref(false)
const mutatingEdge = ref(false)
const planningRoutes = ref(false)
const savingRoutes = ref(false)
const exportingRoutes = ref(false)
const updatingCanvasView = ref(false)
const missionPreview = useMissionPreview()
const {
  previewMission,
  previewStatus,
  previewError,
  previewLoading,
  previewRequestSequence,
  previewSourceRevision,
  getCachedMissionPreview,
  setCachedMissionPreview,
  deleteCachedMissionPreview,
} = missionPreview
const viewportTransform = ref<ViewportTransform>({ x: 0, y: 0, zoom: 1 })
const previewFlowNowMs = ref(0)
const previewFlowRafId = ref<number | null>(null)
const canvasStage = ref<InstanceType<typeof CanvasStage> | null>(null)
const atmosphereWaveCanvas = computed(() => canvasStage.value?.waveCanvas ?? null)
const atmosphereWaveRafId = ref<number | null>(null)
const atmosphereWaveResizeObserver = ref<ResizeObserver | null>(null)
const atmosphereWaveReducedMotion = ref(false)
const atmosphereWaveMotionQuery = ref<MediaQueryList | null>(null)

const bannerTone = ref<'info' | 'success' | 'error'>('info')
const bannerMessage = ref('')

const secondaryNodeGesture = ref<NodeGestureTracker | null>(null)
const middleNodeGesture = ref<NodeGestureTracker | null>(null)
const {
  activeAutoPlanJobId,
  autoPlanJobStatus,
  autoPlanRecovered,
  clearAutoPlanPollTimer,
  scheduleAutoPlanPoll: scheduleAutoPlanPollTimer,
  resetTrackedAutoPlanState: resetAutoPlanTracking,
  getStoredAutoPlanJobId,
  setStoredAutoPlanJobId,
  clearStoredAutoPlanJobId,
} = useAutoPlanJob({
  storageKey: AUTO_PLAN_STORAGE_KEY,
  pollIntervalMs: AUTO_PLAN_POLL_INTERVAL_MS,
  poll: pollAutoPlanJob,
})
const {
  clearAutosaveTimer: clearGraphUiStateAutosaveTimer,
  scheduleAutosave: scheduleGraphUiStateAutosaveTimer,
} = useGraphUiAutosave(400)
const {
  clearAutosaveTimer: clearGroupConfigAutosaveTimer,
  scheduleAutosave: scheduleGroupConfigAutosaveTimer,
} = useGraphUiAutosave(400)
const hydratingGraphUiState = ref(false)
const hydratingGroupConfigForm = ref(false)
const viewportLocked = ref(false)
const activeGroupColor = ref<string | null>(null)
const paintColor = ref<string | null>(null)
const paintModeEnabled = ref(false)
const sessionPaletteColors = ref<string[]>([])
const bridgeColorDraft = ref('#F97316')
const newPaletteColor = ref('#334155')

const { form: planForm } = usePlannerForm(createDefaultPlanFormState())

const nodeDraft = reactive({
  name: '',
  tagsText: '',
  yawHint: '',
  sampleRadius: '',
})

const { form: exportForm } = usePlannerForm(createDefaultExportFormState())
const { form: groupConfigForm } = usePlannerForm(createDefaultGroupConfigFormState())
const { runGraphMutation } = useGraphMutations((envelope) => applyGraphEnvelope(envelope))

const isAutoPlanningMode = computed(() => planForm.planningMode === 'auto')
const isPaintModeActive = computed(() => paintModeEnabled.value && !!paintColor.value)
const graphNodeMap = computed(() => new Map((graph.value?.nodes ?? []).map((node) => [node.id, node])))
const graphEdgeMap = computed(() => new Map((graph.value?.edges ?? []).map((edge) => [edge.id, edge])))
const graphColorGrouping = computed(() => deriveGraphColorGroupingState(graph.value))
const graphViewCenter = computed<[number, number]>(() => computeGraphViewCenter(graph.value))
const canvasViewSummaryText = computed(() => {
  const parts: string[] = []
  if (canvasViewState.rotationQuadrants !== 0) {
    parts.push(`${canvasViewState.rotationQuadrants * 90}°`)
  }
  if (canvasViewState.flipHorizontal) {
    parts.push('水平翻转')
  }
  if (canvasViewState.flipVertical) {
    parts.push('垂直翻转')
  }
  return parts.length ? `视图：${parts.join(' · ')}` : '视图：默认'
})

const selectedNode = computed<GraphNode | null>(() => {
  if (!primarySelectedNodeId.value) {
    return null
  }
  return graphNodeMap.value.get(primarySelectedNodeId.value) ?? null
})

const selectedNodePositionBaseline = computed<[number, number, number] | null>(() => {
  if (!selectedNode.value) {
    return null
  }
  return nodePositionBaseline.value.get(selectedNode.value.id) ?? null
})

const canResetSelectedNodePosition = computed(
  () => !!selectedNode.value && !!selectedNodePositionBaseline.value,
)
const nodeDragStatusText = computed(() =>
  nodeDragEnabled.value && !isPaintModeActive.value ? '节点拖拽已开启' : '节点拖拽已锁定',
)

const selectedEdge = computed<GraphEdge | null>(() => {
  if (!selectedEdgeId.value) {
    return null
  }
  return graphEdgeMap.value.get(selectedEdgeId.value) ?? null
})

const selectedCandidate = computed<RouteCandidate | null>(() => {
  if (!candidateSet.value || !selectedCandidateId.value) {
    return null
  }
  return (
    candidateSet.value.candidates.find(
      (candidate) => candidate.candidate_id === selectedCandidateId.value,
    ) ?? null
  )
})

const selectedCandidateIds = computed(() =>
  candidateSet.value?.candidates
    .filter((candidate) => candidate.selected)
    .map((candidate) => candidate.candidate_id) ?? [],
)
const candidateDisplayRows = computed<CandidateDisplayRow[]>(() => {
  if (!candidateSet.value) {
    return []
  }

  const defaultStartNode = candidateSet.value.anchor_nodes[0] ?? ''
  const defaultEndNode =
    candidateSet.value.anchor_nodes[candidateSet.value.anchor_nodes.length - 1] ?? defaultStartNode

  const sortedCandidates = [...candidateSet.value.candidates].sort((left, right) => {
    const leftFrameCount =
      typeof left.meta.frame_count === 'number' && Number.isFinite(left.meta.frame_count)
        ? left.meta.frame_count
        : 0
    const rightFrameCount =
      typeof right.meta.frame_count === 'number' && Number.isFinite(right.meta.frame_count)
        ? right.meta.frame_count
        : 0
    if (leftFrameCount !== rightFrameCount) {
      return leftFrameCount - rightFrameCount
    }
    if (left.total_length !== right.total_length) {
      return left.total_length - right.total_length
    }
    if (left.rank !== right.rank) {
      return left.rank - right.rank
    }
    return String(left.candidate_id).localeCompare(String(right.candidate_id))
  })

  return sortedCandidates.map((candidate, index) => {
    const frameCount =
      typeof candidate.meta.frame_count === 'number' && Number.isFinite(candidate.meta.frame_count)
        ? candidate.meta.frame_count
        : null

    return {
      id: candidate.candidate_id,
      candidate,
      displayRank: index + 1,
      startNode: String(candidate.meta.auto_start_node ?? '').trim() || defaultStartNode,
      endNode: String(candidate.meta.auto_end_node ?? '').trim() || defaultEndNode,
      frameCount,
      edgePassCount:
        typeof candidate.meta.edge_pass_count === 'number' &&
        Number.isFinite(candidate.meta.edge_pass_count)
          ? candidate.meta.edge_pass_count
          : candidate.edge_passes.length,
      repeatNodeCount:
        typeof candidate.meta.repeat_node_count === 'number' &&
        Number.isFinite(candidate.meta.repeat_node_count)
          ? candidate.meta.repeat_node_count
          : 0,
    }
  })
})
const candidateDisplayRowIndexMap = computed(() => {
  const lookup = new Map<string, number>()
  candidateDisplayRows.value.forEach((row, index) => {
    lookup.set(row.id, index)
  })
  return lookup
})
const hasSelectedCandidateRows = computed(() => selectedCandidateRowIds.value.length > 0)
const selectedCandidateDisplayRank = computed<number | null>(() => {
  if (!selectedCandidateId.value) {
    return null
  }
  const rowIndex = candidateDisplayRowIndexMap.value.get(selectedCandidateId.value)
  return rowIndex == null ? null : rowIndex + 1
})
const selectedCandidateDetailRow = computed<CandidateDisplayRow | null>(() => {
  if (!selectedCandidateId.value) {
    return null
  }
  return candidateDisplayRows.value.find((row) => row.id === selectedCandidateId.value) ?? null
})
const previewRouteMeta = computed<Record<string, unknown> | null>(() => {
  const routeMeta = previewMission.value?.route_meta
  return routeMeta && typeof routeMeta === 'object' ? routeMeta : null
})
const previewFrameCount = computed<number | null>(() => {
  if (!previewMission.value) {
    return null
  }
  return Array.isArray(previewMission.value.positions) ? previewMission.value.positions.length : null
})
const previewStatusText = computed(() => {
  switch (previewStatus.value) {
    case 'no_candidate':
      return '无候选'
    case 'cached':
      return `使用缓存预览${previewFrameCount.value == null ? '' : `，共 ${previewFrameCount.value} 帧`}`
    case 'ready':
      return `已生成轨迹预览${previewFrameCount.value == null ? '' : `，共 ${previewFrameCount.value} 帧`}`
    case 'error':
      return previewError.value ? `预览失败：${previewError.value}` : '预览失败'
    case 'stale':
    default:
      if (previewMission.value && previewFrameCount.value != null) {
        return `预览过期，当前显示缓存预览，共 ${previewFrameCount.value} 帧`
      }
      return '预览过期'
  }
})
const previewStatusTone = computed<'info' | 'success' | 'error'>(() => {
  if (previewStatus.value === 'ready' || previewStatus.value === 'cached') {
    return 'success'
  }
  if (previewStatus.value === 'error') {
    return 'error'
  }
  return 'info'
})
const previewSummaryItems = computed(() => {
  const items: string[] = []
  const routeMeta = previewRouteMeta.value
  const frameCount = previewFrameCount.value
  if (frameCount != null) {
    items.push(`${formatCount(frameCount)} 帧`)
  }
  if (typeof routeMeta?.corner_turn_count === 'number') {
    items.push(`拐角平滑 ${formatCount(routeMeta.corner_turn_count)} 次`)
  }
  if (typeof routeMeta?.u_turn_count === 'number') {
    items.push(`U 型掉头 ${formatCount(routeMeta.u_turn_count)} 次`)
  }
  if (typeof routeMeta?.smoothing_fallback_count === 'number') {
    items.push(`平滑回退 ${formatCount(routeMeta.smoothing_fallback_count)} 次`)
  }
  return items
})
const {
  activeAutoPlanProgress,
  shouldShowAutoPlanStatus,
  autoPlanProgressMaximum,
  autoPlanProgressValue,
  autoPlanProgressPercent,
  autoPlanProgressPercentRounded,
  autoPlanStatusHeadline,
  autoPlanStatusPhaseLabel,
  autoPlanStatusSummary,
} = useAutoPlanJobStatus(autoPlanJobStatus, currentGraphPath)
const plannerGenerateButtonLabel = computed(() => {
  if (!planningRoutes.value) {
    return '生成候选路线'
  }
  return autoPlanJobStatus.value?.state === 'running' ? '自动规划中' : '生成中'
})
const bridgeColor = computed(() => groupEditorState.value?.bridge_color ?? '#F97316')
const paletteState = computed(() => {
  const usedColors = [...groupColorOptions.value]
  const usedLookup = new Set(usedColors)
  const nextSessionColors: string[] = []
  const seenSessionColors = new Set<string>()
  for (const color of sessionPaletteColors.value) {
    if (!color || usedLookup.has(color) || seenSessionColors.has(color)) {
      continue
    }
    seenSessionColors.add(color)
    nextSessionColors.push(color)
  }
  return {
    usedColors,
    sessionColors: nextSessionColors,
    availableColors: [...usedColors, ...nextSessionColors],
  }
})
const activeGroupConfigEnabled = computed(() => !!activeGroupColor.value)
const activeGroupDisplayLabel = computed(() =>
  activeGroupColor.value ? resolveGroupDisplayLabel(activeGroupColor.value) : '全部显示',
)
const currentPaintColorLabel = computed(() => paintColor.value ?? '未选择')
const selectedEdgeColorText = computed(() => {
  if (!selectedEdge.value) {
    return '未选中边'
  }
  if (resolveEdgeKind(selectedEdge.value) === 'bridge') {
    return `桥接色 ${bridgeColor.value}`
  }
  return `组色 ${resolveEdgeBaseColor(selectedEdge.value)}`
})
const viewportLockStatusText = computed(() =>
  viewportLocked.value ? '画布视口已锁定' : '画布视口已解锁',
)
const canCreateEdgeFromSelection = computed(() => selectedNodeIds.value.length === 2)
const canRemoveEdgeFromSelection = computed(
  () => !!selectedEdge.value || selectedNodeIds.value.length === 2,
)
const canMutateSelectedEdge = computed(() => !!selectedEdge.value)
const currentSelectionEdgeSummary = computed(() => {
  if (selectedEdge.value) {
    return `当前边 ${selectedEdge.value.id}：${resolveEdgeKind(selectedEdge.value) === 'bridge' ? '桥接边' : '组内边'}`
  }
  if (selectedNodeIds.value.length === 2) {
    return `当前两节点：${selectedNodeIds.value[0]} ↔ ${selectedNodeIds.value[1]}`
  }
  return '请先选中一条边，或恰好选中两个节点。'
})

const candidatePassLookup = computed(() => {
  const lookup = new Map<string, string>()
  for (const edgePass of selectedCandidate.value?.edge_passes ?? []) {
    const existing = lookup.get(edgePass.edge_id)
    const passText = String(edgePass.pass_index)
    lookup.set(edgePass.edge_id, existing ? `${existing}/${passText}` : passText)
  }
  return lookup
})

const routeEdgeIdSet = computed(() => new Set(candidatePassLookup.value.keys()))
const nodeTypes = {
  topology: markRaw(TopologyNode),
}

const numberFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
const integerFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })
const INITIALIZE_RETRY_DELAY_MS = 1500
const INITIALIZE_MAX_ATTEMPTS = 20
const CANVAS_NODE_GESTURE_WINDOW_MS = 300
const CANVAS_VIEW_META_KEY = GRAPH_GUI_CANVAS_VIEW_META_KEY
const VIEWPORT_LOCK_STORAGE_KEY = 'route_graph_webui_viewport_lock_v1'
const NODE_DIAMETER_PX = 16
const NODE_RADIUS_PX = NODE_DIAMETER_PX / 2
const PREVIEW_CHEVRON_PATH = 'M -4 -2.2 L 0 1.8 L 4 -2.2 L 2.8 -3.4 L 0 -0.6 L -2.8 -3.4 Z'
const PREVIEW_CHEVRON_DENSITY_PX = 12
const PREVIEW_CHEVRON_MIN_PATH_PX = 8
const PREVIEW_CHEVRON_MIN_SEGMENT_PX = 0.05
const PREVIEW_CHEVRON_MAX_GLYPHS = 360
const PREVIEW_FLOW_SPEED_PX_PER_SEC = 25

function sleep(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function readStoredViewportLock() {
  try {
    const raw = window.localStorage.getItem(VIEWPORT_LOCK_STORAGE_KEY)
    if (!raw) {
      return false
    }
    const parsed = JSON.parse(raw)
    return typeof parsed === 'boolean' ? parsed : false
  } catch {
    return false
  }
}

function writeStoredViewportLock(locked: boolean) {
  try {
    window.localStorage.setItem(VIEWPORT_LOCK_STORAGE_KEY, JSON.stringify(locked))
  } catch {
    // Ignore storage failures; the in-memory viewport lock still works.
  }
}

watch(
  selectedNode,
  (node) => {
    if (!node) {
      nodeDraft.name = ''
      nodeDraft.tagsText = ''
      nodeDraft.yawHint = ''
      nodeDraft.sampleRadius = ''
      return
    }
    nodeDraft.name = node.name
    nodeDraft.tagsText = node.tags.join(', ')
    nodeDraft.yawHint = node.yaw_hint == null ? '' : String(node.yaw_hint)
    nodeDraft.sampleRadius =
      typeof node.meta.node_sample_radius === 'number'
        ? String(node.meta.node_sample_radius)
        : ''
  },
  { immediate: true },
)

watch(
  groupColorOptions,
  (colors) => {
    const allowed = new Set(colors)
    planForm.autoAllowedRouteGroupColors = planForm.autoAllowedRouteGroupColors.filter((color) =>
      allowed.has(color),
    )
    planForm.autoExcludedEndpointGroupColors = planForm.autoExcludedEndpointGroupColors.filter((color) =>
      allowed.has(color),
    )
    sessionPaletteColors.value = sessionPaletteColors.value.filter((color) => !allowed.has(color))
    if (activeGroupColor.value && !allowed.has(activeGroupColor.value)) {
      activeGroupColor.value = colors[0] ?? null
    }
    paintColor.value = resolvePaletteBrushColor(
      colors,
      sessionPaletteColors.value,
      paintColor.value,
      activeGroupColor.value,
    )
  },
  { immediate: true },
)

watch(
  [activeGroupColor, () => JSON.stringify(groupConfigLookup.value)],
  () => {
    loadActiveGroupConfigForm()
  },
  { immediate: true },
)

watch(
  paintColor,
  (nextColor) => {
    if (!nextColor) {
      paintModeEnabled.value = false
    }
  },
)

watch(
  [
    () => groupConfigForm.altitudeMode,
    () => groupConfigForm.fixedZ,
    () => groupConfigForm.altitudeOffset,
    () => groupConfigForm.nodeSampleRadius,
    () => groupConfigForm.takeoffLandingRelativeZ,
    () => groupConfigForm.takeoffLandingStepDistance,
  ],
  () => {
    if (!activeGroupColor.value || hydratingGroupConfigForm.value) {
      return
    }
    scheduleGroupConfigAutosave()
  },
)

watch(
  candidateDisplayRows,
  (rows) => {
    const availableIds = new Set(rows.map((row) => row.id))
    selectedCandidateRowIds.value = selectedCandidateRowIds.value.filter((candidateId) =>
      availableIds.has(candidateId),
    )

    if (selectedCandidateId.value && !availableIds.has(selectedCandidateId.value)) {
      selectedCandidateId.value = rows[0]?.id ?? null
    }

    if (!selectedCandidateId.value && rows.length > 0) {
      selectedCandidateId.value = rows[0].id
    }

    if (candidateRowSelectionAnchorId.value && !availableIds.has(candidateRowSelectionAnchorId.value)) {
      candidateRowSelectionAnchorId.value = null
    }

    if (selectedCandidateRowIds.value.length === 0 && selectedCandidateId.value) {
      selectedCandidateRowIds.value = [selectedCandidateId.value]
      candidateRowSelectionAnchorId.value = selectedCandidateId.value
    }
  },
  { immediate: true },
)

watch(
  [
    () => currentGraphPath.value,
    () => JSON.stringify(buildPlannerInputsPersistencePayload()),
    () => JSON.stringify(buildGroupInputsPersistencePayload()),
    () => JSON.stringify(buildAutoPlanInputsPersistencePayload()),
    () => JSON.stringify(buildExportInputsPersistencePayload()),
  ],
  ([graphPath]) => {
    if (!graphPath || hydratingGraphUiState.value) {
      return
    }
    scheduleGraphUiStateAutosave()
  },
)

watch(
  [
    () => currentGraphPath.value,
    () => selectedCandidateId.value,
    () => previewSourceRevision.value,
    () => JSON.stringify(buildMissionGeometryInputsSnapshot()),
    () => JSON.stringify(candidateSet.value?.meta[GRAPH_GROUP_CONFIGS_META_KEY] ?? {}),
  ],
  ([graphPath, candidateId]) => {
    if (!graphPath || !candidateId || !candidateSet.value) {
      resetMissionPreviewState({ clearMission: true, status: 'no_candidate' })
      return
    }
    scheduleMissionPreviewRefresh()
  },
  { immediate: true },
)

function setBanner(message: string, tone: 'info' | 'success' | 'error' = 'info') {
  bannerMessage.value = message
  bannerTone.value = tone
}

function clearBanner() {
  bannerMessage.value = ''
  bannerTone.value = 'info'
}

function parsePersistedInteger(value: unknown, fallback: number) {
  const text = typeof value === 'string' ? value.trim() : String(value ?? '').trim()
  const parsed = Number.parseInt(text, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parsePersistedNumber(value: unknown, fallback: number) {
  const text = typeof value === 'string' ? value.trim() : String(value ?? '').trim()
  const parsed = Number(text)
  return Number.isFinite(parsed) ? parsed : fallback
}

function parseRequiredHexColor(value: string, label: string) {
  const normalized = normalizeOptionalHexColor(value)
  if (!normalized) {
    throw new Error(`${label}必须是 #RRGGBB 颜色值`)
  }
  return normalized
}

function buildGroupConfigDefaults() {
  return {
    altitudeMode: exportForm.altitudeMode,
    fixedZ: exportForm.fixedZ,
    altitudeOffset: exportForm.altitudeOffset,
    nodeSampleRadius: exportForm.nodeSampleRadius,
    takeoffLandingRelativeZ: exportForm.takeoffLandingRelativeZ,
    takeoffLandingStepDistance: exportForm.takeoffLandingStepDistance,
  }
}

function buildGroupConfigPayload(): GroupConfigInputsState {
  return {
    altitude_mode: groupConfigForm.altitudeMode,
    fixed_z: groupConfigForm.fixedZ,
    altitude_offset: groupConfigForm.altitudeOffset,
    node_sample_radius: groupConfigForm.nodeSampleRadius,
    takeoff_landing_relative_z: groupConfigForm.takeoffLandingRelativeZ,
    takeoff_landing_step_distance: groupConfigForm.takeoffLandingStepDistance,
  }
}

function loadActiveGroupConfigForm() {
  const defaults = buildGroupConfigDefaults()
  hydratingGroupConfigForm.value = true
  clearGroupConfigAutosaveTimer()

  const currentPayload = activeGroupColor.value
    ? groupConfigLookup.value[activeGroupColor.value] ?? {}
    : {}

  groupConfigForm.altitudeMode =
    currentPayload.altitude_mode === 'follow_nodes' ? 'follow_nodes' : defaults.altitudeMode
  if (currentPayload.altitude_mode === 'fixed') {
    groupConfigForm.altitudeMode = 'fixed'
  }
  groupConfigForm.fixedZ = currentPayload.fixed_z ?? defaults.fixedZ
  groupConfigForm.altitudeOffset = currentPayload.altitude_offset ?? defaults.altitudeOffset
  groupConfigForm.nodeSampleRadius =
    currentPayload.node_sample_radius ?? defaults.nodeSampleRadius
  groupConfigForm.takeoffLandingRelativeZ =
    currentPayload.takeoff_landing_relative_z ?? defaults.takeoffLandingRelativeZ
  groupConfigForm.takeoffLandingStepDistance =
    currentPayload.takeoff_landing_step_distance ?? defaults.takeoffLandingStepDistance
  bridgeColorDraft.value = bridgeColor.value

  void nextTick(() => {
    hydratingGroupConfigForm.value = false
  })
}

function buildPlannerInputsPersistencePayload() {
  return {
    planning_mode: planForm.planningMode,
    max_routes: String(planForm.maxRoutes),
    max_edge_pass_factor: String(planForm.maxEdgePassFactor),
    min_total_length: planForm.minTotalLength,
    max_total_length: planForm.maxTotalLength,
    min_frame_count: planForm.minFrameCount,
    max_frame_count: planForm.maxFrameCount,
  }
}

function buildGroupInputsPersistencePayload() {
  return {
    active_group_color: activeGroupColor.value ?? '',
  }
}

function buildAutoPlanInputsPersistencePayload() {
  return {
    planning_mode: planForm.planningMode,
    auto_max_output_routes: planForm.autoMaxOutputRoutes,
    auto_max_routes_per_pair: planForm.autoMaxRoutesPerPair,
    auto_max_anchor_pairs_to_evaluate: planForm.autoMaxAnchorPairs,
    auto_distance_per_frame: planForm.autoDistancePerFrame,
    auto_min_frame_count: planForm.autoMinFrameCount,
    auto_max_frame_count: planForm.autoMaxFrameCount,
    auto_min_endpoint_distance: planForm.autoMinEndpointDistance,
    auto_max_search_states: planForm.autoMaxSearchStates,
    auto_coverage_weight: planForm.autoCoverageWeight,
    auto_diversity_weight: planForm.autoDiversityWeight,
    auto_anchor_weight: planForm.autoAnchorWeight,
    auto_reverse_penalty_weight: planForm.autoReversePenaltyWeight,
    auto_node_coverage_weight: planForm.autoNodeCoverageWeight,
    auto_endpoint_reuse_weight: planForm.autoEndpointReuseWeight,
    auto_prefer_connected_anchors: planForm.autoPreferConnectedAnchors,
    auto_prefer_route_diversity: planForm.autoPreferRouteDiversity,
    auto_allow_reverse_direction_counterparts: planForm.autoAllowReverseDirectionCounterparts,
    auto_allowed_route_group_colors: [...planForm.autoAllowedRouteGroupColors],
    auto_excluded_endpoint_group_colors: [...planForm.autoExcludedEndpointGroupColors],
  }
}

function buildExportInputsPersistencePayload() {
  return {
    step_distance: exportForm.stepDistance,
    fps: exportForm.fps,
    altitude_mode: exportForm.altitudeMode,
    fixed_z: exportForm.fixedZ,
    altitude_offset: exportForm.altitudeOffset,
    takeoff_landing_relative_z: exportForm.takeoffLandingRelativeZ,
    takeoff_landing_step_distance: exportForm.takeoffLandingStepDistance,
    node_sample_radius: exportForm.nodeSampleRadius,
    random_seed: exportForm.randomSeed,
    turn_smoothing_enabled: exportForm.turnSmoothingEnabled,
    corner_radius: exportForm.cornerRadius,
    small_turn_yaw_blend_threshold_deg: exportForm.smallTurnYawBlendThresholdDeg,
    corner_min_angle_deg: exportForm.cornerMinAngleDeg,
    u_turn_threshold_deg: exportForm.uTurnThresholdDeg,
    u_turn_transition_distance: exportForm.uTurnTransitionDistance,
    corner_max_yaw_step_deg: exportForm.cornerMaxYawStepDeg,
    u_turn_pivot_yaw_step_deg: exportForm.uTurnPivotYawStepDeg,
    candidate_set_file_name: exportForm.candidateSetFileName,
    missions_output_dir: exportForm.missionsOutputDir,
  }
}

function applyGraphUiState(uiState: GraphUiState | undefined) {
  const planDefaults = createDefaultPlanFormState()
  const exportDefaults = createDefaultExportFormState()
  const plannerInputs = uiState?.planner_inputs ?? {}
  const groupInputs = uiState?.group_inputs ?? {}
  const autoInputs = uiState?.auto_plan_inputs ?? {}
  const exportInputs = uiState?.export_inputs ?? {}

  hydratingGraphUiState.value = true
  clearGraphUiStateAutosaveTimer()

  planForm.planningMode =
    plannerInputs.planning_mode === 'auto' || autoInputs.planning_mode === 'auto'
      ? 'auto'
      : 'manual'
  planForm.maxRoutes = parsePersistedInteger(plannerInputs.max_routes, planDefaults.maxRoutes)
  planForm.maxEdgePassFactor = parsePersistedNumber(
    plannerInputs.max_edge_pass_factor,
    planDefaults.maxEdgePassFactor,
  )
  planForm.minTotalLength =
    plannerInputs.min_total_length ??
    autoInputs.auto_min_total_length ??
    planDefaults.minTotalLength
  planForm.maxTotalLength =
    plannerInputs.max_total_length ??
    autoInputs.auto_max_total_length ??
    planDefaults.maxTotalLength
  planForm.minFrameCount = plannerInputs.min_frame_count ?? planDefaults.minFrameCount
  planForm.maxFrameCount = plannerInputs.max_frame_count ?? planDefaults.maxFrameCount
  planForm.autoMaxOutputRoutes =
    autoInputs.auto_max_output_routes ?? planDefaults.autoMaxOutputRoutes
  planForm.autoMaxRoutesPerPair =
    autoInputs.auto_max_routes_per_pair ?? planDefaults.autoMaxRoutesPerPair
  planForm.autoMaxAnchorPairs =
    autoInputs.auto_max_anchor_pairs_to_evaluate ?? planDefaults.autoMaxAnchorPairs
  planForm.autoDistancePerFrame =
    autoInputs.auto_distance_per_frame ?? planDefaults.autoDistancePerFrame
  planForm.autoMinFrameCount =
    autoInputs.auto_min_frame_count ?? planDefaults.autoMinFrameCount
  planForm.autoMaxFrameCount =
    autoInputs.auto_max_frame_count ?? planDefaults.autoMaxFrameCount
  planForm.autoMinEndpointDistance =
    autoInputs.auto_min_endpoint_distance ?? planDefaults.autoMinEndpointDistance
  planForm.autoMaxSearchStates =
    autoInputs.auto_max_search_states ?? planDefaults.autoMaxSearchStates
  planForm.autoCoverageWeight =
    autoInputs.auto_coverage_weight ?? planDefaults.autoCoverageWeight
  planForm.autoDiversityWeight =
    autoInputs.auto_diversity_weight ?? planDefaults.autoDiversityWeight
  planForm.autoAnchorWeight =
    autoInputs.auto_anchor_weight ?? planDefaults.autoAnchorWeight
  planForm.autoReversePenaltyWeight =
    autoInputs.auto_reverse_penalty_weight ?? planDefaults.autoReversePenaltyWeight
  planForm.autoNodeCoverageWeight =
    autoInputs.auto_node_coverage_weight ?? planDefaults.autoNodeCoverageWeight
  planForm.autoEndpointReuseWeight =
    autoInputs.auto_endpoint_reuse_weight ?? planDefaults.autoEndpointReuseWeight
  planForm.autoAllowedRouteGroupColors = [
    ...(autoInputs.auto_allowed_route_group_colors ?? planDefaults.autoAllowedRouteGroupColors),
  ]
  planForm.autoExcludedEndpointGroupColors = [
    ...(autoInputs.auto_excluded_endpoint_group_colors ??
      planDefaults.autoExcludedEndpointGroupColors),
  ]
  planForm.autoPreferConnectedAnchors =
    autoInputs.auto_prefer_connected_anchors ?? planDefaults.autoPreferConnectedAnchors
  planForm.autoPreferRouteDiversity =
    autoInputs.auto_prefer_route_diversity ?? planDefaults.autoPreferRouteDiversity
  planForm.autoAllowReverseDirectionCounterparts =
    autoInputs.auto_allow_reverse_direction_counterparts ??
    planDefaults.autoAllowReverseDirectionCounterparts

  exportForm.candidateSetFileName =
    exportInputs.candidate_set_file_name ?? exportDefaults.candidateSetFileName
  exportForm.missionsOutputDir =
    exportInputs.missions_output_dir ?? exportDefaults.missionsOutputDir
  exportForm.stepDistance = exportInputs.step_distance ?? exportDefaults.stepDistance
  exportForm.fps = exportInputs.fps ?? exportDefaults.fps
  exportForm.altitudeMode =
    exportInputs.altitude_mode === 'follow_nodes' ? 'follow_nodes' : exportDefaults.altitudeMode
  if (exportInputs.altitude_mode === 'fixed') {
    exportForm.altitudeMode = 'fixed'
  }
  exportForm.fixedZ = exportInputs.fixed_z ?? exportDefaults.fixedZ
  exportForm.altitudeOffset = exportInputs.altitude_offset ?? exportDefaults.altitudeOffset
  exportForm.takeoffLandingRelativeZ =
    exportInputs.takeoff_landing_relative_z ?? exportDefaults.takeoffLandingRelativeZ
  exportForm.takeoffLandingStepDistance =
    exportInputs.takeoff_landing_step_distance ?? exportDefaults.takeoffLandingStepDistance
  exportForm.nodeSampleRadius =
    exportInputs.node_sample_radius ?? exportDefaults.nodeSampleRadius
  exportForm.randomSeed = exportInputs.random_seed ?? exportDefaults.randomSeed
  exportForm.turnSmoothingEnabled =
    exportInputs.turn_smoothing_enabled ?? exportDefaults.turnSmoothingEnabled
  exportForm.cornerRadius = exportInputs.corner_radius ?? exportDefaults.cornerRadius
  exportForm.smallTurnYawBlendThresholdDeg =
    exportInputs.small_turn_yaw_blend_threshold_deg ??
    exportDefaults.smallTurnYawBlendThresholdDeg
  exportForm.cornerMinAngleDeg =
    exportInputs.corner_min_angle_deg ?? exportDefaults.cornerMinAngleDeg
  exportForm.uTurnThresholdDeg =
    exportInputs.u_turn_threshold_deg ?? exportDefaults.uTurnThresholdDeg
  exportForm.uTurnTransitionDistance =
    exportInputs.u_turn_transition_distance ?? exportDefaults.uTurnTransitionDistance
  exportForm.cornerMaxYawStepDeg =
    exportInputs.corner_max_yaw_step_deg ?? exportDefaults.cornerMaxYawStepDeg
  exportForm.uTurnPivotYawStepDeg =
    exportInputs.u_turn_pivot_yaw_step_deg ?? exportDefaults.uTurnPivotYawStepDeg

  if (Object.prototype.hasOwnProperty.call(groupInputs, 'active_group_color')) {
    activeGroupColor.value = normalizeOptionalHexColor(groupInputs.active_group_color ?? '') ?? null
  } else {
    activeGroupColor.value = groupColorOptions.value[0] ?? null
  }

  bridgeColorDraft.value = groupEditorState.value?.bridge_color ?? '#F97316'
  paintModeEnabled.value = false
  paintColor.value = resolvePaletteBrushColor(
    groupColorOptions.value,
    sessionPaletteColors.value,
    paintColor.value,
    activeGroupColor.value,
  )

  void nextTick(() => {
    hydratingGraphUiState.value = false
  })
}

function scheduleGraphUiStateAutosave() {
  if (!currentGraphPath.value || hydratingGraphUiState.value) {
    return
  }
  const graphPath = currentGraphPath.value
  scheduleGraphUiStateAutosaveTimer(async () => {
    try {
      await updateGraphUiState({
        graph: graphPath,
        planner_inputs: buildPlannerInputsPersistencePayload(),
        group_inputs: buildGroupInputsPersistencePayload(),
        auto_plan_inputs: buildAutoPlanInputsPersistencePayload(),
        export_inputs: buildExportInputsPersistencePayload(),
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存图参数失败'
      setBanner(`保存图参数失败：${message}`, 'error')
    }
  })
}

function hasActiveGroupConfigChanges() {
  if (!activeGroupColor.value) {
    return false
  }
  const currentPayload = buildGroupConfigPayload()
  const existingPayload = groupConfigLookup.value[activeGroupColor.value] ?? {}
  return (
    (existingPayload.altitude_mode ?? '') !== currentPayload.altitude_mode ||
    (existingPayload.fixed_z ?? '') !== currentPayload.fixed_z ||
    (existingPayload.altitude_offset ?? '') !== currentPayload.altitude_offset ||
    (existingPayload.node_sample_radius ?? '') !== currentPayload.node_sample_radius ||
    (existingPayload.takeoff_landing_relative_z ?? '') !== currentPayload.takeoff_landing_relative_z ||
    (existingPayload.takeoff_landing_step_distance ?? '') !== currentPayload.takeoff_landing_step_distance
  )
}

async function persistActiveGroupConfig() {
  if (!currentGraphPath.value || !activeGroupColor.value || hydratingGroupConfigForm.value) {
    return
  }
  if (!hasActiveGroupConfigChanges()) {
    return
  }
  const groupColor = activeGroupColor.value
  try {
    const envelope = await updateGraphGroupConfig({
      graph: currentGraphPath.value,
      group_color: groupColor,
      group_config: buildGroupConfigPayload(),
    })
    applyGraphEnvelope(envelope, { preserveCandidateSet: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存颜色组配置失败'
    setBanner(`保存颜色组配置失败：${message}`, 'error')
  }
}

function scheduleGroupConfigAutosave() {
  if (!currentGraphPath.value || !activeGroupColor.value || hydratingGroupConfigForm.value) {
    return
  }
  scheduleGroupConfigAutosaveTimer(async () => {
    try {
      await persistActiveGroupConfig()
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存颜色组配置失败'
      setBanner(`保存颜色组配置失败：${message}`, 'error')
    }
  })
}

async function flushActiveGroupConfigForGeneration() {
  clearGroupConfigAutosaveTimer()
  if (!currentGraphPath.value || !activeGroupColor.value || hydratingGroupConfigForm.value) {
    return
  }
  if (!hasActiveGroupConfigChanges()) {
    return
  }

  const envelope = await updateGraphGroupConfig({
    graph: currentGraphPath.value,
    group_color: activeGroupColor.value,
    group_config: buildGroupConfigPayload(),
  })
  applyGraphEnvelope(envelope, { preserveCandidateSet: true })
}

function resetTrackedAutoPlanState({ keepStatus = false }: { keepStatus?: boolean } = {}) {
  resetAutoPlanTracking({ keepStatus })
  planningRoutes.value = false
}

function applyGeneratedCandidateSet(nextCandidateSet: RouteCandidateSet) {
  candidateSet.value = nextCandidateSet
  const firstCandidateId = nextCandidateSet.candidates[0]?.candidate_id ?? null
  selectedCandidateId.value = firstCandidateId
  selectedCandidateRowIds.value = firstCandidateId ? [firstCandidateId] : []
  candidateRowSelectionAnchorId.value = firstCandidateId
  clearCandidateRowClickTimer()
  resetMissionPreviewState({ clearCache: true, clearMission: true, status: 'no_candidate' })
  bumpPreviewSourceRevision()
  syncCandidateSelections()
  exportForm.missionsOutputDir ||= nextCandidateSet.graph_name
}

function resolveAutoPlanStartBannerMessage() {
  return '自动规划任务已启动，正在后台生成候选路线...'
}

function isAutoPlanJobMissingError(error: unknown) {
  return error instanceof Error && /auto planning job .*not found/i.test(error.message)
}

function scheduleAutoPlanPoll(jobId: number, graphPath: string) {
  scheduleAutoPlanPollTimer(jobId, graphPath)
}

function handleAutoPlanJobStatus(
  status: AutoPlanJobStatus,
  {
    recovered = false,
  }: {
    recovered?: boolean
  } = {},
) {
  autoPlanJobStatus.value = status

  if (status.state === 'running') {
    const shouldAnnounceRecovery = recovered && !autoPlanRecovered.value
    activeAutoPlanJobId.value = status.job_id
    planningRoutes.value = true
    autoPlanRecovered.value = recovered
    scheduleAutoPlanPoll(status.job_id, status.graph)
    if (shouldAnnounceRecovery) {
      setBanner('已恢复自动规划任务进度', 'info')
    }
    return
  }

  const wasRecovered = recovered || autoPlanRecovered.value
  clearAutoPlanPollTimer()
  activeAutoPlanJobId.value = null
  planningRoutes.value = false
  autoPlanRecovered.value = false
  clearStoredAutoPlanJobId(status.graph)

  if (status.state === 'succeeded' && status.candidate_set) {
    applyGeneratedCandidateSet(status.candidate_set)
    setBanner(
      `${wasRecovered ? '已恢复自动规划结果，生成了' : '自动规划完成，生成了'} ${status.candidate_set.candidates.length} 条候选路线${status.candidate_set.meta.truncated ? '（搜索已截断）' : ''}`,
      'success',
    )
    return
  }

  if (status.state === 'failed') {
    setBanner(
      status.error
        ? `${wasRecovered ? '已恢复到自动规划失败状态：' : ''}${status.error}`
        : '自动规划失败',
      'error',
    )
  }
}

async function pollAutoPlanJob(jobId: number, graphPath: string) {
  if (activeAutoPlanJobId.value !== jobId || currentGraphPath.value !== graphPath) {
    return
  }

  try {
    const status = await fetchAutoPlanJob(jobId)
    if (activeAutoPlanJobId.value !== jobId || currentGraphPath.value !== graphPath) {
      return
    }
    handleAutoPlanJobStatus(status, { recovered: autoPlanRecovered.value })
  } catch (error) {
    if (activeAutoPlanJobId.value !== jobId || currentGraphPath.value !== graphPath) {
      return
    }

    if (isAutoPlanJobMissingError(error)) {
      clearStoredAutoPlanJobId(graphPath)
      resetTrackedAutoPlanState()
      setBanner('自动规划任务已失效，请重新发起。', 'error')
      return
    }

    if (bannerMessage.value !== '自动规划进度暂时不可用，正在重试...') {
      setBanner('自动规划进度暂时不可用，正在重试...', 'info')
    }
    scheduleAutoPlanPoll(jobId, graphPath)
  }
}

async function restoreAutoPlanJobForGraph(graphPath: string): Promise<AutoPlanRestoreOutcome> {
  resetTrackedAutoPlanState()
  const storedJobId = getStoredAutoPlanJobId(graphPath)
  if (storedJobId == null) {
    return 'none'
  }

  try {
    const status = await fetchAutoPlanJob(storedJobId)
    if (status.graph !== graphPath) {
      clearStoredAutoPlanJobId(graphPath)
      return 'none'
    }
    handleAutoPlanJobStatus(status, { recovered: true })
    return status.state
  } catch (error) {
    clearStoredAutoPlanJobId(graphPath)
    resetTrackedAutoPlanState()
    if (isAutoPlanJobMissingError(error)) {
      setBanner('之前的自动规划任务已失效，请重新发起。', 'error')
      return 'failed'
    }
    const message = error instanceof Error ? error.message : '恢复自动规划进度失败'
    setBanner(`恢复自动规划进度失败：${message}`, 'error')
    return 'failed'
  }
}

function isMouseEvent(event: MouseEvent | TouchEvent): event is MouseEvent {
  return event instanceof MouseEvent
}

function clearNodeGesture(tracker: Ref<NodeGestureTracker | null>) {
  if (!tracker.value) {
    return
  }
  window.clearTimeout(tracker.value.timeoutId)
  tracker.value = null
}

function commitNodeGesture(
  tracker: Ref<NodeGestureTracker | null>,
  nodeId: string,
  onMatch: () => void,
) {
  if (tracker.value?.nodeId === nodeId) {
    clearNodeGesture(tracker)
    onMatch()
    return
  }

  clearNodeGesture(tracker)
  const timeoutId = window.setTimeout(() => {
    tracker.value = null
  }, CANVAS_NODE_GESTURE_WINDOW_MS)
  tracker.value = { nodeId, timeoutId }
}

function setNodeSelection(nodeIds: string[], primaryNodeId: string | null) {
  const uniqueNodeIds: string[] = []
  const seenNodeIds = new Set<string>()
  for (const nodeId of nodeIds) {
    if (seenNodeIds.has(nodeId)) {
      continue
    }
    uniqueNodeIds.push(nodeId)
    seenNodeIds.add(nodeId)
  }

  selectedNodeIds.value = uniqueNodeIds
  if (primaryNodeId && seenNodeIds.has(primaryNodeId)) {
    primarySelectedNodeId.value = primaryNodeId
    return
  }
  primarySelectedNodeId.value = uniqueNodeIds[uniqueNodeIds.length - 1] ?? null
}

function selectOnlyNode(nodeId: string) {
  setNodeSelection([nodeId], nodeId)
  selectedEdgeId.value = null
}

function focusNodeSelection(nodeId: string) {
  const nextNodeIds = selectedNodeIds.value.filter((item) => item !== nodeId)
  nextNodeIds.push(nodeId)
  setNodeSelection(nextNodeIds, nodeId)
  selectedEdgeId.value = null
}

function toggleNodeSelection(nodeId: string) {
  const nextNodeIds = [...selectedNodeIds.value]
  const existingIndex = nextNodeIds.indexOf(nodeId)

  if (existingIndex >= 0) {
    nextNodeIds.splice(existingIndex, 1)
    const nextPrimaryNodeId =
      primarySelectedNodeId.value === nodeId
        ? (nextNodeIds[nextNodeIds.length - 1] ?? null)
        : primarySelectedNodeId.value
    setNodeSelection(nextNodeIds, nextPrimaryNodeId)
  } else {
    nextNodeIds.push(nodeId)
    setNodeSelection(nextNodeIds, nodeId)
  }

  selectedEdgeId.value = null
}

function selectEdge(edgeId: string) {
  setNodeSelection([], null)
  selectedEdgeId.value = edgeId
}

function invalidateCandidateOutputs() {
  candidateSet.value = null
  selectedCandidateId.value = null
  selectedCandidateRowIds.value = []
  candidateRowSelectionAnchorId.value = null
  clearCandidateRowClickTimer()
  lastExportSummary.value = null
  resetMissionPreviewState({ clearCache: true, clearMission: true, status: 'no_candidate' })
  bumpPreviewSourceRevision()
}

function buildAnchorBannerMessage(message: string, _source: AnchorChangeSource) {
  if (planForm.planningMode !== 'auto') {
    return message
  }
  return `${message} 已更新手动锚点，自动规划不会使用这些锚点。`
}

function applyAnchorChange(
  mutate: () => { changed: boolean; message: string },
  {
    focusNodeId = null,
    source = 'planner',
  }: {
    focusNodeId?: string | null
    source?: AnchorChangeSource
  } = {},
) {
  const result = mutate()
  if (!result.changed) {
    return false
  }

  if (focusNodeId) {
    focusNodeSelection(focusNodeId)
  } else {
    selectedEdgeId.value = null
  }

  invalidateCandidateOutputs()
  setBanner(buildAnchorBannerMessage(result.message, source), 'info')
  return true
}
function setAnchorRole(
  nodeId: string,
  role: Exclude<AnchorRole, 'via'>,
  source: AnchorChangeSource = 'planner',
) {
  return applyAnchorChange(
    () => {
      if (role === 'start') {
        if (planForm.startNodeId === nodeId) {
          return { changed: false, message: '' }
        }
        planForm.startNodeId = nodeId
        return { changed: true, message: `起点已设为 ${nodeId}` }
      }

      if (planForm.endNodeId === nodeId) {
        return { changed: false, message: '' }
      }
      planForm.endNodeId = nodeId
      return { changed: true, message: `终点已设为 ${nodeId}` }
    },
    { focusNodeId: nodeId, source },
  )
}

function toggleAnchorRole(nodeId: string, role: AnchorRole, source: AnchorChangeSource = 'gesture') {
  return applyAnchorChange(
    () => {
      if (role === 'start') {
        const nextStartNodeId = planForm.startNodeId === nodeId ? '' : nodeId
        if (nextStartNodeId === planForm.startNodeId) {
          return { changed: false, message: '' }
        }
        planForm.startNodeId = nextStartNodeId
        return {
          changed: true,
          message: nextStartNodeId
            ? `起点已设为 ${nodeId}`
            : `已取消起点 ${nodeId}`,
        }
      }

      if (role === 'end') {
        const nextEndNodeId = planForm.endNodeId === nodeId ? '' : nodeId
        if (nextEndNodeId === planForm.endNodeId) {
          return { changed: false, message: '' }
        }
        planForm.endNodeId = nextEndNodeId
        return {
          changed: true,
          message: nextEndNodeId ? `终点已设为 ${nodeId}` : `已取消终点 ${nodeId}`,
        }
      }

      const existingIndex = planForm.viaNodeIds.indexOf(nodeId)
      if (existingIndex >= 0) {
        planForm.viaNodeIds.splice(existingIndex, 1)
        return { changed: true, message: `已移除途经点 ${nodeId}` }
      }

      planForm.viaNodeIds.push(nodeId)
      return { changed: true, message: `已添加途经点 ${nodeId}` }
    },
    { focusNodeId: nodeId, source },
  )
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function setCanvasViewState(nextState: CanvasViewState) {
  canvasViewState.rotationQuadrants = ((nextState.rotationQuadrants % 4) + 4) % 4
  canvasViewState.flipHorizontal = nextState.flipHorizontal
  canvasViewState.flipVertical = nextState.flipVertical
}

function coerceCanvasViewBoolean(value: unknown): boolean | null {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number' && Number.isInteger(value) && (value === 0 || value === 1)) {
    return Boolean(value)
  }
  return null
}

function normalizeCanvasViewState(rawValue: unknown): CanvasViewState {
  const nextState: CanvasViewState = {
    rotationQuadrants: 0,
    flipHorizontal: false,
    flipVertical: false,
  }

  if (!rawValue || typeof rawValue !== 'object') {
    return nextState
  }

  const payload = rawValue as Record<string, unknown>
  if (
    typeof payload.rotation_quadrants === 'number' &&
    Number.isInteger(payload.rotation_quadrants) &&
    payload.rotation_quadrants >= 0 &&
    payload.rotation_quadrants <= 3
  ) {
    nextState.rotationQuadrants = payload.rotation_quadrants
  }
  const flipHorizontal = coerceCanvasViewBoolean(payload.flip_horizontal)
  if (flipHorizontal != null) {
    nextState.flipHorizontal = flipHorizontal
  }
  const flipVertical = coerceCanvasViewBoolean(payload.flip_vertical)
  if (flipVertical != null) {
    nextState.flipVertical = flipVertical
  }
  return nextState
}

function readCanvasViewStateFromGraph(nextGraph: RouteGraph | null): CanvasViewState {
  return normalizeCanvasViewState(nextGraph?.meta?.[CANVAS_VIEW_META_KEY])
}

function computeGraphViewCenter(nextGraph: RouteGraph | null): [number, number] {
  const nodes = nextGraph?.nodes ?? []
  if (nodes.length === 0) {
    return [0, 0]
  }
  const xs = nodes.map((node) => node.position[0])
  const ys = nodes.map((node) => node.position[1])
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]
}

function rotateCanvasViewOffset(
  dx: number,
  dy: number,
  rotationQuadrants: number,
): [number, number] {
  const normalizedRotation = ((rotationQuadrants % 4) + 4) % 4
  if (normalizedRotation === 0) {
    return [dx, dy]
  }
  if (normalizedRotation === 1) {
    return [-dy, dx]
  }
  if (normalizedRotation === 2) {
    return [-dx, -dy]
  }
  return [dy, -dx]
}

function transformCanvasViewPosition(
  position: [number, number, number] | XYPosition,
  nextState: CanvasViewState = canvasViewState,
): XYPosition {
  const [centerX, centerY] = graphViewCenter.value
  const worldX = Array.isArray(position) ? position[0] : position.x
  const worldY = Array.isArray(position) ? position[1] : position.y
  let dx = worldX - centerX
  let dy = worldY - centerY
  ;[dx, dy] = rotateCanvasViewOffset(dx, dy, nextState.rotationQuadrants)
  if (nextState.flipHorizontal) {
    dx = -dx
  }
  if (nextState.flipVertical) {
    dy = -dy
  }
  return {
    x: centerX + dx,
    y: centerY + dy,
  }
}

function inverseCanvasViewPosition(
  position: XYPosition,
  nextState: CanvasViewState = canvasViewState,
): XYPosition {
  const [centerX, centerY] = graphViewCenter.value
  let dx = position.x - centerX
  let dy = position.y - centerY
  if (nextState.flipHorizontal) {
    dx = -dx
  }
  if (nextState.flipVertical) {
    dy = -dy
  }
  ;[dx, dy] = rotateCanvasViewOffset(dx, dy, -nextState.rotationQuadrants)
  return {
    x: centerX + dx,
    y: centerY + dy,
  }
}

function computeCanvasScale(nextGraph: RouteGraph): number {
  if (nextGraph.nodes.length < 2) {
    return 0.02
  }
  const xs = nextGraph.nodes.map((node) => node.position[0])
  const ys = nextGraph.nodes.map((node) => node.position[1])
  const spanX = Math.max(...xs) - Math.min(...xs)
  const spanY = Math.max(...ys) - Math.min(...ys)
  const dominantSpan = Math.max(spanX, spanY, 1)
  return clamp(960 / dominantSpan, 0.008, 0.05)
}

function graphNodeCenterToCanvas(position: [number, number, number]): XYPosition {
  const transformed = transformCanvasViewPosition({
    x: position[0],
    y: position[1],
  })
  return {
    x: transformed.x * canvasScale.value,
    y: transformed.y * -canvasScale.value,
  }
}

function graphToCanvas(position: [number, number, number]): XYPosition {
  const center = graphNodeCenterToCanvas(position)
  return {
    x: center.x - NODE_RADIUS_PX,
    y: center.y - NODE_RADIUS_PX,
  }
}

function canvasToGraph(position: XYPosition, z: number): [number, number, number] {
  const transformed = {
    x: (position.x + NODE_RADIUS_PX) / canvasScale.value,
    y: (position.y + NODE_RADIUS_PX) / -canvasScale.value,
  }
  const world = inverseCanvasViewPosition(transformed)
  return [
    Number(world.x.toFixed(3)),
    Number(world.y.toFixed(3)),
    z,
  ]
}

const previewCanvasPoints = computed<XYPosition[]>(() => {
  if (!previewMission.value?.positions?.length) {
    return []
  }

  const points: XYPosition[] = []
  for (const position of previewMission.value.positions) {
    if (!Array.isArray(position.state) || !Array.isArray(position.state[0])) {
      continue
    }
    const xyz = position.state[0]
    if (xyz.length < 2) {
      continue
    }
    const center = graphNodeCenterToCanvas([
      Number(xyz[0]) || 0,
      Number(xyz[1]) || 0,
      Number(xyz[2]) || 0,
    ])
    points.push(center)
  }
  return points
})

const previewPolylinePoints = computed(() =>
  previewCanvasPoints.value.map((point) => `${point.x},${point.y}`).join(' '),
)

const previewPathMetrics = computed<PreviewPathMetrics | null>(() => {
  const points = previewCanvasPoints.value
  if (points.length < 2) {
    return null
  }

  const segments: PreviewPathSegment[] = []
  let totalLength = 0

  for (let index = 1; index < points.length; index += 1) {
    const start = points[index - 1]
    const end = points[index]
    const dx = end.x - start.x
    const dy = end.y - start.y
    const length = Math.hypot(dx, dy)
    if (length < PREVIEW_CHEVRON_MIN_SEGMENT_PX) {
      continue
    }
    segments.push({
      start,
      dx,
      dy,
      length,
      startDistance: totalLength,
      angleDeg: (Math.atan2(dy, dx) * 180) / Math.PI,
    })
    totalLength += length
  }

  if (!segments.length || totalLength < PREVIEW_CHEVRON_MIN_PATH_PX) {
    return null
  }

  const glyphCount = clamp(
    Math.floor(totalLength / PREVIEW_CHEVRON_DENSITY_PX),
    1,
    PREVIEW_CHEVRON_MAX_GLYPHS,
  )
  const spacing = totalLength / glyphCount

  return {
    segments,
    totalLength,
    glyphCount,
    spacing,
  }
})

function locatePointOnPreviewPath(
  metrics: PreviewPathMetrics,
  distancePx: number,
): { x: number; y: number; angle: number } {
  const { segments, totalLength } = metrics
  if (!segments.length || totalLength <= 0) {
    return { x: 0, y: 0, angle: 0 }
  }

  let normalizedDistance = distancePx % totalLength
  if (normalizedDistance < 0) {
    normalizedDistance += totalLength
  }

  let low = 0
  let high = segments.length - 1
  while (low < high) {
    const middle = Math.floor((low + high + 1) / 2)
    if (segments[middle].startDistance <= normalizedDistance) {
      low = middle
    } else {
      high = middle - 1
    }
  }

  const segment = segments[low]
  const localDistance = clamp(normalizedDistance - segment.startDistance, 0, segment.length)
  const ratio = segment.length > 0 ? localDistance / segment.length : 0
  return {
    x: segment.start.x + segment.dx * ratio,
    y: segment.start.y + segment.dy * ratio,
    angle: segment.angleDeg - 90,
  }
}

const previewChevronGlyphs = computed<PreviewChevronGlyph[]>(() => {
  const metrics = previewPathMetrics.value
  if (!metrics) {
    return []
  }

  const elapsedSeconds = previewFlowNowMs.value / 1000
  const flowOffset =
    metrics.spacing > 0 ? (elapsedSeconds * PREVIEW_FLOW_SPEED_PX_PER_SEC) % metrics.spacing : 0
  const glyphs: PreviewChevronGlyph[] = []
  for (let glyphIndex = 0; glyphIndex < metrics.glyphCount; glyphIndex += 1) {
    const distanceAlongPath = (glyphIndex + 0.5) * metrics.spacing + flowOffset
    const point = locatePointOnPreviewPath(metrics, distanceAlongPath)
    glyphs.push({
      id: `preview-chevron-${glyphIndex}`,
      x: point.x,
      y: point.y,
      angle: point.angle,
      tone: glyphIndex % 2 === 0 ? 'yellow' : 'black',
    })
  }
  return glyphs
})

function stopPreviewFlowTicker() {
  if (previewFlowRafId.value == null) {
    return
  }
  window.cancelAnimationFrame(previewFlowRafId.value)
  previewFlowRafId.value = null
}

function startPreviewFlowTicker() {
  if (previewFlowRafId.value != null) {
    return
  }
  const tick = (timestamp: number) => {
    previewFlowNowMs.value = timestamp
    previewFlowRafId.value = window.requestAnimationFrame(tick)
  }
  previewFlowRafId.value = window.requestAnimationFrame(tick)
}

watch(
  () => previewPathMetrics.value?.totalLength ?? 0,
  (totalLength) => {
    if (totalLength > 0) {
      startPreviewFlowTicker()
      return
    }
    stopPreviewFlowTicker()
    previewFlowNowMs.value = 0
  },
  { immediate: true },
)

const previewOverlayTransform = computed(
  () =>
    `translate(${viewportTransform.value.x} ${viewportTransform.value.y}) scale(${viewportTransform.value.zoom})`,
)

function stopAtmosphereWaveAnimation() {
  if (atmosphereWaveRafId.value == null) {
    return
  }
  window.cancelAnimationFrame(atmosphereWaveRafId.value)
  atmosphereWaveRafId.value = null
}

function resizeAtmosphereWaveCanvas() {
  const canvas = atmosphereWaveCanvas.value
  if (!canvas) {
    return
  }
  const cssWidth = Math.max(canvas.clientWidth, 1)
  const cssHeight = Math.max(canvas.clientHeight, 1)
  const dpr = clamp(window.devicePixelRatio || 1, 1, 2)
  const renderWidth = Math.max(Math.round(cssWidth * dpr), 1)
  const renderHeight = Math.max(Math.round(cssHeight * dpr), 1)
  if (canvas.width === renderWidth && canvas.height === renderHeight) {
    return
  }
  canvas.width = renderWidth
  canvas.height = renderHeight
}

function drawAtmosphereWaveFrame(timestamp: number) {
  const canvas = atmosphereWaveCanvas.value
  if (!canvas || atmosphereWaveReducedMotion.value) {
    atmosphereWaveRafId.value = null
    return
  }
  resizeAtmosphereWaveCanvas()
  const context = canvas.getContext('2d')
  if (!context) {
    atmosphereWaveRafId.value = null
    return
  }

  const cssWidth = Math.max(canvas.clientWidth, 1)
  const cssHeight = Math.max(canvas.clientHeight, 1)
  const dpr = canvas.width / cssWidth
  const spacing = 42
  const halfSpacing = spacing / 2
  const diagonalWavelengthInSteps = 11
  const amplitudePx = 12
  const speedCyclePerSecond = 0.22
  const directionX = -Math.SQRT1_2
  const directionY = Math.SQRT1_2
  const elapsedSeconds = timestamp / 1000

  context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.setTransform(dpr, 0, 0, dpr, 0, 0)

  const layers = [
    { offsetX: 0, offsetY: 0, radius: 1.45, color: 'rgba(98, 74, 50, 0.56)' },
    {
      offsetX: halfSpacing,
      offsetY: halfSpacing,
      radius: 1.1,
      color: 'rgba(181, 153, 126, 0.42)',
    },
  ] as const

  for (const layer of layers) {
    context.fillStyle = layer.color
    let iy = -1
    for (let y = layer.offsetY - spacing; y <= cssHeight + spacing; y += spacing) {
      let ix = -1
      for (let x = layer.offsetX - spacing; x <= cssWidth + spacing; x += spacing) {
        const diagonalIndex = ix + iy
        const phase =
          (diagonalIndex / diagonalWavelengthInSteps) - (elapsedSeconds * speedCyclePerSecond)
        const displacement = Math.sin(phase * Math.PI * 2) * amplitudePx
        const drawX = x + displacement * directionX
        const drawY = y + displacement * directionY
        context.beginPath()
        context.arc(drawX, drawY, layer.radius, 0, Math.PI * 2)
        context.fill()
        ix += 1
      }
      iy += 1
    }
  }

  atmosphereWaveRafId.value = window.requestAnimationFrame(drawAtmosphereWaveFrame)
}

function startAtmosphereWaveAnimation() {
  if (atmosphereWaveReducedMotion.value || atmosphereWaveRafId.value != null) {
    return
  }
  atmosphereWaveRafId.value = window.requestAnimationFrame(drawAtmosphereWaveFrame)
}

function handleAtmosphereWaveMotionPreferenceChange(event: MediaQueryListEvent) {
  atmosphereWaveReducedMotion.value = event.matches
  if (event.matches) {
    stopAtmosphereWaveAnimation()
    const canvas = atmosphereWaveCanvas.value
    const context = canvas?.getContext('2d')
    if (canvas && context) {
      context.setTransform(1, 0, 0, 1, 0, 0)
      context.clearRect(0, 0, canvas.width, canvas.height)
    }
    return
  }
  startAtmosphereWaveAnimation()
}

function setupAtmosphereWaveBackground() {
  if (typeof window === 'undefined') {
    return
  }
  resizeAtmosphereWaveCanvas()
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(() => {
      resizeAtmosphereWaveCanvas()
    })
    atmosphereWaveResizeObserver.value = observer
    if (atmosphereWaveCanvas.value) {
      observer.observe(atmosphereWaveCanvas.value)
    }
  }
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  atmosphereWaveMotionQuery.value = motionQuery
  atmosphereWaveReducedMotion.value = motionQuery.matches
  motionQuery.addEventListener('change', handleAtmosphereWaveMotionPreferenceChange)
  startAtmosphereWaveAnimation()
}

function cleanupAtmosphereWaveBackground() {
  stopAtmosphereWaveAnimation()
  if (atmosphereWaveResizeObserver.value) {
    atmosphereWaveResizeObserver.value.disconnect()
    atmosphereWaveResizeObserver.value = null
  }
  if (atmosphereWaveMotionQuery.value) {
    atmosphereWaveMotionQuery.value.removeEventListener(
      'change',
      handleAtmosphereWaveMotionPreferenceChange,
    )
    atmosphereWaveMotionQuery.value = null
  }
}

function parseOptionalNumber(rawValue: string, label: string): number | null {
  const text = rawValue.trim()
  if (!text) {
    return null
  }
  const value = Number(text)
  if (!Number.isFinite(value)) {
    throw new Error(`${label} 必须是数字`)
  }
  return value
}

function parseRequiredPositiveNumber(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number {
  const value = parseOptionalNumber(rawValue, label)
  if (value == null) {
    throw new Error(`${label} 不能为空`)
  }
  if ((!allowZero && value <= 0) || (allowZero && value < 0)) {
    throw new Error(`${label} 必须${allowZero ? '大于等于 0' : '大于 0'}`)
  }
  return value
}

function parseOptionalInteger(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number | null {
  const text = rawValue.trim()
  if (!text) {
    return null
  }
  const value = Number(text)
  if (!Number.isInteger(value)) {
    throw new Error(`${label} 必须是整数`)
  }
  if ((!allowZero && value <= 0) || (allowZero && value < 0)) {
    throw new Error(`${label} 必须${allowZero ? '大于等于 0' : '大于 0'}`)
  }
  return value
}

function parseRequiredInteger(
  rawValue: string,
  label: string,
  { allowZero = false }: { allowZero?: boolean } = {},
): number {
  const value = parseOptionalInteger(rawValue, label, { allowZero })
  if (value == null) {
    throw new Error(`${label} 不能为空`)
  }
  return value
}

function buildMissionGeometryInputsSnapshot() {
  return buildMissionGeometryInputsSnapshotPure(exportForm)
}

function buildMissionConfigRequestPayload() {
  return buildMissionConfigRequestPayloadPure(exportForm, DEFAULT_SMOOTHING_INPUTS)
}

function buildMissionPreviewCacheKey(candidateId: string) {
  return JSON.stringify({
    graph: currentGraphPath.value,
    candidate_id: candidateId,
    mission_inputs: buildMissionGeometryInputsSnapshot(),
    [GRAPH_GROUP_CONFIGS_META_KEY]: candidateSet.value?.meta[GRAPH_GROUP_CONFIGS_META_KEY] ?? {},
  })
}

function clearPreviewRefreshTimer() {
  missionPreview.clearPreviewRefreshTimer()
}

function resetMissionPreviewState(
  {
    clearCache = false,
    clearMission = true,
    status = 'no_candidate' as MissionPreviewStatus,
  }: {
    clearCache?: boolean
    clearMission?: boolean
    status?: MissionPreviewStatus
  } = {},
) {
  previewRequestSequence.value += 1
  missionPreview.resetMissionPreviewState({ clearCache, clearMission, status })
}

function bumpPreviewSourceRevision() {
  missionPreview.bumpPreviewSourceRevision()
}

function syncViewportTransformFromFlow() {
  try {
    viewportTransform.value = getViewport()
  } catch {
    // Vue Flow may not be ready during the first render tick.
  }
}

function handleViewportChange(nextViewport: ViewportTransform) {
  viewportTransform.value = { ...nextViewport }
}

async function refreshMissionPreview({
  force = false,
  showErrors = false,
}: {
  force?: boolean
  showErrors?: boolean
} = {}) {
  if (!candidateSet.value || !selectedCandidateId.value) {
    resetMissionPreviewState({ clearMission: true, status: 'no_candidate' })
    return false
  }

  const candidateId = selectedCandidateId.value
  const graphPath = currentGraphPath.value
  let missionConfig: ReturnType<typeof buildMissionConfigRequestPayload>

  try {
    missionConfig = buildMissionConfigRequestPayload()
  } catch (error) {
    const message = error instanceof Error ? error.message : '轨迹预览参数无效'
    previewLoading.value = false
    previewError.value = message
    previewStatus.value = 'error'
    if (showErrors) {
      setBanner(`轨迹预览失败：${message}`, 'error')
    }
    return false
  }

  const cacheKey = buildMissionPreviewCacheKey(candidateId)
  if (!force) {
    const cachedMission = getCachedMissionPreview(cacheKey)
    if (cachedMission) {
      previewMission.value = cachedMission
      previewStatus.value = 'cached'
      previewError.value = ''
      previewLoading.value = false
      return true
    }
  }

  const requestSequence = previewRequestSequence.value + 1
  previewRequestSequence.value = requestSequence
  previewLoading.value = true
  previewError.value = ''

  try {
    const response = await fetchMissionPreview({
      candidate_set: candidateSet.value,
      candidate_id: candidateId,
      ...missionConfig,
    })

    if (
      requestSequence !== previewRequestSequence.value ||
      currentGraphPath.value !== graphPath ||
      selectedCandidateId.value !== candidateId
    ) {
      return false
    }

    setCachedMissionPreview(cacheKey, response.mission)
    previewMission.value = response.mission
    previewStatus.value = 'ready'
    previewLoading.value = false
    previewError.value = ''
    return true
  } catch (error) {
    if (
      requestSequence !== previewRequestSequence.value ||
      currentGraphPath.value !== graphPath ||
      selectedCandidateId.value !== candidateId
    ) {
      return false
    }

    const message = error instanceof Error ? error.message : '轨迹预览失败'
    previewLoading.value = false
    previewError.value = message
    previewStatus.value = 'error'
    if (showErrors) {
      setBanner(`轨迹预览失败：${message}`, 'error')
    }
    return false
  }
}

function scheduleMissionPreviewRefresh({
  force = false,
  showErrors = false,
}: {
  force?: boolean
  showErrors?: boolean
} = {}) {
  clearPreviewRefreshTimer()

  if (!candidateSet.value || !selectedCandidateId.value) {
    resetMissionPreviewState({ clearMission: true, status: 'no_candidate' })
    return
  }

  const candidateId = selectedCandidateId.value
  if (!force) {
    const cachedMission = getCachedMissionPreview(buildMissionPreviewCacheKey(candidateId))
    if (cachedMission) {
      previewMission.value = cachedMission
      previewStatus.value = 'cached'
      previewError.value = ''
      previewLoading.value = false
      return
    }
  }

  const previewCandidateId =
    previewRouteMeta.value && typeof previewRouteMeta.value.candidate_id === 'string'
      ? String(previewRouteMeta.value.candidate_id)
      : null

  if (previewCandidateId !== candidateId) {
    previewMission.value = null
  }

  previewStatus.value = 'stale'
  previewError.value = ''
  previewLoading.value = true
  missionPreview.schedulePreviewRefresh(() => {
    void refreshMissionPreview({ force, showErrors })
  }, 320)
}

async function forceRefreshMissionPreview() {
  if (!candidateSet.value || !selectedCandidateId.value) {
    setBanner('请先选中一条候选路线', 'error')
    return
  }

  const cacheKey = buildMissionPreviewCacheKey(selectedCandidateId.value)
  deleteCachedMissionPreview(cacheKey)
  const refreshed = await refreshMissionPreview({ force: true, showErrors: true })
  if (refreshed) {
    setBanner('已刷新轨迹预览', 'success')
  }
}

function parseTagList(rawValue: string): string[] {
  return rawValue
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function syncCandidateSelections() {
  if (!candidateSet.value) {
    return
  }
  candidateSet.value.selected_candidate_ids = candidateSet.value.candidates
    .filter((candidate) => candidate.selected)
    .map((candidate) => candidate.candidate_id)
}

function upsertGraphSummary(summary: GraphSummary) {
  upsertGraphSummaryInState(summary)
  graphCatalog.value.sort((left, right) => left.graph_name.localeCompare(right.graph_name))
}

function normalizePlanAnchors(nextGraph: RouteGraph) {
  const nodeIds = new Set(nextGraph.nodes.map((node) => node.id))

  if (planForm.startNodeId && !nodeIds.has(planForm.startNodeId)) {
    planForm.startNodeId = ''
  }
  if (planForm.endNodeId && !nodeIds.has(planForm.endNodeId)) {
    planForm.endNodeId = ''
  }

  const nextViaNodeIds: string[] = []
  const seenViaNodeIds = new Set<string>()
  for (const nodeId of planForm.viaNodeIds) {
    if (!nodeIds.has(nodeId) || seenViaNodeIds.has(nodeId)) {
      continue
    }
    nextViaNodeIds.push(nodeId)
    seenViaNodeIds.add(nodeId)
  }
  planForm.viaNodeIds = nextViaNodeIds
}

async function fitGraphToViewport() {
  await nextTick()
  try {
    await fitView({ duration: 320, padding: 0.18 })
    syncViewportTransformFromFlow()
  } catch {
    // Vue Flow may not be ready on the first tick.
  }
}

async function requestFitGraphToViewport() {
  if (viewportLocked.value) {
    setBanner('画布视口已锁定', 'info')
    return
  }
  await fitGraphToViewport()
}

function setViewportLockState(
  nextLocked: boolean,
  {
    persist = true,
    announce = false,
  }: {
    persist?: boolean
    announce?: boolean
  } = {},
) {
  viewportLocked.value = nextLocked
  if (persist) {
    writeStoredViewportLock(nextLocked)
  }
  if (announce) {
    setBanner(nextLocked ? '画布视口已锁定' : '画布视口已解锁', 'info')
  }
}

function toggleViewportLock() {
  setViewportLockState(!viewportLocked.value, { announce: true })
}

function handleViewportZoomIn() {
  if (viewportLocked.value) {
    return
  }
  void zoomIn({ duration: 180 }).then(() => {
    syncViewportTransformFromFlow()
  })
}

function handleViewportZoomOut() {
  if (viewportLocked.value) {
    return
  }
  void zoomOut({ duration: 180 }).then(() => {
    syncViewportTransformFromFlow()
  })
}

function buildCanvasViewPayload(nextState: CanvasViewState) {
  return {
    rotation_quadrants: nextState.rotationQuadrants,
    flip_horizontal: nextState.flipHorizontal,
    flip_vertical: nextState.flipVertical,
  }
}

async function persistCanvasViewState(
  nextState: CanvasViewState,
  {
    fit = false,
  }: {
    fit?: boolean
  } = {},
) {
  if (!currentGraphPath.value) {
    return
  }

  updatingCanvasView.value = true
  try {
    const envelope = await updateCanvasView({
      graph: currentGraphPath.value,
      ...buildCanvasViewPayload(nextState),
    })
    applyGraphEnvelope(envelope, { fit: fit && !viewportLocked.value, preserveCandidateSet: true })
  } catch (error) {
    const message = error instanceof Error ? error.message : '更新画布视图失败'
    setBanner(message, 'error')
    try {
      const envelope = await fetchGraph(currentGraphPath.value)
      applyGraphEnvelope(envelope, { preserveCandidateSet: true })
    } catch {
      // Keep the existing canvas state if the refresh also fails.
    }
  } finally {
    updatingCanvasView.value = false
  }
}

function snapshotNodePositions(nodes: GraphNode[]) {
  const baseline = new Map<string, [number, number, number]>()
  for (const node of nodes) {
    baseline.set(node.id, [...node.position] as [number, number, number])
  }
  return baseline
}

function resetNodeInteractionState(envelope: GraphEnvelope) {
  nodePositionBaseline.value = snapshotNodePositions(envelope.graph.nodes)
  nodeDragEnabled.value = false
}

function syncCandidateSetGraphMeta(envelope: GraphEnvelope) {
  if (!candidateSet.value) {
    return
  }
  const graphMeta = envelope.graph.meta ?? {}
  const nextCandidateMeta = {
    ...candidateSet.value.meta,
    [GRAPH_GROUP_CONFIGS_META_KEY]:
      typeof graphMeta[GRAPH_GROUP_CONFIGS_META_KEY] === 'object' &&
      graphMeta[GRAPH_GROUP_CONFIGS_META_KEY]
        ? graphMeta[GRAPH_GROUP_CONFIGS_META_KEY]
        : {},
    [GRAPH_BRIDGE_STYLE_META_KEY]:
      typeof graphMeta[GRAPH_BRIDGE_STYLE_META_KEY] === 'object' &&
      graphMeta[GRAPH_BRIDGE_STYLE_META_KEY]
        ? graphMeta[GRAPH_BRIDGE_STYLE_META_KEY]
        : {},
  }
  candidateSet.value = {
    ...candidateSet.value,
    meta: nextCandidateMeta,
  }
}

function toggleNodeDragEnabled() {
  if (isPaintModeActive.value) {
    setBanner('染色模式下不能开启节点拖拽。', 'error')
    return
  }
  nodeDragEnabled.value = !nodeDragEnabled.value
}

function applyGraphEnvelope(
  envelope: GraphEnvelope,
  {
    fit = false,
    preserveCandidateSet = false,
  }: {
    fit?: boolean
    preserveCandidateSet?: boolean
  } = {},
) {
  applyGraphEnvelopeToState(envelope)
  setCanvasViewState(readCanvasViewStateFromGraph(envelope.graph))
  canvasScale.value = computeCanvasScale(envelope.graph)
  upsertGraphSummary(envelope.summary)
  normalizePlanAnchors(envelope.graph)

  const nodeIds = new Set(envelope.graph.nodes.map((node) => node.id))
  const edgeIds = new Set(envelope.graph.edges.map((edge) => edge.id))
  const nextSelectedNodeIds = selectedNodeIds.value.filter((nodeId) => nodeIds.has(nodeId))
  const nextSelectedEdgeId =
    selectedEdgeId.value && edgeIds.has(selectedEdgeId.value) ? selectedEdgeId.value : null

  const nextPrimaryNodeId =
    primarySelectedNodeId.value && nextSelectedNodeIds.includes(primarySelectedNodeId.value)
      ? primarySelectedNodeId.value
      : (nextSelectedNodeIds[nextSelectedNodeIds.length - 1] ?? null)

  if (nextSelectedNodeIds.length === 0 && !nextSelectedEdgeId) {
    const fallbackNodeId = envelope.graph.nodes[0]?.id ?? null
    setNodeSelection(fallbackNodeId ? [fallbackNodeId] : [], fallbackNodeId)
  } else {
    setNodeSelection(nextSelectedNodeIds, nextPrimaryNodeId)
  }
  selectedEdgeId.value = nextSelectedEdgeId

  if (!preserveCandidateSet) {
    invalidateCandidateOutputs()
  } else if (
    selectedCandidateId.value &&
    !candidateSet.value?.candidates.some(
      (candidate) => candidate.candidate_id === selectedCandidateId.value,
    )
  ) {
    selectedCandidateId.value = candidateSet.value?.candidates[0]?.candidate_id ?? null
    syncCandidateSetGraphMeta(envelope)
  } else {
    syncCandidateSetGraphMeta(envelope)
  }

  if (fit) {
    void fitGraphToViewport()
  }
}

async function loadGraphState(
  graphPath?: string,
  {
    fit = false,
    quiet = false,
  }: {
    fit?: boolean
    quiet?: boolean
  } = {},
): Promise<AutoPlanRestoreOutcome> {
  await flushGroupConfigAutosave()
  loadingGraph.value = true
  hydratingGraphUiState.value = true
  clearGraphUiStateAutosaveTimer()
  clearGroupConfigAutosaveTimer()
  if (!quiet) {
    clearBanner()
  }

  try {
    const envelope = await fetchGraph(graphPath)
    const previousGraphPath = currentGraphPath.value
    resetTrackedAutoPlanState()
    applyGraphEnvelope(envelope, { fit })
    applyGraphUiState(envelope.ui_state)
    resetNodeInteractionState(envelope)
    if (!previousGraphPath || previousGraphPath !== envelope.path) {
      sessionPaletteColors.value = []
      paintModeEnabled.value = false
      newPaletteColor.value = groupColorOptions.value[0] ?? '#334155'
    }
    const restoreOutcome = await restoreAutoPlanJobForGraph(envelope.path)
    try {
      await updateLastGraph({ graph: envelope.path })
    } catch (error) {
      const message = error instanceof Error ? error.message : '保存最近打开图失败'
      setBanner(`保存最近打开图失败：${message}`, 'error')
    }
    if (!quiet) {
      if (restoreOutcome === 'none') {
        setBanner(`已加载图 ${envelope.summary.graph_name}`, 'success')
      }
    }
    return restoreOutcome
  } catch (error) {
    hydratingGraphUiState.value = false
    const message = error instanceof Error ? error.message : '加载图失败'
    setBanner(message, 'error')
    return 'failed'
  } finally {
    loadingGraph.value = false
  }
}

async function initialize() {
  try {
    const shouldRestoreViewportLock = readStoredViewportLock()
    setViewportLockState(false, { persist: false })
    const catalog = await fetchGraphCatalog()
    graphCatalog.value = [...catalog.graphs]
    const restoreOutcome = await loadGraphState(catalog.default_graph, { fit: false, quiet: true })
    if (graphEnvelope.value) {
      await fitGraphToViewport()
      setViewportLockState(shouldRestoreViewportLock, { persist: false })
    }
    if (graphEnvelope.value && restoreOutcome === 'none') {
      setBanner(`网页控制台已就绪，当前图：${graphEnvelope.value.summary.graph_name}`, 'success')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '初始化失败'
    setBanner(message, 'error')
  }
}

async function initializeWithRetry() {
  for (let attempt = 1; attempt <= INITIALIZE_MAX_ATTEMPTS; attempt += 1) {
    await initialize()

    if (graphEnvelope.value && graphCatalog.value.length > 0) {
      return
    }

    if (attempt >= INITIALIZE_MAX_ATTEMPTS) {
      const message = bannerMessage.value || '后端未能就绪。'
      setBanner(`后端未能就绪：${message}`, 'error')
      return
    }

    setBanner(`后端启动中，正在重试（${attempt}/${INITIALIZE_MAX_ATTEMPTS}）...`, 'info')
    await sleep(INITIALIZE_RETRY_DELAY_MS)
  }
}

function handleGraphPicker(event: Event) {
  const target = event.target as HTMLSelectElement | null
  if (!target?.value) {
    return
  }
  void loadGraphState(target.value, { fit: true })
}

async function refreshCurrentGraph() {
  const restoreOutcome = await loadGraphState(currentGraphPath.value || undefined, { quiet: true })
  if (graphEnvelope.value && restoreOutcome === 'none') {
    setBanner(`已刷新 ${graphEnvelope.value.summary.graph_name}`, 'success')
  }
}

function rotateCanvasLeft() {
  void persistCanvasViewState({
    rotationQuadrants: (canvasViewState.rotationQuadrants + 3) % 4,
    flipHorizontal: canvasViewState.flipHorizontal,
    flipVertical: canvasViewState.flipVertical,
  })
}

function rotateCanvasRight() {
  void persistCanvasViewState({
    rotationQuadrants: (canvasViewState.rotationQuadrants + 1) % 4,
    flipHorizontal: canvasViewState.flipHorizontal,
    flipVertical: canvasViewState.flipVertical,
  })
}

function toggleCanvasFlipHorizontal() {
  void persistCanvasViewState({
    rotationQuadrants: canvasViewState.rotationQuadrants,
    flipHorizontal: !canvasViewState.flipHorizontal,
    flipVertical: canvasViewState.flipVertical,
  })
}

function toggleCanvasFlipVertical() {
  void persistCanvasViewState({
    rotationQuadrants: canvasViewState.rotationQuadrants,
    flipHorizontal: canvasViewState.flipHorizontal,
    flipVertical: !canvasViewState.flipVertical,
  })
}

function resetCanvasView() {
  void persistCanvasViewState(
    {
      rotationQuadrants: 0,
      flipHorizontal: false,
      flipVertical: false,
    },
    { fit: true },
  )
}

async function runGraphValidation() {
  if (!currentGraphPath.value) {
    return
  }
  validatingGraph.value = true
  try {
    const result = await validateGraph(currentGraphPath.value)
    if (result.is_valid) {
      setBanner('图校验通过，没有阻断性错误', 'success')
    } else {
      setBanner(
        `图校验发现 ${result.error_count} 个错误，${result.warning_count} 个警告`,
        'error',
      )
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : '图校验失败'
    setBanner(message, 'error')
  } finally {
    validatingGraph.value = false
  }
}

function handlePaneClick() {}

function handleNodeClick(payload: NodeMouseEvent) {
  if (isPaintModeActive.value) {
    return
  }
  if (isMouseEvent(payload.event) && payload.event.shiftKey) {
    toggleNodeSelection(payload.node.id)
    return
  }
  selectOnlyNode(payload.node.id)
}

function handleNodeDoubleClick(payload: NodeMouseEvent) {
  if (isPaintModeActive.value) {
    return
  }
  toggleAnchorRole(payload.node.id, 'start', 'gesture')
}

function handleNodeContextMenu(payload: NodeMouseEvent) {
  if (isPaintModeActive.value) {
    return
  }
  if (!isMouseEvent(payload.event)) {
    return
  }
  payload.event.preventDefault()
  commitNodeGesture(secondaryNodeGesture, payload.node.id, () => {
    toggleAnchorRole(payload.node.id, 'end', 'gesture')
  })
}

function handleNodeMiddleButtonGesture(nodeId: string, event: MouseEvent) {
  if (isPaintModeActive.value) {
    return
  }
  event.preventDefault()
  commitNodeGesture(middleNodeGesture, nodeId, () => {
    toggleAnchorRole(nodeId, 'via', 'gesture')
  })
}

async function handleEdgeClick(payload: EdgeMouseEvent) {
  if (isPaintModeActive.value) {
    selectEdge(payload.edge.id)
    await paintEdgeWithCurrentColor(payload.edge.id)
    return
  }
  if (isMouseEvent(payload.event) && payload.event.shiftKey) {
    return
  }
  selectEdge(payload.edge.id)
}

async function handleNodeDragStop(payload: NodeDragEvent) {
  if (!nodeDragEnabled.value || isPaintModeActive.value) {
    return
  }
  const node = graphNodeMap.value.get(payload.node.id)
  if (!graph.value || !node) {
    return
  }
  const [x, y] = canvasToGraph(payload.node.position, node.position[2])
  try {
    await runGraphMutation(moveNode, {
      graph: currentGraphPath.value,
      node_id: node.id,
      x,
      y,
    })
    setBanner(`节点 ${node.id} 坐标已保存`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存节点坐标失败'
    setBanner(message, 'error')
    await loadGraphState(currentGraphPath.value, { quiet: true })
  }
}

async function resetSelectedNodePosition() {
  if (!selectedNode.value || !selectedNodePositionBaseline.value) {
    return
  }
  const nodeId = selectedNode.value.id
  const [x, y] = selectedNodePositionBaseline.value
  resettingNodePosition.value = true
  try {
    await runGraphMutation(moveNode, {
      graph: currentGraphPath.value,
      node_id: nodeId,
      x,
      y,
    })
    setBanner(`节点 ${nodeId} 已重置到载入位置`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '重置节点坐标失败'
    setBanner(message, 'error')
    await loadGraphState(currentGraphPath.value, { quiet: true })
  } finally {
    resettingNodePosition.value = false
  }
}

function resolveEdgeCreationIntent(fromNodeId: string, toNodeId: string) {
  return resolveSharedEdgeCreationIntent(
    fromNodeId,
    toNodeId,
    graphColorGrouping.value,
    paintColor.value ?? activeGroupColor.value,
    { group: EDGE_KIND_GROUP, bridge: EDGE_KIND_BRIDGE },
  )
}

async function createEdgeBetweenNodes(fromNodeId: string, toNodeId: string) {
  const intent = resolveEdgeCreationIntent(fromNodeId, toNodeId)
  const envelope = await addEdge({
    graph: currentGraphPath.value,
    from_node: fromNodeId,
    to_node: toNodeId,
    bidirectional: true,
    edge_kind: intent.edge_kind,
    group_color: intent.group_color,
  })
  if (intent.group_color) {
    activeGroupColor.value = intent.group_color
    await setPaintColorSelection(intent.group_color)
  }
  return envelope
}

async function createSelectedEdge() {
  if (selectedNodeIds.value.length !== 2) {
    setBanner('请先选中恰好两个节点。', 'error')
    return
  }
  mutatingEdge.value = true
  try {
    const [fromNodeId, toNodeId] = selectedNodeIds.value
    const envelope = await createEdgeBetweenNodes(fromNodeId, toNodeId)
    applyGraphEnvelope(envelope)
    setBanner(`已新增边 ${fromNodeId} ↔ ${toNodeId}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '创建边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

async function deleteSelectedEdgeOrBetween() {
  if (selectedEdge.value) {
    await deleteSelectedEdge()
    return
  }
  if (selectedNodeIds.value.length !== 2) {
    setBanner('请先选中一条边，或恰好选中两个节点。', 'error')
    return
  }
  mutatingEdge.value = true
  try {
    const [fromNodeId, toNodeId] = selectedNodeIds.value
    await runGraphMutation(removeEdgeBetween, {
      graph: currentGraphPath.value,
      from_node: fromNodeId,
      to_node: toNodeId,
    })
    setBanner(`已删除 ${fromNodeId} 与 ${toNodeId} 之间的边`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '删除边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

async function handleConnect(connection: Connection) {
  if (isPaintModeActive.value) {
    return
  }
  if (!connection.source || !connection.target) {
    return
  }
  try {
    const envelope = await createEdgeBetweenNodes(connection.source, connection.target)
    applyGraphEnvelope(envelope)
    setBanner(`已新增边 ${connection.source} ↔ ${connection.target}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '新增边失败'
    setBanner(message, 'error')
  }
}

async function submitNodeUpdate() {
  if (!selectedNode.value) {
    return
  }
  savingNode.value = true
  try {
    await runGraphMutation(updateNode, {
      graph: currentGraphPath.value,
      node_id: selectedNode.value.id,
      name: nodeDraft.name.trim() || selectedNode.value.id,
      tags: parseTagList(nodeDraft.tagsText),
      yaw_hint: parseOptionalNumber(nodeDraft.yawHint, '航向提示'),
      sample_radius: parseOptionalNumber(nodeDraft.sampleRadius, '采样半径覆盖'),
    })
    setBanner(`节点 ${selectedNode.value.id} 属性已保存`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存节点失败'
    setBanner(message, 'error')
  } finally {
    savingNode.value = false
  }
}

async function paintEdgeWithCurrentColor(edgeId?: string | null) {
  const targetEdgeId = edgeId ?? selectedEdge.value?.id ?? null
  if (!targetEdgeId) {
    setBanner('请先选中一条边。', 'error')
    return
  }
  if (!paintColor.value) {
    setBanner('请先从调色盘选择一个颜色。', 'error')
    return
  }
  mutatingEdge.value = true
  try {
    const normalizedColor = parseRequiredHexColor(paintColor.value, '组颜色')
    await runGraphMutation(updateEdge, {
      graph: currentGraphPath.value,
      edge_id: targetEdgeId,
      edge_kind: EDGE_KIND_GROUP,
      group_color: normalizedColor,
    })
    activeGroupColor.value = normalizedColor
    await setPaintColorSelection(normalizedColor)
    selectEdge(targetEdgeId)
    setBanner(`已将边 ${targetEdgeId} 染成 ${normalizedColor}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '染边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

async function setSelectedEdgeBridge() {
  if (!selectedEdge.value) {
    setBanner('请先选中一条边。', 'error')
    return
  }
  mutatingEdge.value = true
  try {
    await runGraphMutation(updateEdge, {
      graph: currentGraphPath.value,
      edge_id: selectedEdge.value.id,
      edge_kind: EDGE_KIND_BRIDGE,
      group_color: null,
    })
    setBanner(`边 ${selectedEdge.value.id} 已设为桥接边`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '设置桥接边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

async function applyBridgeColor() {
  if (!currentGraphPath.value) {
    return
  }
  try {
    const normalizedColor = parseRequiredHexColor(bridgeColorDraft.value, '桥接边颜色')
    const envelope = await updateGraphGroupConfig({
      graph: currentGraphPath.value,
      bridge_color: normalizedColor,
    })
    applyGraphEnvelope(envelope, { preserveCandidateSet: true })
    bridgeColorDraft.value = normalizedColor
    setBanner(`桥接边颜色已更新为 ${normalizedColor}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存桥接边颜色失败'
    setBanner(message, 'error')
  }
}

async function patchEdge(payload: { enabled?: boolean; bidirectional?: boolean }) {
  if (!selectedEdge.value) {
    return
  }
  mutatingEdge.value = true
  try {
    await runGraphMutation(updateEdge, {
      graph: currentGraphPath.value,
      edge_id: selectedEdge.value.id,
      ...payload,
    })
    setBanner(`边 ${selectedEdge.value.id} 已更新`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '更新边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

async function deleteSelectedEdge() {
  if (!selectedEdge.value) {
    return
  }
  mutatingEdge.value = true
  try {
    const removedEdgeId = selectedEdge.value.id
    await runGraphMutation(removeEdge, {
      graph: currentGraphPath.value,
      edge_id: removedEdgeId,
    })
    selectedEdgeId.value = null
    setBanner(`边 ${removedEdgeId} 已删除`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '删除边失败'
    setBanner(message, 'error')
  } finally {
    mutatingEdge.value = false
  }
}

function assignSelectedNodeAsStart() {
  if (!selectedNode.value) {
    return
  }
  toggleAnchorRole(selectedNode.value.id, 'start', 'inspector')
}

function assignSelectedNodeAsEnd() {
  if (!selectedNode.value) {
    return
  }
  toggleAnchorRole(selectedNode.value.id, 'end', 'inspector')
}

function toggleSelectedNodeAsVia() {
  if (!selectedNode.value) {
    return
  }
  toggleAnchorRole(selectedNode.value.id, 'via', 'inspector')
}

function removeViaNode(nodeId: string) {
  applyAnchorChange(
    () => {
      if (!planForm.viaNodeIds.includes(nodeId)) {
        return { changed: false, message: '' }
      }
      planForm.viaNodeIds = planForm.viaNodeIds.filter((item) => item !== nodeId)
      return { changed: true, message: `已移除途经点 ${nodeId}` }
    },
    { focusNodeId: nodeId, source: 'planner' },
  )
}

function resetRouteAnchors() {
  const nodes = graph.value?.nodes ?? []
  const fallbackStartNodeId = nodes[0]?.id ?? ''
  const fallbackEndNodeId = nodes[nodes.length - 1]?.id ?? fallbackStartNodeId
  applyAnchorChange(
    () => {
      const changed =
        planForm.startNodeId !== fallbackStartNodeId ||
        planForm.endNodeId !== fallbackEndNodeId ||
        planForm.viaNodeIds.length > 0
      planForm.startNodeId = fallbackStartNodeId
      planForm.endNodeId = fallbackEndNodeId
      planForm.viaNodeIds = []
      return { changed, message: '已重置起点、终点和途经点' }
    },
    { focusNodeId: fallbackStartNodeId || fallbackEndNodeId || null, source: 'reset' },
  )
}

function handleManualStartNodeChange(event: Event) {
  const target = event.target as HTMLSelectElement | null
  if (!target) {
    return
  }
  if (!target.value) {
    applyAnchorChange(
      () => {
        const changed = planForm.startNodeId !== ''
        planForm.startNodeId = ''
        return { changed, message: '已清除起点' }
      },
      { focusNodeId: selectedNode.value?.id ?? null, source: 'planner' },
    )
    return
  }
  setAnchorRole(target.value, 'start', 'planner')
}

function handleManualEndNodeChange(event: Event) {
  const target = event.target as HTMLSelectElement | null
  if (!target) {
    return
  }
  if (!target.value) {
    applyAnchorChange(
      () => {
        const changed = planForm.endNodeId !== ''
        planForm.endNodeId = ''
        return { changed, message: '已清除终点' }
      },
      { focusNodeId: selectedNode.value?.id ?? null, source: 'planner' },
    )
    return
  }
  setAnchorRole(target.value, 'end', 'planner')
}

function buildAutoPlanningPayload() {
  const minTotalLength = parseOptionalNumber(planForm.minTotalLength, '自动规划最小总长度')
  const maxTotalLength = parseOptionalNumber(planForm.maxTotalLength, '自动规划最大总长度')
  const minFrameCount = parseOptionalInteger(planForm.autoMinFrameCount, '自动规划最小帧数')
  const maxFrameCount = parseOptionalInteger(planForm.autoMaxFrameCount, '自动规划最大帧数')
  const missionConfig = buildMissionConfigRequestPayload()
  if (minTotalLength != null && maxTotalLength != null && minTotalLength > maxTotalLength) {
    throw new Error('自动规划最小总长度必须小于或等于最大总长度')
  }
  if (minFrameCount != null && maxFrameCount != null && minFrameCount > maxFrameCount) {
    throw new Error('自动规划最小帧数必须小于或等于最大帧数')
  }
  return {
    graph: currentGraphPath.value || undefined,
    max_output_routes: parseRequiredInteger(planForm.autoMaxOutputRoutes, '最大输出路线数'),
    max_routes_per_pair: parseRequiredInteger(planForm.autoMaxRoutesPerPair, '每对锚点最大路线数'),
    max_anchor_pairs_to_evaluate: parseRequiredInteger(planForm.autoMaxAnchorPairs, '最大锚点评估数'),
    min_frame_count: minFrameCount,
    max_frame_count: maxFrameCount,
    distance_per_frame: parseRequiredPositiveNumber(planForm.autoDistancePerFrame, '每帧距离'),
    min_total_length: minTotalLength,
    max_total_length: maxTotalLength,
    max_edge_pass_factor: Math.max(1, Number(planForm.maxEdgePassFactor) || 1),
    max_search_states: parseRequiredInteger(planForm.autoMaxSearchStates, '最大搜索状态数'),
    min_endpoint_distance: parseRequiredPositiveNumber(planForm.autoMinEndpointDistance, '最小端点距离', { allowZero: true }),
    prefer_connected_anchors: planForm.autoPreferConnectedAnchors,
    prefer_route_diversity: planForm.autoPreferRouteDiversity,
    allow_reverse_direction_counterparts: planForm.autoAllowReverseDirectionCounterparts,
    coverage_weight: parseRequiredPositiveNumber(planForm.autoCoverageWeight, '覆盖权重', { allowZero: true }),
    diversity_weight: parseRequiredPositiveNumber(planForm.autoDiversityWeight, '多样性权重', { allowZero: true }),
    anchor_weight: parseRequiredPositiveNumber(planForm.autoAnchorWeight, '锚点权重', { allowZero: true }),
    reverse_penalty_weight: parseRequiredPositiveNumber(planForm.autoReversePenaltyWeight, '反向惩罚权重', { allowZero: true }),
    node_coverage_weight: parseRequiredPositiveNumber(planForm.autoNodeCoverageWeight, '节点覆盖权重', { allowZero: true }),
    endpoint_reuse_weight: parseRequiredPositiveNumber(planForm.autoEndpointReuseWeight, '端点复用权重', { allowZero: true }),
    allowed_route_group_colors: [...planForm.autoAllowedRouteGroupColors],
    excluded_endpoint_group_colors: [...planForm.autoExcludedEndpointGroupColors],
    export_config: missionConfig,
  }
}

async function generateRouteCandidates() {
  if (planForm.planningMode === 'manual' && (!planForm.startNodeId || !planForm.endNodeId)) {
    setBanner('手动规划前请先设置起点和终点', 'error')
    return
  }
  lastExportSummary.value = null
  try {
    await flushActiveGroupConfigForGeneration()
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存颜色组配置失败'
    setBanner(`保存颜色组配置失败：${message}`, 'error')
    return
  }
  if (planForm.planningMode === 'auto') {
    resetTrackedAutoPlanState()
    try {
      const autoPayload = buildAutoPlanningPayload()
      planningRoutes.value = true
      const status = await startAutoPlanJob(autoPayload)
      activeAutoPlanJobId.value = status.job_id
      autoPlanJobStatus.value = status
      autoPlanRecovered.value = false
      setStoredAutoPlanJobId(status.graph, status.job_id)
      scheduleAutoPlanPoll(status.job_id, status.graph)
      setBanner(resolveAutoPlanStartBannerMessage(), 'info')
    } catch (error) {
      resetTrackedAutoPlanState()
      const message = error instanceof Error ? error.message : '生成候选路线失败'
      setBanner(message, 'error')
    }
    return
  }

  planningRoutes.value = true
  try {
    const minFrameCount = parseOptionalInteger(planForm.minFrameCount, '最小轨迹帧数下限')
    const maxFrameCount = parseOptionalInteger(planForm.maxFrameCount, '最大轨迹帧数上限')
    if (minFrameCount != null && maxFrameCount != null && minFrameCount > maxFrameCount) {
      throw new Error('最小轨迹帧数下限必须小于或等于最大轨迹帧数上限')
    }
    const missionConfig = buildMissionConfigRequestPayload()
    const nextCandidateSet = await generatePlan({
      graph: currentGraphPath.value,
      start_node: planForm.startNodeId,
      end_node: planForm.endNodeId,
      via_nodes: [...planForm.viaNodeIds],
      max_routes: Math.max(1, Math.round(Number(planForm.maxRoutes) || 1)),
      max_edge_pass_factor: Math.max(1, Number(planForm.maxEdgePassFactor) || 1),
      min_total_length: parseOptionalNumber(planForm.minTotalLength, '最小总长度'),
      max_total_length: parseOptionalNumber(planForm.maxTotalLength, '最大总长度'),
      min_frame_count: minFrameCount,
      max_frame_count: maxFrameCount,
      export_config: missionConfig,
    })
    applyGeneratedCandidateSet(nextCandidateSet)
    setBanner(
      `已生成 ${nextCandidateSet.candidates.length} 条候选路线${nextCandidateSet.meta.truncated ? '（搜索已截断）' : ''}`,
      'success',
    )
  } catch (error) {
    const message = error instanceof Error ? error.message : '生成候选路线失败'
    setBanner(message, 'error')
  } finally {
    planningRoutes.value = false
  }
}

async function saveCurrentCandidateSet() {
  if (!candidateSet.value) {
    setBanner('当前没有可保存的候选集合', 'error')
    return
  }
  savingRoutes.value = true
  syncCandidateSelections()
  try {
    const result = await saveCandidateSet({
      candidate_set: candidateSet.value,
      file_name: exportForm.candidateSetFileName.trim() || null,
    })
    lastCandidateSavePath.value = result.path
    setBanner(`候选集合已保存到 ${result.path}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '保存候选集合失败'
    setBanner(message, 'error')
  } finally {
    savingRoutes.value = false
  }
}

async function exportSelectedCandidateMissions() {
  if (!candidateSet.value) {
    setBanner('当前没有可导出的候选集合', 'error')
    return
  }
  if (selectedCandidateIds.value.length === 0) {
    setBanner('导出前请至少保留一条候选路线', 'error')
    return
  }
  exportingRoutes.value = true
  syncCandidateSelections()
  try {
    const missionConfig = buildMissionConfigRequestPayload()
    const result = await exportMissions({
      candidate_set: candidateSet.value,
      output_dir: exportForm.missionsOutputDir.trim() || null,
      candidate_ids: [...selectedCandidateIds.value],
      ...missionConfig,
    })
    lastExportSummary.value = result
    setBanner(`任务导出完成，成功 ${result.succeeded.length} 条`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '任务导出失败'
    setBanner(message, 'error')
  } finally {
    exportingRoutes.value = false
  }
}

function setSelectedCandidateRows(candidateIds: string[], anchorId: string | null = null) {
  setSelectedCandidateRowsInSelection(candidateIds, candidateDisplayRowIndexMap.value, anchorId)
}

function chooseCandidate(candidateId: string) {
  selectedCandidateId.value = candidateId
}

function selectAllCandidateRows() {
  if (candidateDisplayRows.value.length === 0) {
    return
  }
  const allCandidateIds = candidateDisplayRows.value.map((row) => row.id)
  setSelectedCandidateRows(allCandidateIds, selectedCandidateId.value ?? allCandidateIds[0] ?? null)
  if (!selectedCandidateId.value) {
    chooseCandidate(allCandidateIds[0])
  }
}

function selectOnlyCandidateRow(candidateId: string) {
  chooseCandidate(candidateId)
  setSelectedCandidateRows([candidateId], candidateId)
}

function toggleCandidateRowSelection(candidateId: string) {
  const nextCandidateIds = selectedCandidateRowIds.value.filter((item) => item !== candidateId)
  if (nextCandidateIds.length === selectedCandidateRowIds.value.length) {
    nextCandidateIds.push(candidateId)
  }
  chooseCandidate(candidateId)
  setSelectedCandidateRows(nextCandidateIds, candidateId)
}

function selectCandidateRowRange(candidateId: string) {
  const fallbackAnchorId =
    candidateRowSelectionAnchorId.value ??
    selectedCandidateRowIds.value[0] ??
    selectedCandidateId.value ??
    candidateId
  const rowIds = candidateDisplayRows.value.map((row) => row.id)
  const rangeSelection = resolveCandidateRangeSelection(
    rowIds,
    candidateDisplayRowIndexMap.value,
    candidateId,
    fallbackAnchorId,
  )
  if (rangeSelection.ids.length === 1 && rangeSelection.anchorId === candidateId) {
    selectOnlyCandidateRow(candidateId)
    return
  }

  chooseCandidate(candidateId)
  setSelectedCandidateRows(rangeSelection.ids, rangeSelection.anchorId)
}

function resolveCandidateKeepTargetIds(candidateId?: string | null) {
  return resolveCandidateKeepTargetIdsPure(
    candidateId,
    selectedCandidateRowIds.value,
    selectedCandidateRowIdSet.value,
    selectedCandidateId.value,
  )
}

function setCandidatesSelected(candidateIds: string[], selected: boolean) {
  if (!candidateSet.value) {
    return 0
  }

  let updatedCount = 0
  for (const candidateId of candidateIds) {
    const target = candidateSet.value.candidates.find(
      (candidate) => candidate.candidate_id === candidateId,
    )
    if (!target || target.selected === selected) {
      continue
    }
    target.selected = selected
    updatedCount += 1
  }
  syncCandidateSelections()
  return updatedCount
}

function handleCandidateRowClick(candidateId: string, event: MouseEvent) {
  if (event.shiftKey) {
    clearCandidateRowClickTimer()
    selectCandidateRowRange(candidateId)
    return
  }

  if (event.metaKey || event.ctrlKey) {
    clearCandidateRowClickTimer()
    toggleCandidateRowSelection(candidateId)
    return
  }

  if (event.detail > 1) {
    return
  }

  clearCandidateRowClickTimer()
  candidateRowClickTimeoutId.value = window.setTimeout(() => {
    selectOnlyCandidateRow(candidateId)
    candidateRowClickTimeoutId.value = null
  }, 180)
}

function handleCandidateRowDoubleClick(candidateId: string) {
  clearCandidateRowClickTimer()
  chooseCandidate(candidateId)
  if (!selectedCandidateRowIdSet.value.has(candidateId)) {
    setSelectedCandidateRows([candidateId], candidateId)
  }
  const targetIds = resolveCandidateKeepTargetIds(candidateId)
  if (targetIds.length === 0 || !candidateSet.value) {
    return
  }

  const nextSelected = !targetIds.every((item) => {
    const target = candidateSet.value?.candidates.find((candidate) => candidate.candidate_id === item)
    return !!target?.selected
  })
  const updatedCount = setCandidatesSelected(targetIds, nextSelected)
  if (targetIds.length === 1) {
    setBanner(`${nextSelected ? '已保留' : '已取消保留'} ${targetIds[0]}`, 'success')
    return
  }
  setBanner(
    `${nextSelected ? '已保留' : '已取消保留'} ${targetIds.length} 条候选路线（变更 ${updatedCount} 条）`,
    'success',
  )
}

function keepSelectedCandidateRows() {
  if (!hasSelectedCandidateRows.value) {
    setBanner('请先在候选表格中选中至少一条路线', 'error')
    return
  }
  const updatedCount = setCandidatesSelected(selectedCandidateRowIds.value, true)
  setBanner(
    `已保留 ${selectedCandidateRowIds.value.length} 条候选路线（新增 ${updatedCount} 条）`,
    'success',
  )
}

function unkeepSelectedCandidateRows() {
  if (!hasSelectedCandidateRows.value) {
    setBanner('请先在候选表格中选中至少一条路线', 'error')
    return
  }
  const updatedCount = setCandidatesSelected(selectedCandidateRowIds.value, false)
  setBanner(
    `已取消保留 ${selectedCandidateRowIds.value.length} 条候选路线（变更 ${updatedCount} 条）`,
    'success',
  )
}

function toggleSelectedCandidateRowsKeep() {
  if (!hasSelectedCandidateRows.value || !candidateSet.value) {
    setBanner('请先在候选表格中选中至少一条路线', 'error')
    return
  }
  const nextSelected = !selectedCandidateRowIds.value.every((candidateId) => {
    const target = candidateSet.value?.candidates.find((candidate) => candidate.candidate_id === candidateId)
    return !!target?.selected
  })
  const updatedCount = setCandidatesSelected(selectedCandidateRowIds.value, nextSelected)
  setBanner(
    `${nextSelected ? '已保留' : '已取消保留'} ${selectedCandidateRowIds.value.length} 条候选路线（变更 ${updatedCount} 条）`,
    'success',
  )
}

function handleCandidateTableKeydown(event: KeyboardEvent) {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'a') {
    return
  }

  event.preventDefault()
  event.stopPropagation()
  selectAllCandidateRows()
}

function colorSelectionIncludes(
  selections: string[],
  color: string,
) {
  return selections.includes(color)
}

function resolveGroupDisplayLabel(color: string) {
  const config = groupConfigLookup.value[color]
  const groupLabel = typeof config?.label === 'string' ? config.label.trim() : ''
  if (groupLabel && groupLabel !== color) {
    return `${groupLabel} (${color})`
  }
  return color
}

async function flushGroupConfigAutosave() {
  clearGroupConfigAutosaveTimer()
  await persistActiveGroupConfig()
}

async function setActiveGroupFocus(nextColor: string | null) {
  await flushGroupConfigAutosave()
  activeGroupColor.value = nextColor
  paintColor.value = resolvePaletteBrushColor(
    groupColorOptions.value,
    sessionPaletteColors.value,
    paintColor.value,
    activeGroupColor.value,
  )
}

async function setPaintColorSelection(color: string | null) {
  const nextSelection = resolvePaletteSelectionResult(
    groupColorOptions.value,
    sessionPaletteColors.value,
    color,
    activeGroupColor.value,
  )
  if (nextSelection.activeGroupColor !== activeGroupColor.value) {
    await flushGroupConfigAutosave()
    activeGroupColor.value = nextSelection.activeGroupColor
  }
  paintColor.value = nextSelection.paintColor
}

async function addPaletteColor() {
  try {
    const normalized = parseRequiredHexColor(newPaletteColor.value, '调色盘颜色')
    if (
      !groupColorOptions.value.includes(normalized) &&
      !sessionPaletteColors.value.includes(normalized)
    ) {
      sessionPaletteColors.value = [...sessionPaletteColors.value, normalized]
    }
    await setPaintColorSelection(normalized)
    setBanner(`已选择调色盘颜色 ${normalized}`, 'success')
  } catch (error) {
    const message = error instanceof Error ? error.message : '新增调色盘颜色失败'
    setBanner(message, 'error')
  }
}

function togglePaintMode() {
  if (paintModeEnabled.value) {
    paintModeEnabled.value = false
    setBanner('已退出染色模式', 'info')
    return
  }
  if (!paintColor.value) {
    setBanner('请先从调色盘选择一个颜色。', 'error')
    return
  }
  paintModeEnabled.value = true
  setBanner(`已进入染色模式，当前画笔 ${paintColor.value}`, 'info')
}

function toggleAutoGroupColorSelection(
  listKey: 'autoAllowedRouteGroupColors' | 'autoExcludedEndpointGroupColors',
  color: string,
) {
  const nextSelections = [...planForm[listKey]]
  const existingIndex = nextSelections.indexOf(color)
  if (existingIndex >= 0) {
    nextSelections.splice(existingIndex, 1)
  } else {
    nextSelections.push(color)
  }
  planForm[listKey] = nextSelections
}

function candidateSetSummaryText() {
  if (!candidateSet.value) {
    return ''
  }
  if (candidateSet.value.meta.planning_mode === 'auto') {
    return `有向边 ${candidateSet.value.meta.directed_edge_coverage_count ?? 0} · 物理边 ${candidateSet.value.meta.physical_edge_coverage_count ?? 0} · 节点 ${candidateSet.value.meta.node_coverage_count ?? 0}`
  }
  return `锚点 ${candidateSet.value.anchor_nodes.join(' → ')}`
}

function formatCount(value: number) {
  return integerFormatter.format(value)
}

function formatDistance(value: number) {
  return `${numberFormatter.format(value)} u`
}

function formatUpdatedAt(value: string | undefined) {
  if (!value) {
    return '未知'
  }
  return value.replace('T', ' ')
}

function resolveEdgeKind(edge: GraphEdge) {
  return edge.meta[EDGE_KIND_META_KEY] === EDGE_KIND_BRIDGE ? EDGE_KIND_BRIDGE : EDGE_KIND_GROUP
}

function deriveGraphColorGroupingState(targetGraph: RouteGraph | null) {
  const nodeGroupCandidates = new Map<string, Set<string>>()
  const conflictingNodeIds = new Set<string>()
  if (!targetGraph) {
    return {
      nodeGroupLookup: new Map<string, string>(),
      conflictingNodeIds,
    }
  }
  for (const node of targetGraph.nodes) {
    nodeGroupCandidates.set(node.id, new Set())
  }
  for (const edge of targetGraph.edges) {
    if (resolveEdgeKind(edge) !== 'group') {
      continue
    }
    const edgeColor = resolveEdgeBaseColor(edge)
    nodeGroupCandidates.get(edge.from)?.add(edgeColor)
    nodeGroupCandidates.get(edge.to)?.add(edgeColor)
  }
  const nodeGroupLookup = new Map<string, string>()
  for (const [nodeId, candidateColors] of nodeGroupCandidates.entries()) {
    if (candidateColors.size === 1) {
      nodeGroupLookup.set(nodeId, [...candidateColors][0])
      continue
    }
    if (candidateColors.size > 1) {
      conflictingNodeIds.add(nodeId)
    }
  }
  return {
    nodeGroupLookup,
    conflictingNodeIds,
  }
}

function resolveEdgeBaseColor(edge: GraphEdge) {
  if (resolveEdgeKind(edge) === EDGE_KIND_BRIDGE) {
    return bridgeColor.value
  }
  const rawColor = edge.meta[EDGE_GROUP_COLOR_META_KEY]
  return typeof rawColor === 'string' && rawColor.trim()
    ? rawColor.toUpperCase()
    : DEFAULT_GROUP_COLOR
}

function blendHexColor(color: string, target = '#FFFFFF', ratio = 0.72) {
  const source = normalizeOptionalHexColor(color) ?? DEFAULT_GROUP_COLOR
  const destination = normalizeOptionalHexColor(target) ?? '#FFFFFF'
  const sourceChannels = [source.slice(1, 3), source.slice(3, 5), source.slice(5, 7)].map((part) =>
    Number.parseInt(part, 16),
  )
  const targetChannels = [
    destination.slice(1, 3),
    destination.slice(3, 5),
    destination.slice(5, 7),
  ].map((part) => Number.parseInt(part, 16))
  const resolvedRatio = Math.max(0, Math.min(ratio, 1))
  const channels = sourceChannels.map((channel, index) => {
    return Math.round(channel + ((targetChannels[index] - channel) * resolvedRatio))
  })
  return `#${channels.map((channel) => channel.toString(16).padStart(2, '0')).join('').toUpperCase()}`
}

function resolveNodeRoles(nodeId: string): AnchorRole[] {
  const roles: AnchorRole[] = []
  if (nodeId === planForm.startNodeId) {
    roles.push('start')
  }
  if (planForm.viaNodeIds.includes(nodeId)) {
    roles.push('via')
  }
  if (nodeId === planForm.endNodeId) {
    roles.push('end')
  }
  return roles
}

function resolveNodeAccent(nodeId: string) {
  const roles = resolveNodeRoles(nodeId)
  if (roles.length === 0) {
    return '#111827'
  }
  if (roles.length > 1) {
    return '#334155'
  }
  if (roles[0] === 'start') {
    return '#dc2626'
  }
  if (roles[0] === 'end') {
    return '#0f766e'
  }
  return '#b45309'
}

function resolveNodeFill(nodeId: string) {
  const roles = resolveNodeRoles(nodeId)
  if (roles.length === 0) {
    return '#ffffff'
  }
  const fillByRole: Record<AnchorRole, string> = {
    start: '#fff1f2',
    via: '#fffbeb',
    end: '#ecfdf5',
  }
  const fills = roles.map((role) => fillByRole[role])
  if (fills.length === 1) {
    return fills[0]
  }
  const step = 100 / fills.length
  const stops = fills.map((fill, index) => {
    const start = (index * step).toFixed(2)
    const end = ((index + 1) * step).toFixed(2)
    return `${fill} ${start}% ${end}%`
  })
  return `linear-gradient(135deg, ${stops.join(', ')})`
}

function resolveNodeLabel(node: GraphNode) {
  const labels = [node.id]
  if (node.id === planForm.startNodeId) {
    labels.push('[S]')
  }
  if (planForm.viaNodeIds.includes(node.id)) {
    labels.push(`[V${planForm.viaNodeIds.indexOf(node.id) + 1}]`)
  }
  if (node.id === planForm.endNodeId) {
    labels.push('[E]')
  }
  return labels.join(' ')
}

function resolveEdgeDirection(fromNode: GraphNode | undefined, toNode: GraphNode | undefined) {
  if (!fromNode || !toNode) {
    return 'right' as const
  }
  const source = graphNodeCenterToCanvas(fromNode.position)
  const target = graphNodeCenterToCanvas(toNode.position)
  const dx = target.x - source.x
  const dy = target.y - source.y
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? ('right' as const) : ('left' as const)
  }
  return dy >= 0 ? ('bottom' as const) : ('top' as const)
}

function oppositeDirection(direction: 'top' | 'right' | 'bottom' | 'left') {
  if (direction === 'top') {
    return 'bottom' as const
  }
  if (direction === 'right') {
    return 'left' as const
  }
  if (direction === 'bottom') {
    return 'top' as const
  }
  return 'right' as const
}

function directionToPosition(direction: 'top' | 'right' | 'bottom' | 'left') {
  if (direction === 'top') {
    return Position.Top
  }
  if (direction === 'right') {
    return Position.Right
  }
  if (direction === 'bottom') {
    return Position.Bottom
  }
  return Position.Left
}

const flowNodes = computed<FlowNode[]>(() => {
  if (!graph.value) {
    return []
  }
  return graph.value.nodes.map((node) => {
    const isSelected = selectedNodeIdSet.value.has(node.id)
    const isPrimarySelected = node.id === primarySelectedNodeId.value
    const nodePulseState = resolveNodePulseState({
      nodeId: node.id,
      isSelected,
      isPrimarySelected,
    })

    return {
      id: node.id,
      type: 'topology',
      position: graphToCanvas(node.position),
      data: {
        label: resolveNodeLabel(node),
        accent: resolveNodeAccent(node.id),
        fill: resolveNodeFill(node.id),
        isSelected,
        isPrimarySelected,
        pulseVariant: nodePulseState.pulseVariant,
        pulseDelayMs: nodePulseState.pulseDelayMs,
        onMiddleButtonGesture: handleNodeMiddleButtonGesture,
      },
      draggable: nodeDragEnabled.value,
      connectable: true,
      style: {
        width: `${NODE_DIAMETER_PX}px`,
        height: `${NODE_DIAMETER_PX}px`,
        padding: '0',
        border: 'none',
        borderRadius: '999px',
        background: 'transparent',
        boxShadow: 'none',
        overflow: 'visible',
      },
    }
  })
})

const flowEdges = computed<FlowEdge[]>(() => {
  if (!graph.value) {
    return []
  }
  return graph.value.edges.map((edge) => {
    const highlighted = routeEdgeIdSet.value.has(edge.id)
    const selected = edge.id === selectedEdgeId.value
    const sourceNode = graphNodeMap.value.get(edge.from)
    const targetNode = graphNodeMap.value.get(edge.to)
    const sourceDirection = resolveEdgeDirection(sourceNode, targetNode)
    const targetDirection = oppositeDirection(sourceDirection)
    const baseColor = resolveEdgeBaseColor(edge)
    const belongsToActiveGroup =
      !!activeGroupColor.value &&
      resolveEdgeKind(edge) === 'group' &&
      resolveEdgeBaseColor(edge) === activeGroupColor.value
    let strokeColor = !edge.enabled ? '#94a3b8' : highlighted ? '#f97316' : baseColor
    let strokeWidth = highlighted ? 3.6 : selected ? 2.8 : 2.1
    let edgeOpacity = selectedCandidateId.value ? (highlighted ? 1 : 0.28) : edge.enabled ? 0.92 : 0.42
    if (activeGroupColor.value && !highlighted) {
      if (belongsToActiveGroup) {
        strokeWidth = selected ? 5 : 4
      } else {
        strokeColor = edge.enabled ? blendHexColor(baseColor) : '#CBD5E1'
        strokeWidth = selected ? 2 : 1.2
        edgeOpacity = selectedCandidateId.value ? Math.min(edgeOpacity, 0.28) : selected ? 0.72 : 0.44
      }
    }
    return {
      id: edge.id,
      source: edge.from,
      target: edge.to,
      type: 'straight',
      sourceHandle: 'source-center',
      targetHandle: 'target-center',
      sourcePosition: directionToPosition(sourceDirection),
      targetPosition: directionToPosition(targetDirection),
      label: highlighted ? `${candidatePassLookup.value.get(edge.id) ?? ''}` : undefined,
      animated: false,
      selectable: true,
      markerEnd:
        edge.enabled && !edge.bidirectional
          ? {
              type: MarkerType.ArrowClosed,
              color: strokeColor,
            }
          : undefined,
      style: {
        stroke: strokeColor,
        strokeWidth,
        opacity: selected ? 1 : edgeOpacity,
        strokeDasharray: edge.enabled ? undefined : '8 6',
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        transition: 'stroke 0.16s ease, opacity 0.16s ease',
      },
      labelStyle: {
        fill: '#1e293b',
        fontWeight: 600,
        fontSize: '10px',
      },
      labelBgPadding: [4, 3],
      labelBgBorderRadius: 8,
      labelBgStyle: {
        fill: '#fff7ed',
        stroke: '#f97316',
        strokeWidth: 1,
      },
    }
  })
})

function miniMapNodeColor(node: FlowNode) {
  return resolveNodeAccent(node.id)
}

onMounted(() => {
  setupAtmosphereWaveBackground()
  void initializeWithRetry()
  void nextTick(() => {
    syncViewportTransformFromFlow()
  })
})

onBeforeUnmount(() => {
  cleanupAtmosphereWaveBackground()
  stopPreviewFlowTicker()
  clearAutoPlanPollTimer()
  clearGraphUiStateAutosaveTimer()
  clearGroupConfigAutosaveTimer()
  clearCandidateRowClickTimer()
  clearPreviewRefreshTimer()
  previewRequestSequence.value += 1
})
</script><template>
  <div class="app-shell">
    <div class="page-atmosphere" aria-hidden="true">
      <div class="page-atmosphere__base-glow"></div>
      <div class="page-atmosphere__contours-major"></div>
      <div class="page-atmosphere__contours-minor"></div>
    </div>
    <AppHeader
      :available-graphs="availableGraphs"
      :current-graph-path="currentGraphPath"
      :loading-graph="loadingGraph"
      :validating-graph="validatingGraph"
      :viewport-locked="viewportLocked"
      :tracking-depth-card="trackingDepthCard"
      @graph-change="handleGraphPicker"
      @refresh="refreshCurrentGraph"
      @validate="runGraphValidation"
      @fit-view="requestFitGraphToViewport"
    />

    <StatusRibbon
      :node-count="graphSummary ? formatCount(graphSummary.node_count) : '0'"
      :edge-count="graphSummary ? formatCount(graphSummary.edge_count) : '0'"
      :enabled-edge-count="graphSummary ? formatCount(graphSummary.enabled_edge_count) : '0'"
      :group-color-count="String(graphSummary?.group_colors.length ?? 0)"
      :updated-at="graphSummary ? formatUpdatedAt(graphSummary.updated_at) : '未知'"
      :tracking-depth-card="trackingDepthCard"
    />

    <p v-if="bannerMessage" v-depth-card="bannerDepthCard" class="banner" :class="`banner--${bannerTone}`">{{ bannerMessage }}</p>

    <main class="workspace-grid">
      <aside class="column-stack column-stack--left-rail">
        <NodeInspector
          :depth-card="leftRailDepthCard"
          :tracking-enabled="leftRailDepthTrackingEnabled"
          :node-drag-enabled="nodeDragEnabled"
          :node-drag-status-text="nodeDragStatusText"
          :can-reset-selected-node-position="canResetSelectedNodePosition"
          :resetting-node-position="resettingNodePosition"
          :selected-node="selectedNode"
          :selected-node-ids="selectedNodeIds"
          :selected-edge="selectedEdge"
          :plan-start-node-id="planForm.startNodeId"
          :plan-end-node-id="planForm.endNodeId"
          :plan-via-node-ids="planForm.viaNodeIds"
          :node-draft="nodeDraft"
          :saving-node="savingNode"
          @toggle-tracking="leftRailDepthTrackingEnabled = !leftRailDepthTrackingEnabled"
          @toggle-node-drag="toggleNodeDragEnabled"
          @reset-selected-node-position="resetSelectedNodePosition"
          @assign-start="assignSelectedNodeAsStart"
          @toggle-via="toggleSelectedNodeAsVia"
          @assign-end="assignSelectedNodeAsEnd"
          @submit-node-update="submitNodeUpdate"
        />

        <EdgeInspector
          :depth-card="leftRailDepthCard"
          :selected-edge="selectedEdge"
          :selected-edge-length-text="selectedEdge ? formatDistance(selectedEdge.weight) : ''"
          :selected-edge-kind-label="selectedEdge ? (resolveEdgeKind(selectedEdge) === 'bridge' ? '桥接边' : '分组边') : ''"
          :selected-edge-color-text="selectedEdgeColorText"
          :mutating-edge="mutatingEdge"
          :current-selection-edge-summary="currentSelectionEdgeSummary"
          :can-create-edge-from-selection="canCreateEdgeFromSelection"
          :can-remove-edge-from-selection="canRemoveEdgeFromSelection"
          :can-mutate-selected-edge="canMutateSelectedEdge"
          :paint-color="paintColor"
          @patch-edge="patchEdge"
          @delete-selected-edge="deleteSelectedEdge"
          @create-selected-edge="createSelectedEdge"
          @delete-selected-edge-or-between="deleteSelectedEdgeOrBetween"
          @set-selected-edge-bridge="setSelectedEdgeBridge"
          @paint-edge-with-current-color="paintEdgeWithCurrentColor()"
        />

        <PalettePanel
          :depth-card="leftRailDepthCard"
          :current-paint-color-label="currentPaintColorLabel"
          :is-paint-mode-active="isPaintModeActive"
          :paint-color="paintColor"
          v-model:new-palette-color="newPaletteColor"
          :palette-state="paletteState"
          :resolve-group-display-label="resolveGroupDisplayLabel"
          @toggle-paint-mode="togglePaintMode"
          @add-palette-color="addPaletteColor"
          @set-paint-color-selection="setPaintColorSelection"
        />

        <GroupConfigPanel
          :depth-card="leftRailDepthCard"
          :group-color-options="groupColorOptions"
          :active-group-color="activeGroupColor"
          v-model:bridge-color-draft="bridgeColorDraft"
          :active-group-display-label="activeGroupDisplayLabel"
          :active-group-config-enabled="activeGroupConfigEnabled"
          :group-config-form="groupConfigForm"
          :resolve-group-display-label="resolveGroupDisplayLabel"
          @set-active-group-focus="setActiveGroupFocus"
          @apply-bridge-color="applyBridgeColor"
        />
      </aside>

      <CanvasStage
        ref="canvasStage"
        :updating-canvas-view="updatingCanvasView"
        :flip-horizontal="canvasViewState.flipHorizontal"
        :flip-vertical="canvasViewState.flipVertical"
        :canvas-view-summary-text="canvasViewSummaryText"
        :node-drag-status-text="nodeDragStatusText"
        :viewport-lock-status-text="viewportLockStatusText"
        @rotate-left="rotateCanvasLeft"
        @rotate-right="rotateCanvasRight"
        @toggle-flip-horizontal="toggleCanvasFlipHorizontal"
        @toggle-flip-vertical="toggleCanvasFlipVertical"
        @reset-view="resetCanvasView"
      >
          <VueFlow
            class="graph-flow"
            :nodes="flowNodes"
            :edges="flowEdges"
            :node-types="nodeTypes"
            :nodes-draggable="nodeDragEnabled && !isPaintModeActive"
            :connect-on-click="false"
            :pan-on-drag="!viewportLocked"
            :zoom-on-scroll="!viewportLocked"
            :zoom-on-pinch="!viewportLocked"
            :pan-on-scroll="false"
            :prevent-scrolling="!viewportLocked"
            :min-zoom="0.1"
            :max-zoom="2.5"
            :fit-view-on-init="true"
            :zoom-on-double-click="false"
            @node-click="handleNodeClick"
            @node-double-click="handleNodeDoubleClick"
            @node-context-menu="handleNodeContextMenu"
            @edge-click="handleEdgeClick"
            @pane-click="handlePaneClick"
            @connect="handleConnect"
            @node-drag-stop="handleNodeDragStop"
            @viewport-change="handleViewportChange"
          >
            <Background :gap="26" pattern-color="rgba(15, 23, 42, 0.04)" />
            <MiniMap :pannable="!viewportLocked" :zoomable="!viewportLocked" :node-color="miniMapNodeColor" />
            <Controls position="bottom-right">
              <template #control-zoom-in>
                <ControlButton class="vue-flow__controls-zoomin" :disabled="viewportLocked" @click="handleViewportZoomIn">
                  +
                </ControlButton>
              </template>
              <template #control-zoom-out>
                <ControlButton class="vue-flow__controls-zoomout" :disabled="viewportLocked" @click="handleViewportZoomOut">
                  -
                </ControlButton>
              </template>
              <template #control-fit-view>
                <ControlButton
                  class="vue-flow__controls-fitview"
                  :disabled="viewportLocked"
                  title="适配视图"
                  aria-label="适配视图"
                  @click="requestFitGraphToViewport"
                >
                  <svg class="viewport-control-icon viewport-control-icon--stroke" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 3H3v5" />
                    <path d="M16 3h5v5" />
                    <path d="M21 16v5h-5" />
                    <path d="M8 21H3v-5" />
                    <path d="M3 8l6-6" />
                    <path d="M21 8l-6-6" />
                    <path d="M21 16l-6 6" />
                    <path d="M3 16l6 6" />
                  </svg>
                </ControlButton>
              </template>
              <template #control-interactive>
                <ControlButton
                  class="vue-flow__controls-interactive"
                  :title="viewportLocked ? '解锁画布视口' : '锁定画布视口'"
                  :aria-label="viewportLocked ? '解锁画布视口' : '锁定画布视口'"
                  @click="toggleViewportLock"
                >
                  <svg
                    v-if="viewportLocked"
                    class="viewport-control-icon viewport-control-icon--stroke"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <rect x="5" y="11" width="14" height="10" rx="2" />
                    <path d="M8 11V8a4 4 0 1 1 8 0v3" />
                  </svg>
                  <svg
                    v-else
                    class="viewport-control-icon viewport-control-icon--stroke"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <rect x="5" y="11" width="14" height="10" rx="2" />
                    <path d="M8 11V8a4 4 0 1 1 7.5-2" />
                  </svg>
                </ControlButton>
              </template>
            </Controls>
          </VueFlow>
          <svg
            v-if="previewPolylinePoints"
            class="mission-preview-overlay"
            aria-hidden="true"
          >
            <g :transform="previewOverlayTransform">
              <polyline class="mission-preview-overlay__guide" :points="previewPolylinePoints" />
              <g
                v-for="chevron in previewChevronGlyphs"
                :key="chevron.id"
                class="mission-preview-overlay__chevron-glyph"
                :transform="`translate(${chevron.x} ${chevron.y}) rotate(${chevron.angle}) scale(0.66)`"
              >
                <path
                  :d="PREVIEW_CHEVRON_PATH"
                  :class="[
                    'mission-preview-overlay__chevron',
                    chevron.tone === 'yellow'
                      ? 'mission-preview-overlay__chevron--yellow'
                      : 'mission-preview-overlay__chevron--black',
                  ]"
                />
              </g>
            </g>
          </svg>
      </CanvasStage>
      <aside class="column-stack column-stack--right-rail">
        <RoutePlannerPanel
          :depth-card="rightRailDepthCard"
          :tracking-enabled="rightRailDepthTrackingEnabled"
          :plan-form="planForm"
          :is-auto-planning-mode="isAutoPlanningMode"
          :graph="graph"
          :group-color-options="groupColorOptions"
          :planning-routes="planningRoutes"
          :planner-generate-button-label="plannerGenerateButtonLabel"
          :should-show-auto-plan-status="shouldShowAutoPlanStatus"
          :auto-plan-job-status="autoPlanJobStatus"
          :auto-plan-status-headline="autoPlanStatusHeadline"
          :auto-plan-recovered="autoPlanRecovered"
          :active-auto-plan-progress="Boolean(activeAutoPlanProgress)"
          :auto-plan-status-phase-label="autoPlanStatusPhaseLabel"
          :auto-plan-progress-maximum="autoPlanProgressMaximum"
          :auto-plan-progress-value="autoPlanProgressValue"
          :auto-plan-progress-percent="autoPlanProgressPercent"
          :auto-plan-progress-percent-rounded="autoPlanProgressPercentRounded"
          :auto-plan-status-summary="autoPlanStatusSummary"
          :color-selection-includes="colorSelectionIncludes"
          :resolve-group-display-label="resolveGroupDisplayLabel"
          @toggle-tracking="rightRailDepthTrackingEnabled = !rightRailDepthTrackingEnabled"
          @manual-start-node-change="handleManualStartNodeChange"
          @manual-end-node-change="handleManualEndNodeChange"
          @remove-via-node="removeViaNode"
          @reset-route-anchors="resetRouteAnchors"
          @generate-route-candidates="generateRouteCandidates"
          @toggle-auto-group-color-selection="toggleAutoGroupColorSelection"
        />

        <CandidatePanel
          :depth-card="rightRailDepthCard"
          :candidate-set="candidateSet"
          :candidate-display-rows="candidateDisplayRows"
          :selected-candidate-id="selectedCandidateId"
          :selected-candidate-row-ids="selectedCandidateRowIds"
          :selected-candidate-row-id-set="selectedCandidateRowIdSet"
          :selected-candidate-ids="selectedCandidateIds"
          :has-selected-candidate-rows="hasSelectedCandidateRows"
          :selected-candidate="selectedCandidate"
          :selected-candidate-detail-row="selectedCandidateDetailRow"
          :selected-candidate-display-rank="selectedCandidateDisplayRank"
          :preview-summary-items="previewSummaryItems"
          :candidate-set-summary-text="candidateSetSummaryText()"
          :format-distance="formatDistance"
          @keep-selected-candidate-rows="keepSelectedCandidateRows"
          @unkeep-selected-candidate-rows="unkeepSelectedCandidateRows"
          @toggle-selected-candidate-rows-keep="toggleSelectedCandidateRowsKeep"
          @candidate-row-click="handleCandidateRowClick"
          @candidate-row-double-click="handleCandidateRowDoubleClick"
          @candidate-table-keydown="handleCandidateTableKeydown"
        />

        <ExportPanel
          :depth-card="rightRailDepthCard"
          :candidate-set="candidateSet"
          :export-form="exportForm"
          :saving-routes="savingRoutes"
          :last-candidate-save-path="lastCandidateSavePath"
          :selected-candidate="selectedCandidate"
          :preview-status-tone="previewStatusTone"
          :preview-loading="previewLoading"
          :preview-status-text="previewStatusText"
          :preview-summary-items="previewSummaryItems"
          :exporting-routes="exportingRoutes"
          :selected-candidate-ids="selectedCandidateIds"
          :last-export-summary="lastExportSummary"
          @save-current-candidate-set="saveCurrentCandidateSet"
          @force-refresh-mission-preview="forceRefreshMissionPreview"
          @export-selected-candidate-missions="exportSelectedCandidateMissions"
        />
      </aside>
    </main>
  </div>
</template>
