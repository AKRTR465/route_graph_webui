export type AutoPlanJobStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export function readStoredAutoPlanJobs(storage: AutoPlanJobStorage, storageKey: string): Record<string, number> {
  try {
    const raw = storage.getItem(storageKey)
    if (!raw) {
      return {}
    }
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') {
      return {}
    }
    const normalized: Record<string, number> = {}
    for (const [graphPath, jobId] of Object.entries(parsed)) {
      if (!graphPath) {
        continue
      }
      const numericJobId =
        typeof jobId === 'number'
          ? jobId
          : typeof jobId === 'string'
            ? Number.parseInt(jobId, 10)
            : Number.NaN
      if (Number.isFinite(numericJobId) && numericJobId > 0) {
        normalized[graphPath] = numericJobId
      }
    }
    return normalized
  } catch {
    return {}
  }
}

export function writeStoredAutoPlanJobs(
  storage: AutoPlanJobStorage,
  storageKey: string,
  jobMap: Record<string, number>,
): void {
  try {
    if (Object.keys(jobMap).length === 0) {
      storage.removeItem(storageKey)
      return
    }
    storage.setItem(storageKey, JSON.stringify(jobMap))
  } catch {
    // Ignore storage failures; the in-memory progress UI still works.
  }
}

export function getStoredAutoPlanJobId(
  storage: AutoPlanJobStorage,
  storageKey: string,
  graphPath?: string | null,
): number | null {
  const normalizedGraphPath = graphPath?.trim()
  if (!normalizedGraphPath) {
    return null
  }
  return readStoredAutoPlanJobs(storage, storageKey)[normalizedGraphPath] ?? null
}

export function setStoredAutoPlanJobId(
  storage: AutoPlanJobStorage,
  storageKey: string,
  graphPath: string,
  jobId: number,
): void {
  const jobMap = readStoredAutoPlanJobs(storage, storageKey)
  jobMap[graphPath] = jobId
  writeStoredAutoPlanJobs(storage, storageKey, jobMap)
}

export function clearStoredAutoPlanJobId(
  storage: AutoPlanJobStorage,
  storageKey: string,
  graphPath?: string | null,
): void {
  const normalizedGraphPath = graphPath?.trim()
  if (!normalizedGraphPath) {
    return
  }
  const jobMap = readStoredAutoPlanJobs(storage, storageKey)
  if (!(normalizedGraphPath in jobMap)) {
    return
  }
  delete jobMap[normalizedGraphPath]
  writeStoredAutoPlanJobs(storage, storageKey, jobMap)
}
