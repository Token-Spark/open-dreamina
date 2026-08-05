import type { SelectHTMLAttributes } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {}

export function Select({ className, children, ...props }: SelectProps) {
  return (
    <div className="relative">
      <select
        className={cn(
          'flex h-9 w-full appearance-none rounded-btn border border-border bg-bg-tertiary px-3 pr-8 text-sm text-fg-primary',
          'transition-colors duration-200 focus-visible:outline-none focus-visible:border-fg-muted focus-visible:ring-1 focus-visible:ring-fg-muted/40',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-muted"
        aria-hidden
      />
    </div>
  )
}
