import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  createProvider,
  deleteProvider,
  listProviders,
  listSlugOptions,
  testProvider,
  testProviderBeforeCreate,
  updateProvider,
  type CreateProviderPayload,
  type Provider,
  type TestBeforeCreatePayload,
  type TestProviderOverrides,
  type UpdateProviderPayload,
} from '@/api/providers'

export const PROVIDERS_KEY = ['providers'] as const
export const SLUG_OPTIONS_KEY = ['provider-slug-options'] as const

/** Fetch all configured providers (API keys are masked server-side). */
export function useProviders() {
  return useQuery({
    queryKey: PROVIDERS_KEY,
    queryFn: listProviders,
  })
}

/** 可用 slug 列表（极少变化，长期缓存）。 */
export function useSlugOptions() {
  return useQuery({
    queryKey: SLUG_OPTIONS_KEY,
    queryFn: listSlugOptions,
    staleTime: Infinity,
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

/** Connectivity test; does not mutate cached lists.
 * 编辑模式传入 overrides 可用表单当前值测试未保存的改动（api_key 留空则后端用旧 Key）。 */
export function useTestProvider() {
  return useMutation({
    mutationFn: ({ id, overrides }: { id: string; overrides?: TestProviderOverrides }) =>
      testProvider(id, overrides),
  })
}

/** 新建前连通性测试：无需先落库即可校验。 */
export function useTestProviderBeforeCreate() {
  return useMutation({
    mutationFn: (payload: TestBeforeCreatePayload) => testProviderBeforeCreate(payload),
  })
}
