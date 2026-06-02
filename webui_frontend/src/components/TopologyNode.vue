<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position, type NodeProps } from '@vue-flow/core'
import type { NodePulseVariant } from '../lib/node-pulse'

type TopologyNodeData = {
  label: string
  accent: string
  fill: string
  isSelected: boolean
  isPrimarySelected: boolean
  pulseVariant: NodePulseVariant
  pulseDelayMs: number
  onMiddleButtonGesture?: (nodeId: string, event: MouseEvent) => void
}

const props = defineProps<NodeProps<TopologyNodeData>>()

const accent = computed(() => props.data?.accent ?? '#111827')
const fill = computed(() => props.data?.fill ?? '#ffffff')
const label = computed(() => props.data?.label ?? props.id)
const pulseVariant = computed<NodePulseVariant>(() => props.data?.pulseVariant ?? 'none')
const pulseDelay = computed(() => `${props.data?.pulseDelayMs ?? 0}ms`)

function handleMouseDown(event: MouseEvent) {
  if (event.button !== 1) {
    return
  }

  event.preventDefault()
  event.stopPropagation()
  props.data?.onMiddleButtonGesture?.(props.id, event)
}
</script>

<template>
  <div
    class="topology-node"
    :class="{
      'topology-node--selected': props.data?.isSelected,
      'topology-node--primary': props.data?.isPrimarySelected,
      'topology-node--pulse-selected': pulseVariant === 'selected',
      'topology-node--pulse-primary': pulseVariant === 'primary',
    }"
    :style="{ '--node-accent': accent, '--node-fill': fill, '--node-pulse-delay': pulseDelay }"
    @mousedown="handleMouseDown"
  >
    <Handle id="target-top" type="target" :position="Position.Top" class="topology-node__handle" />
    <Handle id="target-right" type="target" :position="Position.Right" class="topology-node__handle" />
    <Handle id="target-bottom" type="target" :position="Position.Bottom" class="topology-node__handle" />
    <Handle id="target-left" type="target" :position="Position.Left" class="topology-node__handle" />
    <Handle
      id="target-center"
      type="target"
      :position="Position.Top"
      class="topology-node__handle topology-node__handle--center"
      :style="{ top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }"
    />

    <Handle id="source-top" type="source" :position="Position.Top" class="topology-node__handle" />
    <Handle id="source-right" type="source" :position="Position.Right" class="topology-node__handle" />
    <Handle id="source-bottom" type="source" :position="Position.Bottom" class="topology-node__handle" />
    <Handle id="source-left" type="source" :position="Position.Left" class="topology-node__handle" />
    <Handle
      id="source-center"
      type="source"
      :position="Position.Top"
      class="topology-node__handle topology-node__handle--center"
      :style="{ top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }"
    />

    <div class="topology-node__dot"></div>
    <div class="topology-node__label">{{ label }}</div>
  </div>
</template>
