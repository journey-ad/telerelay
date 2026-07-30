import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Braces, Edit3, Plus, Route, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { json, request } from '../api/client'
import { ChatTagInput } from '../components/ChatTagInput'
import { RegexField, useRegexValidation } from '../components/RegexField'
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  fieldClass,
  IconButton,
  PageHeader,
  Select,
  Switch,
  tableClass,
  tableWrapClass,
} from '../components/ui'
import type { ForwardingRule } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'
import { lines } from '../utils/parse'

const blankRule = (): ForwardingRule => ({
  name: '',
  enabled: true,
  source_chats: [],
  target_chats: [],
  filters: {
    mode: 'whitelist',
    keywords: [],
    regex_patterns: [],
    media_types: [],
    max_file_size: 0,
    min_file_size: 0,
  },
  ignore: { user_ids: [], keywords: [] },
  forwarding: {
    preserve_format: true,
    add_source_info: true,
    delay: 0.5,
    force_forward: false,
    hide_sender: false,
    deduplicate: false,
    deduplicate_window: 3600,
  },
})

export function RulesPage() {
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<ForwardingRule>(blankRule())
  const [text, setText] = useState({
    keywords: '',
    regex: '',
    ignoredUsers: '',
    ignoredKeywords: '',
  })
  const regexValidation = useRegexValidation()
  const rulesQuery = useQuery({
    queryKey: ['rules'],
    queryFn: () => request<ForwardingRule[]>('/api/v1/rules'),
  })
  const rules = useMemo(
    () =>
      (rulesQuery.data ?? [])
        .map((rule, index) => ({ rule, index }))
        .filter(({ rule }) => rule.name.toLowerCase().includes(search.toLowerCase())),
    [rulesQuery.data, search],
  )

  function createRule() {
    setEditing(null)
    setForm(blankRule())
    setText({
      keywords: '',
      regex: '',
      ignoredUsers: '',
      ignoredKeywords: '',
    })
    regexValidation.reset()
    setOpen(true)
  }
  function editRule(index: number) {
    const value = structuredClone(rulesQuery.data?.[index] ?? blankRule())
    setEditing(index)
    setForm(value)
    setText({
      keywords: value.filters.keywords.join('\n'),
      regex: value.filters.regex_patterns.join('\n'),
      ignoredUsers: value.ignore.user_ids.join('\n'),
      ignoredKeywords: value.ignore.keywords.join('\n'),
    })
    regexValidation.reset()
    setOpen(true)
  }
  const save = useMutation({
    mutationFn: () => {
      const payload = structuredClone(form)
      payload.filters.keywords = lines(text.keywords)
      payload.filters.regex_patterns = lines(text.regex)
      payload.ignore.user_ids = lines(text.ignoredUsers)
        .map((v) => (/^-?\d+$/.test(v) ? Number(v) : null))
        .filter((v): v is number => v !== null)
      payload.ignore.keywords = lines(text.ignoredKeywords)
      return request(
        editing === null ? '/api/v1/rules' : `/api/v1/rules/${editing}`,
        json(editing === null ? 'POST' : 'PUT', payload),
      )
    },
    onSuccess: () => {
      setOpen(false)
      void client.invalidateQueries({ queryKey: ['rules'] })
    },
  })
  const remove = useMutation({
    mutationFn: (index: number) => request(`/api/v1/rules/${index}`, json('DELETE')),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['rules'] }),
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    regexValidation.validate(text.regex).then((valid) => {
      if (valid) save.mutate()
    })
  }
  function deleteRule(index: number) {
    if (window.confirm('确定删除这条转发规则？')) remove.mutate(index)
  }
  const setForwarding = <K extends keyof ForwardingRule['forwarding']>(
    key: K,
    value: ForwardingRule['forwarding'][K],
  ) => setForm((current) => ({ ...current, forwarding: { ...current.forwarding, [key]: value } }))

  return (
    <>
      <PageHeader
        eyebrow="ROUTING MATRIX"
        title="转发规则"
        description="定义消息从来源会话到目标会话的路由与过滤行为。"
        actions={
          <Button icon={Plus} onClick={createRule}>
            新建规则
          </Button>
        }
      />
      <div
        className={cn(
          'mb-3 flex min-h-14 items-center justify-between gap-3 rounded-md',
          'border border-slate-200 bg-white p-3 max-md:flex-col max-md:items-stretch',
        )}
      >
        <div
          className={cn(
            'flex h-9 w-full max-w-85 items-center gap-2 rounded-[5px] border',
            'border-slate-200 bg-slate-50 px-2.5 text-slate-400 max-md:max-w-none',
          )}
        >
          <Search size={17} />
          <input
            className="w-full border-0 bg-transparent text-[11px] text-slate-700 outline-none"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索规则名称"
          />
        </div>
        <span className="text-[9px] text-slate-400">
          {rulesQuery.data?.filter((rule) => rule.enabled).length ?? 0} 条启用 /{' '}
          {rulesQuery.data?.length ?? 0} 条规则
        </span>
      </div>
      <section className={tableWrapClass}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>规则</th>
                <th>状态</th>
                <th>来源</th>
                <th>目标</th>
                <th>过滤方式</th>
                <th aria-label="操作" />
              </tr>
            </thead>
            <tbody>
              {rules.map(({ rule, index }) => (
                <tr key={`${rule.name}-${index}`}>
                  <td>
                    <div className="flex min-w-38 items-center gap-2.5">
                      <span
                        className={cn(
                          'grid size-8 shrink-0 place-items-center rounded',
                          'bg-blue-50 text-blue-600',
                        )}
                      >
                        <Route size={17} />
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <strong className="text-[10px] text-slate-700">{rule.name}</strong>
                        <small className="mt-1 text-[8px] text-slate-400">
                          {rule.forwarding.delay}s 延迟
                        </small>
                      </span>
                    </div>
                  </td>
                  <td>
                    <Badge tone={rule.enabled ? 'green' : 'gray'}>
                      {rule.enabled ? '已启用' : '已停用'}
                    </Badge>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {rule.source_chats.join(', ') || '-'}
                    </span>
                    <small className="mt-1 block text-[8px] text-slate-400">
                      {rule.source_chats.length} 个会话
                    </small>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {rule.target_chats.join(', ') || '-'}
                    </span>
                    <small className="mt-1 block text-[8px] text-slate-400">
                      {rule.target_chats.length} 个会话
                    </small>
                  </td>
                  <td>
                    <Badge>{rule.filters.mode === 'whitelist' ? '白名单' : '黑名单'}</Badge>
                    <small className="mt-1 block text-[8px] text-slate-400">
                      {rule.filters.keywords.length + rule.filters.regex_patterns.length} 个条件
                    </small>
                  </td>
                  <td>
                    <div className="flex justify-end gap-1">
                      <IconButton label="编辑规则" icon={Edit3} onClick={() => editRule(index)} />
                      <IconButton
                        label="删除规则"
                        icon={Trash2}
                        onClick={() => deleteRule(index)}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rules.length ? (
          <EmptyState
            icon={Route}
            title={search ? '没有匹配的规则' : '还没有转发规则'}
            detail={search ? '尝试使用其他关键词。' : '新建规则后即可开始路由消息。'}
          />
        ) : null}
      </section>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={editing === null ? '新建转发规则' : `编辑 ${form.name}`}
        description="每行填写一个会话或匹配项，保存后立即应用。"
      >
        <form onSubmit={submit}>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>规则名称</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </label>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>来源会话</span>
              <ChatTagInput
                value={form.source_chats}
                onChange={(source_chats) => setForm({ ...form, source_chats })}
              />
            </div>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>目标会话</span>
              <ChatTagInput
                value={form.target_chats}
                onChange={(target_chats) => setForm({ ...form, target_chats })}
              />
            </div>
            <label className={fieldClass}>
              <span>过滤方式</span>
              <Select
                value={form.filters.mode}
                onValueChange={(value) =>
                  setForm({
                    ...form,
                    filters: { ...form.filters, mode: value as 'whitelist' | 'blacklist' },
                  })
                }
                options={[
                  { value: 'whitelist', label: '白名单：匹配后转发' },
                  { value: 'blacklist', label: '黑名单：匹配后过滤' },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>转发延迟（秒）</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={form.forwarding.delay}
                onChange={(event) => setForwarding('delay', Number(event.target.value))}
              />
            </label>
            <label className={fieldClass}>
              <span>关键词</span>
              <textarea
                value={text.keywords}
                onChange={(event) => setText({ ...text, keywords: event.target.value })}
                rows={4}
              />
            </label>
            <RegexField
              label="正则表达式"
              value={text.regex}
              onChange={(regex) => setText({ ...text, regex })}
              validation={regexValidation}
            />
            <label className={fieldClass}>
              <span>忽略的用户 ID</span>
              <textarea
                value={text.ignoredUsers}
                onChange={(event) => setText({ ...text, ignoredUsers: event.target.value })}
                rows={3}
              />
            </label>
            <label className={fieldClass}>
              <span>忽略的关键词</span>
              <textarea
                value={text.ignoredKeywords}
                onChange={(event) => setText({ ...text, ignoredKeywords: event.target.value })}
                rows={3}
              />
            </label>
          </div>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <h3 className="mb-3 flex items-center gap-2 text-[10px] font-bold text-slate-600">
              <Braces size={16} />
              转发行为
            </h3>
            <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
              <Switch
                checked={form.enabled}
                onCheckedChange={(enabled) => setForm({ ...form, enabled })}
                label="启用规则"
              />
              <Switch
                checked={form.forwarding.preserve_format}
                onCheckedChange={(value) => setForwarding('preserve_format', value)}
                label="保留格式"
              />
              <Switch
                checked={form.forwarding.add_source_info}
                onCheckedChange={(value) => setForwarding('add_source_info', value)}
                label="附加来源"
              />
              <Switch
                checked={form.forwarding.force_forward}
                onCheckedChange={(value) => setForwarding('force_forward', value)}
                label="强制上传"
              />
              <Switch
                checked={form.forwarding.hide_sender}
                onCheckedChange={(value) => setForwarding('hide_sender', value)}
                label="隐藏发送者"
              />
              <Switch
                checked={form.forwarding.deduplicate}
                onCheckedChange={(value) => setForwarding('deduplicate', value)}
                label="消息去重"
              />
            </div>
          </div>
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
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? '保存中...' : '保存规则'}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
