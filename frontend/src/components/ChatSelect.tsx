import * as Popover from '@radix-ui/react-popover'
import { Check, ChevronDown, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTelegramChats } from '../hooks/useTelegramChats'
import type { TelegramChat } from '../types'
import { cn } from '../utils/cn'

interface ChatSelectProps {
  value: string
  onValueChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

function chatMatches(chat: TelegramChat, term: string) {
  return [chat.id, chat.title, chat.username]
    .filter((value) => value !== null && value !== undefined)
    .some((value) => String(value).toLowerCase().includes(term))
}

function chatLabel(chat: TelegramChat) {
  return chat.username ? `${chat.title} (@${chat.username})` : chat.title
}

export function ChatSelect({
  value,
  onValueChange,
  placeholder,
  disabled = false,
}: ChatSelectProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const chats = useTelegramChats()
  const selected = chats.data?.find((chat) => String(chat.id) === value)
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    return (chats.data ?? []).filter((chat) => chatMatches(chat, term))
  }, [chats.data, search])

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) setSearch('')
  }

  function selectChat(chat: TelegramChat) {
    onValueChange(String(chat.id))
    setOpen(false)
  }

  const selectedLabel = selected
    ? chatLabel(selected)
    : value
      ? t('chatInput.unknown', { id: value })
      : (placeholder ?? t('common.pleaseSelect'))

  return (
    <Popover.Root modal open={open} onOpenChange={handleOpenChange}>
      <Popover.Trigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            'flex h-9.5 w-full min-w-0 items-center justify-between gap-2 rounded-[5px] border',
            'border-slate-200 bg-white px-2.5 text-left text-[13px] outline-none',
            'focus:border-blue-300 focus:ring-3 focus:ring-blue-500/10',
            'disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400',
          )}
        >
          <span
            className={cn('min-w-0 flex-1 truncate', value ? 'text-slate-700' : 'text-slate-400')}
          >
            {selectedLabel}
          </span>
          <ChevronDown size={15} className="shrink-0 text-slate-500" aria-hidden="true" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className={cn(
            'z-100 w-(--radix-popover-trigger-width) overflow-hidden rounded-md border',
            'border-slate-200 bg-white shadow-xl',
          )}
          side="bottom"
          sideOffset={5}
          align="start"
          collisionPadding={12}
        >
          <div className="flex items-center gap-2 border-b border-slate-100 px-3 py-2">
            <Search size={14} className="shrink-0 text-slate-400" aria-hidden="true" />
            <input
              className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
              placeholder={t('chatInput.search')}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              autoFocus
            />
          </div>
          <div className="max-h-58 overflow-y-auto overscroll-contain p-1" role="listbox">
            {filtered.length === 0 ? (
              <p className="px-2 py-4 text-center text-xs text-slate-400">
                {t(chats.isLoading ? 'common.loadingWithDots' : 'chatInput.noMatches')}
              </p>
            ) : (
              filtered.map((chat) => {
                const isSelected = String(chat.id) === value
                return (
                  <button
                    key={chat.id}
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    className={cn(
                      'flex min-h-9 w-full items-center gap-2 rounded px-2 py-1.5',
                      'text-left text-xs text-slate-600 outline-none transition-colors',
                      'hover:bg-slate-50 focus:bg-blue-50 focus:text-blue-700',
                    )}
                    onClick={() => selectChat(chat)}
                  >
                    <span className="min-w-0 flex-1 truncate">{chatLabel(chat)}</span>
                    <span className="shrink-0 text-xs text-slate-400">{chat.id}</span>
                    <span className="grid size-4 shrink-0 place-items-center text-blue-600">
                      {isSelected ? <Check size={13} strokeWidth={2.5} /> : null}
                    </span>
                  </button>
                )
              })
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
