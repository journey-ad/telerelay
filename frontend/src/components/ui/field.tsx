import { cn } from '../../utils/cn'

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
