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

import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  batchDeleteAssets,
  deleteAsset,
  listAssets,
  updateAsset,
  type Asset,
  type ListAssetsQuery,
  type UpdateAssetPayload,
} from '@/api/assets'
import type { Paginated } from '@/api/client'

export const ASSETS_KEY = ['assets'] as const

/** List assets with reactive filters. */
export function useAssets(query: ListAssetsQuery) {
  return useQuery({
    queryKey: [...ASSETS_KEY, query],
    queryFn: () => listAssets(query),
  })
}

/** Toggle favorite / update tags for a single asset. */
export function useUpdateAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateAssetPayload }) =>
      updateAsset(id, payload),
    onSuccess: (asset) => {
      qc.setQueryData([...ASSETS_KEY], (old: Paginated<Asset> | undefined) =>
        old
          ? { ...old, items: old.items.map((a) => (a.id === asset.id ? asset : a)) }
          : old,
      )
      qc.invalidateQueries({ queryKey: ASSETS_KEY })
    },
  })
}

/** Delete a single asset. */
export function useDeleteAsset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteAsset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ASSETS_KEY }),
  })
}

/** Delete many assets at once. */
export function useBatchDeleteAssets() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => batchDeleteAssets(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ASSETS_KEY }),
  })
}
