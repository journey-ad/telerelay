import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Braces, Edit3, FolderKanban, Plus, Route, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { accountRequest, json } from '../api/client'
import { ChatTagInput } from '../components/ChatTagInput'
import { MultiValueInput } from '../components/MultiValueInput'
import { RegexField, useRegexValidation } from '../components/RegexField'
import { useTelegramChats } from '../hooks/useTelegramChats'
import { useAccountScope } from '../hooks/useAccountScope'
import {
  Badge,
  Button,
  confirm,
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
import type { ChatGroup, ChatRef, ForwardingRule, Stats } from '../types'
import { cn } from '../utils/cn'
import { formatNumber, messageFrom } from '../utils/format'
import { lines } from '../utils/parse'

const filterModeLabels = {
  whitelist: 'rules.allowlist',
  blacklist: 'rules.blocklist',
  'media-only': 'rules.mediaOnly',
} as const

function filterModeLabel(mode: ForwardingRule['filters']['mode']) {
  return filterModeLabels[mode] ?? 'rules.allowlist'
}

const blankRule = (): ForwardingRule => ({
  name: '',
  enabled: true,
  source_chats: [],
  target_chats: [],
  source_groups: [],
  target_groups: [],
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
    hide_media_caption: false,
    deduplicate: false,
    deduplicate_window: 3600,
  },
})

