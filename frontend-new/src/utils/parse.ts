import type { ChatRef } from '../types'

export function lines(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function chats(value: string): ChatRef[] {
  return lines(value).map((item) => (/^-?\d+$/.test(item) ? Number(item) : item))
}
