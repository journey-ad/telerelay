import { AlertTriangle } from 'lucide-react'
import { useCallback, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { json, request } from '../api/client'
import { lines } from '../utils/parse'
import { cn } from '../utils/cn'
import { fieldClass } from './ui'

interface RegexValidationResponse {
  valid: boolean
  errors: Array<{ pattern: string; error: string }>
}

export function useRegexValidation() {
  const { t } = useTranslation()
  const requestId = useRef(0)
  const [errors, setErrors] = useState<string[]>([])
  const [validating, setValidating] = useState(false)
  const [valid, setValid] = useState<boolean | null>(null)

  const reset = useCallback(() => {
    requestId.current += 1
    setErrors([])
    setValidating(false)
    setValid(null)
  }, [])

  const validate = useCallback(
    async (value: string): Promise<boolean> => {
      const patterns = lines(value)
      const currentRequest = ++requestId.current

      if (patterns.length === 0) {
        setErrors([])
        setValidating(false)
        setValid(null)
        return true
      }

      setValidating(true)
      setValid(null)
      try {
        const result = await request<RegexValidationResponse>(
          '/api/v1/utils/validate-regex',
          json('POST', { patterns }),
        )
        if (currentRequest !== requestId.current) return false

        setErrors(result.errors.map(({ pattern, error }) => `${pattern}: ${error}`))
        setValid(result.valid)
        return result.valid
      } catch {
        if (currentRequest !== requestId.current) return false

        setErrors([t('validation.regexRequestFailed')])
        setValid(false)
        return false
      } finally {
        if (currentRequest === requestId.current) setValidating(false)
      }
    },
    [t],
  )

  return { errors, reset, valid, validate, validating }
}

type RegexValidation = ReturnType<typeof useRegexValidation>

export function RegexField({
  label,
  value,
  onChange,
  validation,
  rows = 4,
  placeholder,
  className,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  validation: RegexValidation
  rows?: number
  placeholder?: string
  className?: string
}) {
  const { t } = useTranslation()
  const inputId = useId()

  return (
    <div className={cn(fieldClass, className)}>
      <span>
        <label htmlFor={inputId}>{label}</label>
        <button
          type="button"
          disabled={validation.validating}
          className={cn(
            'ml-2 text-[11px]',
            validation.validating
              ? 'text-slate-400'
              : validation.valid === true
                ? 'text-emerald-600'
                : 'text-blue-600 hover:text-blue-800',
          )}
          onClick={() => void validation.validate(value)}
        >
          {validation.validating
            ? t('validation.validating')
            : validation.valid === true
              ? t('validation.valid')
              : t('validation.validate')}
        </button>
      </span>
      <textarea
        id={inputId}
        value={value}
        onChange={(event) => {
          onChange(event.target.value)
          validation.reset()
        }}
        rows={rows}
        placeholder={placeholder}
      />
      {validation.errors.length > 0 ? (
        <ul className="mt-1 space-y-0.5 rounded-[5px] border border-rose-100 bg-rose-50 p-2">
          {validation.errors.map((error, index) => (
            <li
              key={`${index}:${error}`}
              className="flex items-start gap-1.5 text-[11px] text-rose-700"
            >
              <AlertTriangle size={12} className="mt-px shrink-0" />
              {error}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
