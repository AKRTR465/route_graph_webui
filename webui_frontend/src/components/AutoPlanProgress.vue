<script setup lang="ts">
import type { AutoPlanJobStatus } from '../types/route-graph'

defineProps<{
  jobStatus: AutoPlanJobStatus | null
  headline: string
  recovered: boolean
  activeProgress: boolean
  phaseLabel: string
  progressMaximum: number
  progressValue: number
  progressPercent: number
  progressPercentRounded: number
  summary: string[]
}>()
</script>

<template>
  <div class="route-callout plan-progress-card" :class="`plan-progress-card--${jobStatus?.state ?? 'idle'}`">
    <div class="candidate-detail__head plan-progress-card__head">
      <div>
        <p class="panel-kicker">自动规划</p>
        <h3>{{ headline }}</h3>
      </div>
      <span v-if="recovered" class="summary-tag">已恢复</span>
      <span v-else-if="activeProgress" class="summary-tag">{{ phaseLabel }}</span>
    </div>

    <div v-if="activeProgress" class="plan-progress-card__meter">
      <div class="plan-progress-card__bar">
        <div
          class="plan-progress-card__track"
          role="progressbar"
          aria-label="自动规划进度"
          :aria-valuemin="0"
          :aria-valuemax="progressMaximum"
          :aria-valuenow="progressValue"
        >
          <div class="plan-progress-card__fill" :style="{ width: `${progressPercent}%` }" />
        </div>
        <span class="plan-progress-card__percent">{{ progressPercentRounded }}%</span>
      </div>
      <div class="plan-progress-card__stats">
        <span v-for="item in summary" :key="item">{{ item }}</span>
      </div>
    </div>

    <p v-if="jobStatus?.state === 'running'" class="hint-text">
      后台任务正在持续生成候选路线，页面刷新后会自动恢复当前进度。
    </p>
    <p v-else-if="jobStatus?.state === 'succeeded'" class="hint-text">
      当前候选列表已切换为这次自动规划的最新结果。
    </p>
    <p v-else-if="jobStatus?.state === 'failed'" class="hint-text">
      {{ jobStatus?.error || '自动规划失败，请调整参数后重试。' }}
    </p>
  </div>
</template>
