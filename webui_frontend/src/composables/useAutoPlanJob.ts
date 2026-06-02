import { computed, onBeforeUnmount, ref, type Ref } from 'vue'

import type { AutoPlanJobStatus } from '../types/api-contract'

const integerFormatter = new Intl.NumberFormat('zh-CN')

export function useAutoPlanJob({
  storageKey,
  pollIntervalMs,
  poll,
}: {
  storageKey: string
  pollIntervalMs: number
  poll: (jobId: number, graphPath: string) => void | Promise<void>
}) {
  const activeAutoPlanJobId = ref<number | null>(null)
  const autoPlanJobStatus = ref<AutoPlanJobStatus | null>(null)
  const autoPlanRecovered = ref(false)
  const autoPlanPollTimer = ref<number | null>(null)

  function clearAutoPlanPollTimer() {
    if (autoPlanPollTimer.value == null) {
      return
    }
    window.clearTimeout(autoPlanPollTimer.value)
    autoPlanPollTimer.value = null
  }

  function scheduleAutoPlanPoll(jobId: number, graphPath: string) {
    clearAutoPlanPollTimer()
    autoPlanPollTimer.value = window.setTimeout(() => {
      void poll(jobId, graphPath)
    }, pollIntervalMs)
  }

  function resetTrackedAutoPlanState({ keepStatus = false }: { keepStatus?: boolean } = {}) {
    clearAutoPlanPollTimer()
    activeAutoPlanJobId.value = null
    autoPlanRecovered.value = false
    if (!keepStatus) {
      autoPlanJobStatus.value = null
    }
  }

  function readStoredAutoPlanJobs(): Record<string, number> {
    try {
      const rawValue = window.localStorage.getItem(storageKey)
      if (!rawValue) {
        return {}
      }
      const parsed = JSON.parse(rawValue) as Record<string, unknown>
      return Object.fromEntries(
        Object.entries(parsed)
          .map(([graphPath, jobId]) => [graphPath, Number(jobId)] as const)
          .filter((entry): entry is readonly [string, number] => Number.isInteger(entry[1])),
      )
    } catch {
      return {}
    }
  }

  function writeStoredAutoPlanJobs(jobMap: Record<string, number>) {
    window.localStorage.setItem(storageKey, JSON.stringify(jobMap))
  }

  function getStoredAutoPlanJobId(graphPath?: string | null) {
    if (!graphPath) {
      return null
    }
    return readStoredAutoPlanJobs()[graphPath] ?? null
  }

  function setStoredAutoPlanJobId(graphPath: string, jobId: number) {
    writeStoredAutoPlanJobs({
      ...readStoredAutoPlanJobs(),
      [graphPath]: jobId,
    })
  }

  function clearStoredAutoPlanJobId(graphPath?: string | null) {
    if (!graphPath) {
      return
    }
    const jobMap = readStoredAutoPlanJobs()
    delete jobMap[graphPath]
    writeStoredAutoPlanJobs(jobMap)
  }

  onBeforeUnmount(clearAutoPlanPollTimer)

  return {
    activeAutoPlanJobId,
    autoPlanJobStatus,
    autoPlanRecovered,
    clearAutoPlanPollTimer,
    scheduleAutoPlanPoll,
    resetTrackedAutoPlanState,
    readStoredAutoPlanJobs,
    writeStoredAutoPlanJobs,
    getStoredAutoPlanJobId,
    setStoredAutoPlanJobId,
    clearStoredAutoPlanJobId,
  }
}

export function resolveAutoPlanPhaseLabel(phase?: string | null): string {
  switch (phase) {
    case 'enumerating_pairs':
      return '枚举锚点对'
    case 'enumeration_completed':
      return '锚点对枚举完成'
    case 'planning_routes':
      return '生成候选路线'
    case 'optimizing_coverage':
      return '覆盖优化'
    case 'completed':
      return '完成'
    default:
      return '准备中'
  }
}

export function resolveAutoPlanStatusHeadline(state?: AutoPlanJobStatus['state'] | null): string {
  switch (state) {
    case 'running':
      return '自动规划进行中'
    case 'succeeded':
      return '自动规划已完成'
    case 'failed':
      return '自动规划失败'
    case 'cancelled':
      return '自动规划已取消'
    case 'timed_out':
      return '自动规划超时'
    default:
      return ''
  }
}

export function useAutoPlanJobStatus(
  autoPlanJobStatus: Ref<AutoPlanJobStatus | null>,
  currentGraphPath: Ref<string>,
) {
  const activeAutoPlanProgress = computed(() => autoPlanJobStatus.value?.progress ?? null)
  const shouldShowAutoPlanStatus = computed(
    () =>
      !!autoPlanJobStatus.value &&
      !!currentGraphPath.value &&
      autoPlanJobStatus.value.graph === currentGraphPath.value,
  )
  const autoPlanProgressMaximum = computed(() =>
    Math.max(activeAutoPlanProgress.value?.max_pairs_to_evaluate ?? 1, 1),
  )
  const autoPlanProgressValue = computed(() =>
    Math.min(activeAutoPlanProgress.value?.pairs_considered ?? 0, autoPlanProgressMaximum.value),
  )
  const autoPlanProgressPercent = computed(() =>
    Math.max(0, Math.min((autoPlanProgressValue.value / autoPlanProgressMaximum.value) * 100, 100)),
  )
  const autoPlanProgressPercentRounded = computed(() => Math.round(autoPlanProgressPercent.value))
  const autoPlanStatusHeadline = computed(() =>
    resolveAutoPlanStatusHeadline(autoPlanJobStatus.value?.state),
  )
  const autoPlanStatusPhaseLabel = computed(() =>
    resolveAutoPlanPhaseLabel(activeAutoPlanProgress.value?.phase),
  )
  const autoPlanStatusSummary = computed(() => {
    const progress = activeAutoPlanProgress.value
    if (!progress) {
      return []
    }
    return [
      `阶段：${autoPlanStatusPhaseLabel.value}`,
      `已评估 ${integerFormatter.format(progress.pairs_considered)} / ${integerFormatter.format(progress.max_pairs_to_evaluate)}`,
      `候选池 ${integerFormatter.format(progress.candidate_pool_size)} 条`,
      `已选 ${integerFormatter.format(progress.selected_routes)} / ${integerFormatter.format(progress.max_output_routes)} 条`,
    ]
  })

  return {
    activeAutoPlanProgress,
    shouldShowAutoPlanStatus,
    autoPlanProgressMaximum,
    autoPlanProgressValue,
    autoPlanProgressPercent,
    autoPlanProgressPercentRounded,
    autoPlanStatusHeadline,
    autoPlanStatusPhaseLabel,
    autoPlanStatusSummary,
  }
}
