import { computed, ref } from 'vue'

import { sortCandidateIdsByDisplayOrder } from '../lib/candidate-selection'

export function useGraphSelection() {
  const selectedCandidateId = ref<string | null>(null)
  const selectedNodeIds = ref<string[]>([])
  const primarySelectedNodeId = ref<string | null>(null)
  const selectedEdgeId = ref<string | null>(null)
  const selectedCandidateRowIds = ref<string[]>([])
  const candidateRowSelectionAnchorId = ref<string | null>(null)
  const candidateRowClickTimeoutId = ref<number | null>(null)

  const selectedNodeIdSet = computed(() => new Set(selectedNodeIds.value))
  const selectedCandidateRowIdSet = computed(() => new Set(selectedCandidateRowIds.value))

  function clearCandidateRowClickTimer() {
    if (candidateRowClickTimeoutId.value == null) {
      return
    }
    window.clearTimeout(candidateRowClickTimeoutId.value)
    candidateRowClickTimeoutId.value = null
  }

  function setSelectedCandidateRows(
    candidateIds: string[],
    rowIndexLookup: ReadonlyMap<string, number>,
    anchorId: string | null = null,
  ) {
    selectedCandidateRowIds.value = sortCandidateIdsByDisplayOrder(candidateIds, rowIndexLookup)
    candidateRowSelectionAnchorId.value =
      anchorId ??
      selectedCandidateRowIds.value[selectedCandidateRowIds.value.length - 1] ??
      null
  }

  return {
    selectedCandidateId,
    selectedNodeIds,
    primarySelectedNodeId,
    selectedNodeIdSet,
    selectedEdgeId,
    selectedCandidateRowIds,
    selectedCandidateRowIdSet,
    candidateRowSelectionAnchorId,
    candidateRowClickTimeoutId,
    clearCandidateRowClickTimer,
    setSelectedCandidateRows,
  }
}
