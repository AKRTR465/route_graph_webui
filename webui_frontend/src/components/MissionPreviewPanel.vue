<script setup lang="ts">
defineProps<{
  tone: 'info' | 'success' | 'error'
  title: string
  loading: boolean
  statusText: string
  summaryItems: string[]
  refreshDisabled: boolean
}>()

const emit = defineEmits<{
  (event: 'refresh'): void
}>()
</script>

<template>
  <div class="route-callout preview-status-card" :class="`preview-status-card--${tone}`">
    <div class="candidate-detail__head">
      <div>
        <p class="panel-kicker">轨迹预览</p>
        <h3>{{ title }}</h3>
      </div>
      <span v-if="loading" class="summary-tag">更新中</span>
    </div>
    <p class="preview-status-card__text">{{ statusText }}</p>
    <div v-if="summaryItems.length" class="candidate-meta candidate-meta--preview">
      <span v-for="item in summaryItems" :key="`preview-${item}`">{{ item }}</span>
    </div>
    <div class="panel-actions">
      <button class="chip-button" :disabled="refreshDisabled" @click="emit('refresh')">
        刷新轨迹预览
      </button>
    </div>
  </div>
</template>
