import { useEffect } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/Layout'
import { CreatePage } from '@/pages/CreatePage'
import { AssetsPage } from '@/pages/AssetsPage'
import { TemplatesPage } from '@/pages/TemplatesPage'
import { TasksPage } from '@/pages/TasksPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { listTasks, ACTIVE_STATUSES } from '@/api/tasks'
import { useTaskStore } from '@/stores/taskStore'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

/** Recover in-flight tasks on page load and seed the store for SSE subscription. */
function useRecoverActiveTasks() {
  const setActive = useTaskStore((s) => s.setActive)
  useEffect(() => {
    listTasks({ status: ACTIVE_STATUSES.join(','), page_size: 100 })
      .then((res) => setActive(res.items))
      .catch(() => {
        /* backend may be unavailable; tasks will recover on next navigation */
      })
  }, [setActive])
}

export default function App() {
  useRecoverActiveTasks()

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<CreatePage />} />
            <Route path="/assets" element={<AssetsPage />} />
            <Route path="/templates" element={<TemplatesPage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/settings/providers" element={<SettingsPage />} />
            <Route path="/settings/general" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
