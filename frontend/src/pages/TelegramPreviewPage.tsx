import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query'
import {
  Archive,
  ArrowDown,
  ArrowLeft,
  Inbox,
  LoaderCircle,
  MessageCircle,
  MessagesSquare,
  Radio,
  Search,
  Send,
  X,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import { accountRequest, ApiError, json, request } from '../api/client'
import { connectTelegramPreviewUpdates } from '../api/events'
import { Avatar, ChatGlyph, DialogRow } from '../components/preview/DialogList'
import { ImageViewer } from '../components/preview/ImageViewer'
import { MessageBubble } from '../components/preview/MessageBubble'
import { EmptyState, IconButton, PageHeader, Tooltip } from '../components/ui'
import { useAccountScope } from '../hooks/useAccountScope'
import type {
  TelegramAccount,
  TelegramBotCommandsResponse,
  TelegramPreviewDialog,
  TelegramPreviewDialogsPage,
  TelegramPreviewMessage,
  TelegramPreviewMessagesPage,
} from '../types'
import { chatMatches } from '../utils/chatMatch'
import { cn } from '../utils/cn'
import { formatNumber, messageFrom } from '../utils/format'
import { groupMessages, isPreviewableMedia, messageDay } from '../utils/preview'
import type { DialogFolder, ImageGroup } from '../utils/preview'

function Loading({ label }: { label: string }) {
  return (
    <div className="flex min-h-28 items-center justify-center gap-2 text-[13px] text-slate-400">
      <LoaderCircle size={15} className="animate-spin" />
      {label}
    </div>
  )
}

function ToolButton({
  children,
  onClick,
  disabled = false,
}: {
  children: ReactNode
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      className={cn(
        'h-8 rounded-[5px] border px-3 text-[13px] font-semibold',
        disabled
          ? 'cursor-default border-slate-100 bg-slate-50 text-slate-400'
          : 'border-slate-200 bg-white text-slate-600 hover:border-blue-200 hover:text-blue-700',
      )}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  )
}

function retryTelegramConnection(failureCount: number, error: Error) {
  return failureCount < 5 && error instanceof ApiError && error.code === 'telegram_not_connected'
}

export function TelegramPreviewPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'zh-CN'
  const queryClient = useQueryClient()
  const accountId = useAccountScope()
  const [folder, setFolder] = useState<DialogFolder>('main')
  const [dialogFilter, setDialogFilter] = useState('')
  const [selected, setSelected] = useState<TelegramPreviewDialog | null>(null)
  const [searchInput, setSearchInput] = useState('')
  const [messageQuery, setMessageQuery] = useState('')
  const [messageSearchOpen, setMessageSearchOpen] = useState(false)
  const [messageDraft, setMessageDraft] = useState('')
  const [viewerTarget, setViewerTarget] = useState<{ chatId: number; messageId: number } | null>(
    null,
  )
  const [replyTargetId, setReplyTargetId] = useState<number | null>(null)
  const [loadingReplyId, setLoadingReplyId] = useState<number | null>(null)
  const [unavailableReplyId, setUnavailableReplyId] = useState<number | null>(null)
  const dialogsViewportRef = useRef<HTMLDivElement>(null)
  const dialogsLoadMoreRef = useRef<HTMLDivElement>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const messageSearchInputRef = useRef<HTMLInputElement>(null)
  const messageComposerRef = useRef<HTMLTextAreaElement>(null)
  const selectedRef = useRef<TelegramPreviewDialog | null>(null)
  const lastDialogsRefresh = useRef(0)
  const dialogsRefreshPending = useRef(false)
  const previousScrollHeight = useRef<number | null>(null)
  const stickToBottom = useRef(true)
  const suppressAutoLoadRef = useRef(false)
  const replyRequestId = useRef(0)
  /** Scroll snapshot taken when the image viewer opens, restored on close. */
  const viewerScrollSnapshot = useRef<{ scrollHeight: number } | null>(null)

  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: (query) =>
      query.state.data?.some((account) => account.authenticated && !account.connected)
        ? 2_000
        : 30_000,
  })
  const active = accounts.data?.find((account) => account.id === accountId)

  useEffect(() => {
    selectedRef.current = selected
  }, [selected])

  useEffect(() => {
    replyRequestId.current += 1
    selectedRef.current = null
    setSelected(null)
    setViewerTarget(null)
    setSearchInput('')
    setMessageQuery('')
    setMessageSearchOpen(false)
    setMessageDraft('')
    setReplyTargetId(null)
    setLoadingReplyId(null)
    setUnavailableReplyId(null)
  }, [accountId])

  const dialogs = useInfiniteQuery({
    queryKey: ['telegram-preview', accountId, 'dialogs', folder],
    enabled: Boolean(accountId && active?.connected),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ folder, limit: '40' })
      if (pageParam) params.set('cursor', pageParam)
      return accountRequest<TelegramPreviewDialogsPage>(
        accountId,
        `/api/v1/telegram-preview/dialogs?${params}`,
      )
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchOnMount: 'always',
    retry: retryTelegramConnection,
    retryDelay: (failureCount) => Math.min(500 * 2 ** failureCount, 4_000),
  })

  const refreshDialogsFirstPage = useCallback(async () => {
    if (dialogsRefreshPending.current) return
    dialogsRefreshPending.current = true
    try {
      const params = new URLSearchParams({ folder, limit: '40' })
      const firstPage = await accountRequest<TelegramPreviewDialogsPage>(
        accountId,
        `/api/v1/telegram-preview/dialogs?${params}`,
      )
      queryClient.setQueryData<InfiniteData<TelegramPreviewDialogsPage>>(
        ['telegram-preview', accountId, 'dialogs', folder],
        (current) => {
          if (!current?.pages.length) return { pages: [firstPage], pageParams: [null] }

          const refreshedIds = new Set(firstPage.items.map((item) => item.id))
          const retainedItems = current.pages
            .flatMap((page) => page.items)
            .filter((item) => !refreshedIds.has(item.id))
          const lastPage = current.pages[current.pages.length - 1]

          return {
            pages: [
              {
                ...firstPage,
                items: [...firstPage.items, ...retainedItems],
                next_cursor: lastPage.next_cursor,
              },
            ],
            pageParams: [null],
          }
        },
      )
    } finally {
      dialogsRefreshPending.current = false
    }
  }, [accountId, folder, queryClient])

  const messages = useInfiniteQuery({
    queryKey: ['telegram-preview', accountId, 'messages', selected?.id ?? null, messageQuery],
    enabled: Boolean(accountId && active?.connected && selected),
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ limit: '40' })
      if (pageParam) params.set('before_id', String(pageParam))
      if (messageQuery) params.set('query', messageQuery)
      return accountRequest<TelegramPreviewMessagesPage>(
        accountId,
        `/api/v1/telegram-preview/chats/${selected!.id}/messages?${params}`,
      )
    },
    getNextPageParam: (page) => page.next_before_id ?? undefined,
    refetchOnMount: 'always',
  })

  const botCommands = useQuery({
    queryKey: ['telegram-preview', accountId, 'bot-commands', selected?.id ?? null],
    enabled: Boolean(accountId && active?.connected && selected?.kind === 'bot'),
    queryFn: () =>
      accountRequest<TelegramBotCommandsResponse>(
        accountId,
        `/api/v1/telegram-preview/chats/${selected!.id}/bot-commands`,
      ),
    staleTime: 5 * 60_000,
  })

  const appendMessage = useCallback(
    (targetAccountId: string, chatId: number, message: TelegramPreviewMessage) => {
      queryClient.setQueryData<InfiniteData<TelegramPreviewMessagesPage>>(
        ['telegram-preview', targetAccountId, 'messages', chatId, ''],
        (current) => {
          if (!current?.pages.length) return current
          if (current.pages.some((page) => page.items.some((item) => item.id === message.id))) {
            return current
          }
          const pages = [...current.pages]
          pages[0] = { ...pages[0], items: [...pages[0].items, message] }
          return { ...current, pages }
        },
      )
    },
    [queryClient],
  )

  const sendMessage = useMutation({
    mutationFn: ({
      targetAccountId,
      chatId,
      text,
    }: {
      targetAccountId: string
      chatId: number
      text: string
    }) =>
      accountRequest<TelegramPreviewMessage>(
        targetAccountId,
        `/api/v1/telegram-preview/chats/${chatId}/messages`,
        json('POST', { text }),
      ),
    onSuccess: (message, variables) => {
      appendMessage(variables.targetAccountId, variables.chatId, message)
      if (variables.targetAccountId === accountId) {
        void refreshDialogsFirstPage().catch(() => undefined)
      }
      if (accountId === variables.targetAccountId && selected?.id === variables.chatId) {
        stickToBottom.current = true
        setSearchInput('')
        setMessageQuery('')
        setMessageDraft('')
      }
    },
  })

  useEffect(() => {
    if (!accountId || !active?.connected) return
    const controller = new AbortController()

    async function monitor(): Promise<void> {
      while (!controller.signal.aborted) {
        try {
          await connectTelegramPreviewUpdates(
            (update) => {
              const now = Date.now()
              if (now - lastDialogsRefresh.current >= 3_000) {
                lastDialogsRefresh.current = now
                void refreshDialogsFirstPage().catch(() => undefined)
              }
              const current = selectedRef.current
              if (!current || current.id !== update.chat_id) return
              void accountRequest<TelegramPreviewMessage>(
                accountId,
                `/api/v1/telegram-preview/chats/${update.chat_id}/messages/${update.message_id}`,
                { signal: controller.signal },
              )
                .then((message) => appendMessage(accountId, update.chat_id, message))
                .catch(() => undefined)
            },
            controller.signal,
            accountId,
          )
        } catch (error) {
          if (controller.signal.aborted) return
          if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
            return
          }
        }
        await new Promise<void>((resolve) => {
          const onAbort = () => {
            window.clearTimeout(timeout)
            resolve()
          }
          const timeout = window.setTimeout(() => {
            controller.signal.removeEventListener('abort', onAbort)
            resolve()
          }, 2_000)
          controller.signal.addEventListener('abort', onAbort, { once: true })
        })
      }
    }

    void monitor()
    return () => controller.abort()
  }, [accountId, active?.connected, appendMessage, refreshDialogsFirstPage])

  const allDialogs = useMemo(() => {
    const seen = new Set<number>()
    return (dialogs.data?.pages.flatMap((page) => page.items) ?? []).filter((item) => {
      if (seen.has(item.id)) return false
      seen.add(item.id)
      return chatMatches(item, dialogFilter)
    })
  }, [dialogFilter, dialogs.data?.pages])

  const allMessages = useMemo(() => {
    const seen = new Set<number>()
    return [...(messages.data?.pages ?? [])]
      .reverse()
      .flatMap((page) => page.items)
      .filter((item) => {
        if (seen.has(item.id)) return false
        seen.add(item.id)
        return true
      })
      .sort((left, right) => left.id - right.id)
  }, [messages.data?.pages])
  const imageGroups = useMemo<ImageGroup[]>(() => {
    const groups: ImageGroup[] = []
    for (const message of allMessages) {
      const media = message.media
      if (!media || !isPreviewableMedia(media)) continue
      const previous = groups[groups.length - 1]
      if (
        message.grouped_id &&
        previous &&
        previous.message.grouped_id === message.grouped_id &&
        previous.message.chat_id === message.chat_id
      ) {
        previous.items.push(message)
      } else {
        groups.push({ message, items: [message] })
      }
    }
    return groups
  }, [allMessages])
  const viewerGroupIndex = viewerTarget
    ? imageGroups.findIndex((group) =>
        group.items.some(
          (message) =>
            message.chat_id === viewerTarget.chatId && message.id === viewerTarget.messageId,
        ),
      )
    : -1
  const viewerItemIndex =
    viewerTarget && viewerGroupIndex >= 0
      ? imageGroups[viewerGroupIndex].items.findIndex(
          (message) => message.id === viewerTarget.messageId,
        )
      : -1
  const messageGroups = useMemo(() => groupMessages(allMessages), [allMessages])
  const newestMessageId = allMessages[allMessages.length - 1]?.id

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    // While the image viewer is open the message list must stay frozen: no
    // auto-stick-to-bottom, no pagination compensation. Closing the viewer
    // restores the position from the snapshot taken on open, so the list never
    // jumps under the overlay.
    if (viewerTarget) return
    if (previousScrollHeight.current !== null) {
      viewport.scrollTop += viewport.scrollHeight - previousScrollHeight.current
      previousScrollHeight.current = null
      return
    }
    if (stickToBottom.current) viewport.scrollTop = viewport.scrollHeight
  }, [newestMessageId, selected?.id, messages.data?.pages.length, viewerTarget])

  useEffect(() => {
    const viewport = viewportRef.current
    if (viewerTarget) {
      // Snapshot the list height so closing the viewer can compensate for any
      // pagination that appended older messages while it was open.
      viewerScrollSnapshot.current = viewport ? { scrollHeight: viewport.scrollHeight } : null
      return
    }
    const snapshot = viewerScrollSnapshot.current
    viewerScrollSnapshot.current = null
    // A stale pagination marker from before the viewer opened must not be
    // consumed after close: the snapshot compensation below is authoritative.
    previousScrollHeight.current = null
    if (snapshot && viewport) {
      viewport.scrollTop += viewport.scrollHeight - snapshot.scrollHeight
    }
  }, [viewerTarget])

  useEffect(() => {
    const viewport = dialogsViewportRef.current
    const loadMore = dialogsLoadMoreRef.current
    if (
      !viewport ||
      !loadMore ||
      !dialogs.hasNextPage ||
      dialogs.isFetchingNextPage ||
      dialogs.isFetchNextPageError
    ) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) void dialogs.fetchNextPage()
      },
      { root: viewport, rootMargin: '0px 0px 120px 0px' },
    )
    observer.observe(loadMore)
    return () => observer.disconnect()
  }, [
    accountId,
    dialogFilter,
    dialogs.fetchNextPage,
    dialogs.hasNextPage,
    dialogs.isFetchNextPageError,
    dialogs.isFetchingNextPage,
    folder,
  ])

  useEffect(() => {
    if (replyTargetId === null) return
    const target = document.getElementById(`message-${replyTargetId}`)
    if (!target) return
    const targetId = replyTargetId
    target.scrollIntoView({ block: 'center', behavior: 'smooth' })
    target.classList.add('ring-2', 'ring-blue-300')
    const timeout = window.setTimeout(() => {
      target.classList.remove('ring-2', 'ring-blue-300')
      setReplyTargetId((current) => (current === targetId ? null : current))
    }, 900)
    const clearSuppress = window.setTimeout(() => {
      suppressAutoLoadRef.current = false
    }, 1500)
    return () => {
      window.clearTimeout(timeout)
      window.clearTimeout(clearSuppress)
      target.classList.remove('ring-2', 'ring-blue-300')
    }
  }, [allMessages, replyTargetId])

  function selectDialog(dialog: TelegramPreviewDialog) {
    replyRequestId.current += 1
    stickToBottom.current = true
    void queryClient.invalidateQueries({
      queryKey: ['telegram-preview', accountId, 'messages', dialog.id, ''],
      exact: true,
    })
    setSelected(dialog)
    setViewerTarget(null)
    setSearchInput('')
    setMessageQuery('')
    setMessageSearchOpen(false)
    setMessageDraft('')
    sendMessage.reset()
    setReplyTargetId(null)
    setLoadingReplyId(null)
    setUnavailableReplyId(null)
  }

  function searchMessages(event: FormEvent) {
    event.preventDefault()
    stickToBottom.current = false
    setMessageQuery(searchInput.trim())
    setMessageSearchOpen(false)
  }

  function openMessageSearch() {
    setMessageSearchOpen(true)
    window.requestAnimationFrame(() => messageSearchInputRef.current?.focus())
  }

  function submitMessage(event: FormEvent) {
    event.preventDefault()
    const text = messageDraft.trim()
    if (!selected || !text || sendMessage.isPending) return
    sendMessage.mutate({ targetAccountId: accountId, chatId: selected.id, text })
  }

  const loadEarlierImages = useCallback(() => {
    // While the image viewer is open, pagination is compensated by the scroll
    // snapshot on close; do not arm the layout-effect marker then, or it would
    // be consumed (with a stale height) on the close frame.
    if (viewportRef.current && !viewerTarget) {
      previousScrollHeight.current = viewportRef.current.scrollHeight
    }
    void messages.fetchNextPage().catch(() => {
      // A failed page must not leave the marker armed for a later frame.
      previousScrollHeight.current = null
    })
  }, [messages.fetchNextPage, viewerTarget])

  async function loadOlder() {
    stickToBottom.current = false
    if (viewportRef.current) previousScrollHeight.current = viewportRef.current.scrollHeight
    try {
      await messages.fetchNextPage()
    } catch {
      previousScrollHeight.current = null
    }
  }

  async function replyClick(id: number) {
    suppressAutoLoadRef.current = true
    const target = document.getElementById(`message-${id}`)
    if (target) {
      setReplyTargetId(id)
      return
    }
    if (!selected || loadingReplyId !== null) return

    setLoadingReplyId(id)
    setUnavailableReplyId(null)
    stickToBottom.current = false
    const requestId = ++replyRequestId.current
    try {
      const params = new URLSearchParams()
      const message = await accountRequest<TelegramPreviewMessage>(
        accountId,
        `/api/v1/telegram-preview/chats/${selected.id}/messages/${id}?${params}`,
      )
      if (requestId !== replyRequestId.current) return
      queryClient.setQueryData<InfiniteData<TelegramPreviewMessagesPage>>(
        ['telegram-preview', accountId, 'messages', selected.id, messageQuery],
        (current) => {
          if (!current?.pages.length) return current
          if (current.pages.some((page) => page.items.some((item) => item.id === message.id))) {
            return current
          }
          const pages = [...current.pages]
          const oldestIndex = pages.length - 1
          pages[oldestIndex] = {
            ...pages[oldestIndex],
            items: [...pages[oldestIndex].items, message],
          }
          return { ...current, pages }
        },
      )
      setReplyTargetId(id)
    } catch {
      if (requestId === replyRequestId.current) setUnavailableReplyId(id)
    } finally {
      if (requestId === replyRequestId.current) setLoadingReplyId(null)
    }
  }

  const connected = Boolean(active?.connected)
  return (
    <div className="flex min-h-0 flex-1 flex-col [&>header]:shrink-0">
      <PageHeader
        eyebrow={t('telegramPreview.eyebrow')}
        title={t('telegramPreview.title')}
        description={t('telegramPreview.description')}
      />
      <section
        className={cn(
          'grid min-h-0 flex-1 grid-cols-[310px_minmax(0,1fr)] overflow-hidden',
          'rounded-md border border-slate-200 bg-white shadow-sm',
          'max-lg:grid-cols-1',
        )}
      >
        <aside
          className={cn(
            'flex min-h-0 flex-col border-r border-slate-200 bg-white',
            selected && 'max-lg:hidden',
          )}
        >
          <div className="border-b border-slate-200 p-3">
            <div className="grid grid-cols-2 rounded-[5px] bg-slate-100 p-0.5">
              {(['main', 'archived'] as const).map((value) => (
                <button
                  key={value}
                  className={cn(
                    'flex h-8 items-center justify-center gap-1.5 rounded-[4px] border-0 text-[13px] font-semibold',
                    folder === value
                      ? 'bg-white text-slate-700 shadow-sm'
                      : 'bg-transparent text-slate-400',
                  )}
                  onClick={() => {
                    setFolder(value)
                    setSelected(null)
                  }}
                >
                  {value === 'main' ? <Inbox size={13} /> : <Archive size={13} />}
                  {t(value === 'main' ? 'telegramPreview.main' : 'telegramPreview.archived')}
                </button>
              ))}
            </div>
            <label className="mt-2.5 flex h-8.5 items-center gap-2 rounded-[5px] border border-slate-200 px-2.5 text-slate-400 focus-within:border-blue-300">
              <Search size={14} />
              <input
                className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-slate-700 outline-none"
                value={dialogFilter}
                onChange={(event) => setDialogFilter(event.target.value)}
                placeholder={t('telegramPreview.filterChats')}
              />
              {dialogFilter ? (
                <button
                  className="grid size-5 place-items-center border-0 bg-transparent"
                  aria-label={t('telegramPreview.clearChatFilter')}
                  onClick={() => setDialogFilter('')}
                >
                  <X size={12} />
                </button>
              ) : null}
            </label>
          </div>
          <div ref={dialogsViewportRef} className="min-h-0 flex-1 overflow-y-auto">
            {!connected ? (
              <EmptyState
                icon={Radio}
                title={t('telegramPreview.accountDisconnected')}
                detail={t('telegramPreview.accountDisconnectedDetail')}
              />
            ) : dialogs.isLoading ? (
              <Loading label={t('telegramPreview.loadingChats')} />
            ) : dialogs.isError ? (
              <EmptyState
                icon={MessageCircle}
                title={t('telegramPreview.loadChatsFailed')}
                detail={messageFrom(dialogs.error)}
              />
            ) : allDialogs.length ? (
              allDialogs.map((dialog) => (
                <DialogRow
                  key={dialog.id}
                  accountId={accountId}
                  dialog={dialog}
                  selected={selected?.id === dialog.id}
                  onSelect={() => selectDialog(dialog)}
                />
              ))
            ) : (
              <EmptyState
                icon={folder === 'main' ? Inbox : Archive}
                title={
                  dialogFilter
                    ? t('telegramPreview.noMatchingChats')
                    : folder === 'main'
                      ? t('telegramPreview.mainEmpty')
                      : t('telegramPreview.archivedEmpty')
                }
              />
            )}
            {dialogs.hasNextPage ? (
              <div
                ref={dialogsLoadMoreRef}
                className={cn(
                  'flex shrink-0 items-center justify-center text-xs text-slate-400',
                  dialogs.isFetchingNextPage || dialogs.isFetchNextPageError
                    ? 'h-10 border-t border-slate-100'
                    : 'h-px',
                )}
              >
                {dialogs.isFetchingNextPage ? (
                  <span className="flex items-center gap-1.5">
                    <LoaderCircle size={14} className="animate-spin" />
                    {t('telegramPreview.loading')}
                  </span>
                ) : dialogs.isFetchNextPageError ? (
                  <button
                    className="border-0 bg-transparent text-blue-600 hover:text-blue-700"
                    onClick={() => void dialogs.fetchNextPage()}
                  >
                    {t('telegramPreview.retryLoadChats')}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </aside>

        <article
          className={cn(
            'relative min-h-0 min-w-0 flex-col bg-[#f4f7fa]',
            selected ? 'flex' : 'hidden lg:flex',
          )}
        >
          {selected ? (
            <>
              <header className="relative flex h-14 shrink-0 items-center gap-2.5 border-b border-slate-200 bg-white px-3.5">
                <IconButton
                  label={t('telegramPreview.backToChats')}
                  icon={ArrowLeft}
                  className="hidden max-lg:grid"
                  onClick={() => setSelected(null)}
                />
                <Avatar
                  accountId={accountId}
                  peerId={selected.id}
                  inlineSource={selected.inline_avatar}
                  title={selected.title}
                  kind={selected.kind}
                  className="size-9"
                />
                <div className="min-w-0 flex-1 overflow-hidden">
                  <strong className="block truncate text-sm text-slate-700">
                    {selected.title}
                  </strong>
                  <span className="mt-0.5 flex min-w-0 items-center gap-1 overflow-hidden whitespace-nowrap text-xs text-slate-400">
                    <span className="shrink-0">
                      <ChatGlyph kind={selected.kind} size={11} />
                    </span>
                    <span className="truncate">
                      {t(`telegramPreview.kinds.${selected.kind}`)}
                      {selected.username ? ` · @${selected.username}` : ''}
                    </span>
                  </span>
                </div>
                <IconButton
                  type="button"
                  label={t('telegramPreview.searchCurrent')}
                  icon={Search}
                  className="sm:hidden"
                  onClick={openMessageSearch}
                />
                <form
                  className={cn(
                    'flex h-8.5 w-66 items-center gap-1.5 rounded-[5px] border',
                    'border-slate-200 bg-slate-50 px-2',
                    messageSearchOpen
                      ? 'max-sm:absolute max-sm:inset-0 max-sm:z-10 max-sm:h-full max-sm:w-full max-sm:rounded-none max-sm:border-0 max-sm:bg-white max-sm:px-3.5 max-sm:shadow-sm'
                      : 'max-sm:hidden',
                  )}
                  onSubmit={searchMessages}
                >
                  <Search size={13} className="shrink-0 text-slate-400" />
                  <input
                    ref={messageSearchInputRef}
                    className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-slate-700 outline-none"
                    value={searchInput}
                    onChange={(event) => setSearchInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') setMessageSearchOpen(false)
                    }}
                    placeholder={t('telegramPreview.searchCurrent')}
                  />
                  {messageQuery || searchInput || messageSearchOpen ? (
                    <button
                      type="button"
                      className="grid size-5 place-items-center border-0 bg-transparent text-slate-400"
                      aria-label={t('telegramPreview.clearMessageSearch')}
                      onClick={() => {
                        setSearchInput('')
                        setMessageQuery('')
                        setMessageSearchOpen(false)
                        stickToBottom.current = true
                      }}
                    >
                      <X size={12} />
                    </button>
                  ) : null}
                </form>
              </header>
              {messageQuery ? (
                <div className="flex h-8 shrink-0 items-center justify-between border-b border-blue-100 bg-blue-50 px-3.5 text-xs text-blue-700">
                  <span>{t('telegramPreview.searchResults', { query: messageQuery })}</span>
                  <span>{t('telegramPreview.loadedCount', { count: allMessages.length })}</span>
                </div>
              ) : null}
              <div
                ref={viewportRef}
                data-testid="message-viewport"
                className="min-h-0 flex-1 overflow-y-auto px-5 py-4 max-sm:px-2.5"
                onScroll={(event) => {
                  const node = event.currentTarget
                  stickToBottom.current =
                    node.scrollHeight - node.scrollTop - node.clientHeight < 120
                  if (
                    !suppressAutoLoadRef.current &&
                    node.scrollTop < 200 &&
                    messages.hasNextPage &&
                    !messages.isFetchingNextPage
                  ) {
                    void loadOlder()
                  }
                }}
              >
                {messages.hasNextPage ? (
                  <div className="mb-3 flex justify-center">
                    <ToolButton
                      onClick={() => void loadOlder()}
                      disabled={messages.isFetchingNextPage}
                    >
                      {t(
                        messages.isFetchingNextPage
                          ? 'telegramPreview.loadingHistory'
                          : 'telegramPreview.loadOlder',
                      )}
                    </ToolButton>
                  </div>
                ) : null}
                {messages.isLoading ? (
                  <Loading label={t('telegramPreview.loadingMessages')} />
                ) : messages.isError ? (
                  <EmptyState
                    icon={MessageCircle}
                    title={t('telegramPreview.loadMessagesFailed')}
                    detail={messageFrom(messages.error)}
                  />
                ) : messageGroups.length ? (
                  <div className="mx-auto flex max-w-230 flex-col gap-2">
                    {messageGroups.map((group, index) => {
                      const previous = messageGroups[index - 1]?.items[0]
                      return (
                        <MessageBubble
                          key={`${selected.id}:${group.key}`}
                          accountId={accountId}
                          group={group}
                          showDay={
                            !previous ||
                            messageDay(
                              previous.date,
                              locale,
                              t('telegramPreview.unknownDate'),
                              t('telegramPreview.today'),
                              t('telegramPreview.yesterday'),
                            ) !==
                              messageDay(
                                group.items[0].date,
                                locale,
                                t('telegramPreview.unknownDate'),
                                t('telegramPreview.today'),
                                t('telegramPreview.yesterday'),
                              )
                          }
                          onReplyClick={(id) => void replyClick(id)}
                          onOpenPreview={(message) =>
                            setViewerTarget({ chatId: message.chat_id, messageId: message.id })
                          }
                          loadingReplyId={loadingReplyId}
                          unavailableReplyId={unavailableReplyId}
                        />
                      )
                    })}
                  </div>
                ) : (
                  <EmptyState
                    icon={MessagesSquare}
                    title={t(
                      messageQuery
                        ? 'telegramPreview.noMatchingMessages'
                        : 'telegramPreview.chatEmpty',
                    )}
                  />
                )}
              </div>
              {botCommands.data?.items.length ? (
                <div className="shrink-0 border-t border-slate-200 bg-white px-3.5 pt-2 max-sm:px-2.5">
                  <div className="flex h-8 gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    {botCommands.data.items.map((item) => {
                      const button = (
                        <button
                          key={item.command}
                          type="button"
                          className="h-7 shrink-0 rounded-[5px] border border-blue-100 bg-blue-50 px-2.5 text-xs font-semibold text-blue-700 transition hover:border-blue-200 hover:bg-blue-100"
                          onClick={() => {
                            setMessageDraft(`/${item.command}`)
                            window.requestAnimationFrame(() => messageComposerRef.current?.focus())
                          }}
                        >
                          /{item.command}
                        </button>
                      )
                      return item.description ? (
                        <Tooltip key={item.command} label={item.description}>
                          {button}
                        </Tooltip>
                      ) : (
                        button
                      )
                    })}
                  </div>
                </div>
              ) : null}
              <form
                className={cn(
                  'relative flex shrink-0 items-end gap-2 bg-white px-3.5 py-2.5 max-sm:px-2.5',
                  botCommands.data?.items.length ? '' : 'border-t border-slate-200',
                )}
                onSubmit={submitMessage}
              >
                <div className="min-w-0 flex-1">
                  <textarea
                    ref={messageComposerRef}
                    className={cn(
                      'block h-10 w-full resize-none rounded-[5px] border bg-slate-50 px-3 py-2',
                      'text-[13px] leading-5 text-slate-700 outline-none transition',
                      'placeholder:text-slate-400 focus:border-blue-300 focus:bg-white',
                      'focus:ring-3 focus:ring-blue-500/10 disabled:cursor-not-allowed',
                      sendMessage.isError ? 'border-rose-300' : 'border-slate-200',
                    )}
                    value={messageDraft}
                    maxLength={4096}
                    disabled={sendMessage.isPending}
                    placeholder={t('telegramPreview.messagePlaceholder')}
                    aria-label={t('telegramPreview.messagePlaceholder')}
                    onChange={(event) => {
                      setMessageDraft(event.target.value)
                      if (sendMessage.isError) sendMessage.reset()
                    }}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing
                      ) {
                        event.preventDefault()
                        event.currentTarget.form?.requestSubmit()
                      }
                    }}
                  />
                  {sendMessage.isError ? (
                    <span className="mt-1 block text-xs text-rose-600">
                      {messageFrom(sendMessage.error)}
                    </span>
                  ) : messageDraft.length > 3600 ? (
                    <span className="mt-1 block text-right text-[11px] text-slate-400">
                      {formatNumber(messageDraft.length)} / {formatNumber(4096)}
                    </span>
                  ) : null}
                </div>
                <IconButton
                  type="submit"
                  label={t(
                    sendMessage.isPending
                      ? 'telegramPreview.sendingMessage'
                      : 'telegramPreview.sendMessage',
                  )}
                  icon={sendMessage.isPending ? LoaderCircle : Send}
                  disabled={!messageDraft.trim() || sendMessage.isPending}
                  className={cn(
                    'size-10 border-blue-600 bg-blue-600 text-white',
                    'hover:border-blue-700 hover:bg-blue-700 hover:text-white',
                    sendMessage.isPending && '[&_svg]:animate-spin',
                  )}
                />
              </form>
              {!stickToBottom.current && allMessages.length ? (
                <button
                  className={cn(
                    'absolute right-4 grid size-9 place-items-center rounded-full border',
                    'border-slate-200 bg-white text-slate-500 shadow-lg',
                    botCommands.data?.items.length ? 'bottom-32' : 'bottom-24',
                  )}
                  title={t('telegramPreview.latest')}
                  aria-label={t('telegramPreview.latest')}
                  onClick={() => {
                    stickToBottom.current = true
                    viewportRef.current?.scrollTo({
                      top: viewportRef.current.scrollHeight,
                      behavior: 'smooth',
                    })
                  }}
                >
                  <ArrowDown size={16} />
                </button>
              ) : null}
            </>
          ) : (
            <div className="grid h-full place-items-center p-8">
              <div className="max-w-72 text-center">
                <span className="mx-auto grid size-12 place-items-center rounded-md border border-slate-200 bg-white text-blue-600 shadow-sm">
                  <MessagesSquare size={24} />
                </span>
                <strong className="mt-4 block text-sm text-slate-700">
                  {t('telegramPreview.selectChat')}
                </strong>
              </div>
            </div>
          )}
        </article>
      </section>
      {viewerGroupIndex >= 0 && viewerItemIndex >= 0 && viewerTarget ? (
        <ImageViewer
          accountId={accountId}
          groups={imageGroups}
          groupIndex={viewerGroupIndex}
          itemIndex={viewerItemIndex}
          hasNextPage={Boolean(messages.hasNextPage)}
          onNavigate={(message) =>
            setViewerTarget({ chatId: message.chat_id, messageId: message.id })
          }
          onLoadEarlier={loadEarlierImages}
          onClose={() => setViewerTarget(null)}
        />
      ) : null}
    </div>
  )
}
