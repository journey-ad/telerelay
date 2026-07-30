import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../utils/cn'

export function Select({
  value,
  onValueChange,
  options,
  placeholder,
}: {
  value: string
  onValueChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  placeholder?: string
}) {
  const { t } = useTranslation()
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        className={cn(
          'flex h-9.5 w-full items-center justify-between rounded-[5px] border',
          'border-slate-200 bg-white px-2.5 text-left text-[13px] text-slate-700 outline-none',
          'focus:border-blue-300 focus:ring-3 focus:ring-blue-500/10',
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder ?? t('common.pleaseSelect')} />
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
                  'text-[13px] text-slate-600 outline-none',
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
