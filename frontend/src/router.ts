import { createRouter, createWebHistory } from 'vue-router'

const DashboardPage = () => import('./pages/DashboardPage.vue')
const RulesPage = () => import('./pages/RulesPage.vue')
const ButtonRulesPage = () => import('./pages/ButtonRulesPage.vue')
const HistoryPage = () => import('./pages/HistoryPage.vue')
const ExportsPage = () => import('./pages/ExportsPage.vue')
const LogsPage = () => import('./pages/LogsPage.vue')
const SettingsPage = () => import('./pages/SettingsPage.vue')

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: DashboardPage },
    { path: '/rules', name: 'rules', component: RulesPage },
    { path: '/automations', name: 'automations', component: ButtonRulesPage },
    { path: '/history', name: 'history', component: HistoryPage },
    { path: '/exports', name: 'exports', component: ExportsPage },
    { path: '/logs', name: 'logs', component: LogsPage },
    { path: '/settings', name: 'settings', component: SettingsPage },
  ],
})

