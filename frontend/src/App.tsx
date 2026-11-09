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

import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout, RouteFallback } from '@/components/Layout'
import { listTasks, ACTIVE_STATUSES } from '@/api/tasks'
import { useTaskStore } from '@/stores/taskStore'

// 路由级代码分割：画布编辑器（含 React Flow）、审阅中心、创作资产等重页面
// 只在被访问时加载，不再全部塞进首屏 bundle。各页面是 named export，
// lazy 需要 default，故用 then 包一层。
const CreatePage = lazy(() => import('@/pages/CreatePage').then((m) => ({ default: m.CreatePage })))
const AssetsPage = lazy(() => import('@/pages/AssetsPage').then((m) => ({ default: m.AssetsPage })))
const CreationAssetsPage = lazy(() => import('@/pages/CreationAssetsPage').then((m) => ({ default: m.CreationAssetsPage })))
const TemplatesPage = lazy(() => import('@/pages/TemplatesPage').then((m) => ({ default: m.TemplatesPage })))
const TasksPage = lazy(() => import('@/pages/TasksPage').then((m) => ({ default: m.TasksPage })))
const SettingsPage = lazy(() => import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const CanvasListPage = lazy(() => import('@/pages/CanvasListPage').then((m) => ({ default: m.CanvasListPage })))
const CanvasEditorPage = lazy(() => import('@/pages/CanvasEditorPage').then((m) => ({ default: m.CanvasEditorPage })))
const ReviewCenterPage = lazy(() => import('@/pages/ReviewCenterPage').then((m) => ({ default: m.ReviewCenterPage })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

// 启动恢复只取最近的一批活跃任务。每个任务都会占用一条 SSE 预算或退化成
// 3 秒轮询，恢复 100 个历史任务会在页面打开瞬间制造请求风暴；超出这批的
// 任务仍可通过任务中心查看，不影响数据完整性。
const RECOVER_ACTIVE_LIMIT = 20

/** Recover in-flight tasks on page load and seed the store for SSE subscription. */
function useRecoverActiveTasks() {
  const setActive = useTaskStore((s) => s.setActive)
  useEffect(() => {
    listTasks({ status: ACTIVE_STATUSES.join(','), page_size: RECOVER_ACTIVE_LIMIT })
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
        {/* Layout 内部另有 Suspense 包住 Outlet，侧边栏不会在切页时闪烁；
            这里的外层边界服务于全屏画布路由。 */}
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            {/* Canvas editor: full-screen, no sidebar */}
            <Route path="/canvas/:canvasId" element={<CanvasEditorPage />} />
            <Route element={<Layout />}>
              <Route path="/" element={<CreatePage />} />
              <Route path="/canvas" element={<CanvasListPage />} />
              <Route path="/assets" element={<AssetsPage />} />
              <Route path="/creation-assets" element={<CreationAssetsPage />} />
              <Route path="/review" element={<ReviewCenterPage />} />
              {/* 旧「镜头审片」路由重定向到审阅中心的镜头审片模式 */}
              <Route path="/shot-review" element={<Navigate to="/review?mode=shot" replace />} />
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/settings/providers" element={<SettingsPage />} />
              <Route path="/settings/general" element={<SettingsPage />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
