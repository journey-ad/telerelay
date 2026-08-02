import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  Bot,
  Check,
  ChevronDown,
  Languages,
  LogOut,
  Pencil,
  Plus,
  Radio,
  RefreshCw,
  Smartphone,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { accountRequest, json, request } from '../api/client'
import type { TelegramAccount, TelegramAuth } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'
import { AccountAvatar } from './AccountAvatar'
import { clearAuthenticatedImages } from './AuthenticatedImage'
import { Button, confirm, Dialog, fieldClass, IconButton, PasswordInput } from './ui'

function accountSubtitle(account: TelegramAccount, t: TFunction): string {
  const identity = account.username ? `@${account.username}` : ''
  if (account.connected) {
    return identity ? `${identity} · ${t('accounts.connected')}` : t('accounts.connected')
  }
  if (account.running) return t('accounts.running')
  if (identity) return identity
  if (account.authenticated) return t('accounts.saved')
  if (account.kind === 'bot') return t('accounts.bot')
  return t('accounts.awaitingAuth')
}

function accountStatus(account: TelegramAccount, t: TFunction) {
  if (account.connected) {
    return { label: t('accounts.connected'), className: 'bg-emerald-500' }
  }
  if (account.running) {
    return { label: t('accounts.running'), className: 'bg-amber-400' }
  }
  if (account.authenticated) {
    return { label: t('accounts.saved'), className: 'bg-blue-500' }
  }
  return { label: t('accounts.awaitingAuth'), className: 'bg-slate-300' }
}

function AccountStatusDot({ account, t }: { account: TelegramAccount; t: TFunction }) {
  const status = accountStatus(account, t)
  return (
    <span
      className={cn('size-2 shrink-0 rounded-full ring-2 ring-white', status.className)}
      aria-label={status.label}
      title={status.label}
      role="img"
    />
  )
}

function accountSecondaryText(account: TelegramAccount, t: TFunction): string {
  return account.username ? `@${account.username}` : accountSubtitle(account, t)
}

function setActiveAccount(client: ReturnType<typeof useQueryClient>, selected: TelegramAccount) {
  client.setQueryData<TelegramAccount[]>(['telegram-accounts'], (current) => {
    const accounts = current?.some((account) => account.id === selected.id)
      ? current.map((account) => (account.id === selected.id ? selected : account))
      : [...(current ?? []), selected]
    return accounts.map((account) => ({ ...account, active: account.id === selected.id }))
  })
  clearAuthenticatedImages()
}

function removeAccount(client: ReturnType<typeof useQueryClient>, accountId: string) {
  client.setQueryData<TelegramAccount[]>(['telegram-accounts'], (current) => {
    const remaining = (current ?? []).filter((account) => account.id !== accountId)
    if (remaining.some((account) => account.active) || !remaining[0]) return remaining
    return remaining.map((account, index) => ({ ...account, active: index === 0 }))
  })
  client.removeQueries({ predicate: (query) => query.queryKey[1] === accountId })
  clearAuthenticatedImages()
}

