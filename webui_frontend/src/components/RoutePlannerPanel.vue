<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type { AutoPlanJobStatus, RouteGraph } from '../types/route-graph'
import AutoPlanProgress from './AutoPlanProgress.vue'

const vDepthCard = depthCardDirective

type AutoColorField = 'autoAllowedRouteGroupColors' | 'autoExcludedEndpointGroupColors'

defineProps<{
  depthCard: DepthCardOptions
  trackingEnabled: boolean
  planForm: {
    planningMode: 'manual' | 'auto'
    startNodeId: string
    endNodeId: string
    viaNodeIds: string[]
    maxRoutes: number
    maxEdgePassFactor: number
    minTotalLength: string
    maxTotalLength: string
    minFrameCount: string
    maxFrameCount: string
    autoMaxOutputRoutes: string
    autoMaxRoutesPerPair: string
    autoMaxAnchorPairs: string
    autoDistancePerFrame: string
    autoMinFrameCount: string
    autoMaxFrameCount: string
    autoMinEndpointDistance: string
    autoMaxSearchStates: string
    autoCoverageWeight: string
    autoDiversityWeight: string
    autoAnchorWeight: string
    autoReversePenaltyWeight: string
    autoAllowedRouteGroupColors: string[]
    autoExcludedEndpointGroupColors: string[]
  }
  isAutoPlanningMode: boolean
  graph: RouteGraph | null
  groupColorOptions: string[]
  planningRoutes: boolean
  plannerGenerateButtonLabel: string
  shouldShowAutoPlanStatus: boolean
  autoPlanJobStatus: AutoPlanJobStatus | null
  autoPlanStatusHeadline: string
  autoPlanRecovered: boolean
  activeAutoPlanProgress: boolean
  autoPlanStatusPhaseLabel: string
  autoPlanProgressMaximum: number
  autoPlanProgressValue: number
  autoPlanProgressPercent: number
  autoPlanProgressPercentRounded: number
  autoPlanStatusSummary: string[]
  colorSelectionIncludes: (colors: string[], color: string) => boolean
  resolveGroupDisplayLabel: (color: string) => string
}>()

