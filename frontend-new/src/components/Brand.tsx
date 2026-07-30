import { Send } from 'lucide-react'
import { cn } from '../utils/cn'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span
        className={cn(
          'grid size-9 shrink-0 place-items-center rounded-md',
          'bg-blue-600 text-white shadow-[0_7px_16px_rgba(36,118,243,0.22)]',
        )}
      >
        <Send className="-translate-x-px translate-y-px" size={21} fill="currentColor" />
      </span>
      <span className="flex min-w-0 flex-col">
        <strong className="font-display text-base font-bold text-slate-900">TeleRelay</strong>
        {compact ? null : (
          <small className="mt-0.5 text-[10px] text-slate-400">消息中继控制台</small>
        )}
      </span>
    </div>
  )
}
