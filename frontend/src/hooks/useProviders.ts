import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  createProvider,
  deleteProvider,
  listProviders,
  testProvider,
  updateProvider,
  type CreateProviderPayload,
  type Provider,
  type UpdateProviderPayload,
} from '@/api/providers'

export const PROVIDERS_KEY = ['providers'] as const

/** Fetch all configured providers (API keys are masked server-side). */
export function useProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: listProviders,
  })
}

export function useCreateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CreateProviderPayload) => createProvider(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROVIDERS_KEY }),
  })
}

export function useUpdateProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateProviderPayload }) =>
      updateProvider(id, payload),
    onSuccess: (provider) => {
      qc.setQueryData(PROVIDERS_KEY, (old: Provider[] | undefined) =>
        old ? old.map((p) => (p.id === provider.id ? provider : p)) : old,
      )
      qc.invalidateQueries({ queryKey: PROVIDERS_KEY })
    },
  })
}

export function useDeleteProvider() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteProvider(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROVIDERS_KEY }),
  })
}

/** Connectivity test; does not mutate cached lists. */
export function useTestProvider() {
  return useMutation({
    mutationFn: (id: string) => testProvider(id),
  })
}
