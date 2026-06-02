<script setup lang="ts">
import { computed } from 'vue'

import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'

const vDepthCard = depthCardDirective

const props = defineProps<{
  depthCard: DepthCardOptions
  currentPaintColorLabel: string
  isPaintModeActive: boolean
  paintColor: string | null
  newPaletteColor: string
  paletteState: {
    usedColors: string[]
    sessionColors: string[]
  }
  resolveGroupDisplayLabel: (color: string) => string
}>()

const emit = defineEmits<{
  (event: 'toggle-paint-mode'): void
  (event: 'add-palette-color'): void
  (event: 'set-paint-color-selection', color: string | null): void
  (event: 'update:newPaletteColor', color: string): void
}>()

const paletteColorModel = computed({
  get: () => props.newPaletteColor,
  set: (value: string) => emit('update:newPaletteColor', value),
})
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">颜色工具</p>
        <h2>调色盘与染色</h2>
      </div>
    </div>

    <div class="detail-grid">
      <div><dt>当前画笔</dt><dd>{{ currentPaintColorLabel }}</dd></div>
      <div><dt>染色模式</dt><dd>{{ isPaintModeActive ? '已开启' : '已关闭' }}</dd></div>
    </div>

    <div class="panel-actions panel-actions--primary">
      <button class="action-button" :disabled="!paintColor" @click="emit('toggle-paint-mode')">
        {{ isPaintModeActive ? '退出染色模式' : '进入染色模式' }}
      </button>
    </div>
    <p class="hint-text">开启后左键点击边会直接染边，并暂停普通选点、选边、连边和拖拽。</p>

    <div class="field-grid">
      <label class="field-group">
        <span>新增调色盘颜色</span>
        <input v-model="paletteColorModel" type="color" />
      </label>
      <label class="field-group">
        <span>颜色值</span>
        <input v-model="paletteColorModel" type="text" placeholder="#334155" />
      </label>
    </div>

    <div class="panel-actions">
      <button class="chip-button" @click="emit('add-palette-color')">新增调色盘颜色</button>
    </div>

    <div class="field-group">
      <span>已使用颜色</span>
      <div v-if="paletteState.usedColors.length" class="selection-list selection-list--compact">
        <button
          v-for="color in paletteState.usedColors"
          :key="`used-${color}`"
          type="button"
          class="selection-item"
          :class="{ 'selection-item--active': color === paintColor }"
          @click="emit('set-paint-color-selection', color)"
        >
          <span class="selection-item__swatch" :style="{ '--swatch-color': color }" />
          <span class="selection-item__label">{{ resolveGroupDisplayLabel(color) }}</span>
          <span class="selection-item__check">{{ color === paintColor ? '当前画笔' : '设为画笔' }}</span>
        </button>
      </div>
      <div v-else class="empty-state"><p>暂无已使用颜色。</p></div>
    </div>

    <div class="field-group">
      <span>会话新增颜色</span>
      <div v-if="paletteState.sessionColors.length" class="selection-list selection-list--compact">
        <button
          v-for="color in paletteState.sessionColors"
          :key="`session-${color}`"
          type="button"
          class="selection-item"
          :class="{ 'selection-item--active': color === paintColor }"
          @click="emit('set-paint-color-selection', color)"
        >
          <span class="selection-item__swatch" :style="{ '--swatch-color': color }" />
          <span class="selection-item__label">{{ color }}</span>
          <span class="selection-item__check">{{ color === paintColor ? '当前画笔' : '设为画笔' }}</span>
        </button>
      </div>
      <div v-else class="empty-state"><p>暂无会话新增颜色。</p></div>
    </div>
  </section>
</template>
