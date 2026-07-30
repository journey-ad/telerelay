import i18n from '../i18n'

export function formatNumber(value: unknown): string {
  return Number(value ?? 0).toLocaleString(i18n.resolvedLanguage ?? 'zh-CN')
}

export function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : i18n.t('common.requestFailed')
}

export function shortDate(value?: string | null): string {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(i18n.resolvedLanguage ?? 'zh-CN', { hour12: false })
}
