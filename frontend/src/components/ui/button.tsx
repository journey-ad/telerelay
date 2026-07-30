import type { LucideIcon } from 'lucide-react'
import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../utils/cn'
import { Tooltip } from './tooltip'

const buttonVariants = {
  primary: 'border-blue-600 bg-blue-600 text-white shadow-sm hover:bg-blue-700',
  secondary: 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-600',
  danger: 'border-rose-200 bg-rose-50 text-rose-600 hover:bg-rose-100',
  quiet: 'border-transparent bg-transparent text-slate-500 hover:bg-slate-100',
}

export function Button({
  variant = 'primary',
  icon: Icon,
  children,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof buttonVariants
  icon?: LucideIcon
}) {
  return (
    <button
      className={cn(
        'inline-flex min-h-9 items-center justify-center gap-2 rounded-[5px] border px-3.5',
        'text-[13px] font-semibold transition active:translate-y-px',
        'disabled:cursor-not-allowed disabled:opacity-50',
        buttonVariants[variant],
        className,
      )}
      {...props}
    >
      {Icon ? <Icon size={16} strokeWidth={2} aria-hidden /> : null}
      {children}
    </button>
  )
}

export function IconButton({
  label,
  icon: Icon,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: LucideIcon }) {
  return (
    <Tooltip label={label}>
      <button
        className={cn(
          'grid size-8.5 shrink-0 place-items-center rounded-[5px] border border-slate-200',
          'bg-white p-0 text-slate-500 transition',
          'hover:border-blue-200 hover:bg-blue-50 hover:text-blue-600',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
        aria-label={label}
        {...props}
      >
        <Icon size={18} strokeWidth={1.9} />
      </button>
    </Tooltip>
  )
}
