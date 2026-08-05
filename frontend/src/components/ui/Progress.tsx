import { cn } from '@/lib/utils'

export interface ProgressProps {
  /** 0–100 */
  value: number
  className?: string
  /** Apply the breathing-glow animation to the active bar. */
  glow?: boolean
}

export function Progress({ value, className, glow }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value))
  return (
    <div
      className={cn(
        'relative h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary',
        className,
      )}
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn(
          'h-full rounded-full bg-accent transition-[width] duration-300 ease-out',
          glow && 'progress-glow',
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
