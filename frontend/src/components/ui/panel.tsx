import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <header
      className={cn(
        'mb-6 flex min-h-19 items-start justify-between gap-6',
        'max-md:flex-col max-md:gap-4',
      )}
    >
      <div>
        <p className="mb-1.5 text-[13px] font-bold text-blue-600 uppercase">{eyebrow}</p>
        <h1 className="mb-1.5 text-2xl font-bold text-slate-900">{title}</h1>
        <p className="m-0 text-sm leading-5 text-slate-500">{description}</p>
      </div>
      {actions ? (
        <div className="flex items-center gap-2 max-md:w-full max-md:[&>button]:flex-1">
          {actions}
        </div>
      ) : null}
    </header>
  )
}

export function Panel({
  title,
  meta,
  children,
  className = '',
}: {
  title?: string
  meta?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        'min-w-0 rounded-md border border-slate-200 bg-white p-5',
        'shadow-[0_2px_7px_rgba(29,57,96,0.025)] max-md:p-4',
        className,
      )}
    >
      {title || meta ? (
        <header className="mb-4.5 flex min-w-0 items-center justify-between gap-4 max-sm:flex-col max-sm:items-start max-sm:gap-2">
          {title ? (
            <h2 className="m-0 min-w-0 text-[15px] font-bold text-slate-700">{title}</h2>
          ) : (
            <span />
          )}
          {meta ? (
            <div className="min-w-0 max-w-full text-[13px] text-slate-400 max-sm:w-full">
              {meta}
            </div>
          ) : null}
        </header>
      ) : null}
      {children}
    </section>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  detail,
}: {
  icon: LucideIcon
  title: string
  detail?: string
}) {
  return (
    <div
      className={cn(
        'flex min-h-36 flex-col items-center justify-center p-6',
        'text-center text-slate-500',
      )}
    >
      <span
        className={cn(
          'mb-2.5 grid size-10 place-items-center rounded-[5px]',
          'bg-blue-50 text-blue-600',
        )}
      >
        <Icon size={20} />
      </span>
      <strong className="text-[13px] text-slate-600">{title}</strong>
      {detail ? <p className="mt-1 max-w-70 text-[13px] leading-4">{detail}</p> : null}
    </div>
  )
}
