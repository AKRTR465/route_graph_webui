<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { GraphEdge } from '../types/route-graph'

const vDepthCard = depthCardDirective

defineProps<{
  depthCard: DepthCardOptions
  selectedEdge: GraphEdge | null
  selectedEdgeLengthText: string
  selectedEdgeKindLabel: string
  selectedEdgeColorText: string
  mutatingEdge: boolean
  currentSelectionEdgeSummary: string
  canCreateEdgeFromSelection: boolean
  canRemoveEdgeFromSelection: boolean
  canMutateSelectedEdge: boolean
  paintColor: string | null
}>()

const emit = defineEmits<{
  (event: 'patch-edge', payload: { enabled?: boolean; bidirectional?: boolean }): void
  (event: 'delete-selected-edge'): void
  (event: 'create-selected-edge'): void
  (event: 'delete-selected-edge-or-between'): void
  (event: 'set-selected-edge-bridge'): void
  (event: 'paint-edge-with-current-color'): void
}>()
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">选择</p>
        <h2>边检查器</h2>
      </div>
    </div>

    <template v-if="selectedEdge">
      <dl class="detail-grid">
        <div><dt>边 ID</dt><dd>{{ selectedEdge.id }}</dd></div>
        <div><dt>长度</dt><dd>{{ selectedEdgeLengthText }}</dd></div>
        <div><dt>起点</dt><dd>{{ selectedEdge.source }}</dd></div>
        <div><dt>终点</dt><dd>{{ selectedEdge.target }}</dd></div>
        <div><dt>类型</dt><dd>{{ selectedEdgeKindLabel }}</dd></div>
        <div><dt>颜色</dt><dd>{{ selectedEdgeColorText }}</dd></div>
      </dl>

      <div class="anchor-strip">
        <button class="chip-button" :disabled="mutatingEdge" @click="emit('patch-edge', { enabled: !selectedEdge.enabled })">{{ selectedEdge.enabled ? '禁用边' : '启用边' }}</button>
        <button class="chip-button" :disabled="mutatingEdge" @click="emit('patch-edge', { bidirectional: selectedEdge.directed })">{{ selectedEdge.directed ? '切换为双向' : '切换为单向' }}</button>
        <button class="chip-button chip-button--danger" :disabled="mutatingEdge" @click="emit('delete-selected-edge')">删除边</button>
      </div>
    </template>

    <div class="empty-state" v-else>
      <p>在画布中点击边后，这里会显示边信息和编辑入口。</p>
    </div>
  </section>

  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">编辑</p>
        <h2>边操作</h2>
      </div>
    </div>

    <p class="hint-text">{{ currentSelectionEdgeSummary }}</p>

    <div class="panel-actions panel-actions--primary panel-actions--stacked">
      <button class="action-button" :disabled="mutatingEdge || !canCreateEdgeFromSelection" @click="emit('create-selected-edge')">
        创建边
      </button>
      <button class="action-button" :disabled="mutatingEdge || !canRemoveEdgeFromSelection" @click="emit('delete-selected-edge-or-between')">
        删除边
      </button>
    </div>

    <div class="anchor-strip anchor-strip--vertical">
      <button class="chip-button" :disabled="mutatingEdge || !canMutateSelectedEdge" @click="emit('patch-edge', { enabled: true })">启用边</button>
      <button class="chip-button" :disabled="mutatingEdge || !canMutateSelectedEdge" @click="emit('patch-edge', { enabled: false })">禁用边</button>
      <button class="chip-button" :disabled="mutatingEdge || !canMutateSelectedEdge" @click="emit('set-selected-edge-bridge')">设为桥接边</button>
      <button class="chip-button" :disabled="mutatingEdge || !canMutateSelectedEdge || !paintColor" @click="emit('paint-edge-with-current-color')">
        用当前画笔染边
      </button>
    </div>
  </section>
</template>
