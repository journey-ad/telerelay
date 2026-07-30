import { Languages } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '../utils/cn'

export function LanguageToggle({ className }: { className?: string }) {
  const { t, i18n } = useTranslation()
  const switchingToEnglish = i18n.resolvedLanguage !== 'en-US'
  const label = t(switchingToEnglish ? 'language.switchToEnglish' : 'language.switchToChinese')

  return (
    <button
      type="button"
      className={cn(
        'inline-flex h-8.5 min-w-15 items-center justify-center gap-1.5 rounded-[5px] border',
        'border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 shadow-xs',
        'transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500',
        'max-sm:min-w-8.5 max-sm:px-0 max-sm:[&>span]:hidden',
        className,
      )}
      aria-label={label}
      title={label}
      onClick={() => void i18n.changeLanguage(switchingToEnglish ? 'en-US' : 'zh-CN')}
    >
      <Languages size={15} aria-hidden="true" />
      <span>{t(switchingToEnglish ? 'language.englishShort' : 'language.chineseShort')}</span>
    </button>
  )
}
