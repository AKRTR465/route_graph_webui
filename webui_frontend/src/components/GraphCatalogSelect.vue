<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { GraphSummary } from '../types/api-contract'

const vDepthCard = depthCardDirective

defineProps<{
  availableGraphs: GraphSummary[]
  currentGraphPath: string
  trackingDepthCard: DepthCardOptions
}>()

const emit = defineEmits<{
  (event: 'change', value: Event): void
}>()
</script>

<template>
  <div v-depth-card="trackingDepthCard" class="header-control-card header-control-card--graph">
    <span class="header-control-card__label">当前图</span>
    <div class="header-control-card__body">
      <select class="header-control-select" :value="currentGraphPath" @change="emit('change', $event)">
        <option v-for="item in availableGraphs" :key="item.path" :value="item.path">
          {{ item.graph_name }} · {{ item.file_name }}
        </option>
      </select>
    </div>
  </div>
</template>
