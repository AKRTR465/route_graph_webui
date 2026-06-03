<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

import {
  applyCanvasViewToGraphXY,
  computeGraph3DSceneMetrics,
  projectGraphPositionToScene,
  resolveGraph3DGrouping,
  resolveGraph3DNodePositions,
  type CanvasViewStateLike,
  type Graph3DGrouping,
  type Graph3DZLayerMode,
  type ScenePoint3,
} from '../lib/graph-3d-view'
import { edgeWebuiExtension } from '../lib/graph-format'
import {
  DEFAULT_BRIDGE_COLOR,
  DEFAULT_GROUP_COLOR,
  EDGE_GROUP_COLOR_META_KEY,
  EDGE_KIND_BRIDGE,
  EDGE_KIND_META_KEY,
} from '../types/graph-meta'
import type { GraphEdge, MissionPreview, Position3, RouteCandidate, RouteCandidateSet, RouteGraph } from '../types/route-graph'

const props = defineProps<{
  graph: RouteGraph | null
  candidateSet: RouteCandidateSet | null
  selectedCandidateId: string | null
  previewMission: MissionPreview | null
  selectedNodeIds: string[]
  selectedEdgeId: string | null
  groupFocusColor: string | null
  cameraLocked: boolean
  canvasViewState: CanvasViewStateLike
  zLayerMode: Graph3DZLayerMode
}>()

const emit = defineEmits<{
  (event: 'select-node', nodeId: string): void
  (event: 'select-edge', edgeId: string): void
  (event: 'clear-selection'): void
  (event: 'toggle-camera-lock'): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const zExaggeration = ref(4)

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let resizeObserver: ResizeObserver | null = null
let animationFrameId: number | null = null
let contentGroup: THREE.Group | null = null
let raycastTargets: THREE.Object3D[] = []
let pointerDownPoint: { x: number; y: number } | null = null
let lastSceneSignature = ''

const NODE_RADIUS = 1.35
const EDGE_RADIUS = 0.15
const ROUTE_EDGE_RADIUS = 0.34
const DEFAULT_CAMERA_POSITION = new THREE.Vector3(135, 105, 155)
const CAMERA_FIT_DISTANCE_SCALE = 0.54
const MINIMAP_WIDTH = 180
const MINIMAP_HEIGHT = 154
const MINIMAP_PADDING = 12

type MiniMapEdge = {
  id: string
  x1: number
  y1: number
  x2: number
  y2: number
  color: string
  opacity: number
  strokeWidth: number
  dashArray?: string
}

type MiniMapNode = {
  id: string
  x: number
  y: number
  fill: string
  stroke: string
  opacity: number
  radius: number
}

function isValidHexColor(value: unknown): value is string {
  return typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)
}

function normalizeHexColor(value: unknown): string | null {
  return isValidHexColor(value) ? value.toUpperCase() : null
}

function edgeKind(edge: GraphEdge) {
  return edgeWebuiExtension(edge)[EDGE_KIND_META_KEY] === EDGE_KIND_BRIDGE ? EDGE_KIND_BRIDGE : 'group'
}

function edgeBaseColor(edge: GraphEdge) {
  const rawColor = edgeWebuiExtension(edge)[EDGE_GROUP_COLOR_META_KEY]
  const color = normalizeHexColor(rawColor)
  if (color) {
    return color
  }
  return edgeKind(edge) === EDGE_KIND_BRIDGE ? DEFAULT_BRIDGE_COLOR : DEFAULT_GROUP_COLOR
}

function normalizedGroupFocusColor() {
  return normalizeHexColor(props.groupFocusColor)
}

function selectedCandidate(): RouteCandidate | null {
  if (!props.candidateSet || !props.selectedCandidateId) {
    return null
  }
  return (
    props.candidateSet.candidates.find(
      (candidate) => candidate.candidate_id === props.selectedCandidateId,
    ) ?? null
  )
}

const selectedCandidateRouteEdgeIds = computed(
  () => new Set(selectedCandidate()?.edge_passes.map((edgePass) => edgePass.edge_id) ?? []),
)

