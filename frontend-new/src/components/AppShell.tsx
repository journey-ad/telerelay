import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Archive,
  Bot,
  ChevronDown,
  FileClock,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MoreHorizontal,
  RefreshCw,
  Route,
  Settings,
  Sparkles,
  X,
} from 'lucide-react'
import { useCallback, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { request } from '../api/client'
import { useEvents } from '../hooks/useEvents'
import type { BotStatus, SessionInfo } from '../types'
import { cn } from '../utils/cn'
import { Brand } from './Brand'
import { IconButton } from './ui'

const navigation = [
  { to: '/', label: '总览', icon: LayoutDashboard, end: true },
  { to: '/rules', label: '转发规则', icon: Route },
  { to: '/automations', label: '按钮自动化', icon: Sparkles },
  { to: '/history', label: '消息记录', icon: History },
  { to: '/exports', label: '导出中心', icon: Archive },
  { to: '/logs', label: '运行日志', icon: FileClock },
  { to: '/settings', label: '设置', icon: Settings },
]

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `mb-1 flex h-10 items-center gap-3 rounded-[5px] px-3 text-xs font-medium transition ${
    isActive
      ? 'bg-blue-50 text-blue-700 shadow-[inset_2px_0_#2563eb] [&>svg]:text-blue-600'
      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700 [&>svg]:text-slate-400'
  }`

export function AppShell({ session, onLogout }: { session: SessionInfo; onLogout: () => void }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const queryClient = useQueryClient()
  const location = useLocation()
  const statusQuery = useQuery({
    queryKey: ['bot-status'],
    queryFn: () => request<BotStatus>('/api/v1/bot/status'),
    refetchInterval: 5000,
  })
  const invalidateLiveData = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['bot-status'] })
    void queryClient.invalidateQueries({ queryKey: ['stats'] })
  }, [queryClient])
  const { connected } = useEvents(invalidateLiveData)
  const current = navigation.find((item) => item.to === location.pathname) ?? navigation[0]
  const online = Boolean(statusQuery.data?.is_connected)

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
            label="关闭菜单"
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
            <small className="text-[8px] font-bold text-slate-400">Telegram node</small>
            <strong className="mt-0.5 truncate text-[11px] text-slate-700">
              {online ? '连接正常' : '等待连接'}
            </strong>
          </span>
          <span
            className={cn(
              'size-2 rounded-full',
              online ? 'bg-emerald-500 ring-3 ring-emerald-500/10' : 'bg-slate-300',
            )}
          />
        </div>
        <nav className="flex-1 overflow-auto px-3 py-4">
          <span className="block px-2.5 pb-2 text-[9px] font-bold text-slate-400 uppercase">
            工作台
          </span>
          {navigation.slice(0, 5).map(({ icon: Icon, ...item }) => (
            <NavLink
              key={item.to}
              {...item}
              onClick={() => setMobileOpen(false)}
              className={navLinkClass}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
          <span className="mt-5 block px-2.5 pb-2 text-[9px] font-bold text-slate-400 uppercase">
            系统
          </span>
          {navigation.slice(5).map(({ icon: Icon, ...item }) => (
            <NavLink
              key={item.to}
              {...item}
              onClick={() => setMobileOpen(false)}
              className={navLinkClass}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-100 p-3.5">
          <div className="flex items-center gap-2 pb-3 text-[9px] text-slate-400">
            <Activity className="text-emerald-500" size={15} />
            <span>{connected ? '实时事件已连接' : '轮询模式'}</span>
          </div>
          <button
            className={cn(
              'flex h-8.5 w-full items-center gap-2.5 rounded-[5px] border-0',
              'bg-transparent px-2.5 text-[11px] text-slate-500',
              'hover:bg-rose-50 hover:text-rose-600',
            )}
            onClick={onLogout}
          >
            <LogOut size={16} />
            退出登录
          </button>
        </div>
      </aside>
      {mobileOpen ? (
        <button
          className="fixed inset-0 z-29 hidden border-0 bg-slate-900/35 max-md:block"
          aria-label="关闭菜单"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}

      <main className="ml-58 min-h-dvh pb-0 max-md:ml-0 max-md:pb-14.5">
        <header
          className={cn(
            'sticky top-0 z-20 flex h-14.5 items-center justify-between border-b',
            'border-slate-200 bg-white/95 px-6.5 backdrop-blur-xl max-md:h-13.5 max-md:px-3',
          )}
        >
          <IconButton
            label="打开菜单"
            icon={Menu}
            className="hidden max-md:grid"
            onClick={() => setMobileOpen(true)}
          />
          <div
            className={cn(
              'flex items-center gap-2 text-[11px] text-slate-400',
              'max-md:[&>span]:hidden max-md:[&>strong]:hidden',
            )}
          >
            <span>TeleRelay</span>
            <strong>/</strong>
            <b className="font-semibold text-slate-700">{current.label}</b>
          </div>
          <div className="flex items-center gap-2">
            <div className="mr-1 flex items-center gap-2 text-[10px] text-slate-500 max-md:hidden">
              <span
                className={cn(
                  'size-2 rounded-full',
                  online ? 'bg-emerald-500 ring-3 ring-emerald-500/10' : 'bg-slate-300',
                )}
              />
              {online ? '节点在线' : '节点离线'}
            </div>
            <IconButton
              label="刷新当前数据"
              icon={RefreshCw}
              onClick={() => void queryClient.invalidateQueries()}
            />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger
                className={cn(
                  'ml-1 flex h-9.5 items-center gap-2 rounded-md border border-slate-200',
                  'bg-white p-1 pr-2 text-slate-500 max-md:pr-1',
                )}
              >
                <span
                  className={cn(
                    'grid size-7.5 place-items-center rounded bg-blue-50',
                    'text-[10px] font-bold text-blue-700',
                  )}
                >
                  TR
                </span>
                <span className="flex min-w-18 flex-col items-start max-md:hidden">
                  <strong className="text-[10px] text-slate-700">TeleRelay</strong>
                  <small className="text-[8px] text-slate-400">
                    {session.session_type === 'user' ? '用户会话' : '机器人会话'}
                  </small>
                </span>
                <ChevronDown className="max-md:hidden" size={14} />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content
                  className={cn(
                    'z-100 min-w-40 rounded-md border border-slate-200',
                    'bg-white p-1 shadow-xl',
                  )}
                  align="end"
                  sideOffset={8}
                >
                  <DropdownMenu.Item
                    className={cn(
                      'flex h-8.5 items-center gap-2 rounded px-2 text-[11px]',
                      'text-slate-600 outline-none data-[highlighted]:bg-blue-50',
                      'data-[highlighted]:text-blue-700',
                    )}
                    onSelect={onLogout}
                  >
                    <LogOut size={16} />
                    退出登录
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </header>
        <div className="mx-auto w-full max-w-370 px-7 py-7 max-md:px-3.5 max-md:py-5">
          <Outlet />
        </div>
      </main>

      <nav
        className={cn(
          'fixed inset-x-0 bottom-0 z-25 hidden h-14.5 grid-cols-5 border-t',
          'border-slate-200 bg-white/95 backdrop-blur-xl max-md:grid',
        )}
      >
        {navigation.slice(0, 4).map(({ icon: Icon, ...item }) => (
          <NavLink
            key={item.to}
            {...item}
            className={({ isActive }) =>
              cn(
                'flex min-w-0 flex-col items-center justify-center gap-1',
                'text-[8px] no-underline',
                isActive ? 'text-blue-600' : 'text-slate-400',
              )
            }
          >
            <Icon size={19} />
            <span>{item.label}</span>
          </NavLink>
        ))}
        <button
          className={cn(
            'flex min-w-0 flex-col items-center justify-center gap-1',
            'border-0 bg-transparent text-[8px] text-slate-400',
          )}
          onClick={() => setMobileOpen(true)}
        >
          <MoreHorizontal size={20} />
          <span>更多</span>
        </button>
      </nav>
    </div>
  )
}
