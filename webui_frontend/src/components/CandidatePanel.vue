<script setup lang="ts">
import { ref } from 'vue'

import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { RouteCandidate, RouteCandidateSet } from '../types/route-graph'
import CandidateTable from './CandidateTable.vue'

const vDepthCard = depthCardDirective
const candidateTableContainer = ref<HTMLElement | null>(null)
const isCandidateTableFocused = ref(false)

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

defineProps<{
  depthCard: DepthCardOptions
  candidateSet: RouteCandidateSet | null
  candidateDisplayRows: CandidateDisplayRow[]
  selectedCandidateId: string | null
  selectedCandidateRowIds: string[]
  selectedCandidateRowIdSet: Set<string>
  selectedCandidateIds: string[]
  hasSelectedCandidateRows: boolean
  selectedCandidate: RouteCandidate | null
  selectedCandidateDetailRow: CandidateDisplayRow | null
  selectedCandidateDisplayRank: number | null
  previewSummaryItems: string[]
  candidateSetSummaryText: string
  formatDistance: (value: number) => string
}>()

const emit = defineEmits<{
  (event: 'keep-selected-candidate-rows'): void
  (event: 'unkeep-selected-candidate-rows'): void
  (event: 'toggle-selected-candidate-rows-keep'): void
  (event: 'candidate-row-click', candidateId: string, mouseEvent: MouseEvent): void
  (event: 'candidate-row-double-click', candidateId: string): void
  (event: 'candidate-table-keydown', keyboardEvent: KeyboardEvent): void
}>()

function focusCandidateTable() {
  candidateTableContainer.value?.focus()
}
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card panel-card--candidate-panel">
    <div class="panel-head">
      <div><p class="panel-kicker">候选</p><h2>路线候选</h2></div>
      <span class="summary-tag" v-if="candidateSet">{{ candidateSet.candidates.length }} 条</span>
    </div>
    <div class="candidate-summary" v-if="candidateSet">
      <span>已保留 {{ selectedCandidateIds.length }} 条</span>
      <span>{{ candidateSetSummaryText }}</span>
      <span v-if="candidateSet.meta.truncated">搜索已截断</span>
    </div>
    <template v-if="candidateDisplayRows.length">
      <div class="candidate-toolbar">
        <span class="hint-text">表格已选 {{ selectedCandidateRowIds.length }} 行，双击可切换保留，聚焦后可用 Ctrl+A / Cmd+A 全选。</span>
        <div class="anchor-strip">
          <button class="chip-button" :disabled="!hasSelectedCandidateRows" @click="emit('keep-selected-candidate-rows')">保留所选</button>
          <button class="chip-button" :disabled="!hasSelectedCandidateRows" @click="emit('unkeep-selected-candidate-rows')">取消保留</button>
          <button class="chip-button" :disabled="!hasSelectedCandidateRows" @click="emit('toggle-selected-candidate-rows-keep')">切换保留</button>
        </div>
      </div>

      <div
        ref="candidateTableContainer"
        class="candidate-table-wrap"
        :class="{ 'candidate-table-wrap--focused': isCandidateTableFocused }"
        tabindex="0"
        @focus="isCandidateTableFocused = true"
        @blur="isCandidateTableFocused = false"
        @keydown="emit('candidate-table-keydown', $event)"
        @mousedown="focusCandidateTable"
      >
        <CandidateTable
          :rows="candidateDisplayRows"
          :selected-candidate-id="selectedCandidateId"
          :selected-row-id-set="selectedCandidateRowIdSet"
          :format-distance="formatDistance"
          @row-click="(candidateId, mouseEvent) => emit('candidate-row-click', candidateId, mouseEvent)"
          @row-double-click="emit('candidate-row-double-click', $event)"
        />
      </div>

      <div
        v-if="selectedCandidate && selectedCandidateDetailRow"
        v-depth-card="depthCard"
        class="route-callout candidate-detail"
      >
        <div class="candidate-detail__head">
          <div>
            <p class="panel-kicker">当前预览</p>
            <h3>{{ selectedCandidate.candidate_id }}</h3>
          </div>
          <span class="summary-tag">排名 {{ selectedCandidateDisplayRank ?? selectedCandidate.rank }}</span>
        </div>
        <div class="candidate-meta">
          <span>{{ selectedCandidateDetailRow.startNode || '—' }} → {{ selectedCandidateDetailRow.endNode || '—' }}</span>
          <span>{{ formatDistance(selectedCandidate.total_length) }}</span>
          <span>{{ selectedCandidateDetailRow.frameCount == null ? '帧数未知' : `${selectedCandidateDetailRow.frameCount} 帧` }}</span>
          <span>{{ selectedCandidateDetailRow.edgePassCount }} 次边经过</span>
          <span>{{ selectedCandidateDetailRow.repeatNodeCount }} 个重复节点</span>
        </div>
        <div v-if="previewSummaryItems.length" class="candidate-meta candidate-meta--preview">
          <span v-for="item in previewSummaryItems" :key="item">{{ item }}</span>
        </div>
        <p class="candidate-path candidate-path--detail">{{ selectedCandidate.planned_nodes.join(' → ') }}</p>
      </div>
    </template>
    <div class="empty-state" v-else><p>生成候选路线后，可在这里预览并导出。</p></div>
  </section>
</template>
