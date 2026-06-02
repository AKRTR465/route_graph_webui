<script setup lang="ts">
import { depthCardDirective, type DepthCardOptions } from '../lib/depth-card'
import type {
  MissionExportResponse,
  RouteCandidate,
  RouteCandidateSet,
} from '../types/route-graph'
import MissionPreviewPanel from './MissionPreviewPanel.vue'

const vDepthCard = depthCardDirective

defineProps<{
  depthCard: DepthCardOptions
  candidateSet: RouteCandidateSet | null
  exportForm: {
    candidateSetFileName: string
    missionsOutputDir: string
    stepDistance: string
    fps: string
    altitudeMode: 'fixed' | 'follow_nodes'
    fixedZ: string
    altitudeOffset: string
    takeoffLandingRelativeZ: string
    takeoffLandingStepDistance: string
    nodeSampleRadius: string
    randomSeed: string
    turnSmoothingEnabled: boolean
    cornerRadius: string
    smallTurnYawBlendThresholdDeg: string
    cornerMinAngleDeg: string
    uTurnThresholdDeg: string
    uTurnTransitionDistance: string
    cornerMaxYawStepDeg: string
    uTurnPivotYawStepDeg: string
  }
  savingRoutes: boolean
  lastCandidateSavePath: string
  selectedCandidate: RouteCandidate | null
  previewStatusTone: 'info' | 'success' | 'error'
  previewLoading: boolean
  previewStatusText: string
  previewSummaryItems: string[]
  exportingRoutes: boolean
  selectedCandidateIds: string[]
  lastExportSummary: MissionExportResponse | null
}>()

defineEmits<{
  (event: 'save-current-candidate-set'): void
  (event: 'force-refresh-mission-preview'): void
  (event: 'export-selected-candidate-missions'): void
}>()

defineOptions({
  name: 'ExportPanel',
})
</script>

<template>
  <section v-depth-card="depthCard" class="panel-card">
    <div class="panel-head">
      <div>
        <p class="panel-kicker">导出</p>
        <h2>保存与导出</h2>
      </div>
    </div>

    <template v-if="candidateSet">
      <label class="field-group"><span>候选文件名</span><input v-model="exportForm.candidateSetFileName" type="text" placeholder="例如 DowntownWest_manual.candidates.json" /></label>
      <div class="panel-actions panel-actions--primary">
        <button class="action-button" :disabled="savingRoutes" @click="$emit('save-current-candidate-set')">{{ savingRoutes ? '保存中' : '保存候选集合' }}</button>
      </div>
      <p class="hint-text" v-if="lastCandidateSavePath">最近保存路径：{{ lastCandidateSavePath }}</p>
      <div class="field-grid">
        <label class="field-group"><span>任务输出目录</span><input v-model="exportForm.missionsOutputDir" type="text" placeholder="默认使用图名" /></label>
        <label class="field-group"><span>高度模式</span><select v-model="exportForm.altitudeMode"><option value="fixed">固定</option><option value="follow_nodes">跟随节点</option></select></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>步长</span><input v-model="exportForm.stepDistance" type="text" /></label>
        <label class="field-group"><span>帧率</span><input v-model="exportForm.fps" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>固定 Z</span><input v-model="exportForm.fixedZ" type="text" placeholder="可选" /></label>
        <label class="field-group"><span>高度偏移</span><input v-model="exportForm.altitudeOffset" type="text" /></label>
      </div>
      <div class="field-grid">
        <label class="field-group"><span>节点采样半径</span><input v-model="exportForm.nodeSampleRadius" type="text" /></label>
        <label class="field-group"><span>随机种子</span><input v-model="exportForm.randomSeed" type="text" placeholder="可选" /></label>
      </div>
      <label class="toggle-row"><input v-model="exportForm.turnSmoothingEnabled" type="checkbox" /><span>启用转弯平滑</span></label>
      <div class="field-grid field-grid--dense">
        <label class="field-group">
          <span>拐角半径</span>
          <input v-model="exportForm.cornerRadius" type="text" :disabled="!exportForm.turnSmoothingEnabled" />
        </label>
        <label class="field-group">
          <span>小角度偏航混合阈值</span>
          <input
            v-model="exportForm.smallTurnYawBlendThresholdDeg"
            type="text"
            :disabled="!exportForm.turnSmoothingEnabled"
          />
        </label>
      </div>
      <div class="field-grid field-grid--dense">
        <label class="field-group">
          <span>拐角最小角度</span>
          <input v-model="exportForm.cornerMinAngleDeg" type="text" :disabled="!exportForm.turnSmoothingEnabled" />
        </label>
        <label class="field-group">
          <span>U 型掉头阈值</span>
          <input v-model="exportForm.uTurnThresholdDeg" type="text" :disabled="!exportForm.turnSmoothingEnabled" />
        </label>
      </div>
      <div class="field-grid field-grid--dense">
        <label class="field-group">
          <span>U 型掉头过渡距离</span>
          <input
            v-model="exportForm.uTurnTransitionDistance"
            type="text"
            :disabled="!exportForm.turnSmoothingEnabled"
          />
        </label>
        <label class="field-group">
          <span>拐角最大偏航步进</span>
          <input v-model="exportForm.cornerMaxYawStepDeg" type="text" :disabled="!exportForm.turnSmoothingEnabled" />
        </label>
      </div>
      <div class="field-grid field-grid--dense">
        <label class="field-group">
          <span>U 型掉头枢轴偏航步进</span>
          <input
            v-model="exportForm.uTurnPivotYawStepDeg"
            type="text"
            :disabled="!exportForm.turnSmoothingEnabled"
          />
        </label>
        <div class="field-group">
          <span>轨迹预览</span>
          <p class="hint-text">候选切换或参数变化后会自动刷新，必要时也可以手动重算。</p>
        </div>
      </div>
      <MissionPreviewPanel
        :tone="previewStatusTone"
        :title="selectedCandidate?.candidate_id ?? '未选中候选'"
        :loading="previewLoading"
        :status-text="previewStatusText"
        :summary-items="previewSummaryItems"
        :refresh-disabled="!selectedCandidate || previewLoading"
        @refresh="$emit('force-refresh-mission-preview')"
      />
      <div class="panel-actions panel-actions--primary">
        <button class="action-button" :disabled="exportingRoutes" @click="$emit('export-selected-candidate-missions')">{{ exportingRoutes ? '导出中' : `导出已保留路线（${selectedCandidateIds.length}）` }}</button>
      </div>
      <div class="export-report" v-if="lastExportSummary">
        <p>输出目录：{{ lastExportSummary.output_dir }}</p>
        <p>成功：{{ lastExportSummary.succeeded.join(', ') || '无' }}</p>
        <p v-if="lastExportSummary.failed.length">失败：{{ lastExportSummary.failed.join(', ') }}</p>
      </div>
    </template>
    <div class="empty-state" v-else><p>请先生成候选路线，再进行保存或导出。</p></div>
  </section>
</template>
