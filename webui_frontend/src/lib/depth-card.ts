import type { Directive, DirectiveBinding } from 'vue'

export interface DepthCardOptions {
  mode: 'tracking' | 'shadow-only'
  intensity?: 'normal' | 'subtle'
  scale?: number
}

export interface DepthCardRect {
  left: number
  top: number
  width: number
  height: number
}

export interface DepthCardPointer {
  clientX: number
  clientY: number
}

export interface DepthCardComputedState {
  rotateXDeg: number
  rotateYDeg: number
  liftPx: number
  shadowXpx: number
  shadowYpx: number
}

const SHADOW_ONLY_LIFT_PX = 2
const TRACKING_PROFILES = {
  normal: {
    maxRotationDeg: 3.5,
    liftPx: 4,
    shadowXAmplitudePx: 12,
    shadowYBasePx: 22,
    shadowYAmplitudePx: 6,
  },
  subtle: {
    maxRotationDeg: 2.4,
    liftPx: 3,
    shadowXAmplitudePx: 8,
    shadowYBasePx: 18,
    shadowYAmplitudePx: 4,
  },
} as const
const SHADOW_ONLY_STATE: DepthCardComputedState = {
  rotateXDeg: 0,
  rotateYDeg: 0,
  liftPx: SHADOW_ONLY_LIFT_PX,
  shadowXpx: 0,
  shadowYpx: 18,
}

const depthCardStateKey = Symbol('depth-card-state')

type DepthCardElement = HTMLElement & {
  [depthCardStateKey]?: DepthCardDirectiveState
}

type DepthCardDirectiveState = {
  el: DepthCardElement
  options: DepthCardOptions
  enabled: boolean
  rect: DepthCardRect | null
  pointer: DepthCardPointer | null
  frameId: number | null
  disposeMediaListeners: () => void
  onPointerEnter: (event: PointerEvent) => void
  onPointerMove: (event: PointerEvent) => void
  onPointerLeave: () => void
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function round(value: number) {
  return Number(value.toFixed(3))
}

function resolveDepthCardOptions(rawValue: DepthCardOptions | undefined | null): DepthCardOptions {
  return {
    mode: rawValue?.mode === 'shadow-only' ? 'shadow-only' : 'tracking',
    intensity: rawValue?.intensity === 'subtle' ? 'subtle' : 'normal',
    scale: clamp(rawValue?.scale ?? 1, 0, 1),
  }
}

function resolveTrackingProfile(options: DepthCardOptions) {
  return options.intensity === 'subtle' ? TRACKING_PROFILES.subtle : TRACKING_PROFILES.normal
}

function snapshotRect(rect: DOMRect): DepthCardRect {
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
  }
}

function applyDepthCardState(element: HTMLElement, state: DepthCardComputedState) {
  element.style.setProperty('--depth-rotate-x', `${state.rotateXDeg}deg`)
  element.style.setProperty('--depth-rotate-y', `${state.rotateYDeg}deg`)
  element.style.setProperty('--depth-lift', `${state.liftPx}px`)
  element.style.setProperty('--depth-shadow-x', `${state.shadowXpx}px`)
  element.style.setProperty('--depth-shadow-y', `${state.shadowYpx}px`)
}

function resetDepthCardState(element: HTMLElement) {
  applyDepthCardState(element, {
    rotateXDeg: 0,
    rotateYDeg: 0,
    liftPx: 0,
    shadowXpx: 0,
    shadowYpx: 0,
  })
}

function cancelDepthCardFrame(state: DepthCardDirectiveState) {
  if (state.frameId == null || typeof window === 'undefined') {
    return
  }

  window.cancelAnimationFrame(state.frameId)
  state.frameId = null
}

function deactivateDepthCard(state: DepthCardDirectiveState) {
  cancelDepthCardFrame(state)
  state.pointer = null
  state.rect = null
  state.el.classList.remove('depth-card--active')
  resetDepthCardState(state.el)
}

function isInteractiveDepthCardEnvironment() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return true
  }

  return (
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches &&
    window.matchMedia('(hover: hover)').matches &&
    window.matchMedia('(pointer: fine)').matches
  )
}

function syncDepthCardCapability(state: DepthCardDirectiveState) {
  state.enabled = isInteractiveDepthCardEnvironment()
  if (!state.enabled) {
    deactivateDepthCard(state)
  }
}

function subscribeToCapabilityChanges(onChange: () => void) {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {}
  }

  const queries = [
    window.matchMedia('(prefers-reduced-motion: reduce)'),
    window.matchMedia('(hover: hover)'),
    window.matchMedia('(pointer: fine)'),
  ]
  const listener = () => onChange()

  for (const query of queries) {
    const legacyQuery = query as MediaQueryList & {
      addListener?: (callback: () => void) => void
      removeListener?: (callback: () => void) => void
    }

    if ('addEventListener' in query) {
      query.addEventListener('change', listener)
    } else if (legacyQuery.addListener) {
      legacyQuery.addListener(listener)
    }
  }

  return () => {
    for (const query of queries) {
      const legacyQuery = query as MediaQueryList & {
        addListener?: (callback: () => void) => void
        removeListener?: (callback: () => void) => void
      }

      if ('removeEventListener' in query) {
        query.removeEventListener('change', listener)
      } else if (legacyQuery.removeListener) {
        legacyQuery.removeListener(listener)
      }
    }
  }
}

function syncDepthCardModeClasses(element: HTMLElement, options: DepthCardOptions) {
  element.classList.add('depth-card')
  element.classList.toggle('depth-card--tracking', options.mode === 'tracking')
  element.classList.toggle('depth-card--shadow-only', options.mode === 'shadow-only')
}

