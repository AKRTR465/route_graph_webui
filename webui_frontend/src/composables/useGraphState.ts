import { computed, ref } from 'vue'

import type {
  GraphEnvelope,
  GraphSummary,
  GroupConfigInputsState,
  GroupEditorState,
  RouteCandidateSet,
  RouteGraph,
} from '../types/route-graph'

export function useGraphState() {
  const graphCatalog = ref<GraphSummary[]>([])
  const currentGraphPath = ref('')
  const graphEnvelope = ref<GraphEnvelope | null>(null)
  const candidateSet = ref<RouteCandidateSet | null>(null)
  const loadingGraph = ref(false)
  const validatingGraph = ref(false)

  const graph = computed<RouteGraph | null>(() => graphEnvelope.value?.graph ?? null)
  const graphSummary = computed<GraphSummary | null>(() => graphEnvelope.value?.summary ?? null)
  const groupEditorState = computed<GroupEditorState | null>(
    () => graphEnvelope.value?.group_editor_state ?? null,
  )
  const groupColorOptions = computed(() => graphSummary.value?.group_colors ?? [])
  const groupConfigLookup = computed<Record<string, GroupConfigInputsState>>(
    () => groupEditorState.value?.group_configs ?? {},
  )
  const availableGraphs = computed(() => graphCatalog.value.filter((item) => !item.load_error))
  const currentGraphSummary = computed(
    () => graphCatalog.value.find((summary) => summary.path === currentGraphPath.value) ?? null,
  )

  function upsertGraphSummary(summary: GraphSummary) {
    const index = graphCatalog.value.findIndex((item) => item.path === summary.path)
    if (index >= 0) {
      graphCatalog.value[index] = summary
    } else {
      graphCatalog.value.push(summary)
    }
  }

  function applyGraphEnvelopeToState(envelope: GraphEnvelope) {
    currentGraphPath.value = envelope.path
    graphEnvelope.value = envelope
    upsertGraphSummary(envelope.summary)
  }

  return {
    graphCatalog,
    currentGraphPath,
    graphEnvelope,
    candidateSet,
    loadingGraph,
    validatingGraph,
    graph,
    graphSummary,
    groupEditorState,
    groupColorOptions,
    groupConfigLookup,
    availableGraphs,
    currentGraphSummary,
    upsertGraphSummary,
    applyGraphEnvelopeToState,
  }
}
