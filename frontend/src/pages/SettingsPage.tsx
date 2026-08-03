import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Braces,
  Download,
  ExternalLink,
  Github,
  Info,
  KeyRound,
  RefreshCw,
  Save,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
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
  Dialog,
  fieldClass,
  PasswordInput,
  PageHeader,
  Panel,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  tabsListClass,
} from '../components/ui'
import { ConfigJsonEditor, ConfigTreeForm } from '../components/ConfigTreeForm'
import type { AppConfig, MetaInfo, TelegramAccount, TelegramAuth, UpdateInfo } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'

export function SettingsPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const accountId = useAccountScope()
  const [configTree, setConfigTree] = useState<Record<string, unknown> | null>(null)
  const [configMode, setConfigMode] = useState<'form' | 'json'>('form')
  const [authValue, setAuthValue] = useState('')
  const [botTokenInput, setBotTokenInput] = useState('')
  const [tokenDialogOpen, setTokenDialogOpen] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)
  const loadedConfigRef = useRef<string | null>(null)
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
    if (config.data && typeof config.data.config === 'object' && config.data.config !== null) {
      const serialized = `${accountId}:${JSON.stringify(config.data.config)}`
      if (loadedConfigRef.current === serialized) return
      loadedConfigRef.current = serialized
      setConfigTree(config.data.config)
    }
  }, [accountId, config.data])
  const saveConfig = useMutation({
    mutationFn: () => {
      if (!configTree) throw new Error('config-not-loaded')
      return accountRequest(accountId, '/api/v1/config', json('PUT', { config: configTree }))
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: ['config', accountId] }),
  })
  const updatingBotToken = useMutation({
    mutationFn: () =>
      accountRequest<{ code: string }>(
        accountId,
        `/api/v1/telegram-accounts/${accountId}/bot-token`,
        json('PUT', { bot_token: botTokenInput }),
      ),
    onSuccess: async () => {
      setBotTokenInput('')
      setTokenDialogOpen(false)
      await Promise.all([
        accounts.refetch(),
        client.invalidateQueries({ queryKey: ['telegram-auth'] }),
        client.invalidateQueries({ queryKey: ['bot-status'] }),
      ])
    },
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
  const botConnected = activeAccount?.kind === 'bot' && Boolean(activeAccount.connected)
  const botSessionLabel =
    activeAccount?.kind === 'bot'
      ? botConnected
        ? 'settings.botConnected'
        : 'settings.botDisconnected'
      : authSuccess
        ? 'settings.authSuccess'
        : 'settings.authRequired'
  const botSessionMeta =
    activeAccount?.kind === 'bot'
      ? [
          activeAccount.label,
          activeAccount.display_name && activeAccount.display_name !== activeAccount.label
            ? activeAccount.display_name
            : null,
          activeAccount.username ? `@${activeAccount.username}` : null,
          activeAccount.telegram_user_id ? `[ID: ${activeAccount.telegram_user_id}]` : null,
        ]
          .filter(Boolean)
          .join(' ')
      : null
  const authStateLabel =
    activeAccount?.kind === 'bot'
      ? botConnected
        ? 'settings.authState.success'
        : auth.data?.state === 'error'
          ? 'settings.authState.error'
          : 'settings.authState.notRequired'
      : authSuccess && (!auth.data?.state || ['idle', 'success'].includes(auth.data.state))
        ? 'settings.authState.success'
        : (authStateLabels[auth.data?.state as keyof typeof authStateLabels] ??
          'settings.authState.unknown')
  const configDirty = Boolean(
    configTree && config.data && JSON.stringify(configTree) !== JSON.stringify(config.data.config),
  )

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
                <Badge
                  tone={
                    (activeAccount?.kind === 'bot' ? botConnected : authSuccess)
                      ? 'green'
                      : auth.data?.state === 'error'
                        ? 'red'
                        : 'gray'
                  }
                >
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
                  <strong className="text-[13px] text-slate-700">{t(botSessionLabel)}</strong>
                  <p className="mt-1 text-[13px] leading-4 text-slate-500">
                    {auth.data?.user_info ||
                      auth.data?.error ||
                      botSessionMeta ||
                      t('settings.currentMode', {
                        mode: activeAccount?.kind ?? '-',
                      })}
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
                {activeAccount?.kind === 'bot' ? (
                  <Button icon={KeyRound} onClick={() => setTokenDialogOpen(true)}>
                    {t('settings.updateBotToken')}
                  </Button>
                ) : (
                  <>
                    {!authSuccess ? (
                      <Button icon={KeyRound} onClick={() => void startAuth()}>
                        {t('settings.startAuth')}
                      </Button>
                    ) : null}
                    {authSuccess ? (
                      <Button
                        variant="danger"
                        icon={Trash2}
                        onClick={() => void handleClearSession()}
                      >
                        {t('settings.clearSession')}
                      </Button>
                    ) : null}
                  </>
                )}
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
            <Panel title={t('settings.backup')}>
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
          <Panel title={t('settings.advanced')}>
            <Tabs
              value={configMode}
              onValueChange={(value) => setConfigMode(value as 'form' | 'json')}
            >
              <TabsList className={tabsListClass}>
                <TabsTrigger value="form">
                  <SlidersHorizontal size={15} />
                  {t('settings.configModeForm')}
                </TabsTrigger>
                <TabsTrigger value="json">
                  <Braces size={15} />
                  {t('settings.configModeJson')}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="form" className="mt-4 outline-none">
                {configTree && config.data?.schema ? (
                  <ConfigTreeForm
                    value={configTree}
                    schema={config.data.schema}
                    onChange={setConfigTree}
                  />
                ) : (
                  <p className="text-xs leading-4 text-slate-500">{t('common.loading')}</p>
                )}
              </TabsContent>
              <TabsContent value="json" className="mt-4 outline-none">
                {configTree ? (
                  <ConfigJsonEditor value={configTree} onChange={setConfigTree} />
                ) : (
                  <p className="text-xs leading-4 text-slate-500">{t('common.loading')}</p>
                )}
              </TabsContent>
            </Tabs>
            {saveConfig.error ? (
              <p
                className={cn(
                  'mt-4 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                  'text-[13px] text-rose-700',
                )}
              >
                {messageFrom(saveConfig.error)}
              </p>
            ) : null}
            <div className="mt-5 flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <span className="text-xs text-slate-400">
                {t(configDirty ? 'settings.configUnsaved' : 'settings.configSynced')}
              </span>
              <Button
                icon={Save}
                onClick={() => saveConfig.mutate()}
                disabled={saveConfig.isPending || !configTree || !configDirty}
              >
                {t(saveConfig.isPending ? 'settings.saving' : 'settings.save')}
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
      <Dialog
        open={tokenDialogOpen}
        onOpenChange={setTokenDialogOpen}
        title={t('settings.updateBotToken')}
        description={t('settings.updateBotTokenDetail')}
      >
        <div className="space-y-4">
          <label className={fieldClass}>
            <span>{t('accounts.botToken')}</span>
            <PasswordInput
              value={botTokenInput}
              onChange={setBotTokenInput}
              placeholder={t('accounts.botTokenPlaceholder')}
              autoComplete="off"
              autoFocus
              onKeyDown={(event) => {
                if (event.key === 'Enter' && botTokenInput.trim()) updatingBotToken.mutate()
              }}
            />
          </label>
          {updatingBotToken.error ? (
            <p
              className={cn(
                'rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[13px] text-rose-700',
              )}
            >
              {messageFrom(updatingBotToken.error)}
            </p>
          ) : null}
          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="secondary" onClick={() => setTokenDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => updatingBotToken.mutate()}
              disabled={!botTokenInput.trim() || updatingBotToken.isPending}
            >
              {t(updatingBotToken.isPending ? 'settings.saving' : 'common.ok')}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  )
}
