import { useOutletContext } from 'react-router-dom'

export interface AccountScopeContext {
  accountId: string
}

export function useAccountScope(): string {
  return useOutletContext<AccountScopeContext>().accountId
}
