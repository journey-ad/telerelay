import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Braces, Edit3, Plus, Route, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { json, request } from '../api/client'
import { ChatTagInput } from '../components/ChatTagInput'
import { RegexField, useRegexValidation } from '../components/RegexField'
import { useTelegramChats } from '../hooks/useTelegramChats'
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
import type { ChatRef, ForwardingRule } from '../types'
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
  const { t } = useTranslation()
  const client = useQueryClient()
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)
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
  const chatsQuery = useTelegramChats()
  const chatLabels = useMemo(
    () => new Map((chatsQuery.data ?? []).map((chat) => [String(chat.id), chat.title] as const)),
    [chatsQuery.data],
  )
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
    onSuccess: () => {
      setDeletingIndex(null)
      void client.invalidateQueries({ queryKey: ['rules'] })
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    regexValidation.validate(text.regex).then((valid) => {
      if (valid) save.mutate()
    })
  }
  function deleteRule(index: number) {
    setDeletingIndex(index)
  }
  const setForwarding = <K extends keyof ForwardingRule['forwarding']>(
    key: K,
    value: ForwardingRule['forwarding'][K],
  ) => setForm((current) => ({ ...current, forwarding: { ...current.forwarding, [key]: value } }))
  const formatChats = (chatRefs: ChatRef[]) =>
    chatRefs.map((chatRef) => chatLabels.get(String(chatRef)) ?? String(chatRef)).join(', ')

  return (
    <>
      <PageHeader
        eyebrow={t('rules.eyebrow')}
        title={t('rules.title')}
        description={t('rules.description')}
        actions={
          <Button icon={Plus} onClick={createRule}>
            {t('rules.new')}
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
            className="w-full border-0 bg-transparent text-[13px] text-slate-700 outline-none"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('rules.search')}
          />
        </div>
        <span className="text-[13px] text-slate-400">
          {t('rules.summary', {
            enabled: rulesQuery.data?.filter((rule) => rule.enabled).length ?? 0,
            total: rulesQuery.data?.length ?? 0,
          })}
        </span>
      </div>
      <section className={tableWrapClass}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>{t('rules.columns.rule')}</th>
                <th>{t('rules.columns.status')}</th>
                <th>{t('rules.columns.source')}</th>
                <th>{t('rules.columns.destination')}</th>
                <th>{t('rules.columns.filterMode')}</th>
                <th aria-label={t('common.actions')} />
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
                        <strong className="text-xs text-slate-700">{rule.name}</strong>
                        <small className="mt-1 text-xs text-slate-400">
                          {t('common.delaySeconds', { seconds: rule.forwarding.delay })}
                        </small>
                      </span>
                    </div>
                  </td>
                  <td>
                    <Badge tone={rule.enabled ? 'green' : 'gray'}>
                      {t(rule.enabled ? 'common.enabled' : 'common.disabled')}
                    </Badge>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {formatChats(rule.source_chats) || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.chatCount', { count: rule.source_chats.length })}
                    </small>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {formatChats(rule.target_chats) || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.chatCount', { count: rule.target_chats.length })}
                    </small>
                  </td>
                  <td>
                    <Badge>
                      {t(rule.filters.mode === 'whitelist' ? 'rules.allowlist' : 'rules.blocklist')}
                    </Badge>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.conditionCount', {
                        count: rule.filters.keywords.length + rule.filters.regex_patterns.length,
                      })}
                    </small>
                  </td>
                  <td>
                    <div className="flex justify-end gap-1">
                      <IconButton
                        label={t('rules.edit')}
                        icon={Edit3}
                        onClick={() => editRule(index)}
                      />
                      <IconButton
                        label={t('rules.delete')}
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
            title={t(search ? 'rules.noMatches' : 'rules.empty')}
            detail={t(search ? 'rules.tryAnotherSearch' : 'rules.emptyDetail')}
          />
        ) : null}
      </section>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={editing === null ? t('rules.newTitle') : t('common.editNamed', { name: form.name })}
        description={t('rules.dialogDescription')}
      >
        <form onSubmit={submit}>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('rules.name')}</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </label>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('rules.sourceChats')}</span>
              <ChatTagInput
                value={form.source_chats}
                onChange={(source_chats) => setForm({ ...form, source_chats })}
              />
            </div>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('rules.destinationChats')}</span>
              <ChatTagInput
                value={form.target_chats}
                onChange={(target_chats) => setForm({ ...form, target_chats })}
              />
            </div>
            <label className={fieldClass}>
              <span>{t('rules.filterMode')}</span>
              <Select
                value={form.filters.mode}
                onValueChange={(value) =>
                  setForm({
                    ...form,
                    filters: { ...form.filters, mode: value as 'whitelist' | 'blacklist' },
                  })
                }
                options={[
                  { value: 'whitelist', label: t('rules.allowlistDescription') },
                  { value: 'blacklist', label: t('rules.blocklistDescription') },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('rules.delay')}</span>
              <input
                type="number"
                min="0"
                step="0.1"
                value={form.forwarding.delay}
                onChange={(event) => setForwarding('delay', Number(event.target.value))}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('rules.keywords')}</span>
              <textarea
                value={text.keywords}
                onChange={(event) => setText({ ...text, keywords: event.target.value })}
                rows={4}
              />
            </label>
            <RegexField
              label={t('rules.regex')}
              value={text.regex}
              onChange={(regex) => setText({ ...text, regex })}
              validation={regexValidation}
            />
            <label className={fieldClass}>
              <span>{t('rules.ignoredUsers')}</span>
              <textarea
                value={text.ignoredUsers}
                onChange={(event) => setText({ ...text, ignoredUsers: event.target.value })}
                rows={3}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('rules.ignoredKeywords')}</span>
              <textarea
                value={text.ignoredKeywords}
                onChange={(event) => setText({ ...text, ignoredKeywords: event.target.value })}
                rows={3}
              />
            </label>
          </div>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold text-slate-600">
              <Braces size={16} />
              {t('rules.behavior')}
            </h3>
            <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
              <Switch
                checked={form.enabled}
                onCheckedChange={(enabled) => setForm({ ...form, enabled })}
                label={t('rules.enable')}
              />
              <Switch
                checked={form.forwarding.preserve_format}
                onCheckedChange={(value) => setForwarding('preserve_format', value)}
                label={t('rules.preserveFormat')}
              />
              <Switch
                checked={form.forwarding.add_source_info}
                onCheckedChange={(value) => setForwarding('add_source_info', value)}
                label={t('rules.appendSource')}
              />
              <Switch
                checked={form.forwarding.force_forward}
                onCheckedChange={(value) => setForwarding('force_forward', value)}
                label={t('rules.forceUpload')}
              />
              <Switch
                checked={form.forwarding.hide_sender}
                onCheckedChange={(value) => setForwarding('hide_sender', value)}
                label={t('rules.hideSender')}
              />
              <Switch
                checked={form.forwarding.deduplicate}
                onCheckedChange={(value) => setForwarding('deduplicate', value)}
                label={t('rules.deduplicate')}
              />
            </div>
          </div>
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
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {t(save.isPending ? 'common.saving' : 'rules.save')}
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        open={deletingIndex !== null}
        onOpenChange={(next) => {
          if (!next) setDeletingIndex(null)
        }}
        title={t('rules.deleteTitle')}
        description={t('rules.deleteConfirm', {
          name:
            deletingIndex === null
              ? ''
              : (rulesQuery.data?.[deletingIndex]?.name ?? t('rules.fallbackName')),
        })}
        confirmLabel={t('rules.delete')}
        pending={remove.isPending}
        onConfirm={() => {
          if (deletingIndex !== null) remove.mutate(deletingIndex)
        }}
      />
    </>
  )
}
