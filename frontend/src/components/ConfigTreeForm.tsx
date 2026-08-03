import { ChevronRight, LockKeyhole, Plus, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ChatRef, JsonSchema } from '../types'
import { cn } from '../utils/cn'
import { lines } from '../utils/parse'
import { ChatTagInput } from './ChatTagInput'
import { MultiValueInput } from './MultiValueInput'
import { RegexField, useRegexValidation } from './RegexField'
import { Button, IconButton, Select, Switch } from './ui'

type ConfigObject = Record<string, unknown>

function isObject(value: unknown): value is ConfigObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function resolveSchema(schema: JsonSchema | undefined, root: JsonSchema): JsonSchema {
  if (!schema?.$ref?.startsWith('#/')) return schema ?? {}
  const target = schema.$ref
    .slice(2)
    .split('/')
    .reduce<unknown>((value, part) => {
      if (!isObject(value)) return undefined
      return value[part.replaceAll('~1', '/').replaceAll('~0', '~')]
    }, root)
  return isObject(target) ? { ...(target as JsonSchema), ...schema, $ref: undefined } : schema
}

function typedSchema(schema: JsonSchema | undefined, value: unknown, root: JsonSchema): JsonSchema {
  const resolved = resolveSchema(schema, root)
  if (!resolved.anyOf) return resolved
  const match = resolved.anyOf.find((option) => {
    const candidate = resolveSchema(option, root)
    if (candidate.type === 'integer' || candidate.type === 'number')
      return typeof value === 'number'
    return candidate.type === typeof value
  })
  return resolveSchema(match ?? resolved.anyOf[0], root)
}

function defaultValue(schema: JsonSchema | undefined, root: JsonSchema): unknown {
  const resolved = typedSchema(schema, undefined, root)
  if (resolved.default !== undefined) return resolved.default
  if (resolved.enum?.length) return resolved.enum[0]
  if (resolved.type === 'object' || resolved.properties) {
    return Object.fromEntries(
      Object.entries(resolved.properties ?? {}).map(([key, child]) => [
        key,
        defaultValue(child, root),
      ]),
    )
  }
  if (resolved.type === 'array') return []
  if (resolved.type === 'boolean') return false
  if (resolved.type === 'integer' || resolved.type === 'number') return resolved.minimum ?? 0
  return ''
}

function inferredSchema(value: unknown): JsonSchema {
  if (Array.isArray(value)) return { type: 'array', items: inferredSchema(value[0]) }
  if (isObject(value)) {
    return {
      type: 'object',
      properties: Object.fromEntries(
        Object.entries(value).map(([key, child]) => [key, inferredSchema(child)]),
      ),
    }
  }
  if (typeof value === 'boolean') return { type: 'boolean' }
  if (typeof value === 'number') return { type: Number.isInteger(value) ? 'integer' : 'number' }
  return { type: 'string' }
}

function useConfigCopy() {
  const { t } = useTranslation()
  return {
    labels: t('settings.configFields', { returnObjects: true }) as Record<string, string>,
    descriptions: t('settings.configDescriptions', { returnObjects: true }) as Record<
      string,
      string
    >,
    options: t('settings.configOptions', { returnObjects: true }) as Record<string, string>,
    systemGenerated: t('settings.configSystemGenerated'),
  }
}

function FieldHeading({
  name,
  schema,
  compact = false,
}: {
  name: string
  schema: JsonSchema
  compact?: boolean
}) {
  const { labels, descriptions, systemGenerated } = useConfigCopy()
  const label = labels[name] ?? schema.title ?? name
  const description = schema.readOnly ? systemGenerated : descriptions[name]
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5">
        <strong className={cn(compact ? 'text-[13px]' : 'text-sm', 'text-slate-700')}>
          {label}
        </strong>
        {schema.readOnly ? <LockKeyhole size={13} className="shrink-0 text-slate-400" /> : null}
      </div>
      {description && !compact ? (
        <p className="mt-0.5 text-xs leading-4 text-slate-400">{description}</p>
      ) : null}
    </div>
  )
}