const minimapModel = computed(() => {
  const graph = props.graph
  const nodes = graph?.nodes ?? []
  if (!graph || !nodes.length) {
    return {
      viewBox: `0 0 ${MINIMAP_WIDTH} ${MINIMAP_HEIGHT}`,
      edges: [] as MiniMapEdge[],
      nodes: [] as MiniMapNode[],
    }
  }

  const rawXs = nodes.map((node) => Number(node.position[0]) || 0)
  const rawYs = nodes.map((node) => Number(node.position[1]) || 0)
  const metrics = {
    centerX: (Math.min(...rawXs) + Math.max(...rawXs)) / 2,
    centerY: (Math.min(...rawYs) + Math.max(...rawYs)) / 2,
  }
  const transformedNodes = nodes.map((node) => ({
    node,
    xy: applyCanvasViewToGraphXY(node.position, metrics, props.canvasViewState),
  }))
  const xs = transformedNodes.map((item) => item.xy.x)
  const ys = transformedNodes.map((item) => item.xy.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const spanX = Math.max(maxX - minX, 1)
  const spanY = Math.max(maxY - minY, 1)
  const scale = Math.min(
    (MINIMAP_WIDTH - MINIMAP_PADDING * 2) / spanX,
    (MINIMAP_HEIGHT - MINIMAP_PADDING * 2) / spanY,
  )
  const offsetX = (MINIMAP_WIDTH - spanX * scale) / 2
  const offsetY = (MINIMAP_HEIGHT - spanY * scale) / 2
  const project = (xy: { x: number; y: number }) => ({
    x: offsetX + (xy.x - minX) * scale,
    y: offsetY + (maxY - xy.y) * scale,
  })
  const projectedNodeLookup = new Map(
    transformedNodes.map((item) => [item.node.id, project(item.xy)]),
  )
  const grouping = resolveGraph3DGrouping(graph, props.candidateSet)
  const focusColor = normalizedGroupFocusColor()
  const selectedNodeIds = new Set(props.selectedNodeIds)
  const routeEdgeIds = selectedCandidateRouteEdgeIds.value

  const miniEdges: MiniMapEdge[] = []
  for (const edge of graph.edges) {
    const from = projectedNodeLookup.get(edge.source)
    const to = projectedNodeLookup.get(edge.target)
    if (!from || !to) {
      continue
    }
    const isSelected = edge.id === props.selectedEdgeId
    const isRouteEdge = routeEdgeIds.has(edge.id)
    const baseColor = edgeBaseColor(edge)
    const belongsToFocusedGroup = !!focusColor && edgeKind(edge) !== EDGE_KIND_BRIDGE && baseColor === focusColor
    const isDimmed = !!focusColor && !belongsToFocusedGroup && !isRouteEdge && !isSelected
    miniEdges.push({
      id: edge.id,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      color: !edge.enabled ? '#94a3b8' : isRouteEdge ? '#f97316' : baseColor,
      opacity: isDimmed ? 0.14 : !edge.enabled ? 0.34 : isRouteEdge || isSelected || belongsToFocusedGroup ? 0.92 : 0.58,
      strokeWidth: isRouteEdge ? 2.8 : isSelected ? 2.4 : 1.4,
      dashArray: edge.enabled ? undefined : '4 4',
    })
  }

  const miniNodes: MiniMapNode[] = transformedNodes.map(({ node }) => {
    const point = projectedNodeLookup.get(node.id) ?? { x: MINIMAP_WIDTH / 2, y: MINIMAP_HEIGHT / 2 }
    const nodeGroupColor = grouping.nodeGroupLookup.get(node.id)
    const isSelected = selectedNodeIds.has(node.id)
    const belongsToFocusedGroup = !!focusColor && nodeGroupColor === focusColor
    const isDimmed = !!focusColor && !belongsToFocusedGroup && !isSelected
    return {
      id: node.id,
      x: point.x,
      y: point.y,
      fill: isSelected ? '#f97316' : '#ffffff',
      stroke: nodeGroupColor ?? '#64748b',
      opacity: isDimmed ? 0.24 : 0.96,
      radius: isSelected ? 3.6 : 2.8,
    }
  })

  return {
    viewBox: `0 0 ${MINIMAP_WIDTH} ${MINIMAP_HEIGHT}`,
    edges: miniEdges,
    nodes: miniNodes,
  }
})

function toVector3(point: ScenePoint3) {
  return new THREE.Vector3(point.x, point.y, point.z)
}

function createCylinderBetween(
  start: THREE.Vector3,
  end: THREE.Vector3,
  radius: number,
  material: THREE.Material,
) {
  const direction = new THREE.Vector3().subVectors(end, start)
  const length = direction.length()
  if (length <= 1e-6) {
    return null
  }

  const geometry = new THREE.CylinderGeometry(radius, radius, length, 8, 1, false)
  const mesh = new THREE.Mesh(geometry, material)
  mesh.position.copy(start).add(end).multiplyScalar(0.5)
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize())
  return mesh
}

