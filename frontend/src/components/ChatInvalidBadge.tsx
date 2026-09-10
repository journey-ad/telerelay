import { useTranslation } from 'react-i18next'
import type { TelegramChat } from '../types'
import { Badge } from './ui'

/**
 * Severity order: a chat that no longer exists outranks one the account left,
 * which outranks one that can still be read but not posted to.
 */
const invalidVariants = {
  deleted: { tone: 'red', label: 'chatInput.invalidReasons.deleted' },
  deactivated: { tone: 'red', label: 'chatInput.invalidReasons.deactivated' },
  blocked: { tone: 'amber', label: 'chatInput.invalidReasons.blocked' },
  left: { tone: 'amber', label: 'chatInput.invalidReasons.left' },
  readonly: { tone: 'gray', label: 'chatInput.invalidReasons.readonly' },
} as const

export function ChatInvalidBadge({ chat }: { chat: TelegramChat }) {
  const { t } = useTranslation()
  const variant = chat.invalid_reason ? invalidVariants[chat.invalid_reason] : null
  if (!variant) return null

  return <Badge tone={variant.tone}>{t(variant.label)}</Badge>
}