function fieldEntries(value: ConfigObject, schema: JsonSchema, exclude: string[]) {
  const known = Object.keys(schema.properties ?? {})
  const unknown = Object.keys(value).filter((key) => !known.includes(key))
  return [...known, ...unknown].filter((key) => !exclude.includes(key))
}

function ObjectFields({
  value,
  schema,
  root,
  onChange,
  depth,
  exclude = [],
}: {
  value: ConfigObject
  schema: JsonSchema
  root: JsonSchema
  onChange: (next: ConfigObject) => void
  depth: number
  exclude?: string[]
}) {
  return (
    <div
      className={cn(
        depth === 0
          ? 'divide-y divide-slate-100'
          : 'grid grid-cols-[repeat(auto-fit,minmax(210px,1fr))] items-start gap-2.5',
      )}
    >
      {fieldEntries(value, schema, exclude).map((key) => {
        const childSchema = schema.properties?.[key] ?? inferredSchema(value[key])
        const childValue = key in value ? value[key] : defaultValue(childSchema, root)
        return (
          <ConfigField
            key={key}
            name={key}
            value={childValue}
            schema={childSchema}
            root={root}
            depth={depth}
            onChange={(next) => onChange({ ...value, [key]: next })}
          />
        )
      })}
    </div>
  )
}

function TagArrayInput({
  name,
  value,
  integer,
  onChange,
}: {
  name: string
  value: unknown[]
  integer: boolean
  onChange: (next: unknown[]) => void
}) {
  const { t } = useTranslation()
  const { labels } = useConfigCopy()
  const label = labels[name] ?? name
  if (integer) {
    return (
      <MultiValueInput
        value={value.filter((item): item is number => typeof item === 'number')}
        onChange={onChange}
        parse={(input) => {
          if (!/^-?\d+$/.test(input)) return null
          const parsed = Number(input)
          return Number.isSafeInteger(parsed) ? parsed : null
        }}
        ariaLabel={t('settings.listRemove')}
        placeholder={t('rules.ignoredUserPlaceholder')}
        invalidMessage={t('rules.invalidUserId')}
        className="min-h-8.5 py-1"
      />
    )
  }
  return (
    <MultiValueInput
      value={value.filter((item): item is string => typeof item === 'string')}
      onChange={onChange}
      ariaLabel={t('settings.listRemove')}
      placeholder={t('settings.configTagPlaceholder', { field: label })}
      className="min-h-8.5 py-1"
    />
  )
}

function RegexArrayInput({
  value,
  onChange,
}: {
  value: unknown[]
  onChange: (next: unknown[]) => void
}) {
  const { t } = useTranslation()
  const validation = useRegexValidation()
  const text = value.filter((item): item is string => typeof item === 'string').join('\n')
  return (
    <RegexField
      value={text}
      onChange={(next) => onChange(lines(next))}
      validation={validation}
      rows={3}
      placeholder={t('settings.configRegexPlaceholder')}
    />
  )
}