function createLabelSprite(text: string, opacity = 1) {
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }

  context.font = '600 28px Arial, sans-serif'
  const textWidth = Math.ceil(context.measureText(text).width)
  canvas.width = Math.max(96, textWidth + 32)
  canvas.height = 48
  context.font = '600 28px Arial, sans-serif'
  context.fillStyle = 'rgba(255, 255, 255, 0.9)'
  context.strokeStyle = 'rgba(15, 23, 42, 0.16)'
  context.lineWidth = 2
  context.beginPath()
  context.roundRect(1, 1, canvas.width - 2, canvas.height - 2, 14)
  context.fill()
  context.stroke()
  context.fillStyle = '#1e293b'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(text, canvas.width / 2, canvas.height / 2 + 1)

  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity,
    depthTest: false,
  })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set((canvas.width / canvas.height) * 4.2, 4.2, 1)
  sprite.renderOrder = 20
  return sprite
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child: THREE.Object3D) => {
    const mesh = child as THREE.Mesh
    mesh.geometry?.dispose?.()
    const material = mesh.material
    if (Array.isArray(material)) {
      for (const item of material) {
        item.dispose()
      }
    } else {
      material?.dispose?.()
    }
  })
}

function resizeRenderer() {
  const container = containerRef.value
  if (!container || !renderer || !camera) {
    return
  }
  const width = Math.max(container.clientWidth, 1)
  const height = Math.max(container.clientHeight, 1)
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function syncCameraLock() {
  if (!controls) {
    return
  }
  const unlocked = !props.cameraLocked
  controls.enabled = unlocked
  controls.enablePan = unlocked
  controls.enableRotate = unlocked
  controls.enableZoom = unlocked
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function resetCamera({ force = false }: { force?: boolean } = {}) {
  if (!camera || !controls) {
    return
  }
  if (props.cameraLocked && !force) {
    return
  }

  const target = new THREE.Vector3(0, 0, 0)
  let distance = DEFAULT_CAMERA_POSITION.length() * CAMERA_FIT_DISTANCE_SCALE
  if (contentGroup) {
    const box = new THREE.Box3().setFromObject(contentGroup)
    if (!box.isEmpty()) {
      const sphere = box.getBoundingSphere(new THREE.Sphere())
      target.copy(sphere.center)
      const fov = THREE.MathUtils.degToRad(camera.fov)
      distance = (sphere.radius / Math.sin(fov / 2)) * CAMERA_FIT_DISTANCE_SCALE
    }
  }

  const direction = DEFAULT_CAMERA_POSITION.clone().normalize()
  const nextDistance = clamp(distance, controls.minDistance, controls.maxDistance)
  controls.target.copy(target)
  camera.position.copy(target).addScaledVector(direction, nextDistance)
  camera.updateProjectionMatrix()
  controls.update()
}

function zoomCamera(distanceMultiplier: number) {
  if (!camera || !controls || props.cameraLocked) {
    return
  }
  const direction = new THREE.Vector3().subVectors(camera.position, controls.target)
  const currentDistance = direction.length()
  if (currentDistance <= 1e-6) {
    return
  }
  const nextDistance = clamp(
    currentDistance * distanceMultiplier,
    controls.minDistance,
    controls.maxDistance,
  )
  camera.position.copy(controls.target).addScaledVector(direction.normalize(), nextDistance)
  controls.update()
}

function zoomIn() {
  zoomCamera(0.82)
}

function zoomOut() {
  zoomCamera(1.22)
}

function createScenePoint(
  position: Position3,
  metrics: ReturnType<typeof computeGraph3DSceneMetrics>,
) {
  return toVector3(
    projectGraphPositionToScene(
      position,
      metrics,
      props.canvasViewState,
      zExaggeration.value,
    ),
  )
}

function addGrid(group: THREE.Group) {
  const grid = new THREE.GridHelper(150, 12, 0x94a3b8, 0xcbd5e1)
  const material = grid.material as THREE.Material
  material.transparent = true
  material.opacity = 0.28
  group.add(grid)
}

function addNodes(
  group: THREE.Group,
  nodePositions: ReadonlyMap<string, Position3>,
  metrics: ReturnType<typeof computeGraph3DSceneMetrics>,
  grouping: Graph3DGrouping,
) {
  const selectedNodeIds = new Set(props.selectedNodeIds)
  const focusColor = normalizedGroupFocusColor()
  for (const node of props.graph?.nodes ?? []) {
    const position = nodePositions.get(node.id)
    if (!position) {
      continue
    }

    const isSelected = selectedNodeIds.has(node.id)
    const belongsToFocusedGroup = !!focusColor && grouping.nodeGroupLookup.get(node.id) === focusColor
    const isDimmed = !!focusColor && !belongsToFocusedGroup && !isSelected
    const opacity = isDimmed ? 0.18 : 1
    const material = new THREE.MeshStandardMaterial({
      color: isSelected ? '#f97316' : '#ffffff',
      emissive: isSelected ? '#7c2d12' : '#000000',
      emissiveIntensity: isSelected ? 0.35 : 0,
      transparent: opacity < 1,
      opacity,
      metalness: 0.08,
      roughness: 0.55,
    })
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(NODE_RADIUS, 18, 14), material)
    mesh.position.copy(createScenePoint(position, metrics))
    mesh.userData = { kind: 'node', id: node.id }
    group.add(mesh)
    raycastTargets.push(mesh)

    const label = createLabelSprite(node.id, isDimmed ? 0.32 : 1)
    if (label) {
      label.position.copy(mesh.position)
      label.position.y += NODE_RADIUS + 2.2
      group.add(label)
    }
  }
}

function addEdges(
  group: THREE.Group,
  nodePositions: ReadonlyMap<string, Position3>,
  metrics: ReturnType<typeof computeGraph3DSceneMetrics>,
) {
  const routeEdgeIds = new Set(selectedCandidate()?.edge_passes.map((edgePass) => edgePass.edge_id) ?? [])
  const focusColor = normalizedGroupFocusColor()
  for (const edge of props.graph?.edges ?? []) {
    const fromPosition = nodePositions.get(edge.source)
    const toPosition = nodePositions.get(edge.target)
    if (!fromPosition || !toPosition) {
      continue
    }

    const isSelected = edge.id === props.selectedEdgeId
    const isRouteEdge = routeEdgeIds.has(edge.id)
    const baseColor = edgeBaseColor(edge)
    const belongsToFocusedGroup = !!focusColor && edgeKind(edge) !== EDGE_KIND_BRIDGE && baseColor === focusColor
    const isDimmed = !!focusColor && !belongsToFocusedGroup && !isRouteEdge && !isSelected
    const color = !edge.enabled ? '#94a3b8' : isRouteEdge ? '#f97316' : baseColor
    const opacity = isDimmed ? 0.14 : !edge.enabled ? 0.32 : isRouteEdge || isSelected || belongsToFocusedGroup ? 0.96 : 0.72
    const radius = isRouteEdge ? ROUTE_EDGE_RADIUS : isSelected ? EDGE_RADIUS * 1.8 : EDGE_RADIUS
    const material = new THREE.MeshStandardMaterial({
      color,
      transparent: true,
      opacity,
      roughness: 0.42,
      metalness: 0.12,
    })
    const mesh = createCylinderBetween(
      createScenePoint(fromPosition, metrics),
      createScenePoint(toPosition, metrics),
      radius,
      material,
    )
    if (!mesh) {
      continue
    }
    mesh.userData = { kind: 'edge', id: edge.id }
    group.add(mesh)
    raycastTargets.push(mesh)
  }
}

function addMissionPath(
  group: THREE.Group,
  metrics: ReturnType<typeof computeGraph3DSceneMetrics>,
) {
  const positions = props.previewMission?.positions ?? []
  const points: THREE.Vector3[] = []
  for (const position of positions) {
    const xyz = position.state?.[0]
    if (!Array.isArray(xyz) || xyz.length < 3) {
      continue
    }
    points.push(createScenePoint([Number(xyz[0]) || 0, Number(xyz[1]) || 0, Number(xyz[2]) || 0], metrics))
  }

  if (points.length < 2) {
    return
  }

  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  const material = new THREE.LineBasicMaterial({
    color: '#0f172a',
    transparent: true,
    opacity: 0.82,
  })
  const line = new THREE.Line(geometry, material)
  line.renderOrder = 10
  group.add(line)
}

function rebuildScene() {
  if (!scene) {
    return
  }

  if (contentGroup) {
    scene.remove(contentGroup)
    disposeObject(contentGroup)
  }

  raycastTargets = []
  const group = new THREE.Group()
  contentGroup = group
  scene.add(group)

  const nodePositions = resolveGraph3DNodePositions(props.graph, props.candidateSet, props.zLayerMode)
  const grouping = resolveGraph3DGrouping(props.graph, props.candidateSet)
  const metrics = computeGraph3DSceneMetrics(props.graph, nodePositions)
  const sceneSignature = [
    props.graph?.name ?? '',
    props.graph?.nodes.length ?? 0,
    props.graph?.edges.length ?? 0,
    props.zLayerMode,
  ].join(':')

  addGrid(group)
  addEdges(group, nodePositions, metrics)
  addNodes(group, nodePositions, metrics, grouping)
  addMissionPath(group, metrics)

  if (sceneSignature !== lastSceneSignature) {
    lastSceneSignature = sceneSignature
    resetCamera()
  }
}

function animate() {
  if (!renderer || !scene || !camera) {
    return
  }
  animationFrameId = window.requestAnimationFrame(animate)
  controls?.update()
  renderer.render(scene, camera)
}

function pickObject(event: PointerEvent) {
  if (!renderer || !camera || !raycastTargets.length) {
    emit('clear-selection')
    return
  }

  const rect = renderer.domElement.getBoundingClientRect()
  const pointer = new THREE.Vector2(
    ((event.clientX - rect.left) / rect.width) * 2 - 1,
    -(((event.clientY - rect.top) / rect.height) * 2 - 1),
  )
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(pointer, camera)
  const hit = raycaster.intersectObjects(raycastTargets, true)[0]
  const target = hit?.object
  if (!target?.userData?.kind) {
    emit('clear-selection')
    return
  }

  if (target.userData.kind === 'node') {
    emit('select-node', String(target.userData.id))
    return
  }
  if (target.userData.kind === 'edge') {
    emit('select-edge', String(target.userData.id))
  }
}

function handlePointerDown(event: PointerEvent) {
  pointerDownPoint = { x: event.clientX, y: event.clientY }
}

function handlePointerUp(event: PointerEvent) {
  if (!pointerDownPoint) {
    return
  }
  const distance = Math.hypot(event.clientX - pointerDownPoint.x, event.clientY - pointerDownPoint.y)
  pointerDownPoint = null
  if (distance <= 5) {
    pickObject(event)
  }
}

onMounted(() => {
  const container = containerRef.value
  if (!container) {
    return
  }

  scene = new THREE.Scene()
  scene.add(new THREE.AmbientLight(0xffffff, 0.76))
  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.92)
  directionalLight.position.set(80, 120, 80)
  scene.add(directionalLight)

  camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1200)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.domElement.className = 'graph-3d-preview__canvas'
  container.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.enablePan = true
  controls.enableRotate = true
  controls.enableZoom = true
  controls.zoomToCursor = true
  controls.dampingFactor = 0.08
  controls.minDistance = 28
  controls.maxDistance = 420
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.DOLLY,
    RIGHT: THREE.MOUSE.PAN,
  }
  controls.touches = {
    ONE: THREE.TOUCH.ROTATE,
    TWO: THREE.TOUCH.DOLLY_PAN,
  }
  syncCameraLock()
  resetCamera({ force: true })

  resizeObserver = new ResizeObserver(resizeRenderer)
  resizeObserver.observe(container)
  resizeRenderer()
  rebuildScene()
  animate()
})

