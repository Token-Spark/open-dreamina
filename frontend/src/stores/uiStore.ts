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

import { create } from 'zustand'

export type Theme = 'dark' | 'light'

const THEME_STORAGE_KEY = 'aigc-studio.theme'

/** Read the initial theme: explicit user choice → system preference → dark. */
function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'dark'
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (saved === 'dark' || saved === 'light') return saved
  const prefersLight =
    window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
  return prefersLight ? 'light' : 'dark'
}

/** Apply the theme class to <html>. Idempotent; safe to call repeatedly. */
export function applyThemeClass(theme: Theme): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.remove('dark', 'light')
  root.classList.add(theme)
}

interface UIState {
  /** Active color theme. Drives the `dark` / `light` class on <html>. */
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  /** Whether the left auxiliary panel (e.g. advanced params) is collapsed. */
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  /** Transient toast notifications rendered at the bottom. */
  toasts: Toast[]
  pushToast: (toast: Omit<Toast, 'id'> & { id?: string }) => void
  dismissToast: (id: string) => void
}

export interface Toast {
  id: string
  message: string
  variant: 'default' | 'success' | 'error'
}

let toastSeq = 0

const initialTheme = readInitialTheme()
// Apply once at module load so the correct palette is active before first paint.
applyThemeClass(initialTheme)

export const useUIStore = create<UIState>((set) => ({
  theme: initialTheme,
  setTheme: (theme) => {
    applyThemeClass(theme)
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme)
    } catch {
      /* localStorage may be unavailable (private mode); theme still applies for the session. */
    }
    set({ theme })
  },
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'dark' ? 'light' : 'dark'
      applyThemeClass(next)
      try {
        window.localStorage.setItem(THEME_STORAGE_KEY, next)
      } catch {
        /* see setTheme */
      }
      return { theme: next }
    }),
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  toasts: [],
  pushToast: (toast) =>
    set((s) => ({
      toasts: [...s.toasts, { ...toast, id: toast.id ?? `t${++toastSeq}` }],
    })),
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

/** Convenience helper: push a toast and auto-dismiss after 5s. */
export function toast(
  message: string,
  variant: Toast['variant'] = 'default',
): void {
  const id = `t${++toastSeq}`
  useUIStore.getState().pushToast({ id, message, variant })
  window.setTimeout(() => useUIStore.getState().dismissToast(id), 5000)
}