function PrimitiveArray({
  value,
  itemSchema,
  root,
  onChange,
}: {
  value: unknown[]
  itemSchema: JsonSchema
  root: JsonSchema
  onChange: (next: unknown[]) => void
}) {
  const { t } = useTranslation()
  const { options } = useConfigCopy()
  if (itemSchema.enum) {
    return (
      <div className="grid grid-cols-[repeat(auto-fit,minmax(100px,1fr))] gap-1.5">
        {itemSchema.enum.map((option) => {
          const selected = value.includes(option)
          return (
            <label
              key={String(option)}
              className={cn(
                'flex min-h-8.5 items-center gap-2 rounded-[5px] border px-2 text-xs cursor-pointer',
                selected
                  ? 'border-blue-200 bg-blue-50 text-blue-700'
                  : 'border-slate-200 bg-white text-slate-600',
              )}
            >
              <input
                type="checkbox"
                checked={selected}
                onChange={() =>
                  onChange(selected ? value.filter((item) => item !== option) : [...value, option])
                }
                className="size-3.5 accent-blue-600 cursor-pointer"
              />
              {options[String(option)] ?? String(option)}
            </label>
          )
        })}
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      {value.length === 0 ? (
        <p className="py-1 text-xs text-slate-400">{t('settings.listEmpty')}</p>
      ) : null}
      {value.map((item, index) => {
        const resolved = typedSchema(itemSchema, item, root)
        return (
          <div key={index} className="flex items-center gap-2">
            {resolved.type === 'boolean' ? (
              <Switch
                checked={Boolean(item)}
                onCheckedChange={(next) => {
                  const copy = value.slice()
                  copy[index] = next
                  onChange(copy)
                }}
                label={`${index + 1}`}
                showLabel={false}
                className="min-h-8.5 min-w-0 flex-1 py-1"
              />
            ) : (
              <input
                type={resolved.type === 'number' || resolved.type === 'integer' ? 'number' : 'text'}
                value={String(item ?? '')}
                min={resolved.minimum}
                max={resolved.maximum}
                step={resolved.multipleOf ?? (resolved.type === 'integer' ? 1 : undefined)}
                onChange={(event) => {
                  const copy = value.slice()
                  copy[index] =
                    resolved.type === 'number' || resolved.type === 'integer'
                      ? Number(event.target.value)
                      : event.target.value
                  onChange(copy)
                }}
                className={cn(
                  'h-8.5 min-w-0 flex-1 rounded-[5px] border border-slate-200 bg-white px-2.5',
                  'text-[13px] text-slate-700 outline-none focus:border-blue-300',
                  'focus:ring-3 focus:ring-blue-500/10',
                )}
              />
            )}
            <IconButton
              icon={Trash2}
              label={t('settings.listRemove')}
              onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}
            />
          </div>
        )
      })}
    </div>
  )
}

function ObjectArray({
  value,
  itemSchema,
  root,
  onChange,
}: {
  value: unknown[]
  itemSchema: JsonSchema
  root: JsonSchema
  onChange: (next: unknown[]) => void
}) {
  const { t } = useTranslation()
  const { labels } = useConfigCopy()
  if (value.length === 0) {
    return <p className="py-2 text-xs text-slate-400">{t('settings.listEmpty')}</p>
  }
  return (
    <div className="space-y-2">
      {value.map((item, index) => {
        const objectValue = isObject(item) ? item : {}
        const itemName =
          typeof objectValue.name === 'string' && objectValue.name
            ? objectValue.name
            : `#${index + 1}`
        return (
          <details
            key={index}
            className="group rounded-[5px] border border-slate-200 bg-slate-50/50"
          >
            <summary className="flex min-h-9.5 list-none items-center gap-2 px-2.5 marker:hidden cursor-pointer">
              <ChevronRight
                size={16}
                className="shrink-0 text-slate-400 transition-transform group-open:rotate-90"
              />
              <strong className="min-w-0 flex-1 truncate text-[13px] text-slate-700">
                {itemName}
              </strong>
              <Switch
                checked={Boolean(objectValue.enabled)}
                onCheckedChange={(enabled) => {
                  const copy = value.slice()
                  copy[index] = { ...objectValue, enabled }
                  onChange(copy)
                }}
                onClick={(event) => event.stopPropagation()}
                label={labels.enabled ?? 'enabled'}
                showLabel={false}
                className="min-h-0 border-transparent bg-transparent p-0"
              />
              <IconButton
                icon={Trash2}
                label={t('settings.listRemove')}
                onClick={(event) => {
                  event.preventDefault()
                  onChange(value.filter((_, itemIndex) => itemIndex !== index))
                }}
                className="ml-1"
              />
            </summary>
            <div className="border-t border-slate-200 bg-white p-2.5">
              <ObjectFields
                value={objectValue}
                schema={itemSchema}
                root={root}
                depth={1}
                exclude={['enabled']}
                onChange={(next) => {
                  const copy = value.slice()
                  copy[index] = next
                  onChange(copy)
                }}
              />
            </div>
          </details>
        )
      })}
    </div>
  )
}

