import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, KeyRound, Save, Settings, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { json, request } from '../api/client'
import { downloadFile } from '../api/downloads'
import {
  Badge,
  Button,
  ConfirmDialog,
  fieldClass,
  PageHeader,
  Panel,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  tabsListClass,
} from '../components/ui'
import type { AppConfig, TelegramAuth } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'

export function SettingsPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [rawConfig, setRawConfig] = useState('')
  const [authValue, setAuthValue] = useState('')
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)
  const config = useQuery({
    queryKey: ['config'],
    queryFn: () => request<AppConfig>('/api/v1/config'),
  })
  const auth = useQuery({
    queryKey: ['telegram-auth'],
    queryFn: () => request<TelegramAuth>('/api/v1/telegram-auth'),
    refetchInterval: 1800,
  })
  useEffect(() => {
    if (config.data) setRawConfig(JSON.stringify(config.data.config, null, 2))
  }, [config.data])
  const save = useMutation({
    mutationFn: () => request('/api/v1/config', json('PUT', { config: JSON.parse(rawConfig) })),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['config'] }),
  })
  const waitingLabels = {
    waiting_phone: 'settings.phone',
    waiting_code: 'settings.code',
    waiting_password: 'settings.password',
  } as const
  const waitingLabel = waitingLabels[auth.data?.state as keyof typeof waitingLabels]
  async function startAuth() {
    await request('/api/v1/telegram-auth/start', json('POST'))
    await auth.refetch()
  }
  async function submitAuth() {
    const state = auth.data?.state
    const kind =
      state === 'waiting_phone' ? 'phone' : state === 'waiting_code' ? 'code' : 'password'
    await request(`/api/v1/telegram-auth/${kind}`, json('POST', { value: authValue }))
    setAuthValue('')
    await auth.refetch()
  }
  const clearSession = useMutation({
    mutationFn: () => request('/api/v1/telegram-auth/session', json('DELETE')),
    onSuccess: async () => {
      setClearConfirmOpen(false)
      await auth.refetch()
    },
  })
  async function importConfig(file?: File) {
    if (!file) return
    const data = new FormData()
    data.append('file', file)
    await request('/api/v1/config/import', { method: 'POST', body: data })
    await config.refetch()
  }
  const authSuccess = auth.data?.state === 'success'

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
                <Badge tone={authSuccess ? 'green' : 'gray'}>{auth.data?.state ?? 'unknown'}</Badge>
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
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
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
                <Button variant="danger" icon={Trash2} onClick={() => setClearConfirmOpen(true)}>
                  {t('settings.clearSession')}
                </Button>
              </div>
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
                  <p className="mt-1 text-[11px] leading-4 text-slate-500">
                    {t('settings.backupDetail')}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  icon={Download}
                  onClick={() =>
                    void downloadFile('/api/v1/config/export', 'telerelay-config.yaml')
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
            <p className="text-[12px] leading-4 text-slate-500">{t('settings.advancedDetail')}</p>
            <textarea
              className={cn(
                'min-h-127.5 w-full resize-y rounded-[5px] border border-slate-700',
                'bg-slate-900 p-3 font-mono text-[12px] leading-4 text-blue-100 outline-none',
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
                  'text-[11px] text-rose-700',
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
      </Tabs>
      <ConfirmDialog
        open={clearConfirmOpen}
        onOpenChange={setClearConfirmOpen}
        title={t('settings.clearTitle')}
        description={t('settings.clearDescription')}
        confirmLabel={t('settings.clearSession')}
        pending={clearSession.isPending}
        onConfirm={() => clearSession.mutate()}
      />
    </>
  )
}
