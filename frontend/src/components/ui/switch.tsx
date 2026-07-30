import * as SwitchPrimitive from '@radix-ui/react-switch'
import { cn } from '../../utils/cn'

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
        <strong className="text-[11px] text-slate-600">{label}</strong>
        {detail ? (
          <small className="mt-0.5 text-[10px] leading-3.5 text-slate-400">{detail}</small>
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
