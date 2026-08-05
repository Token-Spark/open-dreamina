import { cn } from '@/lib/utils'

export interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

export function Switch({
  checked,
  onCheckedChange,
  disabled,
  className,
  'aria-label': ariaLabel,
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border transition-colors duration-200',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg-muted/40',
        'disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'bg-accent' : 'bg-bg-tertiary',
        className,
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 transform rounded-full transition-transform duration-200',
          checked ? 'translate-x-[18px] bg-bg-primary' : 'translate-x-0.5 bg-fg-secondary',
        )}
      />
    </button>
  )
}
