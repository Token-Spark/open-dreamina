import { useEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

export interface DropdownProps {
  trigger: ReactNode
  children: ReactNode
  align?: 'start' | 'center' | 'end'
  placement?: 'top' | 'bottom'
  /** 为 true 时面板使用完全不透明的背景，避免与下层内容相互干扰（如尺寸选择面板）。 */
  opaque?: boolean
}

export function Dropdown({
  trigger,
  children,
  align = 'start',
  placement = 'bottom',
  opaque = false,
}: DropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  return (
    <div ref={ref} className="relative inline-block">
      <div onClick={() => setOpen((v) => !v)}>{trigger}</div>
      {open && (
        <div
          className={cn(
            'absolute z-50 min-w-[12rem] rounded-card border border-border p-1 shadow-xl',
            opaque
              ? 'bg-bg-secondary'
              : 'bg-bg-secondary/95 backdrop-blur-sm',
            placement === 'top' ? 'bottom-full mb-1.5' : 'mt-1.5',
            align === 'start' && 'left-0',
            align === 'end' && 'right-0',
            align === 'center' && 'left-1/2 -translate-x-1/2',
          )}
        >
          {children}
        </div>
      )}
    </div>
  )
}

export interface DropdownItemProps {
  active?: boolean
  onClick?: () => void
  children: ReactNode
  className?: string
}

export function DropdownItem({ active, onClick, children, className }: DropdownItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-btn px-3 py-2 text-sm transition-colors',
        active
          ? 'bg-accent text-bg-primary'
          : 'text-fg-secondary hover:bg-bg-tertiary hover:text-fg-primary',
        className,
      )}
    >
      {children}
    </button>
  )
}