const emit = defineEmits<{
  (event: 'toggle-tracking'): void
  (event: 'manual-start-node-change', value: Event): void
  (event: 'manual-end-node-change', value: Event): void
  (event: 'remove-via-node', nodeId: string): void
  (event: 'reset-route-anchors'): void
  (event: 'generate-route-candidates'): void
  (event: 'toggle-auto-group-color-selection', field: AutoColorField, color: string): void
}>()
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">规划器</p>
        <h2>路线构建器</h2>
      </div>
      <button
        type="button"
        class="chip-button"
        :class="{ 'chip-button--active': trackingEnabled }"
        :aria-pressed="trackingEnabled"
        @click="emit('toggle-tracking')"
      >
        {{ trackingEnabled ? '右侧倾斜开' : '右侧倾斜关' }}
      </button>
    </div>

    <div class="field-grid">
      <label class="field-group">
        <span>规划模式</span>
        <select v-model="planForm.planningMode">
          <option value="manual">手动</option>
          <option value="auto">自动</option>
        </select>
      </label>
      <label class="field-group">
        <span>最大边经过倍数</span>
        <input v-model.number="planForm.maxEdgePassFactor" type="number" min="1" step="0.1" />
      </label>
    </div>

    <template v-if="!isAutoPlanningMode">
      <div class="field-grid">
        <label class="field-group">
          <span>起点</span>
          <select :value="planForm.startNodeId" @change="emit('manual-start-node-change', $event)">
            <option value="">未设置</option>
            <option v-for="node in graph?.nodes ?? []" :key="node.id" :value="node.id">{{ node.id }} · {{ node.label || node.id }}</option>
          </select>
        </label>
        <label class="field-group">
          <span>终点</span>
          <select :value="planForm.endNodeId" @change="emit('manual-end-node-change', $event)">
            <option value="">未设置</option>
            <option v-for="node in graph?.nodes ?? []" :key="node.id" :value="node.id">{{ node.id }} · {{ node.label || node.id }}</option>
          </select>
        </label>
      </div>
      <div class="field-group">
        <span>途经顺序</span>
        <div class="token-row" v-if="planForm.viaNodeIds.length">
          <button v-for="nodeId in planForm.viaNodeIds" :key="nodeId" class="token-chip" @click="emit('remove-via-node', nodeId)">{{ nodeId }} <small>移除</small></button>
        </div>
        <p class="hint-text" v-else>可通过检查器或中键手势添加途经点。</p>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>最大路线数</span><input v-model.number="planForm.maxRoutes" type="number" min="1" step="1" /></label>
        <div class="field-group"><span>手动规划</span><p class="hint-text">手动规划会使用起点、终点和有序途经列表。</p></div>
      </div>
      <div class="field-grid">
        <label class="field-group">
          <span>最小轨迹帧数下限</span>
          <input v-model="planForm.minFrameCount" type="text" placeholder="可选" />
        </label>
        <label class="field-group">
          <span>最大轨迹帧数上限</span>
          <input v-model="planForm.maxFrameCount" type="text" placeholder="可选" />
        </label>
      </div>
    </template>

    <template v-else>
      <div class="field-grid">
        <label class="field-group"><span>最大输出路线数</span><input v-model="planForm.autoMaxOutputRoutes" type="text" /></label>
        <label class="field-group"><span>每对锚点最大路线数</span><input v-model="planForm.autoMaxRoutesPerPair" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>最大锚点评估数</span><input v-model="planForm.autoMaxAnchorPairs" type="text" /></label>
        <label class="field-group"><span>每帧距离</span><input v-model="planForm.autoDistancePerFrame" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>自动最小帧数</span><input v-model="planForm.autoMinFrameCount" type="text" placeholder="可选" /></label>
        <label class="field-group"><span>自动最大帧数</span><input v-model="planForm.autoMaxFrameCount" type="text" placeholder="可选" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>最小端点距离</span><input v-model="planForm.autoMinEndpointDistance" type="text" /></label>
        <label class="field-group"><span>最大搜索状态数</span><input v-model="planForm.autoMaxSearchStates" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>覆盖权重</span><input v-model="planForm.autoCoverageWeight" type="text" /></label>
        <label class="field-group"><span>多样性权重</span><input v-model="planForm.autoDiversityWeight" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>锚点权重</span><input v-model="planForm.autoAnchorWeight" type="text" /></label>
        <label class="field-group"><span>反向惩罚权重</span><input v-model="planForm.autoReversePenaltyWeight" type="text" /></label>
      </div>
      <div class="field-group">
        <span>允许的路线分组颜色</span>
        <p class="hint-text">留空表示不限制，已选 {{ planForm.autoAllowedRouteGroupColors.length }} 项。</p>
        <div v-if="groupColorOptions.length" class="selection-list" role="group" aria-label="允许的路线分组颜色">
          <button
            v-for="color in groupColorOptions"
            :key="`allow-${color}`"
            type="button"
            class="selection-item"
            :class="{ 'selection-item--active': colorSelectionIncludes(planForm.autoAllowedRouteGroupColors, color) }"
            role="checkbox"
            :aria-checked="colorSelectionIncludes(planForm.autoAllowedRouteGroupColors, color)"
            @click="emit('toggle-auto-group-color-selection', 'autoAllowedRouteGroupColors', color)"
          >
            <span class="selection-item__swatch" :style="{ '--swatch-color': color }" />
            <span class="selection-item__label">{{ resolveGroupDisplayLabel(color) }}</span>
            <span class="selection-item__check">{{ colorSelectionIncludes(planForm.autoAllowedRouteGroupColors, color) ? '已选' : '未选' }}</span>
          </button>
        </div>
        <div v-else class="empty-state"><p>当前图还没有可用的路线分组颜色。</p></div>
      </div>
      <div class="field-group">
        <span>排除的端点分组颜色</span>
        <p class="hint-text">已选颜色不会作为自动规划起点或终点，已选 {{ planForm.autoExcludedEndpointGroupColors.length }} 项。</p>
        <div v-if="groupColorOptions.length" class="selection-list" role="group" aria-label="排除的端点分组颜色">
          <button
            v-for="color in groupColorOptions"
            :key="`exclude-${color}`"
            type="button"
            class="selection-item"
            :class="{ 'selection-item--active': colorSelectionIncludes(planForm.autoExcludedEndpointGroupColors, color) }"
            role="checkbox"
            :aria-checked="colorSelectionIncludes(planForm.autoExcludedEndpointGroupColors, color)"
            @click="emit('toggle-auto-group-color-selection', 'autoExcludedEndpointGroupColors', color)"
          >
            <span class="selection-item__swatch" :style="{ '--swatch-color': color }" />
            <span class="selection-item__label">{{ resolveGroupDisplayLabel(color) }}</span>
            <span class="selection-item__check">{{ colorSelectionIncludes(planForm.autoExcludedEndpointGroupColors, color) ? '已选' : '未选' }}</span>
          </button>
        </div>
        <div v-else class="empty-state"><p>当前图还没有可用的端点分组颜色。</p></div>
      </div>
    </template>

    <p v-if="isAutoPlanningMode" class="hint-text hint-text--anchor-note">画布锚点只会在切回手动模式后影响规划。</p>

    <div class="field-grid">
      <label class="field-group"><span>最小总长度</span><input v-model="planForm.minTotalLength" type="text" placeholder="可选" /></label>
      <label class="field-group"><span>最大总长度</span><input v-model="planForm.maxTotalLength" type="text" placeholder="可选" /></label>
    </div>

    <div class="panel-actions panel-actions--primary">
      <div class="anchor-strip">
        <button v-if="!isAutoPlanningMode" class="chip-button" @click="emit('reset-route-anchors')">重置锚点</button>
        <button class="action-button" :disabled="planningRoutes" @click="emit('generate-route-candidates')">{{ plannerGenerateButtonLabel }}</button>
      </div>
    </div>

    <AutoPlanProgress
      v-if="shouldShowAutoPlanStatus"
      :job-status="autoPlanJobStatus"
      :headline="autoPlanStatusHeadline"
      :recovered="autoPlanRecovered"
      :active-progress="activeAutoPlanProgress"
      :phase-label="autoPlanStatusPhaseLabel"
      :progress-maximum="autoPlanProgressMaximum"
      :progress-value="autoPlanProgressValue"
      :progress-percent="autoPlanProgressPercent"
      :progress-percent-rounded="autoPlanProgressPercentRounded"
      :summary="autoPlanStatusSummary"
    />
  </section>
</template>
