import { Eye, EyeOff } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '../../utils/cn'

export function PasswordInput({
  value,
  onChange,
  placeholder,
  autoComplete,
  autoFocus,
  onKeyDown,
  className,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  autoComplete?: string
  autoFocus?: boolean
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void
  className?: string
}) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)
  const label = visible ? t('common.hidePassword') : t('common.showPassword')
  return (
    <div className={cn('relative', className)}>
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        onKeyDown={onKeyDown}
        className={cn(
          'h-9.5 w-full rounded-[5px] border border-slate-200 bg-white px-2.5 pr-9',
          'text-[13px] text-slate-700 outline-none',
          'focus:border-blue-300 focus:ring-3 focus:ring-blue-500/10',
        )}
      />
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={() => setVisible((current) => !current)}
        className="absolute top-1/2 right-1.5 grid size-7 -translate-y-1/2 place-items-center rounded-[5px] text-slate-400 transition hover:bg-slate-100 hover:text-blue-600"
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </button>
    </div>
  )
}
