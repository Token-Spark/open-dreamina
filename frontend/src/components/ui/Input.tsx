import type { InputHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'flex h-9 w-full rounded-btn border border-border bg-bg-tertiary px-3 py-1 text-sm text-fg-primary',
        'placeholder:text-fg-muted transition-colors duration-200',
        'focus-visible:outline-none focus-visible:border-fg-muted focus-visible:ring-1 focus-visible:ring-fg-muted/40',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
