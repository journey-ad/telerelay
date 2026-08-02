import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Download,
  ExternalLink,
  Github,
  Info,
  KeyRound,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  Trash2,
  Upload,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { accountRequest, json, request } from '../api/client'
import { downloadFile } from '../api/downloads'
import { useAccountScope } from '../hooks/useAccountScope'
import {
  Badge,
  Button,
  confirm,
  fieldClass,
  PageHeader,
  Panel,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  tabsListClass,
} from '../components/ui'
import type { AppConfig, MetaInfo, TelegramAccount, TelegramAuth, UpdateInfo } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'

export function SettingsPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const accountId = useAccountScope()
  const [rawConfig, setRawConfig] = useState('')
  const [authValue, setAuthValue] = useState('')
  const importRef = useRef<HTMLInputElement>(null)
  const config = useQuery({
    queryKey: ['config', accountId],
    queryFn: () => accountRequest<AppConfig>(accountId, '/api/v1/config'),
  })
  const auth = useQuery({
    queryKey: ['telegram-auth', accountId],
    queryFn: () => accountRequest<TelegramAuth>(accountId, '/api/v1/telegram-auth'),
    refetchInterval: (query) =>
      ['connecting', 'waiting_phone', 'waiting_code', 'waiting_password'].includes(
        query.state.data?.state ?? '',
      )
        ? 1000
        : false,
  })
  const accounts = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    enabled: Boolean(auth.data && auth.data.state !== 'not_required'),
  })
  const activeAccount = accounts.data?.find((account) => account.id === accountId)
  const deleteAccount = useMutation({
    mutationFn: (deletedAccountId: string) =>
      request(`/api/v1/telegram-accounts/${deletedAccountId}`, json('DELETE')),
    onSuccess: async (_, deletedAccountId) => {
      client.setQueryData<TelegramAccount[]>(['telegram-accounts'], (current) => {
        const remaining = (current ?? []).filter((account) => account.id !== deletedAccountId)
        if (remaining.some((account) => account.active) || !remaining[0]) return remaining
        return remaining.map((account, index) => ({ ...account, active: index === 0 }))
      })
      client.removeQueries({
        predicate: (query) => query.queryKey[1] === deletedAccountId,
      })
      await Promise.all([
        client.invalidateQueries({ queryKey: ['telegram-accounts'] }),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
      ])
    },
  })
  const meta = useQuery({
    queryKey: ['meta'],
    queryFn: () => request<MetaInfo>('/api/v1/meta'),
  })
  const checkUpdate = useMutation({
    mutationFn: () => request<UpdateInfo>('/api/v1/update-check'),
  })
  useEffect(() => {
    if (config.data) setRawConfig(JSON.stringify(config.data.config, null, 2))
  }, [config.data])
  const save = useMutation({
    mutationFn: () =>
      accountRequest(accountId, '/api/v1/config', json('PUT', { config: JSON.parse(rawConfig) })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['config', accountId] }),
  })
  const waitingLabels = {
    waiting_phone: 'settings.phone',
    waiting_code: 'settings.code',
    waiting_password: 'settings.password',
  } as const
  const waitingLabel = waitingLabels[auth.data?.state as keyof typeof waitingLabels]
  async function startAuth() {
    await accountRequest(accountId, '/api/v1/telegram-auth/start', json('POST'))
    await auth.refetch()
  }
  async function submitAuth() {
    const state = auth.data?.state
    const kind =
      state === 'waiting_phone' ? 'phone' : state === 'waiting_code' ? 'code' : 'password'
    await accountRequest(
      accountId,
      `/api/v1/telegram-auth/${kind}`,
      json('POST', { value: authValue }),
    )
    setAuthValue('')
    await auth.refetch()
  }
  const clearSession = useMutation({
    mutationFn: () => accountRequest(accountId, '/api/v1/telegram-auth/session', json('DELETE')),
    onSuccess: async () => {
      await auth.refetch()
    },
  })
  async function handleClearSession() {
    await confirm({
      title: t('settings.clearTitle'),
      description: t('settings.clearDescription'),
      confirmLabel: t('settings.clearSession'),
      onConfirm: () => clearSession.mutateAsync(),
    })
  }
  async function handleDeleteAccount() {
    if (!activeAccount) return
    await confirm({
      title: t('accounts.deleteTitle'),
      description: t('accounts.deleteConfirm', { name: activeAccount.label }),
      confirmLabel: t('accounts.delete'),
      onConfirm: () => deleteAccount.mutateAsync(activeAccount.id),
    })
  }
  async function importConfig(file?: File) {
    if (!file) return
    const data = new FormData()
    data.append('file', file)
    await accountRequest(accountId, '/api/v1/config/import', { method: 'POST', body: data })
    await config.refetch()
  }
  const authStateLabels = {
    idle: 'settings.authState.idle',
    connecting: 'settings.authState.connecting',
    waiting_phone: 'settings.authState.waitingPhone',
    waiting_code: 'settings.authState.waitingCode',
    waiting_password: 'settings.authState.waitingPassword',
    success: 'settings.authState.success',
    error: 'settings.authState.error',
    not_required: 'settings.authState.notRequired',
  } as const
  const authSuccess = Boolean(
    activeAccount?.authenticated || auth.data?.authenticated || auth.data?.state === 'success',
  )
  const authStateLabel =
    authSuccess && (!auth.data?.state || ['idle', 'success'].includes(auth.data.state))
      ? 'settings.authState.success'
      : (authStateLabels[auth.data?.state as keyof typeof authStateLabels] ??
        'settings.authState.unknown')

  return (
    <>
      <PageHeader
        eyebrow={t('settings.eyebrow')}
        title={t('settings.title')}
        description={t('settings.description')}
      />
      <Tabs defaultValue="session">
        <TabsList className={tabsListClass}>
          <TabsTrigger value="session">
            <KeyRound size={16} />
            {t('settings.telegramSession')}
          </TabsTrigger>
          <TabsTrigger value="config">
            <Settings size={16} />
            {t('settings.advanced')}
          </TabsTrigger>
          <TabsTrigger value="about">
            <Info size={16} />
            {t('settings.about')}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="session" className="outline-none">
          <div
            className={cn(
              'grid grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)] gap-3',
              'max-lg:grid-cols-1',
            )}
          >
            <Panel
              title={t('settings.telegramSession')}
              meta={
                <Badge tone={authSuccess ? 'green' : auth.data?.state === 'error' ? 'red' : 'gray'}>
                  {t(authStateLabel)}
                </Badge>
              }
            >
              <div
                className={cn(
                  'flex items-center gap-3 rounded-[5px] border border-slate-100',
                  'bg-slate-50 p-3',
                )}
              >
                <span
                  className={cn(
                    'grid size-11 shrink-0 place-items-center rounded-[5px] border',
                    authSuccess
                      ? 'border-emerald-100 bg-emerald-50 text-emerald-600'
                      : 'border-slate-200 bg-white text-slate-400',
                  )}
                >
                  <ShieldCheck size={24} />
                </span>
                <div className="min-w-0">
                  <strong className="text-[13px] text-slate-700">
                    {t(authSuccess ? 'settings.authSuccess' : 'settings.authRequired')}
                  </strong>
                  <p className="mt-1 text-[13px] leading-4 text-slate-500">
                    {auth.data?.user_info ||
                      auth.data?.error ||
                      t('settings.currentMode', { mode: config.data?.runtime.session_type ?? '-' })}
                  </p>
                </div>
              </div>
              {waitingLabel ? (
                <div className="mt-4 grid grid-cols-[1fr_auto] items-end gap-2">
                  <label className={fieldClass}>
                    <span>{t(waitingLabel)}</span>
                    <input
                      value={authValue}
                      onChange={(event) => setAuthValue(event.target.value)}
                      type={auth.data?.state === 'waiting_password' ? 'password' : 'text'}
                      autoFocus
                    />
                  </label>
                  <Button onClick={() => void submitAuth()}>{t('common.submit')}</Button>
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button icon={KeyRound} onClick={() => void startAuth()}>
                  {t('settings.startAuth')}
                </Button>
                <Button variant="danger" icon={Trash2} onClick={() => void handleClearSession()}>
                  {t('settings.clearSession')}
                </Button>
                {activeAccount ? (
                  <Button variant="danger" icon={Trash2} onClick={() => void handleDeleteAccount()}>
                    {t('accounts.delete')}
                  </Button>
                ) : null}
              </div>
              {deleteAccount.error ? (
                <p
                  className={cn(
                    'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                    'text-[13px] text-rose-700',
                  )}
                >
                  {messageFrom(deleteAccount.error)}
                </p>
              ) : null}
            </Panel>
            <Panel title={t('settings.backup')} meta={<span>{t('settings.backupMeta')}</span>}>
              <div
                className={cn(
                  'flex items-center gap-3 rounded-[5px] border border-slate-100',
                  'bg-slate-50 p-3',
                )}
              >
                <span
                  className={cn(
                    'grid size-11 shrink-0 place-items-center rounded-[5px] border',
                    'border-slate-200 bg-white text-slate-400',
                  )}
                >
                  <Download size={22} />
                </span>
                <div>
                  <strong className="text-[13px] text-slate-700">
                    {t('settings.backupTitle')}
                  </strong>
                  <p className="mt-1 text-[13px] leading-4 text-slate-500">
                    {t('settings.backupDetail')}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  icon={Download}
                  onClick={() =>
                    void downloadFile('/api/v1/config/export', 'telerelay-config.yaml', accountId)
                  }
                >
                  {t('settings.exportYaml')}
                </Button>
                <Button
                  variant="secondary"
                  icon={Upload}
                  onClick={() => importRef.current?.click()}
                >
                  {t('settings.importYaml')}
                </Button>
                <input
                  ref={importRef}
                  type="file"
                  accept=".yaml,.yml"
                  hidden
                  onChange={(event) => void importConfig(event.target.files?.[0])}
                />
              </div>
            </Panel>
          </div>
        </TabsContent>
        <TabsContent value="config" className="outline-none">
          <Panel title={t('settings.advanced')} meta={<span>{t('settings.advancedMeta')}</span>}>
            <p className="text-xs leading-4 text-slate-500">{t('settings.advancedDetail')}</p>
            <textarea
              className={cn(
                'min-h-127.5 w-full resize-y rounded-[5px] border border-slate-700',
                'bg-slate-900 p-3 font-mono text-xs leading-4 text-blue-100 outline-none',
                'focus:border-blue-500 focus:ring-3 focus:ring-blue-500/10',
              )}
              value={rawConfig}
              onChange={(event) => setRawConfig(event.target.value)}
              spellCheck={false}
              rows={25}
            />
            {save.error ? (
              <p
                className={cn(
                  'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                  'text-[13px] text-rose-700',
                )}
              >
                {messageFrom(save.error)}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end border-t border-slate-100 pt-4">
              <Button icon={Save} onClick={() => save.mutate()} disabled={save.isPending}>
                {t(save.isPending ? 'settings.saving' : 'settings.save')}
              </Button>
            </div>
          </Panel>
        </TabsContent>
        <TabsContent value="about" className="outline-none">
          <Panel title={t('settings.about')}>
            <div
              className={cn(
                'flex items-center gap-3 rounded-[5px] border border-slate-100',
                'bg-slate-50 p-3',
              )}
            >
              <span
                className={cn(
                  'grid size-11 shrink-0 place-items-center rounded-[5px] border',
                  'border-blue-100 bg-blue-50 text-blue-600',
                )}
              >
                <Github size={24} />
              </span>
              <div className="min-w-0">
                <strong className="text-[13px] text-slate-700">TeleRelay</strong>
                <p className="mt-1 text-[13px] leading-4 text-slate-500">
                  {t('settings.versionLabel', { version: meta.data?.version ?? '-' })}
                  {meta.data?.commit ? ` (${meta.data.commit})` : ''}
                </p>
              </div>
            </div>
            <div className="mt-4">
              <a
                href={meta.data?.repository}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-blue-600 hover:text-blue-700 hover:underline"
              >
                {t('settings.repository')}
                <ExternalLink size={14} />
              </a>
            </div>
            <div className="mt-5 border-t border-slate-100 pt-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <strong className="text-[13px] text-slate-700">
                    {t('settings.updateCheck')}
                  </strong>
                  <p className="mt-1 text-[13px] leading-4 text-slate-500">
                    {t('settings.updateCheckDetail')}
                  </p>
                </div>
                <Button
                  icon={RefreshCw}
                  onClick={() => checkUpdate.mutate()}
                  disabled={checkUpdate.isPending}
                >
                  {t(checkUpdate.isPending ? 'settings.checking' : 'settings.checkUpdate')}
                </Button>
              </div>
              {checkUpdate.isError ? (
                <p
                  className={cn(
                    'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                    'text-[13px] text-rose-700',
                  )}
                >
                  {t('settings.checkFailed')}
                </p>
              ) : checkUpdate.data ? (
                checkUpdate.data.error ? (
                  <p
                    className={cn(
                      'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                      'text-[13px] text-rose-700',
                    )}
                  >
                    {t('settings.checkFailed')}: {checkUpdate.data.error}
                  </p>
                ) : checkUpdate.data.update_available ? (
                  <div
                    className={cn(
                      'mt-3 flex flex-wrap items-center justify-between gap-3 rounded-[5px]',
                      'border border-amber-100 bg-amber-50 p-3 text-[13px] text-amber-800',
                    )}
                  >
                    <span>
                      {t('settings.updateAvailable', {
                        version:
                          checkUpdate.data.latest_version ?? checkUpdate.data.latest_tag ?? '',
                      })}
                    </span>
                    {checkUpdate.data.release_url ? (
                      <a
                        href={checkUpdate.data.release_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 font-semibold text-amber-700 hover:underline"
                      >
                        {t('settings.viewRelease')}
                        <ExternalLink size={13} />
                      </a>
                    ) : null}
                  </div>
                ) : (
                  <p
                    className={cn(
                      'mt-3 rounded-[5px] border border-emerald-100 bg-emerald-50 p-2',
                      'text-[13px] text-emerald-700',
                    )}
                  >
                    {t('settings.upToDate')}
                  </p>
                )
              ) : null}
            </div>
          </Panel>
        </TabsContent>
      </Tabs>
    </>
  )
}
