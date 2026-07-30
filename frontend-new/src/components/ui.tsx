import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as SelectPrimitive from '@radix-ui/react-select'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { Check, ChevronDown, X, type LucideIcon } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '../utils/cn'

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
        'text-[11px] font-semibold transition active:translate-y-px',
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

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <TooltipPrimitive.Provider delayDuration={250}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            className="z-100 rounded bg-slate-900 px-2 py-1.5 text-[10px] text-white shadow-xl"
            sideOffset={7}
          >
            {label}
            <TooltipPrimitive.Arrow className="fill-slate-900" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

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
        <p className="mb-1.5 text-[9px] font-bold text-blue-600 uppercase">{eyebrow}</p>
        <h1 className="mb-1.5 text-2xl font-bold text-slate-900">{title}</h1>
        <p className="m-0 text-xs leading-5 text-slate-500">{description}</p>
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
        <header className="mb-4.5 flex items-center justify-between gap-4">
          {title ? <h2 className="m-0 text-[13px] font-bold text-slate-700">{title}</h2> : <span />}
          {meta ? <div className="text-[9px] text-slate-400">{meta}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  )
}

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
        'text-[8px] font-semibold whitespace-nowrap',
        badgeTones[tone],
      )}
    >
      {children}
    </span>
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
      <strong className="text-[11px] text-slate-600">{title}</strong>
      {detail ? <p className="mt-1 max-w-70 text-[9px] leading-4">{detail}</p> : null}
    </div>
  )
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-80 bg-slate-900/45 backdrop-blur-[3px]',
            'data-[state=open]:animate-in data-[state=open]:fade-in',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed top-0 right-0 z-81 h-dvh w-full max-w-155 overflow-y-auto',
            'bg-white p-5.5 shadow-2xl outline-none max-md:p-4',
            'data-[state=open]:animate-in data-[state=open]:slide-in-from-right-8',
          )}
        >
          <header
            className={cn(
              '-mx-5.5 -mt-5.5 mb-5.5 flex items-start justify-between gap-5',
              'border-b border-slate-200 p-5.5 max-md:-mx-4 max-md:-mt-4 max-md:p-4',
            )}
          >
            <div>
              <DialogPrimitive.Title className="mb-1 text-[17px] font-bold text-slate-800">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="m-0 text-[10px] leading-4 text-slate-500">
                  {description}
                </DialogPrimitive.Description>
              ) : null}
            </div>
            <DialogPrimitive.Close asChild>
              <IconButton label="关闭" icon={X} type="button" />
            </DialogPrimitive.Close>
          </header>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

