import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
import { json, request } from '../api/client'
import type { TelegramAccount, TelegramAuth } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'
import { AccountAvatar } from './AccountAvatar'
import { clearAuthenticatedImages } from './AuthenticatedImage'
import { Button, Dialog, fieldClass, IconButton } from './ui'

function accountSubtitle(account: TelegramAccount): string {
  if (account.username) return `@${account.username}`
  if (account.connected) return '当前已连接'
  if (account.authenticated) return '会话已保存'
  return '等待认证'
}

export function AccountSwitcher({ onLogout }: { onLogout: () => void }) {
  const client = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
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

  const waitingLabels: Record<string, string> = {
    waiting_phone: '手机号码（含国家区号）',
    waiting_code: 'Telegram 登录验证码',
    waiting_password: '两步验证密码',
  }
  const waitingLabel = waitingLabels[auth.data?.state ?? '']
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

  async function deleteAccount(account: TelegramAccount) {
    if (!window.confirm(`确定删除 Telegram 账号“${account.label}”及其本地会话？`)) return
    deleting.mutate(account.id)
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
            className="size-7.5 bg-blue-50"
            fallbackClassName="text-[9px] text-blue-700"
          />
          <span className="flex min-w-20 flex-1 flex-col items-start overflow-hidden max-md:hidden">
            <strong className="w-full truncate text-left text-[10px] text-slate-700">
              {active?.label ?? 'Telegram'}
            </strong>
            <small className="w-full truncate text-left text-[8px] text-slate-400">
              {active ? accountSubtitle(active) : '正在读取账号'}
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
            <DropdownMenu.Label className="px-2 py-1.5 text-[8px] font-bold text-slate-400 uppercase">
              Telegram 账号
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
                  className="size-7.5"
                  fallbackClassName="text-[8px]"
                />
                <span className="min-w-0">
                  <strong className="block truncate text-[10px] text-slate-700">
                    {account.label}
                  </strong>
                  <small className="block truncate text-[8px] text-slate-400">
                    {accountSubtitle(account)}
                  </small>
                </span>
                {account.active ? <Check size={14} className="text-blue-600" /> : null}
              </DropdownMenu.Item>
            ))}
            <DropdownMenu.Separator className="my-1 h-px bg-slate-100" />
            <DropdownMenu.Item
              className="flex h-9 items-center gap-2 rounded px-2 text-[10px] text-blue-700 outline-none data-[highlighted]:bg-blue-50"
              onSelect={openAccountDialog}
            >
              <Plus size={15} />
              添加或管理账号
            </DropdownMenu.Item>
            <DropdownMenu.Item
              className="flex h-9 items-center gap-2 rounded px-2 text-[10px] text-slate-600 outline-none data-[highlighted]:bg-slate-50"
              onSelect={onLogout}
            >
              <LogOut size={15} />
              退出控制台
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <Dialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        title="Telegram 账号"
        description="账号会话只保存在本机；同一时间仅一个账号连接转发节点。"
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
                fallbackClassName="text-[10px]"
              />
              <div className="min-w-0">
                <strong className="block truncate text-[11px] text-slate-700">
                  {account.label}
                </strong>
                <p className="mt-0.5 truncate text-[9px] text-slate-400">
                  {accountSubtitle(account)}
                </p>
              </div>
              <div className="flex gap-1.5">
                {!account.active ? (
                  <IconButton
                    label={`切换到 ${account.label}`}
                    icon={Radio}
                    onClick={() => switching.mutate(account.id)}
                    disabled={switching.isPending}
                  />
                ) : null}
                {account.active && !account.authenticated ? (
                  <IconButton
                    label={`认证 ${account.label}`}
                    icon={Smartphone}
                    onClick={() => startingAuth.mutate()}
                    disabled={startingAuth.isPending || authenticating}
                  />
                ) : null}
                <IconButton
                  label={`删除 ${account.label}`}
                  icon={Trash2}
                  className="hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600"
                  onClick={() => void deleteAccount(account)}
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
                <strong className="text-[11px] text-slate-700">正在认证 {active?.label}</strong>
                <p className="mt-0.5 text-[9px] text-slate-500">
                  {waitingLabel ?? '正在建立安全连接，请稍候'}
                </p>
              </div>
            </div>
            {waitingLabel ? (
              <div className="grid grid-cols-[1fr_auto] items-end gap-2 max-sm:grid-cols-1">
                <label className={fieldClass}>
                  <span>{waitingLabel}</span>
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
                  提交
                </Button>
              </div>
            ) : null}
          </section>
        ) : (
          <section>
            <div className="mb-3 flex items-center gap-2">
              <UserRound size={17} className="text-blue-600" />
              <strong className="text-[11px] text-slate-700">添加新账号</strong>
            </div>
            <div className="grid grid-cols-[1fr_auto] items-end gap-2 max-sm:grid-cols-1">
              <label className={fieldClass}>
                <span>账号名称</span>
                <input
                  value={label}
                  onChange={(event) => setLabel(event.target.value)}
                  placeholder="例如：工作账号"
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
                {creating.isPending ? '正在创建' : '添加账号'}
              </Button>
            </div>
          </section>
        )}

        {auth.data?.state === 'success' ? (
          <p className="mt-4 rounded-[5px] border border-emerald-100 bg-emerald-50 p-2.5 text-[9px] text-emerald-700">
            当前账号认证成功，可在右上角随时切换。
          </p>
        ) : null}
        {flowError || auth.data?.error || switching.error || startingAuth.error ? (
          <p className="mt-4 rounded-[5px] border border-rose-100 bg-rose-50 p-2.5 text-[9px] text-rose-700">
            {flowError || auth.data?.error || messageFrom(switching.error || startingAuth.error)}
          </p>
        ) : null}
      </Dialog>
    </>
  )
}
