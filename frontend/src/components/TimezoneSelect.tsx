import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { accountRequest } from '../api/client'
import { useAccountScope } from '../hooks/useAccountScope'
import type { AppConfig, JsonSchema } from '../types'
import { Select } from './ui'

/** Timezone catalog shared with the settings form, which reads it from the same schema. */
function timezoneOptions(schema: JsonSchema | undefined) {
  const timezone = schema?.$defs?.ConfigExport?.properties?.timezone
  const names = timezone?.enum ?? []
  const labels = timezone?.['x-enum-labels'] ?? []

  return names.map((name, index) => ({
    value: String(name),
    label: labels[index] ?? String(name),
  }))
}

export function TimezoneSelect({
  value,
  onValueChange,
}: {
  value: string
  onValueChange: (value: string) => void
}) {
  const accountId = useAccountScope()
  const config = useQuery({
    queryKey: ['config', accountId],
    queryFn: () => accountRequest<AppConfig>(accountId, '/api/v1/config'),
  })
  const options = useMemo(() => timezoneOptions(config.data?.schema), [config.data])

  return (
    <Select
      value={value}
      onValueChange={onValueChange}
      options={options}
      disabled={!options.length}
    />
  )
}