function ArrayField({
  name,
  value,
  schema,
  root,
  onChange,
  depth,
}: {
  name: string
  value: unknown[]
  schema: JsonSchema
  root: JsonSchema
  onChange: (next: unknown[]) => void
  depth: number
}) {
  const { t } = useTranslation()
  const itemSchema =
    schema['x-item-control'] === 'chat-ref'
      ? { type: 'string', 'x-control': 'chat-ref' }
      : typedSchema(schema.items, value[0], root)
  const objectItems = itemSchema.type === 'object' || Boolean(itemSchema.properties)
  const itemControl = schema['x-item-control']
  const managedInput = ['chat-ref', 'tags', 'integer-tags', 'regex'].includes(itemControl ?? '')
  return (
    <section className={cn(depth === 0 ? 'py-4 first:pt-0 last:pb-0' : 'min-w-0')}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <FieldHeading name={name} schema={schema} compact={depth > 0} />
        {!schema.readOnly && !itemSchema.enum && !managedInput ? (
          <Button
            variant="secondary"
            icon={Plus}
            onClick={() =>
              onChange([
                ...value,
                schema['x-item-control'] === 'chat-ref' ? '' : defaultValue(schema.items, root),
              ])
            }
            className="min-h-8 shrink-0 px-2.5"
          >
            {t('settings.listAdd')}
          </Button>
        ) : null}
      </div>
      {itemControl === 'chat-ref' ? (
        <ChatTagInput
          value={value.filter(
            (item): item is ChatRef => typeof item === 'string' || typeof item === 'number',
          )}
          onChange={onChange}
          className="min-h-8.5 py-1"
        />
      ) : itemControl === 'tags' || itemControl === 'integer-tags' ? (
        <TagArrayInput
          name={name}
          value={value}
          integer={itemControl === 'integer-tags'}
          onChange={onChange}
        />
      ) : itemControl === 'regex' ? (
        <RegexArrayInput value={value} onChange={onChange} />
      ) : objectItems ? (
        <ObjectArray value={value} itemSchema={itemSchema} root={root} onChange={onChange} />
      ) : (
        <PrimitiveArray value={value} itemSchema={itemSchema} root={root} onChange={onChange} />
      )}
    </section>
  )
}

function ScalarField({
  name,
  value,
  schema,
  onChange,
}: {
  name: string
  value: unknown
  schema: JsonSchema
  onChange: (next: unknown) => void
}) {
  const { labels, descriptions, options, systemGenerated } = useConfigCopy()
  const label = labels[name] ?? schema.title ?? name
  const description = schema.readOnly ? systemGenerated : descriptions[name]
  if (schema.type === 'boolean') {
    return (
      <Switch
        checked={Boolean(value)}
        onCheckedChange={onChange}
        label={label}
        detail={description}
        disabled={schema.readOnly}
        className="min-h-9 py-1.5"
      />
    )
  }
  return (
    <label className="flex min-w-0 flex-col gap-1" title={description}>
      <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-600">
        {label}
        {schema.readOnly ? <LockKeyhole size={13} className="text-slate-400" /> : null}
      </span>
      {schema.enum ? (
        <Select
          value={String(value ?? '')}
          onValueChange={onChange}
          options={schema.enum.map((option, index) => ({
            value: String(option),
            label: schema['x-enum-labels']?.[index] ?? options[String(option)] ?? String(option),
          }))}
          disabled={schema.readOnly}
          className="h-8.5"
        />
      ) : (
        <input
          type={schema.type === 'number' || schema.type === 'integer' ? 'number' : 'text'}
          value={String(value ?? '')}
          min={schema.minimum}
          max={schema.maximum}
          step={schema.multipleOf ?? (schema.type === 'integer' ? 1 : undefined)}
          minLength={schema.minLength}
          maxLength={schema.maxLength}
          placeholder={description}
          disabled={schema.readOnly}
          onChange={(event) =>
            onChange(
              schema.type === 'number' || schema.type === 'integer'
                ? Number(event.target.value)
                : event.target.value,
            )
          }
          className={cn(
            'h-8.5 w-full rounded-[5px] border border-slate-200 bg-white px-2.5',
            'text-[13px] text-slate-700 outline-none focus:border-blue-300',
            'focus:ring-3 focus:ring-blue-500/10 disabled:bg-slate-100 disabled:text-slate-400',
          )}
        />
      )}
      {description ? (
        <small className="text-xs leading-4 text-slate-400">{description}</small>
      ) : null}
    </label>
  )
}

