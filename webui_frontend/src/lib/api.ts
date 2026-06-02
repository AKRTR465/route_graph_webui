import { apiGet, apiPost } from './request'

import type {
  AddEdgeRequest,
  AutoPlanJobStatus,
  AutoPlanRequestPayload,
  CandidateSaveResponse,
  ExportMissionsPayload,
  GeneratePlanPayload,
  GraphCatalogResponse,
  GraphEnvelope,
  MissionExportResponse,
  MissionPreviewResponse,
  NodeMoveRequest,
  NodeUpdateRequest,
  PreviewMissionPayload,
  RemoveEdgeBetweenRequest,
  RemoveEdgeRequest,
  RouteCandidateSet,
  SaveCandidateSetPayload,
  ScopedGraphRequest,
  UpdateCanvasViewRequest,
  UpdateEdgeRequest,
  UpdateGraphUiStateRequest,
  ValidationReport,
} from '../types/api-contract'
import type { GraphUiState, GroupConfigInputsState } from '../types/route-graph'

export function fetchGraphCatalog(): Promise<GraphCatalogResponse> {
  return apiGet<GraphCatalogResponse>('/api/graphs')
}

export function fetchGraph(graph?: string | null): Promise<GraphEnvelope> {
  return apiGet<GraphEnvelope>('/api/graph', {
    params: graph ? { graph } : undefined,
  })
}

export function updateLastGraph(payload: ScopedGraphRequest): Promise<{
  last_graph: string | null
  updated_at?: string
}> {
  return apiPost('/api/app/last-graph', payload)
}

export function validateGraph(graph?: string | null): Promise<ValidationReport> {
  return apiGet<ValidationReport>('/api/graph/validate', {
    params: graph ? { graph } : undefined,
  })
}

export function updateCanvasView(payload: UpdateCanvasViewRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/graph/canvas-view', payload)
}

export function updateGraphUiState(payload: UpdateGraphUiStateRequest): Promise<{
  graph: string
  ui_state: GraphUiState
}> {
  return apiPost('/api/graph/ui-state', payload)
}

export function moveNode(payload: NodeMoveRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/node/move', payload)
}

export function updateNode(payload: NodeUpdateRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/node/update', payload)
}

export function addEdge(payload: AddEdgeRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/edge/add', payload)
}

export function updateEdge(payload: UpdateEdgeRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/edge/update', payload)
}

export function removeEdge(payload: RemoveEdgeRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/edge/remove', payload)
}

export function removeEdgeBetween(payload: RemoveEdgeBetweenRequest): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/edge/remove-between', payload)
}

export function updateGraphGroupConfig(payload: {
  graph?: string | null
  group_color?: string | null
  group_config?: GroupConfigInputsState
  bridge_color?: string | null
}): Promise<GraphEnvelope> {
  return apiPost<GraphEnvelope>('/api/graph/group-config', payload)
}

export function generatePlan(payload: GeneratePlanPayload): Promise<RouteCandidateSet> {
  return apiPost<RouteCandidateSet>('/api/plan', payload)
}

export function startAutoPlanJob(payload: AutoPlanRequestPayload): Promise<AutoPlanJobStatus> {
  return apiPost<AutoPlanJobStatus>('/api/plan/auto/jobs', payload)
}

export function fetchAutoPlanJob(jobId: number): Promise<AutoPlanJobStatus> {
  return apiGet<AutoPlanJobStatus>(`/api/plan/auto/jobs/${jobId}`)
}

export function cancelAutoPlanJob(jobId: number): Promise<AutoPlanJobStatus> {
  return apiPost<AutoPlanJobStatus>(`/api/plan/auto/jobs/${jobId}/cancel`)
}

export function saveCandidateSet(payload: SaveCandidateSetPayload): Promise<CandidateSaveResponse> {
  return apiPost<CandidateSaveResponse>('/api/candidate-set/save', payload)
}

export function exportMissions(payload: ExportMissionsPayload): Promise<MissionExportResponse> {
  return apiPost<MissionExportResponse>('/api/missions/export', payload)
}

export function fetchMissionPreview(payload: PreviewMissionPayload): Promise<MissionPreviewResponse> {
  return apiPost<MissionPreviewResponse>('/api/missions/preview', payload)
}
