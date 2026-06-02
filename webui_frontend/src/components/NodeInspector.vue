<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { GraphEdge, GraphNode } from '../types/route-graph'

const vDepthCard = depthCardDirective
const integerFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })

defineProps<{
  depthCard: DepthCardOptions
  trackingEnabled: boolean
  nodeDragEnabled: boolean
  nodeDragStatusText: string
  canResetSelectedNodePosition: boolean
  resettingNodePosition: boolean
  selectedNode: GraphNode | null
  selectedNodeIds: string[]
  selectedEdge: GraphEdge | null
  planStartNodeId: string
  planEndNodeId: string
  planViaNodeIds: string[]
  nodeDraft: {
    name: string
    tagsText: string
    yawHint: string
    sampleRadius: string
  }
  savingNode: boolean
}>()

const emit = defineEmits<{
  (event: 'toggle-tracking'): void
  (event: 'toggle-node-drag'): void
  (event: 'reset-selected-node-position'): void
  (event: 'assign-start'): void
  (event: 'toggle-via'): void
  (event: 'assign-end'): void
  (event: 'submit-node-update'): void
}>()
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">选择</p>
        <h2>节点检查器</h2>
      </div>
      <button
        type="button"
        class="chip-button"
        :class="{ 'chip-button--active': trackingEnabled }"
        :aria-pressed="trackingEnabled"
        @click="emit('toggle-tracking')"
      >
        {{ trackingEnabled ? '左侧倾斜开' : '左侧倾斜关' }}
      </button>
    </div>

    <div class="inspector-tools">
      <span class="inline-chip status-chip" :class="nodeDragEnabled ? 'status-chip--active' : 'status-chip--locked'">
        {{ nodeDragStatusText }}
      </span>
      <div class="anchor-strip">
        <button class="chip-button" @click="emit('toggle-node-drag')">{{ nodeDragEnabled ? '关闭拖拽' : '开启拖拽' }}</button>
        <button class="chip-button" :disabled="!canResetSelectedNodePosition || resettingNodePosition" @click="emit('reset-selected-node-position')">
          {{ resettingNodePosition ? '重置中' : '重置主节点位置' }}
        </button>
      </div>
    </div>

    <template v-if="selectedNode">
      <dl class="detail-grid">
        <div><dt>节点 ID</dt><dd>{{ selectedNode.id }}</dd></div>
        <div>
          <dt>坐标</dt>
          <dd>
            {{ integerFormatter.format(selectedNode.position[0]) }},
            {{ integerFormatter.format(selectedNode.position[1]) }},
            {{ integerFormatter.format(selectedNode.position[2]) }}
          </dd>
        </div>
      </dl>

      <p class="hint-text" v-if="selectedNodeIds.length > 1">
        当前已多选 {{ selectedNodeIds.length }} 个节点，检查器显示主节点内容。
      </p>

      <div class="anchor-strip">
        <button class="chip-button" @click="emit('assign-start')">{{ planStartNodeId === selectedNode.id ? '取消起点' : '设为起点' }}</button>
        <button class="chip-button" @click="emit('toggle-via')">{{ planViaNodeIds.includes(selectedNode.id) ? '移除途经' : '设为途经' }}</button>
        <button class="chip-button" @click="emit('assign-end')">{{ planEndNodeId === selectedNode.id ? '取消终点' : '设为终点' }}</button>
      </div>

      <label class="field-group">
        <span>显示名称</span>
        <input v-model="nodeDraft.name" type="text" placeholder="节点显示名称" />
      </label>
      <label class="field-group">
        <span>标签</span>
        <textarea v-model="nodeDraft.tagsText" rows="3" placeholder="道路, 风景, 检查点" />
      </label>
      <div class="field-grid">
        <label class="field-group">
          <span>航向提示</span>
          <input v-model="nodeDraft.yawHint" type="text" placeholder="留空表示清除" />
        </label>
        <label class="field-group">
          <span>采样半径覆盖</span>
          <input v-model="nodeDraft.sampleRadius" type="text" placeholder="留空表示使用默认值" />
        </label>
      </div>
      <div class="panel-actions panel-actions--primary">
        <button class="action-button" :disabled="savingNode" @click="emit('submit-node-update')">{{ savingNode ? '保存中' : '保存节点属性' }}</button>
      </div>
    </template>

    <div class="empty-state" v-else>
      <p>{{ selectedEdge ? '当前选中的是边，节点检查器保持空状态。' : '在画布中点击节点后，这里会显示节点信息和编辑入口。' }}</p>
    </div>
  </section>
</template>