export function AccountSwitcher({
  onLogout,
  onRefresh,
}: {
  onLogout: () => void
  onRefresh: () => void
}) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [label, setLabel] = useState('')
  const [accountKind, setAccountKind] = useState<'user' | 'bot'>('user')
  const [botToken, setBotToken] = useState('')
  const [authValue, setAuthValue] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingLabel, setEditingLabel] = useState('')
  const [flowError, setFlowError] = useState<string | null>(null)
  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: 30_000,
  })
  const active = useMemo(
    () => accounts.data?.find((account) => account.active) ?? accounts.data?.[0],
    [accounts.data],
  )
  const auth = useQuery({
    queryKey: ['telegram-auth', active?.id ?? 'none'],
    queryFn: () => accountRequest<TelegramAuth>(active?.id ?? '', '/api/v1/telegram-auth'),
    enabled: dialogOpen,
  })
  const switching = useMutation({
    mutationFn: (accountId: string) =>
      request<TelegramAccount>(`/api/v1/telegram-accounts/${accountId}/activate`, json('POST')),
    onSuccess: async (account) => {
      setActiveAccount(client, account)
      navigate('/')
      if (!account.authenticated) {
        setDialogOpen(true)
        try {
          await accountRequest(account.id, '/api/v1/telegram-auth/start', json('POST'))
        } catch (error) {
          setFlowError(messageFrom(error))
        }
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: ['telegram-accounts'] }),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
      ])
    },
  })
  const creating = useMutation({
    mutationFn: async () => {
      const account = await request<TelegramAccount>(
        '/api/v1/telegram-accounts',
        json('POST', {
          label,
          kind: accountKind,
          ...(accountKind === 'bot' ? { bot_token: botToken } : {}),
        }),
      )
      if (accountKind === 'user') {
        await accountRequest(account.id, '/api/v1/telegram-auth/start', json('POST'))
      }
      return account
    },
    onSuccess: async (account) => {
      setActiveAccount(client, account)
      setFlowError(null)
      setLabel('')
      setBotToken('')
      await Promise.all([
        client.invalidateQueries({ queryKey: ['telegram-accounts'] }),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
      ])
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  const startingAuth = useMutation({
    mutationFn: () => accountRequest(active?.id ?? '', '/api/v1/telegram-auth/start', json('POST')),
    onSuccess: async () => {
      setFlowError(null)
      await auth.refetch()
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  const deleting = useMutation({
    mutationFn: (accountId: string) =>
      request(`/api/v1/telegram-accounts/${accountId}`, json('DELETE')),
    onSuccess: async (_, accountId) => {
      removeAccount(client, accountId)
      await Promise.all([
        client.invalidateQueries({ queryKey: ['telegram-accounts'] }),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
      ])
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  const renaming = useMutation({
    mutationFn: ({ accountId, nextLabel }: { accountId: string; nextLabel: string }) =>
      request<TelegramAccount>(
        `/api/v1/telegram-accounts/${accountId}`,
        json('PUT', { label: nextLabel }),
      ),
    onSuccess: async () => {
      setEditingId(null)
      setEditingLabel('')
      setFlowError(null)
      await accounts.refetch()
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  async function confirmDeleteAccount(account: TelegramAccount) {
    await confirm({
      title: t('accounts.deleteTitle'),
      description: t('accounts.deleteConfirm', { name: account.label }),
      confirmLabel: t('accounts.delete'),
      onConfirm: () => deleting.mutateAsync(account.id),
    })
  }

  useEffect(() => {
    if (auth.data?.state === 'success') {
      clearAuthenticatedImages()
      void accounts.refetch()
    }
  }, [auth.data?.state]) // eslint-disable-line react-hooks/exhaustive-deps

  const waitingLabels = {
    waiting_phone: 'accounts.phone',
    waiting_code: 'accounts.code',
    waiting_password: 'accounts.password',
  } as const
  const waitingLabel = waitingLabels[auth.data?.state as keyof typeof waitingLabels]
  const authenticating = Boolean(
    auth.data?.state &&
    ['waiting_phone', 'waiting_code', 'waiting_password', 'connecting'].includes(auth.data.state),
  )
  const switchingToEnglish = i18n.resolvedLanguage !== 'en-US'
  const languageActionLabel = switchingToEnglish
    ? t('language.switchToEnglish')
    : t('language.switchToChinese')

  function openAccountDialog() {
    setFlowError(null)
    setAuthValue('')
    setBotToken('')
    setDialogOpen(true)
  }

  async function submitAuth() {
    const state = auth.data?.state
    const kind =
      state === 'waiting_phone' ? 'phone' : state === 'waiting_code' ? 'code' : 'password'
    try {
      await accountRequest(
        active?.id ?? '',
        `/api/v1/telegram-auth/${kind}`,
        json('POST', { value: authValue }),
      )
      setAuthValue('')
      setFlowError(null)
      await auth.refetch()
    } catch (error) {
      setFlowError(messageFrom(error))
    }
  }

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger
          className={cn(
            'ml-1 flex h-9.5 max-w-55 items-center gap-2 rounded-md border border-slate-200',
            'bg-white p-1 pr-2 text-slate-500 outline-none transition hover:border-blue-200',
            'data-[state=open]:border-blue-300 data-[state=open]:ring-3 data-[state=open]:ring-blue-500/10',
            'max-md:pr-1',
          )}
        >
          <AccountAvatar
            account={active}
            className="size-7.5 rounded-[5px] bg-blue-50"
            fallbackClassName="text-[13px]"
          />
          <span className="flex min-w-20 flex-1 flex-col items-start overflow-hidden max-md:hidden">
            <strong className="flex w-full min-w-0 items-center gap-1 text-left text-xs text-slate-700">
              <span className="min-w-0 truncate">{active?.label ?? 'Telegram'}</span>
              {active?.kind === 'bot' ? (
                <Bot size={12} className="shrink-0 text-slate-500" aria-hidden="true" />
              ) : null}
            </strong>
            {active ? (
              <small className="flex w-full min-w-0 items-center gap-1 text-left text-xs text-slate-400">
                <span className="min-w-0 truncate">{accountSecondaryText(active, t)}</span>
                <AccountStatusDot account={active} t={t} />
              </small>
            ) : (
              <small className="w-full truncate text-left text-xs text-slate-400">
                {t('accounts.loading')}
              </small>
            )}
          </span>
          <ChevronDown className="shrink-0 max-md:hidden" size={14} />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="z-100 w-66 rounded-md border border-slate-200 bg-white p-1.5 shadow-xl"
            align="end"
            sideOffset={8}
          >
            <DropdownMenu.Label className="px-2 py-1.5 text-xs font-bold text-slate-400 uppercase">
              {t('accounts.title')}
            </DropdownMenu.Label>
            {accounts.data?.map((account) => (
              <DropdownMenu.Item
                key={account.id}
                className={cn(
                  'grid min-h-10.5 grid-cols-[30px_1fr_16px] items-center gap-2 rounded px-2 py-1.5',
                  'text-slate-600 outline-none data-[highlighted]:bg-blue-50',
                  'data-[disabled]:opacity-60',
                )}
                disabled={switching.isPending}
                onSelect={() => {
                  if (!account.active) switching.mutate(account.id)
                }}
              >
                <AccountAvatar
                  account={account}
                  className="size-7.5 rounded-[5px]"
                  fallbackClassName="text-xs"
                />
                <span className="min-w-0">
                  <strong className="flex min-w-0 items-center gap-1 text-xs text-slate-700">
                    <span className="min-w-0 truncate">{account.label}</span>
                    {account.kind === 'bot' ? (
                      <Bot size={12} className="shrink-0 text-slate-500" aria-hidden="true" />
                    ) : null}
                  </strong>
                  <small className="flex min-w-0 items-center gap-1 text-xs text-slate-400">
                    <span className="min-w-0 truncate">{accountSecondaryText(account, t)}</span>
                    <AccountStatusDot account={account} t={t} />
                  </small>
                </span>
                {account.active ? <Check size={14} className="text-blue-600" /> : null}
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="my-1 h-px bg-slate-100" />
            <DropdownMenu.Item
              className="flex h-9 items-center gap-2 rounded px-2 text-xs text-blue-700 outline-none data-[highlighted]:bg-blue-50"
              onSelect={openAccountDialog}
            >
              <Plus size={15} />
              {t('accounts.add')}
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="my-1 hidden h-px bg-slate-100 max-md:block" />
            <div className="hidden grid-cols-3 gap-1 px-1 max-md:grid">
              <DropdownMenu.Item
                className="flex h-9 items-center justify-center rounded text-slate-600 outline-none data-[highlighted]:bg-slate-50"
                aria-label={t('nav.refresh')}
                title={t('nav.refresh')}
                onSelect={onRefresh}
              >
                <RefreshCw size={16} aria-hidden="true" />
              </DropdownMenu.Item>
              <DropdownMenu.Item
                className="flex h-9 items-center justify-center rounded text-slate-600 outline-none data-[highlighted]:bg-slate-50"
                aria-label={languageActionLabel}
                title={languageActionLabel}
                onSelect={() => void i18n.changeLanguage(switchingToEnglish ? 'en-US' : 'zh-CN')}
              >
                <Languages size={16} aria-hidden="true" />
              </DropdownMenu.Item>
              <DropdownMenu.Item
                className="flex h-9 items-center justify-center rounded text-slate-600 outline-none data-[highlighted]:bg-slate-50"
                aria-label={t('accounts.exitConsole')}
                title={t('accounts.exitConsole')}
                onSelect={onLogout}
              >
                <LogOut size={16} aria-hidden="true" />
              </DropdownMenu.Item>
            </div>
            <DropdownMenu.Item
              className="flex h-9 items-center gap-2 rounded px-2 text-xs text-slate-600 outline-none data-[highlighted]:bg-slate-50 max-md:hidden"
              onSelect={onLogout}
            >
              <LogOut size={15} />
              {t('accounts.exitConsole')}
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title={t('accounts.title')}
        description={t('accounts.description')}
      >
        <section className="space-y-2">
          {accounts.data?.map((account) => (
            <div
              key={account.id}
              className={cn(
                'grid min-h-15 grid-cols-[38px_1fr_auto] items-center gap-3 rounded-[5px] border p-2.5',
                account.active ? 'border-blue-200 bg-blue-50/60' : 'border-slate-200 bg-white',
              )}
            >
              <AccountAvatar
                account={account}
                className="size-9.5 rounded-[5px] border border-slate-200 bg-white"
                fallbackClassName="text-xs"
              />
              <div className="min-w-0">
                {editingId === account.id ? (
                  <input
                    className="h-8 w-full rounded-[5px] border border-blue-300 bg-white px-2 text-[13px] text-slate-700 outline-none ring-3 ring-blue-500/10"
                    value={editingLabel}
                    onChange={(event) => setEditingLabel(event.target.value)}
                    maxLength={100}
                    autoFocus
                    aria-label={t('accounts.name')}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && editingLabel.trim()) {
                        renaming.mutate({ accountId: account.id, nextLabel: editingLabel.trim() })
                      }
                      if (event.key === 'Escape') setEditingId(null)
                    }}
                  />
                ) : (
                  <strong className="block truncate text-[13px] text-slate-700">
                    {account.label}
                  </strong>
                )}
                <p className="mt-0.5 truncate text-[13px] text-slate-400">
                  {accountSubtitle(account, t)}
                </p>
              </div>
              <div className="flex gap-1.5">
                {editingId === account.id ? (
                  <>
                    <IconButton
                      label={t('accounts.saveName')}
                      icon={Check}
                      onClick={() =>
                        renaming.mutate({
                          accountId: account.id,
                          nextLabel: editingLabel.trim(),
                        })
                      }
                      disabled={!editingLabel.trim() || renaming.isPending}
                    />
                    <IconButton
                      label={t('accounts.cancelEdit')}
                      icon={X}
                      onClick={() => setEditingId(null)}
                      disabled={renaming.isPending}
                    />
                  </>
                ) : (
                  <IconButton
                    label={t('accounts.editName', { name: account.label })}
                    icon={Pencil}
                    onClick={() => {
                      setEditingId(account.id)
                      setEditingLabel(account.label)
                    }}
                  />
                )}
                {!account.active ? (
                  <IconButton
                    label={t('accounts.switchTo', { name: account.label })}
                    icon={Radio}
                    onClick={() => switching.mutate(account.id)}
                    disabled={switching.isPending}
                  />
                ) : null}
                {account.active && !account.authenticated ? (
                  <IconButton
                    label={t('accounts.authenticate', { name: account.label })}
                    icon={Smartphone}
                    onClick={() => startingAuth.mutate()}
                    disabled={startingAuth.isPending || authenticating}
                  />
                ) : null}
                {editingId !== account.id ? (
                  <IconButton
                    label={t('accounts.deleteNamed', { name: account.label })}
                    icon={Trash2}
                    className="hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
                    onClick={() => void confirmDeleteAccount(account)}
                    disabled={deleting.isPending || accounts.data.length === 1}
                  />
                ) : null}
              </div>
            </div>
          ))}
        </section>

        <div className="my-5 h-px bg-slate-200" />

        {authenticating ? (
          <section>
            <div className="mb-4 flex items-center gap-3 rounded-[5px] border border-blue-100 bg-blue-50 p-3">
              <Smartphone size={20} className="text-blue-600" />
              <div>
                <strong className="text-[13px] text-slate-700">
                  {t('accounts.authenticating', { name: active?.label ?? '' })}
                </strong>
                <p className="mt-0.5 text-[13px] text-slate-500">
                  {waitingLabel ? t(waitingLabel) : t('accounts.connecting')}
                </p>
              </div>
            </div>
            {waitingLabel ? (
              <div className="grid grid-cols-[1fr_auto] items-end gap-2 max-sm:grid-cols-1">
                <label className={fieldClass}>
                  <span>{t(waitingLabel)}</span>
                  <input
                    value={authValue}
                    onChange={(event) => setAuthValue(event.target.value)}
                    type={auth.data?.state === 'waiting_password' ? 'password' : 'text'}
                    autoFocus
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && authValue) void submitAuth()
                    }}
                  />
                </label>
                <Button onClick={() => void submitAuth()} disabled={!authValue}>
                  {t('common.submit')}
                </Button>
              </div>
            ) : null}
          </section>
        ) : (
          <section>
            <div className="mb-3 flex items-center gap-2">
              <UserRound size={17} className="text-blue-600" />
              <strong className="text-[13px] text-slate-700">{t('accounts.addNew')}</strong>
            </div>
            <div className="mb-2 grid grid-cols-2 gap-2">
              {(['user', 'bot'] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setAccountKind(kind)}
                  className={cn(
                    'h-8 rounded-[5px] border text-[13px] outline-none transition',
                    accountKind === kind
                      ? 'border-blue-300 bg-blue-50 text-blue-700 ring-3 ring-blue-500/10'
                      : 'border-slate-200 bg-white text-slate-500 hover:border-blue-200',
                  )}
                >
                  {t(kind === 'user' ? 'accounts.user' : 'accounts.bot')}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-[1fr_auto] items-end gap-2 max-sm:grid-cols-1">
              <label className={fieldClass}>
                <span>{t('accounts.name')}</span>
                <input
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder={t('accounts.namePlaceholder')}
                  maxLength={100}
                  onKeyDown={(event) => {
                    if (
                      event.key === 'Enter' &&
                      label.trim() &&
                      (accountKind === 'user' || botToken.trim())
                    ) {
                      creating.mutate()
                    }
                  }}
                />
              </label>
              <Button
                icon={Plus}
                onClick={() => creating.mutate()}
                disabled={
                  !label.trim() || (accountKind === 'bot' && !botToken.trim()) || creating.isPending
                }
              >
                {t(creating.isPending ? 'accounts.creating' : 'accounts.add')}
              </Button>
            </div>
            {accountKind === 'bot' ? (
              <label className={cn(fieldClass, 'mt-2')}>
                <span>{t('accounts.botToken')}</span>
                <PasswordInput
                  value={botToken}
                  onChange={setBotToken}
                  placeholder={t('accounts.botTokenPlaceholder')}
                  autoComplete="off"
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && label.trim() && botToken.trim()) {
                      creating.mutate()
                    }
                  }}
                />
              </label>
            ) : null}
          </section>
        )}

        {flowError || auth.data?.error || switching.error || startingAuth.error ? (
          <p className="mt-4 rounded-[5px] border border-rose-100 bg-rose-50 p-2.5 text-[13px] text-rose-700">
            {flowError || auth.data?.error || messageFrom(switching.error || startingAuth.error)}
          </p>
        ) : null}
      </Dialog>
    </>
  )
}