export function RulesPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const accountId = useAccountScope()
  const rulesKey = ['rules', accountId] as const
  const statsKey = ['stats', accountId, 'all'] as const
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [groupsOpen, setGroupsOpen] = useState(false)
  const [editingGroup, setEditingGroup] = useState<number | null>(null)
  const [groupForm, setGroupForm] = useState<ChatGroup>({ name: '', chats: [] })
  const [editing, setEditing] = useState<number | null>(null)
  const [form, setForm] = useState<ForwardingRule>(blankRule())
  const [regex, setRegex] = useState('')
  const regexValidation = useRegexValidation()
  const rulesQuery = useQuery({
    queryKey: rulesKey,
    queryFn: () => accountRequest<ForwardingRule[]>(accountId, '/api/v1/rules'),
  })
  const statsQuery = useQuery({
    queryKey: statsKey,
    queryFn: () => accountRequest<Stats>(accountId, '/api/v1/stats?date_limit=all'),
  })
  const chatsQuery = useTelegramChats()
  const groupsKey = ['chat-groups', accountId] as const
  const groupsQuery = useQuery({
    queryKey: groupsKey,
    queryFn: () => accountRequest<ChatGroup[]>(accountId, '/api/v1/chat-groups'),
  })
  const chatLabels = useMemo(
    () => new Map((chatsQuery.data ?? []).map((chat) => [String(chat.id), chat.title] as const)),
    [chatsQuery.data],
  )
  const ruleStats = useMemo(
    () => new Map((statsQuery.data?.rules ?? []).map((item) => [item.rule_name, item] as const)),
    [statsQuery.data],
  )
  const groupMap = useMemo(
    () => new Map((groupsQuery.data ?? []).map((group) => [group.name, group.chats] as const)),
    [groupsQuery.data],
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
    setRegex('')
    regexValidation.reset()
    toggle.reset()
    setOpen(true)
  }
  function editRule(index: number) {
    const value = structuredClone(rulesQuery.data?.[index] ?? blankRule())
    value.source_groups = value.source_groups ?? []
    value.target_groups = value.target_groups ?? []
    setEditing(index)
    setForm(value)
    setRegex(value.filters.regex_patterns.join('\n'))
    regexValidation.reset()
    toggle.reset()
    setOpen(true)
  }
  const save = useMutation({
    mutationFn: ({
      rule,
      regexPatterns,
      index,
    }: {
      rule: ForwardingRule
      regexPatterns: string[]
      index: number | null
    }) => {
      const payload = structuredClone(rule)
      payload.filters.regex_patterns = regexPatterns
      return accountRequest<ForwardingRule>(
        accountId,
        index === null ? '/api/v1/rules' : `/api/v1/rules/${index}`,
        json(index === null ? 'POST' : 'PUT', payload),
      )
    },
    onSuccess: (updated, { index }) => {
      setOpen(false)
      client.setQueryData<ForwardingRule[]>(rulesKey, (current) => {
        if (!current) return index === null ? [updated] : current
        if (index === null) return [...current, updated]
        return current.map((rule, position) => (position === index ? updated : rule))
      })
      void client.invalidateQueries({ queryKey: statsKey })
    },
  })
  const toggle = useMutation({
    mutationFn: ({ index, enabled }: { index: number; enabled: boolean }) => {
      const rule = rulesQuery.data?.[index]
      if (!rule) throw new Error('Forwarding rule does not exist')
      return accountRequest<ForwardingRule>(
        accountId,
        `/api/v1/rules/${index}`,
        json('PATCH', { enabled }),
      )
    },
    onSuccess: (updated, { index }) => {
      client.setQueryData<ForwardingRule[]>(rulesKey, (current) =>
        current?.map((rule, position) => (position === index ? updated : rule)),
      )
    },
  })
  function setEnabled(enabled: boolean) {
    if (editing === null) {
      setForm((current) => ({ ...current, enabled }))
      return
    }
    const previous = form.enabled
    setForm((current) => ({ ...current, enabled }))
    toggle.mutate(
      { index: editing, enabled },
      {
        onError: () => setForm((current) => ({ ...current, enabled: previous })),
      },
    )
  }
  const remove = useMutation({
    mutationFn: (index: number) =>
      accountRequest(accountId, `/api/v1/rules/${index}`, json('DELETE')),
    onSuccess: (_, index) => {
      client.setQueryData<ForwardingRule[]>(rulesKey, (current) =>
        current?.filter((_, position) => position !== index),
      )
      void client.invalidateQueries({ queryKey: statsKey })
    },
  })
  const saveGroup = useMutation({
    mutationFn: ({ group, index }: { group: ChatGroup; index: number | null }) =>
      accountRequest<ChatGroup>(
        accountId,
        index === null ? '/api/v1/chat-groups' : `/api/v1/chat-groups/${index}`,
        json(index === null ? 'POST' : 'PUT', group),
      ),
    onSuccess: (updated, { index }) => {
      client.setQueryData<ChatGroup[]>(groupsKey, (current) => {
        if (!current) return [updated]
        if (index === null) return [...current, updated]
        return current.map((group, position) => (position === index ? updated : group))
      })
      setEditingGroup(null)
      setGroupForm({ name: '', chats: [] })
    },
  })
  const removeGroup = useMutation({
    mutationFn: (index: number) =>
      accountRequest(accountId, `/api/v1/chat-groups/${index}`, json('DELETE')),
    onSuccess: (_, index) => {
      client.setQueryData<ChatGroup[]>(groupsKey, (current) =>
        current?.filter((_, position) => position !== index),
      )
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (form.filters.mode === 'media-only') {
      // Keywords and regex do not participate in media-only mode; stored
      // patterns are carried over untouched.
      save.mutate({ rule: structuredClone(form), regexPatterns: lines(regex), index: editing })
      return
    }
    regexValidation.validate(regex).then((valid) => {
      if (valid) {
        save.mutate({ rule: structuredClone(form), regexPatterns: lines(regex), index: editing })
      }
    })
  }
  async function deleteRule(index: number) {
    await confirm({
      title: t('rules.deleteTitle'),
      description: t('rules.deleteConfirm', {
        name: rulesQuery.data?.[index]?.name ?? t('rules.fallbackName'),
      }),
      confirmLabel: t('rules.delete'),
      onConfirm: () => remove.mutateAsync(index),
    })
  }
  async function deleteGroup(index: number) {
    await confirm({
      title: t('rules.groups.deleteTitle'),
      description: t('rules.groups.deleteConfirm', {
        name: groupsQuery.data?.[index]?.name ?? '',
      }),
      confirmLabel: t('rules.groups.delete'),
      onConfirm: () => removeGroup.mutateAsync(index),
    })
  }
  const setForwarding = <K extends keyof ForwardingRule['forwarding']>(
    key: K,
    value: ForwardingRule['forwarding'][K],
  ) => setForm((current) => ({ ...current, forwarding: { ...current.forwarding, [key]: value } }))
  const formatChats = (chatRefs: ChatRef[]) =>
    chatRefs.map((chatRef) => chatLabels.get(String(chatRef)) ?? String(chatRef)).join(', ')
  const formatEndpoint = (chats: ChatRef[], groups: string[] = []) =>
    [formatChats(chats), ...groups.map((name) => t('rules.groupLabel', { name }))]
      .filter(Boolean)
      .join(', ')
  const endpointCount = (chats: ChatRef[], groups: string[] = []) =>
    new Set([...chats, ...groups.flatMap((name) => groupMap.get(name) ?? [])].map(String)).size

  return (
    <>
      <PageHeader
        eyebrow={t('rules.eyebrow')}
        title={t('rules.title')}
        description={t('rules.description')}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" icon={FolderKanban} onClick={() => setGroupsOpen(true)}>
              {t('rules.groups.manage')}
            </Button>
            <Button icon={Plus} onClick={createRule}>
              {t('rules.new')}
            </Button>
          </div>
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
                <th>{t('rules.columns.status')}</th>
                <th>{t('rules.columns.rule')}</th>
                <th>{t('rules.columns.source')}</th>
                <th>{t('rules.columns.destination')}</th>
                <th>{t('rules.columns.filterMode')}</th>
                <th>{t('rules.columns.triggerCount')}</th>
                <th aria-label={t('common.actions')} />
              </tr>
            </thead>
            <tbody>
              {rules.map(({ rule, index }) => (
                <tr key={`${rule.name}-${index}`}>
                  <td>
                    <Switch
                      checked={rule.enabled}
                      disabled={toggle.isPending}
                      onCheckedChange={(enabled) => toggle.mutate({ index, enabled })}
                      label={t('rules.enable')}
                      showLabel={false}
                      className="min-h-8 min-w-8 justify-center border-0 bg-transparent px-0 py-0"
                    />
                  </td>
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
                    <span className="block max-w-48 truncate">
                      {formatEndpoint(rule.source_chats, rule.source_groups) || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.chatCount', {
                        count: endpointCount(rule.source_chats, rule.source_groups),
                      })}
                    </small>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {formatEndpoint(rule.target_chats, rule.target_groups) || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.chatCount', {
                        count: endpointCount(rule.target_chats, rule.target_groups),
                      })}
                    </small>
                  </td>
                  <td>
                    <Badge>{t(filterModeLabel(rule.filters.mode))}</Badge>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.conditionCount', {
                        count: rule.filters.keywords.length + rule.filters.regex_patterns.length,
                      })}
                    </small>
                  </td>
                  <td>
                    <strong className="font-mono text-xs font-semibold text-slate-700">
                      {formatNumber(ruleStats.get(rule.name)?.forwarded ?? 0)}
                    </strong>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('rules.filteredDetail', {
                        count: formatNumber(ruleStats.get(rule.name)?.filtered ?? 0),
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
          <div className="mb-4 border-b border-slate-100 pb-4">
            <Switch
              checked={form.enabled}
              disabled={editing !== null && toggle.isPending}
              onCheckedChange={setEnabled}
              label={t('rules.enable')}
            />
          </div>
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
                groups={groupsQuery.data ?? []}
                selectedGroups={form.source_groups}
                onGroupsChange={(source_groups) => setForm({ ...form, source_groups })}
              />
            </div>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('rules.destinationChats')}</span>
              <ChatTagInput
                value={form.target_chats}
                onChange={(target_chats) => setForm({ ...form, target_chats })}
                groups={groupsQuery.data ?? []}
                selectedGroups={form.target_groups}
                onGroupsChange={(target_groups) => setForm({ ...form, target_groups })}
              />
            </div>
            <label className={fieldClass}>
              <span>{t('rules.filterMode')}</span>
              <Select
                value={form.filters.mode}
                onValueChange={(value) =>
                  setForm({
                    ...form,
                    filters: {
                      ...form.filters,
                      mode: value as ForwardingRule['filters']['mode'],
                    },
                  })
                }
                options={[
                  { value: 'whitelist', label: t('rules.allowlistDescription') },
                  { value: 'blacklist', label: t('rules.blocklistDescription') },
                  { value: 'media-only', label: t('rules.mediaOnlyDescription') },
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
            {form.filters.mode === 'media-only' ? null : (
              <>
                <div className={fieldClass}>
                  <span>{t('rules.keywords')}</span>
                  <MultiValueInput
                    value={form.filters.keywords}
                    onChange={(keywords) =>
                      setForm((current) => ({
                        ...current,
                        filters: { ...current.filters, keywords },
                      }))
                    }
                    ariaLabel={t('rules.removeKeyword')}
                    placeholder={t('rules.keywordPlaceholder')}
                  />
                </div>
                <RegexField
                  label={t('rules.regex')}
                  value={regex}
                  onChange={setRegex}
                  validation={regexValidation}
                />
              </>
            )}
            <div className={fieldClass}>
              <span>{t('rules.ignoredUsers')}</span>
              <MultiValueInput
                value={form.ignore.user_ids}
                onChange={(user_ids) =>
                  setForm((current) => ({
                    ...current,
                    ignore: { ...current.ignore, user_ids },
                  }))
                }
                parse={(value) => {
                  if (!/^-?\d+$/.test(value)) return null
                  const parsed = Number(value)
                  return Number.isSafeInteger(parsed) ? parsed : null
                }}
                ariaLabel={t('rules.removeIgnoredUser')}
                placeholder={t('rules.ignoredUserPlaceholder')}
                invalidMessage={t('rules.invalidUserId')}
              />
            </div>
            <div className={fieldClass}>
              <span>{t('rules.ignoredKeywords')}</span>
              <MultiValueInput
                value={form.ignore.keywords}
                onChange={(keywords) =>
                  setForm((current) => ({
                    ...current,
                    ignore: { ...current.ignore, keywords },
                  }))
                }
                ariaLabel={t('rules.removeIgnoredKeyword')}
                placeholder={t('rules.ignoredKeywordPlaceholder')}
              />
            </div>
          </div>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold text-slate-600">
              <Braces size={16} />
              {t('rules.behavior')}
            </h3>
            <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
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
                checked={form.forwarding.hide_sender}
                onCheckedChange={(value) => setForwarding('hide_sender', value)}
                label={t('rules.hideSender')}
              />
              <Switch
                checked={form.forwarding.hide_media_caption}
                onCheckedChange={(value) => setForwarding('hide_media_caption', value)}
                label={t('rules.hideMediaCaption')}
              />
              <Switch
                checked={form.forwarding.force_forward}
                onCheckedChange={(value) => setForwarding('force_forward', value)}
                label={t('rules.forceUpload')}
              />
              <Switch
                checked={form.forwarding.deduplicate}
                onCheckedChange={(value) => setForwarding('deduplicate', value)}
                label={t('rules.deduplicate')}
              />
            </div>
          </div>
          {save.error || toggle.error ? (
            <p
              className={cn(
                'mt-3 rounded-[5px] border border-rose-100 bg-rose-50 p-2',
                'text-[13px] text-rose-700',
              )}
            >
              {messageFrom(save.error ?? toggle.error)}
            </p>
          ) : null}
          <div className="mt-5 flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={save.isPending || toggle.isPending}>
              {t(save.isPending ? 'common.saving' : 'rules.save')}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={groupsOpen}
        onOpenChange={setGroupsOpen}
        title={t('rules.groups.title')}
        description={t('rules.groups.description')}
      >
        <div className="mb-4 space-y-2">
          {(groupsQuery.data ?? []).map((group, index) => (
            <div
              key={group.name}
              className="flex items-center gap-3 rounded-md border border-slate-200 p-3"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded bg-amber-50 text-amber-700">
                <FolderKanban size={17} />
              </span>
              <span className="min-w-0 flex-1">
                <strong className="block truncate text-[13px] text-slate-700">{group.name}</strong>
                <small className="text-xs text-slate-400">
                  {t('common.chatCount', { count: group.chats.length })}
                </small>
              </span>
              <IconButton
                label={t('rules.groups.edit')}
                icon={Edit3}
                onClick={() => {
                  setEditingGroup(index)
                  setGroupForm(structuredClone(group))
                }}
              />
              <IconButton
                label={t('rules.groups.delete')}
                icon={Trash2}
                onClick={() => deleteGroup(index)}
              />
            </div>
          ))}
        </div>
        <form
          className="rounded-md border border-slate-200 bg-slate-50 p-4"
          onSubmit={(event) => {
            event.preventDefault()
            saveGroup.mutate({ group: structuredClone(groupForm), index: editingGroup })
          }}
        >
          <h3 className="mb-3 text-sm font-bold text-slate-700">
            {t(editingGroup === null ? 'rules.groups.new' : 'rules.groups.editNamed', {
              name: groupForm.name,
            })}
          </h3>
          <label className={fieldClass}>
            <span>{t('rules.groups.name')}</span>
            <input
              value={groupForm.name}
              onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })}
              required
            />
          </label>
          <div className={cn(fieldClass, 'mt-3')}>
            <span>{t('rules.groups.chats')}</span>
            <ChatTagInput
              value={groupForm.chats}
              onChange={(chats) => setGroupForm({ ...groupForm, chats })}
            />
          </div>
          {saveGroup.error || removeGroup.error ? (
            <p className="mt-3 rounded border border-rose-100 bg-rose-50 p-2 text-[13px] text-rose-700">
              {messageFrom(saveGroup.error ?? removeGroup.error)}
            </p>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            {editingGroup !== null ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setEditingGroup(null)
                  setGroupForm({ name: '', chats: [] })
                }}
              >
                {t('common.cancel')}
              </Button>
            ) : null}
            <Button type="submit" disabled={saveGroup.isPending || groupForm.chats.length === 0}>
              {t(saveGroup.isPending ? 'common.saving' : 'rules.groups.save')}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
