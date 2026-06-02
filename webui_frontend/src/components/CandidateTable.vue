<script setup lang="ts">
import type { RouteCandidate } from '../types/route-graph'

export type CandidateDisplayRow = {
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
  rows: CandidateDisplayRow[]
  selectedCandidateId: string | null
  selectedRowIdSet: Set<string>
  formatDistance: (value: number) => string
}>()

const emit = defineEmits<{
  (event: 'row-click', candidateId: string, mouseEvent: MouseEvent): void
  (event: 'row-double-click', candidateId: string): void
}>()
</script>

<template>
  <table class="candidate-table">
    <thead>
      <tr>
        <th>保留</th>
        <th>排名</th>
        <th>候选ID</th>
        <th>起点</th>
        <th>终点</th>
        <th>长度</th>
        <th>帧数</th>
        <th>边经过数</th>
        <th>重复节点数</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="row in rows"
        :key="row.id"
        class="candidate-table__row"
        :class="{
          'candidate-table__row--current': row.id === selectedCandidateId,
          'candidate-table__row--selected': selectedRowIdSet.has(row.id),
        }"
        @click="emit('row-click', row.id, $event)"
        @dblclick="emit('row-double-click', row.id)"
      >
        <td class="candidate-table__keep">{{ row.candidate.selected ? 'Y' : '' }}</td>
        <td>{{ row.displayRank }}</td>
        <td>{{ row.id }}</td>
        <td>{{ row.startNode || '—' }}</td>
        <td>{{ row.endNode || '—' }}</td>
        <td>{{ formatDistance(row.candidate.total_length) }}</td>
        <td>{{ row.frameCount == null ? '—' : row.frameCount }}</td>
        <td>{{ row.edgePassCount }}</td>
        <td>{{ row.repeatNodeCount }}</td>
      </tr>
    </tbody>
  </table>
</template>
