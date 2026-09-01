// Copyright 2026 Open Dreamina Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { apiClient, type Paginated } from './client'

// ---------------- Types ----------------

export interface CanvasSummary {
  id: string
  name: string
  description: string
  tags: string[]
  conversation_id: string | null
  cover_asset_id: string | null
  cover_thumbnail_url: string | null
  version: number
  node_count: number
  last_run_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface CanvasDocumentPayload {
  schema_version: number
  viewport: { x: number; y: number; zoom: number }
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

export interface CanvasNode {
  id: string
  type: CanvasNodeType
  position: { x: number; y: number }
  data: Record<string, unknown>
  title?: string
}

export interface CanvasEdge {
  id: string
  source: string
  source_port: string
  target: string
  target_port: string
  order: number
}

export type CanvasNodeType = 'asset' | 'prompt' | 'image_gen' | 'video_gen' | 'preview' | 'note'

export interface CanvasDetail extends CanvasSummary {
  document: CanvasDocumentPayload
  runtime: Record<string, unknown>
}

export interface CanvasDocumentResponse {
  version: number
  document: CanvasDocumentPayload
  actor: string
  actor_name: string
  change_summary: string
  created_at: string | null
}

export interface CanvasCreate {
  name?: string
  description?: string
  tags?: string[]
  template_id?: string
  document?: CanvasDocumentPayload
}

export interface CanvasUpdate {
  name?: string
  description?: string
  tags?: string[]
}

export interface CanvasOperation {
  op: string
  node?: Record<string, unknown>
  node_id?: string
  edge?: Record<string, unknown>
  edge_id?: string
  patch?: Record<string, unknown>
  position?: { x: number; y: number }
  order?: number
  name?: string
  description?: string
  tags?: string[]
}

export interface CanvasOperationsRequest {
  base_version?: number
  actor?: string
  actor_name?: string
  change_summary?: string
  operations: CanvasOperation[]
}

export interface CanvasOperationResult {
  version: number
  applied: Record<string, unknown>[]
  warnings: Record<string, unknown>[]
}

export interface CanvasValidationItem {
  level: 'error' | 'warning'
  code: string
  message: string
  node_ids: string[]
  edge_ids: string[]
  fix: string | null
}

export interface CanvasValidation {
  valid: boolean
  errors: CanvasValidationItem[]
  warnings: CanvasValidationItem[]
}

export interface CanvasVersionItem {
  version: number
  actor: string
  actor_name: string
  change_summary: string
  created_at: string | null
}

export interface CanvasRunSummary {
  id: string
  canvas_id: string
  doc_version: number
  scope: string
  target_node_id: string | null
  status: string
  trigger: string
  created_at: string | null
  completed_at: string | null
}

export interface CanvasRunDetail extends CanvasRunSummary {
  node_states: Record<string, unknown>
  error_msg: string | null
}

export interface CanvasRunRequest {
  scope?: string
  node_id?: string
  force?: boolean
  trigger?: string
}

export interface NodeSpecPort {
  id: string
  types: string[]
  multi: boolean
  max: number | null
}

export interface NodeSpec {
  inputs: NodeSpecPort[]
  outputs: NodeSpecPort[]
}

export type NodeSpecs = Record<string, NodeSpec>

// ---------------- API ----------------

export async function listCanvases(
  query: { search?: string; tags?: string; page?: number; page_size?: number } = {},
): Promise<Paginated<CanvasSummary>> {
  const { data } = await apiClient.get<Paginated<CanvasSummary>>('/canvas', { params: query })
  return data
}

export async function getCanvas(canvasId: string): Promise<CanvasDetail> {
  const { data } = await apiClient.get<CanvasDetail>(`/canvas/${canvasId}`)
  return data
}

export async function createCanvas(payload: CanvasCreate): Promise<CanvasDetail> {
  const { data } = await apiClient.post<CanvasDetail>('/canvas', payload)
  return data
}

export async function updateCanvas(
  canvasId: string,
  payload: CanvasUpdate,
): Promise<CanvasSummary> {
  const { data } = await apiClient.patch<CanvasSummary>(`/canvas/${canvasId}`, payload)
  return data
}

export async function deleteCanvas(canvasId: string): Promise<void> {
  await apiClient.delete(`/canvas/${canvasId}`)
}

export async function duplicateCanvas(
  canvasId: string,
  name?: string,
): Promise<CanvasDetail> {
  const { data } = await apiClient.post<CanvasDetail>(
    `/canvas/${canvasId}/duplicate`,
    null,
    { params: name ? { name } : undefined },
  )
  return data
}

export async function getCanvasDocument(
  canvasId: string,
  version?: number,
): Promise<CanvasDocumentResponse> {
  const { data } = await apiClient.get<CanvasDocumentResponse>(
    `/canvas/${canvasId}/document`,
    { params: version ? { version } : undefined },
  )
  return data
}

export async function saveCanvasDocument(
  canvasId: string,
  payload: {
    document: CanvasDocumentPayload
    base_version: number
    actor?: string
    actor_name?: string
    change_summary?: string
  },
): Promise<CanvasDocumentResponse> {
  const { data } = await apiClient.put<CanvasDocumentResponse>(
    `/canvas/${canvasId}/document`,
    payload,
  )
  return data
}

export async function applyOperations(
  canvasId: string,
  payload: CanvasOperationsRequest,
): Promise<CanvasOperationResult> {
  const { data } = await apiClient.post<CanvasOperationResult>(
    `/canvas/${canvasId}/operations`,
    payload,
  )
  return data
}

export async function validateCanvas(
  canvasId: string,
  version?: number,
): Promise<CanvasValidation> {
  const { data } = await apiClient.post<CanvasValidation>(
    `/canvas/${canvasId}/validate`,
    null,
    { params: version ? { version } : undefined },
  )
  return data
}

export async function listVersions(canvasId: string): Promise<CanvasVersionItem[]> {
  const { data } = await apiClient.get<{ items: CanvasVersionItem[] }>(
    `/canvas/${canvasId}/versions`,
  )
  return data.items
}

export async function revertToVersion(
  canvasId: string,
  targetVersion: number,
): Promise<CanvasDocumentResponse> {
  const { data } = await apiClient.post<CanvasDocumentResponse>(
    `/canvas/${canvasId}/revert`,
    { target_version: targetVersion },
  )
  return data
}

export async function listTemplates(): Promise<{ id: string; name: string }[]> {
  const { data } = await apiClient.get<{ id: string; name: string }[]>(
    '/canvas/templates/list',
  )
  return data
}

export async function getNodeSpecs(): Promise<NodeSpecs> {
  const { data } = await apiClient.get<{ specs: NodeSpecs }>('/canvas/node-specs')
  return data.specs
}

export async function createRun(
  canvasId: string,
  payload: CanvasRunRequest,
): Promise<{ run_id: string }> {
  const { data } = await apiClient.post<{ run_id: string }>(
    `/canvas/${canvasId}/runs`,
    payload,
  )
  return data
}

export async function listRuns(
  canvasId: string,
  page: number = 1,
  pageSize: number = 20,
): Promise<Paginated<CanvasRunSummary>> {
  const { data } = await apiClient.get<Paginated<CanvasRunSummary>>(
    `/canvas/${canvasId}/runs`,
    { params: { page, page_size: pageSize } },
  )
  return data
}

export async function getRun(
  canvasId: string,
  runId: string,
): Promise<CanvasRunDetail> {
  const { data } = await apiClient.get<CanvasRunDetail>(
    `/canvas/${canvasId}/runs/${runId}`,
  )
  return data
}
