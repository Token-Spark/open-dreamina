import { ImagePlus, X } from 'lucide-react'

export interface ReferenceSlotProps {
  previewUrl: string | null
  onPick: () => void
  onClear: () => void
}

export function ReferenceSlot({ previewUrl, onPick, onClear }: ReferenceSlotProps) {
  return previewUrl ? (
    <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-btn border border-border">
      <img src={previewUrl} alt="参考图" className="h-full w-full object-cover" />
      <button
        type="button"
        onClick={onClear}
        className="absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white hover:bg-black/80"
        aria-label="移除"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  ) : (
    <button
      type="button"
      onClick={onPick}
      className="flex h-16 w-16 shrink-0 flex-col items-center justify-center gap-1 rounded-btn border border-dashed border-border text-fg-muted transition-colors hover:border-fg-muted hover:text-fg-secondary"
      aria-label="上传参考图"
    >
      <ImagePlus className="h-5 w-5" />
    </button>
  )
}
