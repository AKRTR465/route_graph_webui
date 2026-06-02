<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  updatingCanvasView: boolean
  flipHorizontal: boolean
  flipVertical: boolean
  canvasViewSummaryText: string
  nodeDragStatusText: string
  viewportLockStatusText: string
}>()

const emit = defineEmits<{
  (event: 'rotate-left'): void
  (event: 'rotate-right'): void
  (event: 'toggle-flip-horizontal'): void
  (event: 'toggle-flip-vertical'): void
  (event: 'reset-view'): void
}>()

const waveCanvas = ref<HTMLCanvasElement | null>(null)

defineExpose({
  waveCanvas,
})
</script>

<template>
  <section class="canvas-stage">
    <div class="canvas-stage__header">
      <div>
        <p class="panel-kicker">交互画布</p>
        <h2>路线图画布</h2>
      </div>
      <div class="canvas-stage__tools">
        <div class="anchor-strip">
          <button class="chip-button" :disabled="updatingCanvasView" @click="emit('rotate-left')">逆时针旋转</button>
          <button class="chip-button" :disabled="updatingCanvasView" @click="emit('rotate-right')">顺时针旋转</button>
          <button
            class="chip-button"
            :class="{ 'chip-button--active': flipHorizontal }"
            :disabled="updatingCanvasView"
            @click="emit('toggle-flip-horizontal')"
          >
            水平翻转
          </button>
          <button
            class="chip-button"
            :class="{ 'chip-button--active': flipVertical }"
            :disabled="updatingCanvasView"
            @click="emit('toggle-flip-vertical')"
          >
            垂直翻转
          </button>
          <button class="chip-button" :disabled="updatingCanvasView" @click="emit('reset-view')">重置视图</button>
        </div>
        <p class="hint-text">{{ canvasViewSummaryText }}</p>
      </div>
      <div class="legend-row">
        <span class="legend-item"><span class="legend-line legend-line--route" />高亮路线</span>
        <span class="legend-item"><span class="legend-line legend-line--preview" />模拟轨迹</span>
        <span class="legend-item"><span class="legend-line legend-line--group" />普通边</span>
        <span class="legend-item"><span class="legend-line legend-line--disabled" />已禁用边</span>
      </div>
    </div>

    <div class="canvas-stage__surface">
      <div class="canvas-atmosphere" aria-hidden="true">
        <div class="canvas-atmosphere__grid" />
        <canvas ref="waveCanvas" class="canvas-atmosphere__wave-canvas" />
        <div class="canvas-atmosphere__glow" />
        <div class="canvas-atmosphere__scanline" />
      </div>
      <slot />
    </div>

    <div class="canvas-stage__footer">
      <div class="canvas-stage__copy">
        <p>单击可以选择节点或边，候选路线高亮会直接叠加在画布上。</p>
        <p class="hint-text">当前状态：{{ nodeDragStatusText }}。重置会使用图载入时的基线位置。</p>
        <p class="hint-text">{{ viewportLockStatusText }}。锁定后只会禁用缩放与平移。</p>
        <p class="hint-text hint-text--anchor-note">左键双击起点，右键双击终点，中键双击途经，Shift + 单击多选。</p>
      </div>
    </div>
  </section>
</template>
