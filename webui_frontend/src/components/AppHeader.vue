<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { GraphSummary } from '../types/api-contract'
import GraphCatalogSelect from './GraphCatalogSelect.vue'

const vDepthCard = depthCardDirective

defineProps<{
  availableGraphs: GraphSummary[]
  currentGraphPath: string
  loadingGraph: boolean
  validatingGraph: boolean
  viewportLocked: boolean
  trackingDepthCard: DepthCardOptions
}>()

const emit = defineEmits<{
  (event: 'graph-change', value: Event): void
  (event: 'refresh'): void
  (event: 'validate'): void
  (event: 'fit-view'): void
}>()
</script>

<template>
  <header class="app-header">
    <div class="brand-block">
      <h1>任务路线网页控制台</h1>
      <p class="hero-copy">
        全自动路径规划生成
      </p>
    </div>

    <div class="header-controls">
      <GraphCatalogSelect
        :available-graphs="availableGraphs"
        :current-graph-path="currentGraphPath"
        :tracking-depth-card="trackingDepthCard"
        @change="emit('graph-change', $event)"
      />

      <div v-depth-card="trackingDepthCard" class="header-control-card">
        <span class="header-control-card__label">刷新</span>
        <div class="header-control-card__body">
          <button
            class="action-button action-button--ghost action-button--header"
            :disabled="loadingGraph"
            @click="emit('refresh')"
          >
            {{ loadingGraph ? '刷新中' : '刷新图' }}
          </button>
        </div>
      </div>

      <div v-depth-card="trackingDepthCard" class="header-control-card">
        <span class="header-control-card__label">校验</span>
        <div class="header-control-card__body">
          <button
            class="action-button action-button--ghost action-button--header"
            :disabled="validatingGraph"
            @click="emit('validate')"
          >
            {{ validatingGraph ? '校验中' : '校验图' }}
          </button>
        </div>
      </div>

      <div v-depth-card="trackingDepthCard" class="header-control-card">
        <span class="header-control-card__label">视图</span>
        <div class="header-control-card__body">
          <button
            class="action-button action-button--ghost action-button--header"
            :disabled="viewportLocked"
            @click="emit('fit-view')"
          >
            适配视图
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
