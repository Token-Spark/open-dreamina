import { NavLink, Outlet } from 'react-router-dom'
import {
  Brush,
  CheckCircle2,
  AlertCircle,
  X,
  Sparkles,
  Settings2,
  FolderOpen,
  Layers,
  ListTodo,
  Sun,
  Moon,
} from 'lucide-react'
import { TaskBar } from '@/components/TaskBar'
import { TaskSSEManager } from '@/components/TaskSSEManager'
import { useUIStore } from '@/stores/uiStore'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/', label: '创作', icon: Brush },
  { to: '/assets', label: '资产库', icon: FolderOpen },
  { to: '/templates', label: '模板', icon: Layers },
  { to: '/tasks', label: '任务中心', icon: ListTodo },
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
        <aside className="flex w-16 shrink-0 flex-col border-r border-border bg-bg-secondary">
          <div className="flex h-14 items-center justify-center border-b border-border">
            <NavLink to="/" className="flex h-8 w-8 items-center justify-center rounded-btn bg-accent text-bg-primary">
              <Sparkles className="h-4 w-4" />
            </NavLink>
          </div>

          <nav className="flex flex-1 flex-col items-center gap-1 py-3">
            {NAV.map((item) => {
              const Icon = item.icon
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'group relative flex h-10 w-10 items-center justify-center rounded-btn transition-colors',
                      isActive
                        ? 'bg-bg-tertiary text-fg-primary'
                        : 'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
                    )
                  }
                >
                  <Icon className="h-5 w-5" />
                  <span className="pointer-events-none absolute left-full ml-2 rounded-btn border border-border bg-bg-tertiary px-2 py-1 text-xs text-fg-primary opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                    {item.label}
                  </span>
                </NavLink>
              )
            })}
          </nav>

          {/* Theme toggle pinned to the bottom of the rail */}
          <div className="flex justify-center border-t border-border py-3">
            <button
              type="button"
              onClick={toggleTheme}
              className={cn(
                'group relative flex h-10 w-10 items-center justify-center rounded-btn transition-colors',
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
              <span className="pointer-events-none absolute left-full ml-2 rounded-btn border border-border bg-bg-tertiary px-2 py-1 text-xs text-fg-primary opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
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
