import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

const badgeTones = {
  blue: 'border-blue-100 bg-blue-50 text-blue-700',
  green: 'border-emerald-100 bg-emerald-50 text-emerald-700',
  gray: 'border-slate-200 bg-slate-100 text-slate-500',
  amber: 'border-amber-100 bg-amber-50 text-amber-700',
  red: 'border-rose-100 bg-rose-50 text-rose-700',
}

export function Badge({
  children,
  tone = 'blue',
}: {
  children: ReactNode
  tone?: keyof typeof badgeTones
}) {
  return (
    <span
      className={cn(
        'inline-flex min-h-5 items-center justify-center rounded border px-1.5 py-0.5',
        'text-[10px] font-semibold whitespace-nowrap',
        badgeTones[tone],
      )}
    >
      {children}
    </span>
  )
}
