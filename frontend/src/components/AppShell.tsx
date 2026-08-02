import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Archive,
  Bot,
  FileClock,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  MoreHorizontal,
  RefreshCw,
  Route,
  Settings,
  Sparkles,
  X,
} from 'lucide-react'
import { useCallback, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { accountRequest, json, request } from '../api/client'
import { useEvents } from '../hooks/useEvents'
import type { BotStatus, RelayEvent, TelegramAccount } from '../types'
import { cn } from '../utils/cn'
import { AccountSwitcher } from './AccountSwitcher'
import { Brand } from './Brand'
import { LanguageToggle } from './LanguageToggle'
import { IconButton } from './ui'

const navigation = [
  { to: '/', label: 'nav.dashboard', icon: LayoutDashboard, end: true },
  { to: '/telegram', label: 'nav.telegram', icon: MessageSquareText },
  { to: '/rules', label: 'nav.rules', icon: Route },
  { to: '/automations', label: 'nav.automations', icon: Sparkles },
  { to: '/history', label: 'nav.history', icon: History },
  { to: '/exports', label: 'nav.exports', icon: Archive },
  { to: '/logs', label: 'nav.logs', icon: FileClock },
  { to: '/settings', label: 'nav.settings', icon: Settings },
] as const

const mobileNavigation = [
  { ...navigation[0], label: 'nav.mobile.dashboard' },
  { ...navigation[1], label: 'nav.mobile.telegram' },
  { ...navigation[2], label: 'nav.mobile.rules' },
  { ...navigation[3], label: 'nav.mobile.automations' },
] as const

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `mb-1 flex h-10 items-center gap-3 rounded-[5px] px-3 text-sm font-medium transition ${
    isActive
      ? 'bg-blue-50 text-blue-700 shadow-[inset_2px_0_#2563eb] [&>svg]:text-blue-600'
      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700 [&>svg]:text-slate-400'
  }`

export function AppShell({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const queryClient = useQueryClient()
  const location = useLocation()
  const accountsQuery = useQuery({
    queryKey: ['telegram-accounts'],
    queryFn: () => request<TelegramAccount[]>('/api/v1/telegram-accounts'),
    refetchInterval: 30_000,
  })
  const activeAccount =
    accountsQuery.data?.find((account) => account.active) ?? accountsQuery.data?.[0]
  const accountId = activeAccount?.id ?? ''
  const activeAccountKind = activeAccount?.kind ?? 'user'
  const botUnavailableRoutes = ['/telegram', '/automations', '/exports']
  const workspaceNavigation = navigation
    .slice(0, 6)
    .filter((item) => activeAccountKind !== 'bot' || !botUnavailableRoutes.includes(item.to))
  const systemNavigation = navigation.slice(6)
  const visibleMobileNavigation = mobileNavigation.filter(
    (item) => activeAccountKind !== 'bot' || !botUnavailableRoutes.includes(item.to),
  )
  const statusQuery = useQuery({
    queryKey: ['bot-status', accountId],
    queryFn: () => accountRequest<BotStatus>(accountId, '/api/v1/bot/status'),
    enabled: Boolean(accountId),
    refetchInterval: 15_000,
  })
  const invalidateLiveData = useCallback(
    (event: RelayEvent) => {
      if (event.type === 'bot') {
        void queryClient.invalidateQueries({ queryKey: ['bot-status'] })
      }
      if (event.type === 'stats') {
        void queryClient.invalidateQueries({ queryKey: ['stats'] })
      }
      if (event.type === 'telegram-account') {
        void queryClient.invalidateQueries({ queryKey: ['telegram-accounts'] })
      }
      if (event.type === 'telegram-auth') {
        void queryClient.invalidateQueries({ queryKey: ['telegram-auth'] })
      }
    },
    [queryClient],
  )
  useEvents(invalidateLiveData, { accountId: accountId || undefined })
  const refreshData = useCallback(async () => {
    if (accountId && statusQuery.data?.is_connected) {
      try {
        const refreshed = await accountRequest<TelegramAccount>(
          accountId,
          `/api/v1/telegram-accounts/${accountId}/refresh`,
          json('POST'),
        )
        queryClient.setQueryData<TelegramAccount[]>(['telegram-accounts'], (current) =>
          current?.map((account) => (account.id === refreshed.id ? refreshed : account)),
        )
      } catch {}
    }
    await queryClient.invalidateQueries()
  }, [accountId, queryClient, statusQuery.data?.is_connected])
  const current = navigation.find((item) => item.to === location.pathname) ?? navigation[0]
  const online = Boolean(statusQuery.data?.is_connected)
  const nodeLabel =
    typeof statusQuery.data?.connected_account_count === 'number' &&
    accountsQuery.data !== undefined
      ? t('node.accountsConnected', {
          connected: statusQuery.data.connected_account_count,
          total: accountsQuery.data.length,
        })
      : t(online ? 'node.connected' : 'node.waiting')
  const previewRoute =
    location.pathname === '/telegram' || location.pathname.startsWith('/telegram/')

  return (
    <div className="min-h-dvh">
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-30 flex w-58 flex-col border-r border-slate-200',
          'bg-white transition-transform max-md:w-62 max-md:-translate-x-full max-md:shadow-2xl',
          mobileOpen && 'max-md:translate-x-0',
        )}
      >
        <div className="flex h-19 items-center justify-between border-b border-slate-100 px-5">
          <Brand />
          <IconButton
            label={t('nav.closeMenu')}
            icon={X}
            className="hidden max-md:grid"
            onClick={() => setMobileOpen(false)}
          />
        </div>
        <div
          className={cn(
            'mx-3.5 mt-4.5 mb-2 grid grid-cols-[34px_1fr_8px] items-center gap-2',
            'rounded-md border border-blue-100 bg-blue-50/60 p-2.5',
          )}
        >
          <span
            className={cn(
              'grid size-8.5 place-items-center rounded-[5px] border border-slate-200 bg-white',
              online ? 'text-blue-600' : 'text-slate-400',
            )}
          >
            <Bot size={19} />
          </span>
          <span className="flex min-w-0 flex-col">
            <small className="text-xs font-bold text-slate-400">{t('node.title')}</small>
            <strong className="mt-0.5 truncate text-[13px] text-slate-700">{nodeLabel}</strong>
          </span>
          <span
            className={cn(
              'size-2 rounded-full',
              online ? 'bg-emerald-500 ring-3 ring-emerald-500/10' : 'bg-slate-300',
            )}
          />
        </div>
        <nav className="flex-1 overflow-auto px-3 py-4">
          <span className="block px-2.5 pb-2 text-[13px] font-bold text-slate-400 uppercase">
            {t('nav.workspace')}
          </span>
          {workspaceNavigation.map(({ icon: Icon, ...item }) => (
            <NavLink
              key={item.to}
              {...item}
              onClick={() => setMobileOpen(false)}
              className={navLinkClass}
            >
              <Icon size={18} />
              <span>{t(item.label)}</span>
            </NavLink>
          ))}
          <span className="mt-5 block px-2.5 pb-2 text-[13px] font-bold text-slate-400 uppercase">
            {t('nav.system')}
          </span>
          {systemNavigation.map(({ icon: Icon, ...item }) => (
            <NavLink
              key={item.to}
              {...item}
              onClick={() => setMobileOpen(false)}
              className={navLinkClass}
            >
              <Icon size={18} />
              <span>{t(item.label)}</span>
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-3.5">
          <button
            className={cn(
              'flex h-8.5 w-full items-center gap-2.5 rounded-[5px] border-0',
              'bg-transparent px-2.5 text-[13px] text-slate-500',
              'hover:bg-rose-50 hover:text-rose-600',
            )}
            onClick={onLogout}
          >
            <LogOut size={16} />
            {t('nav.logout')}
          </button>
        </div>
      </aside>
      {mobileOpen ? (
        <button
          className="fixed inset-0 z-29 hidden border-0 bg-slate-900/35 max-md:block"
          aria-label={t('nav.closeMenu')}
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <main
        className={cn(
          'ml-58 max-md:ml-0',
          previewRoute
            ? 'flex h-dvh min-h-0 flex-col overflow-hidden max-md:pb-14.5'
            : 'min-h-dvh pb-0 max-md:pb-14.5',
        )}
      >
        <header
          className={cn(
            'sticky top-0 z-20 flex h-14.5 shrink-0 items-center justify-between border-b',
            'border-slate-200 bg-white/95 px-6.5 backdrop-blur-xl max-md:h-13.5 max-md:px-3',
          )}
        >
          <IconButton
            label={t('nav.openMenu')}
            icon={Menu}
            className="hidden max-md:grid"
            onClick={() => setMobileOpen(true)}
          />
          <div
            className={cn(
              'flex items-center gap-2 text-[13px] text-slate-400',
              'max-md:[&>span]:hidden max-md:[&>strong]:hidden',
            )}
          >
            <span>TeleRelay</span>
            <strong>/</strong>
            <b className="font-semibold text-slate-700">{t(current.label)}</b>
          </div>
          <div className="flex items-center gap-2">
            <div className="mr-1 flex items-center gap-2 text-xs text-slate-500 max-md:hidden">
              <span
                className={cn(
                  'size-2 rounded-full',
                  online ? 'bg-emerald-500 ring-3 ring-emerald-500/10' : 'bg-slate-300',
                )}
              />
              {t(online ? 'node.online' : 'node.offline')}
            </div>
            <LanguageToggle className="max-md:hidden" />
            <IconButton
              label={t('nav.refresh')}
              icon={RefreshCw}
              className="max-md:hidden"
              onClick={refreshData}
            />
            <AccountSwitcher onLogout={onLogout} onRefresh={refreshData} />
          </div>
        </header>
        <div
          className={cn(
            'mx-auto w-full max-w-370 px-7 py-7 max-md:px-3.5 max-md:py-5',
            previewRoute && 'flex min-h-0 flex-1 flex-col',
          )}
        >
          {accountId ? <Outlet key={accountId} context={{ accountId }} /> : null}
        </div>
      </main>

      <nav
        className={cn(
          'fixed inset-x-0 bottom-0 z-25 hidden h-14.5 grid-cols-5 border-t',
          'border-slate-200 bg-white/95 backdrop-blur-xl max-md:grid',
          activeAccountKind === 'bot' && 'grid-cols-3',
        )}
      >
        {visibleMobileNavigation.map(({ icon: Icon, label, ...item }) => (
          <NavLink
            key={item.to}
            {...item}
            className={({ isActive }) =>
              cn(
                'flex min-w-0 flex-col items-center justify-center gap-1',
                'text-[11px] no-underline',
                isActive ? 'text-blue-600' : 'text-slate-400',
              )
            }
          >
            <Icon size={19} />
            <span className="w-full truncate px-0.5 text-center leading-none">{t(label)}</span>
          </NavLink>
        ))}
        <button
          className={cn(
            'flex min-w-0 flex-col items-center justify-center gap-1',
            'border-0 bg-transparent text-xs text-slate-400',
          )}
          onClick={() => setMobileOpen(true)}
        >
          <MoreHorizontal size={20} />
          <span className="w-full truncate px-0.5 text-center leading-none">{t('nav.more')}</span>
        </button>
      </nav>
    </div>
  )
}