export function Select({
  value,
  onValueChange,
  options,
  placeholder = '请选择',
}: {
  value: string
  onValueChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  placeholder?: string
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        className={cn(
          'flex h-9.5 w-full items-center justify-between rounded-[5px] border',
          'border-slate-200 bg-white px-2.5 text-left text-[11px] text-slate-700 outline-none',
          'focus:border-blue-300 focus:ring-3 focus:ring-blue-500/10',
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown size={15} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className={cn(
            'z-100 max-h-70 min-w-(--radix-select-trigger-width) rounded-md border',
            'border-slate-200 bg-white p-1 shadow-xl',
          )}
          position="popper"
          sideOffset={5}
        >
          <SelectPrimitive.Viewport>
            {options.map((option) => (
              <SelectPrimitive.Item
                className={cn(
                  'flex h-8.5 items-center justify-between rounded px-2',
                  'text-[11px] text-slate-600 outline-none',
                  'data-[highlighted]:bg-blue-50 data-[highlighted]:text-blue-700',
                )}
                value={option.value}
                key={option.value}
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check size={14} />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

export function Switch({
  checked,
  onCheckedChange,
  label,
  detail,
}: {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
  detail?: string
}) {
  return (
    <label
      className={cn(
        'flex min-h-11 items-center justify-between gap-3 rounded-[5px]',
        'border border-slate-100 bg-slate-50 px-2.5 py-2',
      )}
    >
      <span className="flex flex-col">
        <strong className="text-[9px] text-slate-600">{label}</strong>
        {detail ? (
          <small className="mt-0.5 text-[8px] leading-3.5 text-slate-400">{detail}</small>
        ) : null}
      </span>
      <SwitchPrimitive.Root
        className={cn(
          'relative h-4.5 w-8 shrink-0 rounded-full bg-slate-300 p-0',
          'data-[state=checked]:bg-blue-600',
        )}
        checked={checked}
        onCheckedChange={onCheckedChange}
      >
        <SwitchPrimitive.Thumb
          className={cn(
            'block size-3.5 translate-x-0.5 rounded-full bg-white shadow',
            'transition-transform data-[state=checked]:translate-x-4',
          )}
        />
      </SwitchPrimitive.Root>
    </label>
  )
}

export const Tabs = TabsPrimitive.Root
export const TabsList = TabsPrimitive.List
export const TabsTrigger = TabsPrimitive.Trigger
export const TabsContent = TabsPrimitive.Content

export const fieldClass = cn(
  'flex min-w-0 flex-col gap-1.5',
  '[&>span]:text-[9px] [&>span]:font-semibold [&>span]:text-slate-500',
  '[&>input]:h-9.5 [&>input]:w-full [&>input]:rounded-[5px] [&>input]:border',
  '[&>input]:border-slate-200 [&>input]:bg-white [&>input]:px-2.5',
  '[&>input]:text-[11px] [&>input]:text-slate-700 [&>input]:outline-none',
  '[&>input]:focus:border-blue-300 [&>input]:focus:ring-3 [&>input]:focus:ring-blue-500/10',
  '[&>textarea]:min-h-19 [&>textarea]:w-full [&>textarea]:resize-y',
  '[&>textarea]:rounded-[5px] [&>textarea]:border [&>textarea]:border-slate-200',
  '[&>textarea]:bg-white [&>textarea]:px-2.5 [&>textarea]:py-2',
  '[&>textarea]:text-[11px] [&>textarea]:leading-4 [&>textarea]:text-slate-700',
  '[&>textarea]:outline-none [&>textarea]:focus:border-blue-300',
  '[&>textarea]:focus:ring-3 [&>textarea]:focus:ring-blue-500/10',
)

export const tableWrapClass = cn(
  'overflow-hidden rounded-md border border-slate-200 bg-white',
  'shadow-[0_2px_7px_rgba(29,57,96,0.025)]',
  'max-md:-mx-3.5 max-md:rounded-none max-md:border-x-0',
)

export const tableClass = cn(
  'w-full border-collapse',
  '[&_th]:h-10 [&_th]:whitespace-nowrap [&_th]:border-b [&_th]:border-slate-200',
  '[&_th]:bg-slate-50 [&_th]:px-4 [&_th]:text-left',
  '[&_th]:text-[8px] [&_th]:font-bold [&_th]:text-slate-400 [&_th]:uppercase',
  '[&_td]:max-w-70 [&_td]:border-b [&_td]:border-slate-100 [&_td]:px-4 [&_td]:py-3',
  '[&_td]:align-middle [&_td]:text-[10px] [&_td]:text-slate-600',
  '[&_tbody_tr:last-child_td]:border-b-0 [&_tbody_tr:hover]:bg-slate-50/60',
)

export const tabsListClass = cn(
  'mb-3 flex w-fit max-w-full gap-1 overflow-x-auto rounded-md bg-slate-200/70 p-1',
  '[&>button]:flex [&>button]:h-8.5 [&>button]:min-w-max [&>button]:items-center',
  '[&>button]:gap-2 [&>button]:rounded [&>button]:border-0 [&>button]:bg-transparent',
  '[&>button]:px-3 [&>button]:text-[10px] [&>button]:text-slate-500',
  '[&>button[data-state=active]]:bg-white [&>button[data-state=active]]:text-blue-700',
  '[&>button[data-state=active]]:shadow-sm',
)
