export function sortCandidateIdsByDisplayOrder(
  candidateIds: string[],
  rowIndexLookup: ReadonlyMap<string, number>,
): string[] {
  const uniqueCandidateIds: string[] = []
  const seenCandidateIds = new Set<string>()
  for (const candidateId of candidateIds) {
    if (seenCandidateIds.has(candidateId) || !rowIndexLookup.has(candidateId)) {
      continue
    }
    seenCandidateIds.add(candidateId)
    uniqueCandidateIds.push(candidateId)
  }

  uniqueCandidateIds.sort((left, right) => {
    return (
      (rowIndexLookup.get(left) ?? Number.MAX_SAFE_INTEGER) -
      (rowIndexLookup.get(right) ?? Number.MAX_SAFE_INTEGER)
    )
  })
  return uniqueCandidateIds
}

export function resolveCandidateRangeSelection(
  rowIds: string[],
  rowIndexLookup: ReadonlyMap<string, number>,
  targetId: string,
  fallbackAnchorId: string,
): { ids: string[]; anchorId: string } {
  const anchorIndex = rowIndexLookup.get(fallbackAnchorId)
  const targetIndex = rowIndexLookup.get(targetId)
  if (anchorIndex == null || targetIndex == null) {
    return { ids: [targetId], anchorId: targetId }
  }

  const startIndex = Math.min(anchorIndex, targetIndex)
  const endIndex = Math.max(anchorIndex, targetIndex)
  return {
    ids: rowIds.slice(startIndex, endIndex + 1),
    anchorId: fallbackAnchorId,
  }
}

export function resolveCandidateKeepTargetIds(
  candidateId: string | null | undefined,
  selectedRowIds: string[],
  selectedRowIdSet: ReadonlySet<string>,
  selectedCandidateId: string | null | undefined,
): string[] {
  if (candidateId && selectedRowIdSet.has(candidateId) && selectedRowIds.length > 1) {
    return [...selectedRowIds]
  }
  if (candidateId) {
    return [candidateId]
  }
  if (selectedRowIds.length > 0) {
    return [...selectedRowIds]
  }
  if (selectedCandidateId) {
    return [selectedCandidateId]
  }
  return []
}
