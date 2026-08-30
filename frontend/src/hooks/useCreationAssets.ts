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

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createCreationAsset,
  createProject,
  deleteCreationAsset,
  getAutoSyncConfig,
  getSyncConfig,
  listCreationAssetTags,
  listCreationAssets,
  listProjects,
  pullAssetsByTag,
  runAutoSyncNow,
  syncAssetsByTag,
  updateAutoSyncConfig,
  updateCreationAsset,
  updateOwnerName,
  type CreateCreationAssetPayload,
  type ListCreationAssetsQuery,
  type UpdateCreationAssetPayload,
} from '@/api/creationAssets'

export const CREATION_ASSETS_KEY = ['creation-assets'] as const
export const CREATION_ASSET_TAGS_KEY = ['creation-assets', 'tags'] as const
export const SYNC_CONFIG_KEY = ['creation-assets', 'sync-config'] as const
export const PROJECTS_KEY = ['creation-assets', 'projects'] as const
export const AUTO_SYNC_CONFIG_KEY = ['creation-assets', 'auto-sync-config'] as const

export function useCreationAssets(query: ListCreationAssetsQuery) {
  return useQuery({
    queryKey: [...CREATION_ASSETS_KEY, query],
    queryFn: () => listCreationAssets(query),
  })
}

export function useCreationAssetTags() {
  return useQuery({
    queryKey: CREATION_ASSET_TAGS_KEY,
    queryFn: listCreationAssetTags,
  })
}

export function useSyncConfig() {
  return useQuery({
    queryKey: SYNC_CONFIG_KEY,
    queryFn: getSyncConfig,
  })
}

export function useCreateCreationAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateCreationAssetPayload) => createCreationAsset(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
    },
  })
}

export function useUpdateCreationAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateCreationAssetPayload }) =>
      updateCreationAsset(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
    },
  })
}

export function useDeleteCreationAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteCreationAsset(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
    },
  })
}

export function useProjects(enabled = true) {
  return useQuery({
    queryKey: PROJECTS_KEY,
    queryFn: listProjects,
    enabled,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, description }: { name: string; description: string }) =>
      createProject(name, description),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_KEY })
    },
  })
}

export function useSyncAssetsByTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tag: string) => syncAssetsByTag(tag),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
    },
  })
}

export function usePullAssetsByTag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (tag: string) => pullAssetsByTag(tag),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
    },
  })
}

export function useUpdateOwnerName() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ownerName: string) => updateOwnerName(ownerName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SYNC_CONFIG_KEY })
    },
  })
}

// ---------------- 集中化自动同步 ----------------

export function useAutoSyncConfig() {
  return useQuery({
    queryKey: AUTO_SYNC_CONFIG_KEY,
    queryFn: getAutoSyncConfig,
  })
}

export function useUpdateAutoSyncConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ enabled, tag }: { enabled: boolean; tag: string }) =>
      updateAutoSyncConfig(enabled, tag),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: AUTO_SYNC_CONFIG_KEY })
    },
  })
}

export function useRunAutoSyncNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => runAutoSyncNow(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CREATION_ASSETS_KEY })
      qc.invalidateQueries({ queryKey: AUTO_SYNC_CONFIG_KEY })
    },
  })
}
