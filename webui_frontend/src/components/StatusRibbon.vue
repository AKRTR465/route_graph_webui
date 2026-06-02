<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'

const vDepthCard = depthCardDirective

defineProps<{
  nodeCount: string
  edgeCount: string
  enabledEdgeCount: string
  groupColorCount: string
  updatedAt: string
  trackingDepthCard: DepthCardOptions
}>()
</script>

<template>
  <section class="status-ribbon">
    <div v-depth-card="trackingDepthCard" class="stat-pill"><span>节点</span><strong>{{ nodeCount }}</strong></div>
    <div v-depth-card="trackingDepthCard" class="stat-pill"><span>边</span><strong>{{ edgeCount }}</strong></div>
    <div v-depth-card="trackingDepthCard" class="stat-pill"><span>启用边</span><strong>{{ enabledEdgeCount }}</strong></div>
    <div v-depth-card="trackingDepthCard" class="stat-pill"><span>颜色组</span><strong>{{ groupColorCount }}</strong></div>
    <div v-depth-card="trackingDepthCard" class="stat-pill"><span>更新时间</span><strong>{{ updatedAt }}</strong></div>
  </section>
</template>
