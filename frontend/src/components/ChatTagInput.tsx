import * as Popover from '@radix-ui/react-popover'
import { Check, FolderKanban, Plus, Search, TriangleAlert, X } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useReferencedChats, useTelegramChats } from '../hooks/useTelegramChats'
import type { ChatGroup, ChatRef, TelegramChat } from '../types'
import { chatKindCounts, chatKindSections, type ChatKindFilter } from '../utils/chatKind'
import { chatLabel, chatRowLabel } from '../utils/chatLabel'
import { chatMatches } from '../utils/chatMatch'
import { cn } from '../utils/cn'
import { ChatInvalidBadge } from './ChatInvalidBadge'
import { ChatKindFilterTabs, ChatKindHeading } from './ChatKindPicker'

interface ChatTagInputProps {
  value: ChatRef[]
  onChange: (value: ChatRef[]) => void
  groups?: ChatGroup[]
  selectedGroups?: string[]
  onGroupsChange?: (value: string[]) => void
  /** Render the chat-group picker alone; the chat directory is not shown or fetched. */
  groupsOnly?: boolean
  className?: string
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

function groupMatches(group: ChatGroup, term: string) {
  const query = term.trim().toLowerCase()
  return !query || group.name.toLowerCase().includes(query)
}

export function ChatTagInput({
  value,
  onChange,
  groups = [],
  selectedGroups = [],
  onGroupsChange,
  groupsOnly = false,
  className,
}: ChatTagInputProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [kindFilter, setKindFilter] = useState<ChatKindFilter>('all')
  const [anchor, setAnchor] = useState({ x: 0, y: 0 })

  const chats = useTelegramChats({ enabled: !groupsOnly })
  const extras = useReferencedChats(chats.data, groupsOnly ? [] : value)
  // Referenced chats that Telegram no longer lists stay visible here, marked by
  // the badge component instead of showing up as unknown.
  const directory = useMemo(
    () => [...(chats.data ?? []), ...(extras.data ?? [])],
    [chats.data, extras.data],
  )

  const filtered = useMemo(
    () => directory.filter((chat) => chatMatches(chat, search)),
    [directory, search],
  )
  const counts = useMemo(() => chatKindCounts(filtered), [filtered])
  const sections = useMemo(() => chatKindSections(filtered, kindFilter), [filtered, kindFilter])
  const matchingGroups = useMemo(
    () => groups.filter((group) => groupMatches(group, search)),
    [groups, search],
  )

  const customChat = search.trim() ? parseChatRef(search.trim()) : null
  const customChatSelected = customChat !== null && value.some((item) => sameChat(item, customChat))

  const handleOpenChange = useCallback(
    (next: boolean) => {
      setOpen(next)
      if (!next) {
        setSearch('')
        setKindFilter('all')
      }
      if (next) void chats.refetch()
    },
    [chats.refetch],
  )

  function toggleChat(chatId: ChatRef) {
    const selected = value.some((item) => sameChat(item, chatId))
    onChange(selected ? value.filter((item) => !sameChat(item, chatId)) : [...value, chatId])
  }

  function removeChat(index: number) {
    onChange(value.filter((_, itemIndex) => itemIndex !== index))
  }

  function toggleGroup(name: string) {
    if (!onGroupsChange) return
    onGroupsChange(
      selectedGroups.includes(name)
        ? selectedGroups.filter((item) => item !== name)
        : [...selectedGroups, name],
    )
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
          className,
        )}
      >
        {selectedGroups.map((name) => {
          const known = groups.some((group) => group.name === name)
          return (
            <span
              key={`group-${name}`}
              title={known ? undefined : t('chatInput.unknownGroup', { name })}
              className={cn(
                'inline-flex h-6.5 items-center gap-1 rounded border px-1.5 text-xs',
                known
                  ? 'border-amber-200 bg-amber-50 text-amber-800'
                  : 'border-rose-200 bg-rose-50 text-rose-700',
              )}
            >
              {known ? (
                <FolderKanban className="shrink-0" size={12} />
              ) : (
                <TriangleAlert className="shrink-0" size={12} />
              )}
              {name}
              <button
                type="button"
                aria-label={t('chatInput.remove', { name })}
                className={cn(
                  'grid size-4 place-items-center rounded-sm',
                  known ? 'text-amber-500 hover:bg-amber-100' : 'text-rose-400 hover:bg-rose-100',
                )}
                onClick={(event) => {
                  event.stopPropagation()
                  toggleGroup(name)
                }}
              >
                <X size={12} strokeWidth={2.5} />
              </button>
            </span>
          )
        })}
        {groupsOnly
          ? null
          : value.map((chatId, index) => {
              const chat = findChat(directory, chatId)
              // A chat Telegram stopped naming is as unknown here as one the
              // directory does not list, so both keep the muted warning chip.
              const unknown = chat ? !chat.title : chats.isSuccess
              const label = unknown
                ? t('chatInput.unknown', { id: chatId })
                : chat
                  ? chatLabel(chat, t)
                  : String(chatId)

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
                  {chat ? <ChatInvalidBadge chat={chat} /> : null}
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
            aria-label={t(groupsOnly ? 'chatInput.addGroup' : 'chatInput.addChat')}
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
            {groupsOnly
              ? selectedGroups.length === 0
                ? t('chatInput.addGroup')
                : null
              : value.length === 0
                ? t('chatInput.addChat')
                : null}
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
            'z-100 w-80 overflow-hidden rounded-md border',
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
              placeholder={t(groupsOnly ? 'chatInput.searchGroup' : 'chatInput.search')}
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
          {groupsOnly ? null : (
            <ChatKindFilterTabs value={kindFilter} onChange={setKindFilter} counts={counts} />
          )}
          <div className="max-h-52 overflow-y-auto overscroll-contain p-1">
            {groupsOnly ? (
              matchingGroups.length === 0 ? (
                <p className="px-2 py-3 text-center text-xs text-slate-400">
                  {t(groups.length === 0 ? 'chatInput.noGroups' : 'chatInput.noGroupMatches')}
                </p>
              ) : (
                matchingGroups.map((group) => {
                  const selected = selectedGroups.includes(group.name)
                  return (
                    <button
                      key={`group-${group.name}`}
                      type="button"
                      aria-pressed={selected}
                      className={cn(
                        'flex w-full items-center gap-2 rounded px-2 py-1.5',
                        'text-left text-xs text-amber-800 transition-colors hover:bg-amber-50',
                        selected && 'bg-amber-50',
                      )}
                      onClick={() => toggleGroup(group.name)}
                    >
                      <FolderKanban size={13} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{group.name}</span>
                      <span className="shrink-0 text-[10px] text-amber-500">
                        {t('chatInput.itemCount', { count: group.chats.length })}
                      </span>
                      <span className="grid size-4 shrink-0 place-items-center text-amber-600">
                        {selected ? <Check size={13} strokeWidth={2.5} /> : null}
                      </span>
                    </button>
                  )
                })
              )
            ) : (
              <>
                {kindFilter === 'all' && groups.length > 0 ? (
                  <>
                    <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      {t('chatInput.groups')}
                    </p>
                    {groups
                      .filter(
                        (group) =>
                          groupMatches(group, search) && !selectedGroups.includes(group.name),
                      )
                      .map((group) => {
                        const selected = selectedGroups.includes(group.name)
                        return (
                          <button
                            key={`group-${group.name}`}
                            type="button"
                            aria-pressed={selected}
                            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs text-amber-800 transition-colors hover:bg-amber-50"
                            onClick={() => toggleGroup(group.name)}
                          >
                            <FolderKanban size={13} className="shrink-0" />
                            <span className="min-w-0 flex-1 truncate">{group.name}</span>
                            <span className="shrink-0 text-[10px] text-amber-500">
                              {t('chatInput.itemCount', { count: group.chats.length })}
                            </span>
                            <span className="grid size-4 shrink-0 place-items-center text-amber-600">
                              {selected ? <Check size={13} strokeWidth={2.5} /> : null}
                            </span>
                          </button>
                        )
                      })}
                    <div className="my-1 border-t border-slate-100" />
                  </>
                ) : null}
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
                {sections.length === 0 ? (
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
                  sections.map((section) => (
                    <div key={section.kind}>
                      <ChatKindHeading kind={section.kind} count={section.chats.length} />
                      {section.chats.map((chat) => {
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
                            <span className="flex min-w-0 flex-1 items-center gap-1">
                              <span className="truncate">{chatRowLabel(chat, t)}</span>
                              <ChatInvalidBadge chat={chat} />
                            </span>
                            <span className="shrink-0 text-xs text-slate-400">{chat.id}</span>
                            <span className="grid size-4 shrink-0 place-items-center text-blue-600">
                              {selected ? <Check size={13} strokeWidth={2.5} /> : null}
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  ))
                )}
              </>
            )}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
