import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import {
  Check,
  ChevronDown,
  LogOut,
  Plus,
  Radio,
  Smartphone,
  Trash2,
  UserRound,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { json, request } from '../api/client'
import type { TelegramAccount, TelegramAuth } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'
import { AccountAvatar } from './AccountAvatar'
import { clearAuthenticatedImages } from './AuthenticatedImage'
import { Button, ConfirmDialog, Dialog, fieldClass, IconButton } from './ui'

function accountSubtitle(account: TelegramAccount, t: TFunction): string {
  if (account.username) return `@${account.username}`
  if (account.connected) return t('accounts.connected')
  if (account.authenticated) return t('accounts.saved')
  return t('accounts.awaitingAuth')
}

export function AccountSwitcher({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deletingAccount, setDeletingAccount] = useState<TelegramAccount | null>(null)
  const [label, setLabel] = useState('')
  const [authValue, setAuthValue] = useState('')
  const [flowError, setFlowError] = useState<string | null>(null)
  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: 5000,
  })
  const auth = useQuery({
    queryKey: ['telegram-auth'],
    queryFn: () => request<TelegramAuth>('/api/v1/telegram-auth'),
    enabled: dialogOpen,
    refetchInterval: dialogOpen ? 1200 : false,
  })
  const active = useMemo(
    () => accounts.data?.find((account) => account.active) ?? accounts.data?.[0],
    [accounts.data],
  )
  const switching = useMutation({
    mutationFn: (accountId: string) =>
      request<TelegramAccount>(`/api/v1/telegram-accounts/${accountId}/activate`, json('POST')),
    onSuccess: async (account) => {
      client.removeQueries({ queryKey: ['telegram-preview'] })
      clearAuthenticatedImages()
      if (!account.authenticated) {
        setDialogOpen(true)
        try {
          await request('/api/v1/telegram-auth/start', json('POST'))
        } catch (error) {
          setFlowError(messageFrom(error))
        }
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: ['telegram-accounts'] }),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
        client.invalidateQueries({ queryKey: ['export-chats'] }),
      ])
    },
  })
  const creating = useMutation({
    mutationFn: async () => {
      const account = await request<TelegramAccount>(
        '/api/v1/telegram-accounts',
        json('POST', { label }),
      )
      await request('/api/v1/telegram-auth/start', json('POST'))
      return account
    },
    onSuccess: async () => {
      client.removeQueries({ queryKey: ['telegram-preview'] })
      clearAuthenticatedImages()
      setFlowError(null)
      setLabel('')
      await Promise.all([accounts.refetch(), auth.refetch()])
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  const startingAuth = useMutation({
    mutationFn: () => request('/api/v1/telegram-auth/start', json('POST')),
    onSuccess: async () => {
      client.removeQueries({ queryKey: ['telegram-preview'] })
      clearAuthenticatedImages()
      setFlowError(null)
      await auth.refetch()
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })
  const deleting = useMutation({
    mutationFn: (accountId: string) =>
      request(`/api/v1/telegram-accounts/${accountId}`, json('DELETE')),
    onSuccess: async () => {
      setDeletingAccount(null)
      client.removeQueries({ queryKey: ['telegram-preview'] })
      clearAuthenticatedImages()
      await Promise.all([
        accounts.refetch(),
        auth.refetch(),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
      ])
    },
    onError: (error) => setFlowError(messageFrom(error)),
  })

  useEffect(() => {
    if (auth.data?.state === 'success') {
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

  function openAccountDialog() {
    setFlowError(null)
    setAuthValue('')
    setDialogOpen(true)
  }

  async function submitAuth() {
    const state = auth.data?.state
    const kind =
      state === 'waiting_phone' ? 'phone' : state === 'waiting_code' ? 'code' : 'password'
    try {
      await request(`/api/v1/telegram-auth/${kind}`, json('POST', { value: authValue }))
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
            <strong className="w-full truncate text-left text-xs text-slate-700">
              {active?.label ?? 'Telegram'}
            </strong>
            <small className="w-full truncate text-left text-xs text-slate-400">
              {active ? accountSubtitle(active, t) : t('accounts.loading')}
            </small>
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
                  <strong className="block truncate text-xs text-slate-700">{account.label}</strong>
                  <small className="block truncate text-xs text-slate-400">
                    {accountSubtitle(account, t)}
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
            <DropdownMenu.Item
              className="flex h-9 items-center gap-2 rounded px-2 text-xs text-slate-600 outline-none data-[highlighted]:bg-slate-50"
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
                <strong className="block truncate text-[13px] text-slate-700">
                  {account.label}
                </strong>
                <p className="mt-0.5 truncate text-[13px] text-slate-400">
                  {accountSubtitle(account, t)}
                </p>
              </div>
              <div className="flex gap-1.5">
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
                <IconButton
                  label={t('accounts.deleteNamed', { name: account.label })}
                  icon={Trash2}
                  className="hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
                  onClick={() => setDeletingAccount(account)}
                  disabled={deleting.isPending || accounts.data.length === 1}
                />
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
            <div className="grid grid-cols-[1fr_auto] items-end gap-2 max-sm:grid-cols-1">
              <label className={fieldClass}>
                <span>{t('accounts.name')}</span>
                <input
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder={t('accounts.namePlaceholder')}
                  maxLength={100}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && label.trim()) creating.mutate()
                  }}
                />
              </label>
              <Button
                icon={Plus}
                onClick={() => creating.mutate()}
                disabled={!label.trim() || creating.isPending}
              >
                {t(creating.isPending ? 'accounts.creating' : 'accounts.add')}
              </Button>
            </div>
          </section>
        )}

        {auth.data?.state === 'success' ? (
          <p className="mt-4 rounded-[5px] border border-emerald-100 bg-emerald-50 p-2.5 text-[13px] text-emerald-700">
            {t('accounts.authSuccess')}
          </p>
        ) : null}
        {flowError || auth.data?.error || switching.error || startingAuth.error ? (
          <p className="mt-4 rounded-[5px] border border-rose-100 bg-rose-50 p-2.5 text-[13px] text-rose-700">
            {flowError || auth.data?.error || messageFrom(switching.error || startingAuth.error)}
          </p>
        ) : null}
      </Dialog>
      <ConfirmDialog
        open={deletingAccount !== null}
        onOpenChange={(next) => {
          if (!next) setDeletingAccount(null)
        }}
        title={t('accounts.deleteTitle')}
        description={t('accounts.deleteConfirm', {
          name: deletingAccount?.label ?? '',
        })}
        confirmLabel={t('accounts.delete')}
        pending={deleting.isPending}
        onConfirm={() => {
          if (deletingAccount) deleting.mutate(deletingAccount.id)
        }}
      />
    </>
  )
}
