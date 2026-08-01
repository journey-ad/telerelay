import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Edit3, MousePointerClick, Plus, Search, Trash2 } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { json, request } from '../api/client'
import { ChatTagInput } from '../components/ChatTagInput'
import { RegexField, useRegexValidation } from '../components/RegexField'
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
  const { t } = useTranslation()
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
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
    mutationFn: ({
      rule,
      buttonTexts,
      index,
    }: {
      rule: ButtonRule
      buttonTexts: string[]
      index: number | null
    }) =>
      request<ButtonRule>(
        index === null ? '/api/v1/button-rules' : `/api/v1/button-rules/${index}`,
        json(index === null ? 'POST' : 'PUT', {
          ...rule,
          button_texts: buttonTexts,
        }),
      ),
    onSuccess: (updated, { index }) => {
      setOpen(false)
      client.setQueryData<ButtonRule[]>(['button-rules'], (current) => {
        if (!current) return index === null ? [updated] : current
        if (index === null) return [...current, updated]
        return current.map((rule, position) => (position === index ? updated : rule))
      })
    },
  })
  const toggle = useMutation({
    mutationFn: ({ index, enabled }: { index: number; enabled: boolean }) => {
      const rule = query.data?.[index]
      if (!rule) throw new Error('Button automation does not exist')
      return request<ButtonRule>(
        `/api/v1/button-rules/${index}`,
        json('PUT', { ...structuredClone(rule), enabled }),
      )
    },
    onSuccess: (updated, { index }) => {
      client.setQueryData<ButtonRule[]>(['button-rules'], (current) =>
        current?.map((rule, position) => (position === index ? updated : rule)),
      )
    },
  })
  const remove = useMutation({
    mutationFn: (index: number) => request(`/api/v1/button-rules/${index}`, json('DELETE')),
    onSuccess: (_, index) => {
      client.setQueryData<ButtonRule[]>(['button-rules'], (current) =>
        current?.filter((_, position) => position !== index),
      )
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (form.match_mode !== 'regex') {
      save.mutate({ rule: structuredClone(form), buttonTexts: lines(buttons), index: editing })
      return
    }
    regexValidation.validate(buttons).then((valid) => {
      if (valid) {
        save.mutate({ rule: structuredClone(form), buttonTexts: lines(buttons), index: editing })
      }
    })
  }
  async function deleteRule(index: number) {
    await confirm({
      title: t('automations.deleteTitle'),
      description: t('automations.deleteConfirm', {
        name: query.data?.[index]?.name ?? t('automations.fallbackName'),
      }),
      confirmLabel: t('automations.delete'),
      onConfirm: () => remove.mutateAsync(index),
    })
  }

  return (
    <>
      <PageHeader
        eyebrow={t('automations.eyebrow')}
        title={t('automations.title')}
        description={t('automations.description')}
        actions={
          <Button icon={Plus} onClick={create}>
            {t('automations.new')}
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
            placeholder={t('automations.search')}
          />
        </div>
        <span className="text-[13px] text-slate-400">
          {t('automations.summary', {
            enabled: query.data?.filter((rule) => rule.enabled).length ?? 0,
            total: query.data?.length ?? 0,
          })}
        </span>
      </div>
      <section className={tableWrapClass}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead>
              <tr>
                <th>{t('automations.columns.status')}</th>
                <th>{t('automations.columns.automation')}</th>
                <th>{t('automations.columns.source')}</th>
                <th>{t('automations.columns.matchMode')}</th>
                <th>{t('automations.columns.buttonText')}</th>
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
                      label={t('automations.enable')}
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
                        <MousePointerClick size={17} />
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <strong className="text-xs text-slate-700">{rule.name}</strong>
                        <small className="mt-1 text-xs text-slate-400">
                          {t('common.delaySeconds', { seconds: rule.delay })}
                        </small>
                      </span>
                    </div>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {rule.source_chats.join(', ') || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.chatCount', { count: rule.source_chats.length })}
                    </small>
                  </td>
                  <td>
                    <Badge>
                      {
                        {
                          exact: t('automations.exact'),
                          contains: t('automations.contains'),
                          regex: t('automations.regexMatch'),
                        }[rule.match_mode]
                      }
                    </Badge>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t(
                        rule.click_all_matches ? 'automations.clickAll' : 'automations.clickFirst',
                      )}
                    </small>
                  </td>
                  <td>
                    <span className="block max-w-48 truncate">
                      {rule.button_texts.join(' / ') || '-'}
                    </span>
                    <small className="mt-1 block text-xs text-slate-400">
                      {t('common.patternCount', { count: rule.button_texts.length })}
                    </small>
                  </td>
                  <td>
                    <div className="flex justify-end gap-1">
                      <IconButton
                        label={t('automations.edit')}
                        icon={Edit3}
                        onClick={() => edit(index)}
                      />
                      <IconButton
                        label={t('automations.delete')}
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
            title={t(search ? 'automations.noMatches' : 'automations.empty')}
            detail={t('automations.emptyDetail')}
          />
        ) : null}
      </section>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={
          editing === null ? t('automations.newTitle') : t('common.editNamed', { name: form.name })
        }
        description={t('automations.dialogDescription')}
      >
        <form onSubmit={submit}>
          <div className="mb-4 border-b border-slate-100 pb-4">
            <Switch
              checked={form.enabled}
              onCheckedChange={(enabled) => setForm((current) => ({ ...current, enabled }))}
              label={t('automations.enable')}
            />
          </div>
          <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('automations.name')}</span>
              <input
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
              />
            </label>
            <div className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
              <span>{t('automations.sourceChats')}</span>
              <ChatTagInput
                value={form.source_chats}
                onChange={(source_chats) => setForm({ ...form, source_chats })}
              />
            </div>
            {form.match_mode === 'regex' ? (
              <RegexField
                className="col-span-2 max-md:col-span-1"
                label={t('automations.buttonPattern')}
                value={buttons}
                onChange={setButtons}
                validation={regexValidation}
                rows={5}
                placeholder={t('automations.regexPlaceholder')}
              />
            ) : (
              <label className={cn(fieldClass, 'col-span-2 max-md:col-span-1')}>
                <span>{t('automations.buttonPattern')}</span>
                <textarea
                  value={buttons}
                  onChange={(event) => setButtons(event.target.value)}
                  rows={5}
                  placeholder={t('automations.textPlaceholder')}
                />
              </label>
            )}
            <label className={fieldClass}>
              <span>{t('automations.matchMode')}</span>
              <Select
                value={form.match_mode}
                onValueChange={(value) => {
                  setForm({ ...form, match_mode: value as ButtonRule['match_mode'] })
                  regexValidation.reset()
                }}
                options={[
                  { value: 'exact', label: t('automations.exact') },
                  { value: 'contains', label: t('automations.contains') },
                  { value: 'regex', label: t('automations.regex') },
                ]}
              />
            </label>
            <label className={fieldClass}>
              <span>{t('automations.delay')}</span>
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
              checked={form.click_all_matches}
              onCheckedChange={(click_all_matches) =>
                setForm((current) => ({ ...current, click_all_matches }))
              }
              label={t('automations.clickAll')}
            />
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
              {t(save.isPending ? 'common.saving' : 'automations.save')}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  )
}
