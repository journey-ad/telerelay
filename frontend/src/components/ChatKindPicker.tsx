import { Bot, CircleHelp, Radio, UserRound, UsersRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { TelegramChat } from '../types'
import { chatKindFilters, type ChatKind, type ChatKindFilter } from '../utils/chatKind'
import { cn } from '../utils/cn'

const kindIcons: Record<TelegramChat['kind'], typeof Bot> = {
  private: UserRound,
  bot: Bot,
  group: UsersRound,
  supergroup: UsersRound,
  channel: Radio,
  unknown: CircleHelp,
}

type KindLabelKey =
  | 'chatInput.kind.all'
  | 'chatInput.kind.private'
  | 'chatInput.kind.bot'
  | 'chatInput.kind.group'
  | 'chatInput.kind.channel'
  | 'chatInput.kind.unknown'

const kindLabels: Record<ChatKindFilter, KindLabelKey> = {
  all: 'chatInput.kind.all',
  private: 'chatInput.kind.private',
  bot: 'chatInput.kind.bot',
  group: 'chatInput.kind.group',
  channel: 'chatInput.kind.channel',
  unknown: 'chatInput.kind.unknown',
}

export function ChatKindIcon({ kind, size = 13 }: { kind: TelegramChat['kind']; size?: number }) {
  const Icon = kindIcons[kind]
  return <Icon size={size} />
}

/** Type filter shared by the chat pickers; totals follow the active search. */
export function ChatKindFilterTabs({
  value,
  onChange,
  counts,
  className,
}: {
  value: ChatKindFilter
  onChange: (value: ChatKindFilter) => void
  counts: Record<ChatKindFilter, number>
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1 border-b border-slate-100 px-2 py-1.5',
        className,
      )}
    >
      {chatKindFilters.map((kind) => (
        <button
          key={kind}
          type="button"
          aria-pressed={value === kind}
          className={cn(
            'inline-flex h-6 items-center gap-1 rounded-full px-2 text-[11px] transition-colors',
            value === kind ? 'bg-blue-50 text-blue-700' : 'text-slate-500 hover:bg-slate-100',
          )}
          onClick={() => onChange(kind)}
        >
          {kind === 'all' ? null : <ChatKindIcon kind={kind} size={11} />}
          {t(kindLabels[kind])}
          <span className={cn('text-[10px]', value === kind ? 'text-blue-400' : 'text-slate-400')}>
            {counts[kind]}
          </span>
        </button>
      ))}
    </div>
  )
}

export function ChatKindHeading({ kind, count }: { kind: ChatKind; count: number }) {
  const { t } = useTranslation()
  return (
    <p className="flex items-center gap-1.5 px-2 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
      <ChatKindIcon kind={kind} size={11} />
      {t(kindLabels[kind])}
      <span className="font-normal text-slate-300">{count}</span>
    </p>
  )
}
