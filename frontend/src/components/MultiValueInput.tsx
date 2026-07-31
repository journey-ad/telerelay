import { X } from 'lucide-react'
import { useRef, useState, type KeyboardEvent } from 'react'
import { cn } from '../utils/cn'

type Scalar = string | number

interface MultiValueInputProps<T extends Scalar> {
  value: T[]
  onChange: (value: T[]) => void
  ariaLabel: string
  placeholder?: string
  invalidMessage?: string
  parse?: (value: string) => T | null
  format?: (value: T) => string
}

export function MultiValueInput<T extends Scalar>({
  value,
  onChange,
  ariaLabel,
  placeholder,
  invalidMessage,
  parse,
  format = String,
}: MultiValueInputProps<T>) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  function setValidationError(message: string) {
    setError(message)
    inputRef.current?.setCustomValidity(message)
  }

  function commit(rawValue = draft) {
    const tokens = rawValue
      .split(/[\n,，]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    if (tokens.length === 0) {
      setDraft('')
      setValidationError('')
      return
    }

    const existing = new Set(value.map(format))
    const next = [...value]
    const invalid: string[] = []
    for (const token of tokens) {
      const parsed = parse ? parse(token) : (token as T)
      if (parsed === null) {
        invalid.push(token)
        continue
      }
      const key = format(parsed)
      if (!existing.has(key)) {
        existing.add(key)
        next.push(parsed)
      }
    }

    if (next.length !== value.length) onChange(next)
    setDraft(invalid.join(', '))
    setValidationError(invalid.length > 0 ? (invalidMessage ?? '') : '')
  }

  function remove(index: number) {
    onChange(value.filter((_, itemIndex) => itemIndex !== index))
    inputRef.current?.focus()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return
    if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
      event.preventDefault()
      commit()
      return
    }
    if (event.key === 'Backspace' && !draft && value.length > 0) {
      event.preventDefault()
      remove(value.length - 1)
    }
  }

  return (
    <div>
      <div
        className={cn(
          'flex min-h-19 w-full flex-wrap content-start items-center gap-1.5 rounded-[5px] border',
          'bg-white px-2 py-2 transition-shadow focus-within:ring-3',
          error
            ? 'border-rose-300 focus-within:border-rose-400 focus-within:ring-rose-500/10'
            : 'border-slate-200 focus-within:border-blue-300 focus-within:ring-blue-500/10',
        )}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((item, index) => {
          const label = format(item)
          return (
            <span
              key={`${label}:${index}`}
              className={cn(
                'flex h-7 max-w-full items-center gap-1 rounded border border-slate-200',
                'bg-slate-50 pl-2 text-xs text-slate-700',
              )}
            >
              <span className="max-w-52 truncate">{label}</span>
              <button
                type="button"
                className="grid size-7 shrink-0 place-items-center text-slate-400 hover:text-rose-600"
                aria-label={`${ariaLabel}: ${label}`}
                onClick={(event) => {
                  event.stopPropagation()
                  remove(index)
                }}
              >
                <X size={13} />
              </button>
            </span>
          )
        })}
        <input
          ref={inputRef}
          className="h-7 min-w-28 flex-1 border-0 bg-transparent px-1 text-[13px] text-slate-700 outline-none"
          value={draft}
          aria-label={ariaLabel}
          aria-invalid={Boolean(error)}
          placeholder={value.length === 0 ? placeholder : undefined}
          onChange={(event) => {
            setDraft(event.target.value)
            setValidationError('')
          }}
          onKeyDown={handleKeyDown}
          onBlur={() => commit()}
          onPaste={(event) => {
            const pasted = event.clipboardData.getData('text')
            if (!/[\n,，]/.test(pasted)) return
            event.preventDefault()
            commit([draft, pasted].filter(Boolean).join('\n'))
          }}
        />
      </div>
      {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : null}
    </div>
  )
}
