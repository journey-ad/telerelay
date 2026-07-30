export function formatNumber(value: unknown): string {
  return Number(value ?? 0).toLocaleString()
}

export function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

export function shortDate(value?: string | null): string {
  if (!value) return '-'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}