function scheduleDepthCardFrame(state: DepthCardDirectiveState) {
  if (
    state.frameId != null ||
    state.options.mode !== 'tracking' ||
    state.pointer == null ||
    state.rect == null ||
    typeof window === 'undefined'
  ) {
    return
  }

  state.frameId = window.requestAnimationFrame(() => {
    state.frameId = null

    if (state.pointer == null || state.rect == null) {
      return
    }

    applyDepthCardState(state.el, computeDepthCardState(state.rect, state.pointer, state.options))
  })
}

function activateDepthCard(state: DepthCardDirectiveState, event: PointerEvent) {
  if (!state.enabled) {
    return
  }

  state.rect = snapshotRect(state.el.getBoundingClientRect())
  state.el.classList.add('depth-card--active')

  if (state.options.mode === 'shadow-only') {
    applyDepthCardState(state.el, SHADOW_ONLY_STATE)
    return
  }

  state.pointer = {
    clientX: event.clientX,
    clientY: event.clientY,
  }
  scheduleDepthCardFrame(state)
}

function createDepthCardState(
  element: DepthCardElement,
  binding: DirectiveBinding<DepthCardOptions | undefined>,
): DepthCardDirectiveState {
  const state: DepthCardDirectiveState = {
    el: element,
    options: resolveDepthCardOptions(binding.value),
    enabled: isInteractiveDepthCardEnvironment(),
    rect: null,
    pointer: null,
    frameId: null,
    disposeMediaListeners: () => {},
    onPointerEnter: () => {},
    onPointerMove: () => {},
    onPointerLeave: () => {},
  }

  state.disposeMediaListeners = subscribeToCapabilityChanges(() => syncDepthCardCapability(state))

  state.onPointerEnter = (event) => {
    activateDepthCard(state, event)
  }

  state.onPointerMove = (event) => {
    if (!state.enabled || state.options.mode !== 'tracking') {
      return
    }

    state.pointer = {
      clientX: event.clientX,
      clientY: event.clientY,
    }
    scheduleDepthCardFrame(state)
  }

  state.onPointerLeave = () => {
    deactivateDepthCard(state)
  }

  return state
}

function mountDepthCard(
  element: DepthCardElement,
  binding: DirectiveBinding<DepthCardOptions | undefined>,
) {
  const state = createDepthCardState(element, binding)
  element[depthCardStateKey] = state

  syncDepthCardModeClasses(element, state.options)
  resetDepthCardState(element)

  element.addEventListener('pointerenter', state.onPointerEnter)
  element.addEventListener('pointermove', state.onPointerMove)
  element.addEventListener('pointerleave', state.onPointerLeave)
  element.addEventListener('pointercancel', state.onPointerLeave)
}

function updateDepthCard(
  element: DepthCardElement,
  binding: DirectiveBinding<DepthCardOptions | undefined>,
) {
  const state = element[depthCardStateKey]
  if (!state) {
    return
  }

  const nextOptions = resolveDepthCardOptions(binding.value)
  const modeChanged = state.options.mode !== nextOptions.mode
  const intensityChanged = state.options.intensity !== nextOptions.intensity

  if (modeChanged) {
    deactivateDepthCard(state)
  }

  state.options = nextOptions
  syncDepthCardModeClasses(element, state.options)

  if (!modeChanged && intensityChanged && state.el.classList.contains('depth-card--active')) {
    if (state.options.mode === 'shadow-only') {
      applyDepthCardState(state.el, SHADOW_ONLY_STATE)
    } else if (state.pointer != null && state.rect != null) {
      applyDepthCardState(state.el, computeDepthCardState(state.rect, state.pointer, state.options))
    }
  }

  syncDepthCardCapability(state)
}

function unmountDepthCard(element: DepthCardElement) {
  const state = element[depthCardStateKey]
  if (!state) {
    return
  }

  deactivateDepthCard(state)
  state.disposeMediaListeners()
  element.removeEventListener('pointerenter', state.onPointerEnter)
  element.removeEventListener('pointermove', state.onPointerMove)
  element.removeEventListener('pointerleave', state.onPointerLeave)
  element.removeEventListener('pointercancel', state.onPointerLeave)
  delete element[depthCardStateKey]
}

export function computeDepthCardState(
  rect: DepthCardRect,
  pointer: DepthCardPointer,
  options?: DepthCardOptions,
): DepthCardComputedState {
  const resolvedOptions = resolveDepthCardOptions(options)
  if (resolvedOptions.mode === 'shadow-only') {
    return SHADOW_ONLY_STATE
  }

  const halfWidth = Math.max(rect.width / 2, 1)
  const halfHeight = Math.max(rect.height / 2, 1)
  const normalizedX = clamp((pointer.clientX - (rect.left + halfWidth)) / halfWidth, -1, 1)
  const normalizedY = clamp((pointer.clientY - (rect.top + halfHeight)) / halfHeight, -1, 1)
  const profile = resolveTrackingProfile(resolvedOptions)
  const scale = resolvedOptions.scale ?? 1

  return {
    rotateXDeg: round(normalizedY * -profile.maxRotationDeg * scale),
    rotateYDeg: round(normalizedX * profile.maxRotationDeg * scale),
    liftPx: round(profile.liftPx * scale),
    shadowXpx: round(normalizedX * profile.shadowXAmplitudePx * scale),
    shadowYpx: round((profile.shadowYBasePx + normalizedY * profile.shadowYAmplitudePx) * scale),
  }
}

export const depthCardDirective: Directive<HTMLElement, DepthCardOptions | undefined> = {
  mounted(element, binding) {
    mountDepthCard(element as DepthCardElement, binding)
  },
  updated(element, binding) {
    updateDepthCard(element as DepthCardElement, binding)
  },
  unmounted(element) {
    unmountDepthCard(element as DepthCardElement)
  },
}
