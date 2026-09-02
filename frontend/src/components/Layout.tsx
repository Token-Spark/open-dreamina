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

import { NavLink, Outlet } from 'react-router-dom'
import {
  Brush,
  CheckCircle2,
  AlertCircle,
  X,
  Sparkles,
  Settings2,
  FolderOpen,
  Boxes,
  Layers,
  ListTodo,
  Workflow,
  Sun,
  Moon,
  Github,
} from 'lucide-react'
import { TaskBar } from '@/components/TaskBar'
import { TaskSSEManager } from '@/components/TaskSSEManager'
import { useUIStore } from '@/stores/uiStore'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: '创作', icon: Brush },
  { to: '/canvas', label: '画布', icon: Workflow },
  { to: '/creation-assets', label: '素材库', icon: Boxes },
  { to: '/assets', label: '资产库', icon: FolderOpen },
  { to: '/templates', label: '模板', icon: Layers },
  { to: '/tasks', label: '任务', icon: ListTodo },
  { to: '/settings/providers', label: '设置', icon: Settings2 },
]

export function Layout() {
  const toasts = useUIStore((s) => s.toasts)
  const dismiss = useUIStore((s) => s.dismissToast)
  const theme = useUIStore((s) => s.theme)
  const toggleTheme = useUIStore((s) => s.toggleTheme)

  return (
    <div className="flex h-screen flex-col bg-bg-primary">
      <div className="flex flex-1 overflow-hidden">
        {/* Left icon rail */}
        <aside className="flex w-16 shrink-0 flex-col bg-bg-secondary border-r border-border">
          <div className="flex h-14 items-center justify-center">
            <NavLink to="/" className="flex h-8 w-8 items-center justify-center rounded-btn bg-accent text-bg-primary transition-transform hover:scale-105 active:scale-95">
              <Sparkles className="h-4 w-4" />
            </NavLink>
          </div>

          <nav className="flex flex-1 flex-col items-center gap-1.5 py-3">
            {NAV.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'group relative flex h-10 w-10 items-center justify-center rounded-btn transition-all duration-200',
                      isActive
                        ? 'bg-bg-tertiary text-fg-primary'
                        : 'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
                    )
                  }
                >
                  <Icon className="h-5 w-5" />
                  <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-btn border border-border bg-bg-tertiary px-2.5 py-1 text-xs font-medium text-fg-primary opacity-0 shadow-elevated transition-opacity group-hover:opacity-100">
                    {item.label}
                  </span>
                </NavLink>
              )
            })}
          </nav>

          {/* GitHub link + theme toggle pinned to the bottom of the rail */}
          <div className="flex flex-col items-center gap-1.5 py-3">
            <a
              href="https://github.com/Token-Spark/open-dreamina"
              target="_blank"
              rel="noreferrer"
              className={cn(
                'group relative flex h-10 w-10 items-center justify-center rounded-btn transition-all duration-200',
                'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
              )}
              aria-label="GitHub 仓库"
            >
              <Github className="h-5 w-5" />
              <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-btn border border-border bg-bg-tertiary px-2.5 py-1 text-xs font-medium text-fg-primary opacity-0 shadow-elevated transition-opacity group-hover:opacity-100">
                GitHub
              </span>
            </a>
            <button
              type="button"
              onClick={toggleTheme}
              className={cn(
                'group relative flex h-10 w-10 items-center justify-center rounded-btn transition-all duration-200',
                'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
              )}
              aria-label={theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'}
              title={theme === 'dark' ? '切换到亮色模式' : '切换到暗色模式'}
            >
              {theme === 'dark' ? (
                <Sun className="h-5 w-5" />
              ) : (
                <Moon className="h-5 w-5" />
              )}
              <span className="pointer-events-none absolute left-full ml-2 z-50 whitespace-nowrap rounded-btn border border-border bg-bg-tertiary px-2.5 py-1 text-xs font-medium text-fg-primary opacity-0 shadow-elevated transition-opacity group-hover:opacity-100">
                {theme === 'dark' ? '亮色模式' : '暗色模式'}
              </span>
            </button>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 overflow-auto scrollbar-thin">
          <Outlet />
        </main>
      </div>

      <TaskSSEManager />
      <TaskBar />

      {/* Toasts */}
      <div className="pointer-events-none fixed bottom-20 right-4 z-[70] flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex items-center gap-2 rounded-btn border border-border bg-bg-tertiary px-3 py-2 text-sm text-fg-primary shadow-lg animate-slide-up',
            )}
          >
            {t.variant === 'success' && <CheckCircle2 className="h-4 w-4 text-success" />}
            {t.variant === 'error' && <AlertCircle className="h-4 w-4 text-error" />}
            {t.variant === 'warning' && <AlertCircle className="h-4 w-4 text-warning" />}
            <span>{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              className="ml-2 text-fg-muted hover:text-fg-primary"
              aria-label="关闭"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
