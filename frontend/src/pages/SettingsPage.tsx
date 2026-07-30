import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, KeyRound, Save, Settings, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { json, request } from '../api/client'
import { downloadFile } from '../api/downloads'
import {
  Badge,
  Button,
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
  const client = useQueryClient()
  const [rawConfig, setRawConfig] = useState('')
  const [authValue, setAuthValue] = useState('')
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
  const waitingLabels: Record<string, string> = {
    waiting_phone: '手机号码',
    waiting_code: '登录验证码',
    waiting_password: '两步验证密码',
  }
  const waitingLabel = waitingLabels[auth.data?.state ?? '']
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
  async function clearSession() {
    if (!window.confirm('确定清除 Telegram 会话？运行中的节点会先停止。')) return
    await request('/api/v1/telegram-auth/session', json('DELETE'))
    await auth.refetch()
  }
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
        eyebrow="LOCAL CONFIGURATION"
        title="设置"
        description="管理 Telegram 会话、配置备份与高级运行参数。"
      />
      <Tabs defaultValue="session">
        <TabsList className={tabsListClass}>
          <TabsTrigger value="session">
            <KeyRound size={16} />
            Telegram 会话
          </TabsTrigger>
          <TabsTrigger value="config">
            <Settings size={16} />
            高级配置
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
              title="Telegram 会话"
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
                  <strong className="text-[11px] text-slate-700">
                    {authSuccess ? '会话认证成功' : '需要完成会话认证'}
                  </strong>
                  <p className="mt-1 text-[9px] leading-4 text-slate-500">
                    {auth.data?.user_info ||
                      auth.data?.error ||
                      `当前模式：${config.data?.runtime.session_type ?? '-'}`}
                  </p>
                </div>
              </div>
              {waitingLabel ? (
                <div className="mt-4 grid grid-cols-[1fr_auto] items-end gap-2">
                  <label className={fieldClass}>
                    <span>{waitingLabel}</span>
                    <input
                      value={authValue}
                      onChange={(event) => setAuthValue(event.target.value)}
                      type={auth.data?.state === 'waiting_password' ? 'password' : 'text'}
                      autoFocus
                    />
                  </label>
                  <Button onClick={() => void submitAuth()}>提交</Button>
                </div>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button icon={KeyRound} onClick={() => void startAuth()}>
                  开始认证
                </Button>
                <Button variant="danger" icon={Trash2} onClick={() => void clearSession()}>
                  清除会话
                </Button>
              </div>
            </Panel>
            <Panel title="配置备份" meta={<span>YAML · 最大 1 MiB</span>}>
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
                  <strong className="text-[11px] text-slate-700">导出或恢复规则配置</strong>
                  <p className="mt-1 text-[9px] leading-4 text-slate-500">
                    下载当前 YAML 配置，或上传经过验证的备份文件。
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
                  导出 YAML
                </Button>
                <Button
                  variant="secondary"
                  icon={Upload}
                  onClick={() => importRef.current?.click()}
                >
                  导入 YAML
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
          <Panel title="高级配置" meta={<span>JSON 编辑 · 保存为 YAML</span>}>
            <p className="text-[10px] leading-4 text-slate-500">
              保存前会由后端验证结构。无效配置不会替换当前运行配置。
            </p>
            <textarea
              className={cn(
                'min-h-127.5 w-full resize-y rounded-[5px] border border-slate-700',
                'bg-slate-900 p-3 font-mono text-[10px] leading-4 text-blue-100 outline-none',
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
                  'text-[9px] text-rose-700',
                )}
              >
                {messageFrom(save.error)}
              </p>
            ) : null}
            <div className="mt-5 flex justify-end border-t border-slate-100 pt-4">
              <Button icon={Save} onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending ? '正在保存...' : '保存配置'}
              </Button>
            </div>
          </Panel>
        </TabsContent>
      </Tabs>
    </>
  )
}
