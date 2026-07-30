import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Edit3, MousePointerClick, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { json, request } from '../api/client'
import { ChatTagInput } from '../components/ChatTagInput'
import { RegexField, useRegexValidation } from '../components/RegexField'
import {
  Badge,
  Button,
  ConfirmDialog,
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
import type { ButtonRule } from '../types'
import { cn } from '../utils/cn'
import { messageFrom } from '../utils/format'
import { lines } from '../utils/parse'

const blankRule = (): ButtonRule => ({
  name: '',
  enabled: false,
  source_chats: [],
  button_texts: [],
  match_mode: 'exact',
  delay: 0,
  click_all_matches: false,
})

export function AutomationsPage() {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [form, setForm] = useState<ButtonRule>(blankRule())
  const [buttons, setButtons] = useState('')
  const regexValidation = useRegexValidation()
  const query = useQuery({
    queryKey: ['button-rules'],
    queryFn: () => request<ButtonRule[]>('/api/v1/button-rules'),
  })
  const rules = useMemo(
    () =>
      (query.data ?? [])
        .map((rule, index) => ({ rule, index }))
        .filter(({ rule }) => rule.name.toLowerCase().includes(search.toLowerCase())),
    [query.data, search],
  )

  function create() {
    setEditing(null)
    setForm(blankRule())
    setButtons('')
    regexValidation.reset()
    setOpen(true)
  }
  function edit(index: number) {
    const value = structuredClone(query.data?.[index] ?? blankRule())
    setEditing(index)
    setForm(value)
    setButtons(value.button_texts.join('\n'))
    regexValidation.reset()
    setOpen(true)
  }
  const save = useMutation({
    mutationFn: () =>
      request(
        editing === null ? '/api/v1/button-rules' : `/api/v1/button-rules/${editing}`,
        json(editing === null ? 'POST' : 'PUT', {
          ...form,
          button_texts: lines(buttons),
        }),
      ),
    onSuccess: () => {
      setOpen(false)
      void client.invalidateQueries({ queryKey: ['button-rules'] })
    },
  })
  const remove = useMutation({
    mutationFn: (index: number) => request(`/api/v1/button-rules/${index}`, json('DELETE')),
    onSuccess: () => {
      setDeletingIndex(null)
      void client.invalidateQueries({ queryKey: ['button-rules'] })
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (form.match_mode !== 'regex') {
      save.mutate()
      return
    }
    regexValidation.validate(buttons).then((valid) => {
      if (valid) save.mutate()
    })
  }
  function deleteRule(index: number) {
    setDeletingIndex(index)
  }

  return (
    <>
      <PageHeader
        eyebrow="INTERACTION ENGINE"
        title="按钮自动化"
        description="在指定会话中匹配并点击 Telegram 消息按钮。"
        actions={
          <Button icon={Plus} onClick={create}>
            新建自动化
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
            placeholder="搜索自动化名称"
          />
        </div>
        <span className="text-[9px] text-slate-400">
          {query.data?.filter((rule) => rule.enabled).length ?? 0} 条启用 /{' '}
          {query.data?.length ?? 0} 条自动化
        </span>
      </div>
      <section className={tableWrapClass}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>自动化</th>
                <th>状态</th>
                <th>来源</th>
                <th>匹配方式</th>
                <th>按钮文本</th>
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
                        <MousePointerClick size={17} />
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <strong className="text-[10px] text-slate-700">{rule.name}</strong>
                        <small className="mt-1 text-[8px] text-slate-400">{rule.delay}s 延迟</small>
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
                    <Badge>
                      {
                        { exact: '精确匹配', contains: '包含文本', regex: '正则匹配' }[
                          rule.match_mode
                        ]
                      }
                    </Badge>
                    <small className="mt-1 block text-[8px] text-slate-400">
                      {rule.click_all_matches ? '点击全部匹配' : '点击首个匹配'}
                    </small>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {rule.button_texts.join(' / ') || '-'}
                    </span>
                    <small className="mt-1 block text-[8px] text-slate-400">
                      {rule.button_texts.length} 个模式
                    </small>
                  </td>
                  <td>
                    <div className="flex justify-end gap-1">
                      <IconButton label="编辑自动化" icon={Edit3} onClick={() => edit(index)} />
                      <IconButton
                        label="删除自动化"
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
            icon={Bot}
            title={search ? '没有匹配的自动化' : '还没有按钮自动化'}
            detail="添加自动化后，用户会话会按规则点击按钮。"
          />
        ) : null}
      </section>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={editing === null ? '新建按钮自动化' : `编辑 ${form.name}`}
        description="自动化仅在 Telegram 用户会话模式下生效。"
      >
        <form onSubmit={submit}>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>自动化名称</span>
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
            {form.match_mode === 'regex' ? (
              <RegexField
                className="col-span-2 max-md:col-span-1"
                label="按钮文本或模式"
                value={buttons}
                onChange={setButtons}
                validation={regexValidation}
                rows={5}
                placeholder="\\b(确认|领取)\\b"
              />
            ) : (
              <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                <span>按钮文本或模式</span>
                <textarea
                  value={buttons}
                  onChange={(event) => setButtons(event.target.value)}
                  rows={5}
                  placeholder={'确认\n领取奖励'}
                />
              </label>
            )}
            <label className={fieldClass}>
              <span>匹配方式</span>
              <Select
                value={form.match_mode}
                onValueChange={(value) => {
                  setForm({ ...form, match_mode: value as ButtonRule['match_mode'] })
                  regexValidation.reset()
                }}
                options={[
                  { value: 'exact', label: '精确匹配' },
                  { value: 'contains', label: '包含文本' },
                  { value: 'regex', label: '正则表达式' },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>点击延迟（秒）</span>
              <input
                type="number"
                min="0"
                max="30"
                step="0.1"
                value={form.delay}
                onChange={(event) => setForm({ ...form, delay: Number(event.target.value) })}
              />
            </label>
          </div>
          <div
            className={cn(
              'mt-5 grid grid-cols-2 gap-2 border-t border-slate-100 pt-4',
              'max-md:grid-cols-1',
            )}
          >
            <Switch
              checked={form.enabled}
              onCheckedChange={(enabled) => setForm({ ...form, enabled })}
              label="启用自动化"
            />
            <Switch
              checked={form.click_all_matches}
              onCheckedChange={(click_all_matches) => setForm({ ...form, click_all_matches })}
              label="点击全部匹配"
            />
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
              {save.isPending ? '保存中...' : '保存自动化'}
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={deletingIndex !== null}
        onOpenChange={(next) => {
          if (!next) setDeletingIndex(null)
        }}
        title="删除按钮自动化"
        description={`确定删除“${deletingIndex === null ? '' : (query.data?.[deletingIndex]?.name ?? '这条自动化')}”？删除后无法恢复。`}
        confirmLabel="删除自动化"
        pending={remove.isPending}
        onConfirm={() => {
          if (deletingIndex !== null) remove.mutate(deletingIndex)
        }}
      />
    </>
  )
}
