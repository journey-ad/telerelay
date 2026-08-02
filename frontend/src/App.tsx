import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { request } from './api/client'
import { clearCredentials } from './api/credentials'
import { AppShell } from './components/AppShell'
import { Brand } from './components/Brand'
import { Login } from './components/Login'
import type { SessionInfo } from './types'
import { cn } from './utils/cn'

const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((module) => ({ default: module.DashboardPage })),
)
const RulesPage = lazy(() =>
  import('./pages/RulesPage').then((module) => ({ default: module.RulesPage })),
)
const AutomationsPage = lazy(() =>
  import('./pages/AutomationsPage').then((module) => ({ default: module.AutomationsPage })),
)
const HistoryPage = lazy(() =>
  import('./pages/HistoryPage').then((module) => ({ default: module.HistoryPage })),
)
const TelegramPreviewPage = lazy(() =>
  import('./pages/TelegramPreviewPage').then((module) => ({ default: module.TelegramPreviewPage })),
)
const ExportsPage = lazy(() =>
  import('./pages/ExportsPage').then((module) => ({ default: module.ExportsPage })),
)
const LogsPage = lazy(() =>
  import('./pages/LogsPage').then((module) => ({ default: module.LogsPage })),
)
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((module) => ({ default: module.SettingsPage })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 15_000, refetchOnWindowFocus: false },
  },
})

function Console({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const page = (children: ReactNode) => (
    <Suspense
      fallback={
        <div
          className={cn(
            'flex min-h-[60vh] items-center justify-center gap-3',
            'text-xs text-slate-500',
          )}
        >
          <span
            className={cn(
              'size-5 animate-spin rounded-full border-2',
              'border-blue-100 border-t-blue-600',
            )}
          />
          {t('common.loading')}
        </div>
      }
    >
      {children}
    </Suspense>
  )
  const router = createBrowserRouter([
    {
      element: <AppShell onLogout={onLogout} />,
      children: [
        { path: '/', element: page(<DashboardPage />) },
        { path: '/telegram', element: page(<TelegramPreviewPage />) },
        { path: '/rules', element: page(<RulesPage />) },
        { path: '/automations', element: page(<AutomationsPage />) },
        { path: '/history', element: page(<HistoryPage />) },
        { path: '/exports', element: page(<ExportsPage />) },
        { path: '/logs', element: page(<LogsPage />) },
        { path: '/settings', element: page(<SettingsPage />) },
      ],
    },
  ])
  return <RouterProvider router={router} />
}

export default function App() {
  const { t } = useTranslation()
  const [ready, setReady] = useState(false)
  const [session, setSession] = useState<SessionInfo | null>(null)

  useEffect(() => {
    request<SessionInfo>('/api/v1/session')
      .then(setSession)
      .catch(() => setSession(null))
      .finally(() => setReady(true))
  }, [])

  function logout() {
    clearCredentials()
    setSession(null)
    queryClient.clear()
  }

  if (!ready) {
    return (
      <main
        className={cn(
          'flex min-h-dvh flex-col items-center justify-center gap-6',
          'bg-slate-50 text-xs text-slate-500',
        )}
      >
        <Brand />
        <span
          className={cn(
            'size-6 animate-spin rounded-full border-2',
            'border-blue-100 border-t-blue-600',
          )}
        />
        <p>{t('node.connecting')}</p>
      </main>
    )
  }

  return (
    <QueryClientProvider client={queryClient}>
      {session ? <Console onLogout={logout} /> : <Login onAuthenticated={setSession} />}
    </QueryClientProvider>
  )
}
