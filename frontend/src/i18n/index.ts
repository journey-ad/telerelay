import { createI18n } from 'vue-i18n'

const zh = {
  brand: { kicker: 'TELEGRAM RELAY SYSTEM', name: 'TeleRelay', console: '中继控制台' },
  nav: {
    dashboard: '总览', rules: '转发规则', automations: '按钮自动化', history: '消息历史',
    exports: '数据导出', logs: '运行日志', settings: '系统设置',
  },
  common: {
    online: '已连接', offline: '未连接', running: '运行中', stopped: '已停止',
    save: '保存', create: '新建', edit: '编辑', delete: '删除', cancel: '取消',
    refresh: '刷新', start: '启动', stop: '停止', restart: '重启', loading: '加载中',
    enabled: '启用', disabled: '停用', actions: '操作', all: '全部', search: '搜索',
    noData: '暂无数据', confirmDelete: '确认删除这条记录？', copied: '已复制',
  },
  dashboard: {
    title: '信号总览', subtitle: 'Telegram 消息链路、队列与规则的实时运行状态',
    forwarded: '已转发', filtered: '已过滤', total: '处理总量', queued: '队列积压',
    trend: '近 14 天流量', ruleHealth: '规则吞吐', control: '运行控制', recent: '最新事件',
  },
  login: { title: '进入中继控制台', subtitle: '使用 WEB_AUTH 凭据连接此节点', username: '用户名', password: '密码', submit: '连接节点', failed: '认证失败' },
  rules: { title: '转发规则', subtitle: '定义消息从何处进入、如何筛选以及发送到哪里', new: '新建规则' },
  automations: { title: '按钮自动化', subtitle: '在 User Session 中匹配并点击 Telegram 回调按钮', new: '新建自动化' },
  history: { title: '消息历史', subtitle: '检索已经由 TeleRelay 处理和转发的消息' },
  exports: { title: '数据导出', subtitle: '创建一次性导出并管理持久化定时任务' },
  logs: { title: '运行日志', subtitle: '实时查看 Telegram、队列与导出模块事件' },
  settings: { title: '系统设置', subtitle: 'Telegram 会话、运行配置和备份' },
}

const en = {
  brand: { kicker: 'TELEGRAM RELAY SYSTEM', name: 'TeleRelay', console: 'Relay Console' },
  nav: { dashboard: 'Overview', rules: 'Relay rules', automations: 'Button automation', history: 'History', exports: 'Exports', logs: 'Runtime logs', settings: 'Settings' },
  common: { online: 'Connected', offline: 'Offline', running: 'Running', stopped: 'Stopped', save: 'Save', create: 'Create', edit: 'Edit', delete: 'Delete', cancel: 'Cancel', refresh: 'Refresh', start: 'Start', stop: 'Stop', restart: 'Restart', loading: 'Loading', enabled: 'Enabled', disabled: 'Disabled', actions: 'Actions', all: 'All', search: 'Search', noData: 'No data', confirmDelete: 'Delete this item?', copied: 'Copied' },
  dashboard: { title: 'Signal overview', subtitle: 'Live health of Telegram links, queue and routing rules', forwarded: 'Forwarded', filtered: 'Filtered', total: 'Processed', queued: 'Queue depth', trend: '14-day traffic', ruleHealth: 'Rule throughput', control: 'Runtime control', recent: 'Recent events' },
  login: { title: 'Enter relay console', subtitle: 'Connect using WEB_AUTH credentials', username: 'Username', password: 'Password', submit: 'Connect node', failed: 'Authentication failed' },
  rules: { title: 'Relay rules', subtitle: 'Control where messages enter, how they are filtered and where they go', new: 'New rule' },
  automations: { title: 'Button automation', subtitle: 'Match and click Telegram callback buttons in User Session mode', new: 'New automation' },
  history: { title: 'Message history', subtitle: 'Search messages processed and forwarded by TeleRelay' },
  exports: { title: 'Data exports', subtitle: 'Run one-off exports and manage persistent schedules' },
  logs: { title: 'Runtime logs', subtitle: 'Inspect Telegram, queue and export events in real time' },
  settings: { title: 'System settings', subtitle: 'Telegram session, runtime configuration and backup' },
}

export const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('telerelay.locale') ?? 'zh',
  fallbackLocale: 'en',
  messages: { zh, en },
})