function ConfigField({
  name,
  value,
  schema: rawSchema,
  root,
  onChange,
  depth,
}: {
  name: string
  value: unknown
  schema: JsonSchema
  root: JsonSchema
  onChange: (next: unknown) => void
  depth: number
}) {
  const schema = typedSchema(rawSchema, value, root)
  if (schema.type === 'array' || Array.isArray(value)) {
    return (
      <ArrayField
        name={name}
        value={Array.isArray(value) ? value : []}
        schema={schema}
        root={root}
        onChange={onChange}
        depth={depth}
      />
    )
  }
  if (schema.type === 'object' || schema.properties || isObject(value)) {
    const objectValue = isObject(value) ? value : {}
    return (
      <section
        className={cn(
          depth === 0
            ? 'py-4 first:pt-0 last:pb-0'
            : 'col-span-full border-l-2 border-slate-100 pl-2.5',
        )}
      >
        <div className="mb-2">
          <FieldHeading name={name} schema={schema} compact={depth > 0} />
        </div>
        <ObjectFields
          value={objectValue}
          schema={schema}
          root={root}
          depth={depth + 1}
          onChange={onChange}
        />
      </section>
    )
  }
  return (
    <div className={cn(depth === 0 ? 'py-4 first:pt-0 last:pb-0' : '')}>
      <ScalarField name={name} value={value} schema={schema} onChange={onChange} />
    </div>
  )
}

export function ConfigTreeForm({
  value,
  schema,
  onChange,
}: {
  value: ConfigObject
  schema: JsonSchema
  onChange: (next: ConfigObject) => void
}) {
  return <ObjectFields value={value} schema={schema} root={schema} depth={0} onChange={onChange} />
}

export function ConfigJsonEditor({
  value,
  onChange,
}: {
  value: ConfigObject
  onChange: (next: ConfigObject) => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = useState<string | null>(null)
  const emitted = useRef('')

  useEffect(() => {
    const serialized = JSON.stringify(value)
    if (serialized === emitted.current) {
      emitted.current = ''
      return
    }
    setText(JSON.stringify(value, null, 2))
    setError(null)
  }, [value])

  return (
    <div>
      <textarea
        className={cn(
          'min-h-127.5 w-full resize-y rounded-[5px] border border-slate-700',
          'bg-slate-900 p-3 font-mono text-xs leading-5 text-blue-100 outline-none',
          'focus:border-blue-500 focus:ring-3 focus:ring-blue-500/10',
          error && 'border-rose-500',
        )}
        value={text}
        onChange={(event) => {
          const nextText = event.target.value
          setText(nextText)
          try {
            const parsed = JSON.parse(nextText)
            if (!isObject(parsed)) throw new Error('root-not-object')
            emitted.current = JSON.stringify(parsed)
            onChange(parsed)
            setError(null)
          } catch {
            setError(t('settings.invalidJson'))
          }
        }}
        spellCheck={false}
        rows={25}
      />
      {error ? <p className="mt-2 text-xs text-rose-600">{error}</p> : null}
    </div>
  )
}
