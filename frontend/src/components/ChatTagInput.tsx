import * as Popover from '@radix-ui/react-popover'
import { Check, Plus, Search, TriangleAlert, X } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useTelegramChats } from '../hooks/useTelegramChats'
import type { ChatRef, TelegramChat } from '../types'
import { cn } from '../utils/cn'

interface ChatTagInputProps {
  value: ChatRef[]
  onChange: (value: ChatRef[]) => void
}

function findChat(chats: TelegramChat[] | undefined, chatId: ChatRef) {
  return chats?.find((chat) => String(chat.id) === String(chatId))
}

function sameChat(left: ChatRef, right: ChatRef) {
  return String(left) === String(right)
}

function parseChatRef(value: string): ChatRef {
  return /^-?\d+$/.test(value) ? Number(value) : value
}

export function ChatTagInput({ value, onChange }: ChatTagInputProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [anchor, setAnchor] = useState({ x: 0, y: 0 })

  const chats = useTelegramChats()

  const filtered = useMemo(() => {
    if (!chats.data) return []
    const term = search.trim().toLowerCase()
    return chats.data.filter((chat) =>
      [chat.id, chat.title, chat.username]
        .filter((value) => value !== null && value !== undefined)
        .some((value) => String(value).toLowerCase().includes(term)),
    )
  }, [chats.data, search])

  const customChat = search.trim() ? parseChatRef(search.trim()) : null
  const customChatSelected = customChat !== null && value.some((item) => sameChat(item, customChat))

  const handleOpenChange = useCallback((next: boolean) => {
    setOpen(next)
    if (!next) setSearch('')
  }, [])

  function toggleChat(chatId: ChatRef) {
    const selected = value.some((item) => sameChat(item, chatId))
    onChange(selected ? value.filter((item) => !sameChat(item, chatId)) : [...value, chatId])
  }

  function removeChat(index: number) {
    onChange(value.filter((_, itemIndex) => itemIndex !== index))
  }

  function addCustomChat() {
    if (customChat === null || customChatSelected) return
    onChange([...value, customChat])
    setSearch('')
  }

  return (
    <Popover.Root modal open={open} onOpenChange={handleOpenChange}>
      <div
        className={cn(
          'flex min-h-9.5 w-full flex-wrap items-center gap-1.5',
          'rounded-[5px] border border-slate-200 bg-white px-2.5 py-1.5',
          'hover:border-blue-300 focus-within:border-blue-300',
          'focus-within:ring-3 focus-within:ring-blue-500/10',
        )}
      >
        {value.map((chatId, index) => {
          const chat = findChat(chats.data, chatId)
          const unknown = chats.isSuccess && !chat
          const label =
            chat?.title ?? (unknown ? t('chatInput.unknown', { id: chatId }) : String(chatId))

          return (
            <span
              key={`${String(chatId)}-${index}`}
              className={cn(
                'inline-flex h-6.5 items-center gap-1 rounded border px-1.5',
                'text-xs',
                unknown
                  ? 'border-slate-200 bg-slate-100 text-slate-500'
                  : 'border-blue-100 bg-blue-50 text-blue-700',
              )}
            >
              {unknown ? <TriangleAlert className="shrink-0" size={12} /> : null}
              {label}
              <button
                type="button"
                aria-label={t('chatInput.remove', { name: label })}
                className={cn(
                  'grid size-4 place-items-center rounded-sm',
                  unknown
                    ? 'text-slate-400 hover:bg-slate-200 hover:text-slate-700'
                    : 'text-blue-400 hover:bg-blue-100 hover:text-blue-700',
                )}
                onClick={(event) => {
                  event.stopPropagation()
                  removeChat(index)
                }}
              >
                <X size={12} strokeWidth={2.5} />
              </button>
            </span>
          )
        })}
        <Popover.Trigger asChild>
          <button
            type="button"
            aria-label={t('chatInput.addChat')}
            className={cn(
              'inline-flex h-7 items-center gap-1 rounded px-1.5 text-xs',
              'text-slate-400 outline-none hover:bg-slate-100 hover:text-blue-600',
            )}
            onPointerDown={(event) => {
              if (!open) setAnchor({ x: event.clientX, y: event.clientY })
            }}
            onKeyDown={(event) => {
              if (!open && (event.key === 'Enter' || event.key === ' ')) {
                const bounds = event.currentTarget.getBoundingClientRect()
                setAnchor({
                  x: bounds.left + bounds.width / 2,
                  y: bounds.top + bounds.height / 2,
                })
              }
            }}
          >
            <Plus size={13} />
            {value.length === 0 ? t('chatInput.addChat') : null}
          </button>
        </Popover.Trigger>
      </div>
      <Popover.Anchor asChild>
        <span
          aria-hidden
          className="pointer-events-none fixed size-px"
          style={{ left: anchor.x, top: anchor.y }}
        />
      </Popover.Anchor>
      <Popover.Portal>
        <Popover.Content
          className={cn(
            'z-100 w-64 overflow-hidden rounded-md border',
            'border-slate-200 bg-white shadow-xl',
          )}
          side="bottom"
          sideOffset={6}
          align="start"
          collisionPadding={12}
        >
          <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-100 bg-white px-3 py-2">
            <Search size={14} className="shrink-0 text-slate-400" />
            <input
              className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
              placeholder={t('chatInput.search')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && customChat !== null && filtered.length === 0) {
                  event.preventDefault()
                  addCustomChat()
                }
              }}
              autoFocus
            />
          </div>
          <div className="max-h-52 overflow-y-auto overscroll-contain p-1">
            {customChat !== null && !customChatSelected ? (
              <button
                type="button"
                className={cn(
                  'flex w-full items-center gap-2 rounded px-2 py-1.5',
                  'text-left text-xs text-blue-700 outline-none',
                  'hover:bg-blue-50 focus:bg-blue-50',
                )}
                onClick={addCustomChat}
              >
                <Plus size={13} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">
                  {t('chatInput.addId', { id: String(customChat) })}
                </span>
              </button>
            ) : null}
            {filtered.length === 0 ? (
              <p className="px-2 py-3 text-center text-xs text-slate-400">
                {t(
                  chats.isLoading
                    ? 'common.loadingWithDots'
                    : customChat === null
                      ? 'chatInput.noMatches'
                      : 'chatInput.addManually',
                )}
              </p>
            ) : (
              filtered.map((chat) => {
                const selected = value.some((item) => sameChat(item, chat.id))

                return (
                  <button
                    key={chat.id}
                    type="button"
                    aria-pressed={selected}
                    className={cn(
                      'flex w-full items-center gap-2 rounded px-2 py-1.5',
                      'text-left text-xs text-slate-600 transition-colors',
                      'hover:bg-slate-50',
                    )}
                    onClick={() => toggleChat(chat.id)}
                  >
                    <span className="min-w-0 flex-1 truncate">
                      {chat.title}
                      {chat.username ? ` (@${chat.username})` : ''}
                    </span>
                    <span className="shrink-0 text-xs text-slate-400">{chat.id}</span>
                    <span className="grid size-4 shrink-0 place-items-center text-blue-600">
                      {selected ? <Check size={13} strokeWidth={2.5} /> : null}
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
