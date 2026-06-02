import { onBeforeUnmount, ref } from 'vue'

import type { MissionPreview, MissionPreviewStatus } from '../types/route-graph'

export function useMissionPreview() {
  const previewMission = ref<MissionPreview | null>(null)
  const previewStatus = ref<MissionPreviewStatus>('no_candidate')
  const previewError = ref('')
  const previewLoading = ref(false)
  const previewCache = ref(new Map<string, MissionPreview>())
  const previewRefreshTimer = ref<number | null>(null)
  const previewRequestSequence = ref(0)
  const previewSourceRevision = ref(0)

  function getCachedMissionPreview(cacheKey: string): MissionPreview | null {
    return previewCache.value.get(cacheKey) ?? null
  }

  function setCachedMissionPreview(cacheKey: string, mission: MissionPreview) {
    previewCache.value.set(cacheKey, mission)
  }

  function deleteCachedMissionPreview(cacheKey: string) {
    const nextCache = new Map(previewCache.value)
    nextCache.delete(cacheKey)
    previewCache.value = nextCache
  }

  function clearMissionPreviewCache() {
    previewCache.value = new Map()
  }

  function clearPreviewRefreshTimer() {
    if (previewRefreshTimer.value == null) {
      return
    }
    window.clearTimeout(previewRefreshTimer.value)
    previewRefreshTimer.value = null
  }

  function schedulePreviewRefresh(callback: () => void | Promise<void>, delayMs: number) {
    clearPreviewRefreshTimer()
    previewRefreshTimer.value = window.setTimeout(() => {
      previewRefreshTimer.value = null
      void callback()
    }, delayMs)
  }

  function resetMissionPreviewState({
    clearCache = false,
    clearMission = true,
    status = 'no_candidate',
    error = '',
  }: {
    clearCache?: boolean
    clearMission?: boolean
    status?: MissionPreviewStatus
    error?: string
  } = {}) {
    clearPreviewRefreshTimer()
    previewLoading.value = false
    previewStatus.value = status
    previewError.value = error
    if (clearMission) {
      previewMission.value = null
    }
    if (clearCache) {
      clearMissionPreviewCache()
    }
  }

  function bumpPreviewSourceRevision() {
    previewSourceRevision.value += 1
  }

  onBeforeUnmount(clearPreviewRefreshTimer)

  return {
    previewMission,
    previewStatus,
    previewError,
    previewLoading,
    previewCache,
    previewRefreshTimer,
    previewRequestSequence,
    previewSourceRevision,
    getCachedMissionPreview,
    setCachedMissionPreview,
    deleteCachedMissionPreview,
    clearMissionPreviewCache,
    clearPreviewRefreshTimer,
    schedulePreviewRefresh,
    resetMissionPreviewState,
    bumpPreviewSourceRevision,
  }
}
