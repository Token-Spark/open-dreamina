import type { TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export function Textarea({ className, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        'flex w-full rounded-btn border border-border bg-bg-tertiary px-3 py-2 text-sm text-fg-primary',
        'placeholder:text-fg-muted transition-colors duration-200 scrollbar-thin',
        'focus-visible:outline-none focus-visible:border-fg-muted focus-visible:ring-1 focus-visible:ring-fg-muted/40',
        'disabled:cursor-not-allowed disabled:opacity-50 resize-none',
        className,
      )}
      {...props}
    />
  )
}
