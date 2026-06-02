<script setup lang="ts">
import { computed } from 'vue'

import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'

const vDepthCard = depthCardDirective

const props = defineProps<{
  depthCard: DepthCardOptions
  groupColorOptions: string[]
  activeGroupColor: string | null
  bridgeColorDraft: string
  activeGroupDisplayLabel: string
  activeGroupConfigEnabled: boolean
  groupConfigForm: {
    altitudeMode: 'fixed' | 'follow_nodes'
    fixedZ: string
    altitudeOffset: string
    nodeSampleRadius: string
    takeoffLandingRelativeZ: string
    takeoffLandingStepDistance: string
  }
  resolveGroupDisplayLabel: (color: string) => string
}>()

const emit = defineEmits<{
  (event: 'set-active-group-focus', color: string | null): void
  (event: 'update:bridgeColorDraft', color: string): void
  (event: 'apply-bridge-color'): void
}>()

const bridgeColorModel = computed({
  get: () => props.bridgeColorDraft,
  set: (value: string) => emit('update:bridgeColorDraft', value),
})
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">颜色组</p>
        <h2>颜色组配置</h2>
      </div>
    </div>

    <div class="field-group">
      <span>当前颜色组</span>
      <div v-if="groupColorOptions.length" class="selection-list selection-list--compact">
        <button
          type="button"
          class="selection-item"
          :class="{ 'selection-item--active': activeGroupColor == null }"
          @click="emit('set-active-group-focus', null)"
        >
          <span class="selection-item__swatch selection-item__swatch--empty" />
          <span class="selection-item__label">取消聚焦 / 全部显示</span>
          <span class="selection-item__check">{{ activeGroupColor == null ? '当前' : '切换' }}</span>
        </button>
        <button
          v-for="color in groupColorOptions"
          :key="`group-${color}`"
          type="button"
          class="selection-item"
          :class="{ 'selection-item--active': color === activeGroupColor }"
          @click="emit('set-active-group-focus', color)"
        >
          <span class="selection-item__swatch" :style="{ '--swatch-color': color }" />
          <span class="selection-item__label">{{ resolveGroupDisplayLabel(color) }}</span>
          <span class="selection-item__check">{{ color === activeGroupColor ? '当前' : '切换' }}</span>
        </button>
      </div>
      <div v-else class="empty-state"><p>当前图还没有可用的颜色组。</p></div>
    </div>

    <div class="field-grid">
      <label class="field-group">
        <span>桥接边颜色</span>
        <input v-model="bridgeColorModel" type="color" />
      </label>
      <label class="field-group">
        <span>颜色值</span>
        <input v-model="bridgeColorModel" type="text" placeholder="#F97316" />
      </label>
    </div>

    <div class="panel-actions">
      <button class="chip-button" @click="emit('apply-bridge-color')">应用桥接色</button>
    </div>

    <p class="hint-text">当前颜色组：{{ activeGroupDisplayLabel }}。桥接色只影响桥接边显示和后续导出。</p>

    <template v-if="activeGroupConfigEnabled">
      <div class="field-grid">
        <label class="field-group">
          <span>当前组节点采样半径</span>
          <input v-model="groupConfigForm.nodeSampleRadius" type="text" />
        </label>
        <label class="field-group">
          <span>当前组高度模式</span>
          <select v-model="groupConfigForm.altitudeMode">
            <option value="fixed">固定</option>
            <option value="follow_nodes">跟随节点</option>
          </select>
        </label>
      </div>
      <div class="field-grid">
        <label class="field-group">
          <span>当前组固定高度 Z</span>
          <input v-model="groupConfigForm.fixedZ" type="text" placeholder="可选" />
        </label>
        <label class="field-group">
          <span>当前组高度偏移</span>
          <input v-model="groupConfigForm.altitudeOffset" type="text" />
        </label>
      </div>
      <div class="field-grid">
        <label class="field-group">
          <span>当前组起降相对航线下偏移</span>
          <input v-model="groupConfigForm.takeoffLandingRelativeZ" type="text" placeholder="可选" />
        </label>
        <label class="field-group">
          <span>当前组起飞 / 降落插值步长</span>
          <input v-model="groupConfigForm.takeoffLandingStepDistance" type="text" placeholder="可留空继承全局" />
        </label>
      </div>
    </template>
    <div v-else class="empty-state">
      <p>当前处于全部显示状态。选择一个具体颜色组后，才能编辑该组的导出覆盖参数。</p>
    </div>
  </section>
</template>