onBeforeUnmount(() => {
  if (animationFrameId != null) {
    window.cancelAnimationFrame(animationFrameId)
  }
  resizeObserver?.disconnect()
  controls?.dispose()
  if (contentGroup) {
    disposeObject(contentGroup)
  }
  renderer?.dispose()
  renderer?.domElement.remove()
  renderer = null
  scene = null
  camera = null
  controls = null
})

watch(
  () => [
    props.graph,
    props.candidateSet,
    props.selectedCandidateId,
    props.previewMission,
    props.selectedEdgeId,
    props.selectedNodeIds.join('|'),
    props.groupFocusColor,
    props.canvasViewState.rotationQuadrants,
    props.canvasViewState.flipHorizontal,
    props.canvasViewState.flipVertical,
    props.zLayerMode,
    zExaggeration.value,
  ],
  rebuildScene,
  { deep: true },
)

watch(
  () => props.cameraLocked,
  syncCameraLock,
)

defineExpose({
  resetCamera,
  zoomIn,
  zoomOut,
})
</script>

<template>
  <div
    ref="containerRef"
    class="graph-3d-preview"
    @pointerdown="handlePointerDown"
    @pointerup="handlePointerUp"
    @contextmenu.prevent
  >
    <div class="graph-3d-preview__hud">
      <label class="graph-3d-preview__control">
        <span>Z 倍率</span>
        <span class="graph-3d-preview__range">
          <input
            v-model.number="zExaggeration"
            aria-label="Z 倍率"
            type="range"
            min="1"
            max="12"
            step="0.5"
          />
        </span>
        <strong>{{ zExaggeration.toFixed(1) }}x</strong>
      </label>
    </div>
    <div
      class="graph-3d-controls"
      role="group"
      aria-label="3D 视角控件"
      @pointerdown.stop
      @pointerup.stop
      @click.stop
    >
      <svg class="graph-3d-minimap" :viewBox="minimapModel.viewBox" aria-hidden="true">
        <rect class="graph-3d-minimap__backdrop" x="0" y="0" width="180" height="154" rx="10" />
        <line
          v-for="edge in minimapModel.edges"
          :key="edge.id"
          class="graph-3d-minimap__edge"
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          :stroke="edge.color"
          :stroke-opacity="edge.opacity"
          :stroke-width="edge.strokeWidth"
          :stroke-dasharray="edge.dashArray"
        />
        <circle
          v-for="node in minimapModel.nodes"
          :key="node.id"
          class="graph-3d-minimap__node"
          :cx="node.x"
          :cy="node.y"
          :r="node.radius"
          :fill="node.fill"
          :stroke="node.stroke"
          :opacity="node.opacity"
        />
      </svg>
      <div class="graph-3d-controls__buttons">
        <button type="button" :disabled="cameraLocked" title="放大 3D 视角" aria-label="放大 3D 视角" @click="zoomIn">
          +
        </button>
        <button type="button" :disabled="cameraLocked" title="缩小 3D 视角" aria-label="缩小 3D 视角" @click="zoomOut">
          -
        </button>
        <button
          type="button"
          :disabled="cameraLocked"
          title="适配 3D 视角"
          aria-label="适配 3D 视角"
          @click="resetCamera()"
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
        </button>
        <button
          type="button"
          :title="cameraLocked ? '解锁 3D 视角' : '锁定 3D 视角'"
          :aria-label="cameraLocked ? '解锁 3D 视角' : '锁定 3D 视角'"
          @click="emit('toggle-camera-lock')"
        >
          <svg
            v-if="cameraLocked"
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
        </button>
      </div>
    </div>
  </div>
</template>
