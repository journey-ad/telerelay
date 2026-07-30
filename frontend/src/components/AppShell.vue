<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { request, json } from '../api/client'
import { useSessionStore } from '../stores/session'
import { useEvents } from '../composables/useEvents'

const { t, locale } = useI18n()
const route = useRoute()
const session = useSessionStore()
const queryClient = useQueryClient()
const { connected: eventsConnected } = useEvents(() => queryClient.invalidateQueries({ queryKey: ['bot-status'] }))

const statusQuery = useQuery({
  queryKey: ['bot-status'],
  queryFn: () => request<any>('/api/v1/bot/status'),
  refetchInterval: 5000,
})

const nav = computed(() => [
  { to: '/', label: t('nav.dashboard'), icon: '⌂' },
  { to: '/rules', label: t('nav.rules'), icon: '⇄' },
  { to: '/automations', label: t('nav.automations'), icon: '✦' },
  { to: '/history', label: t('nav.history'), icon: '▤' },
  { to: '/exports', label: t('nav.exports'), icon: '↗' },
  { to: '/logs', label: t('nav.logs'), icon: '▥' },
  { to: '/settings', label: t('nav.settings'), icon: '⚙' },
])

const botOnline = computed(() => Boolean(statusQuery.data.value?.is_connected))
const botRunning = computed(() => Boolean(statusQuery.data.value?.is_running))

async function control(action: 'start' | 'stop' | 'restart') {
  await request(`/api/v1/bot/${action}`, json('POST'))
  await queryClient.invalidateQueries({ queryKey: ['bot-status'] })
}

function toggleLocale() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem('telerelay.locale', locale.value)
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-lockup shell-brand">
        <div class="signal-logo"><i></i><i></i><i></i></div>
        <div><span class="brand-kicker">{{ t('brand.kicker') }}</span><strong>{{ t('brand.name') }}</strong><small>{{ t('brand.console') }}</small></div>
      </div>
      <div class="node-status" :class="{ online: botOnline }">
        <span class="pulse-dot"></span><div><strong>{{ botOnline ? t('common.online') : t('common.offline') }}</strong><small>TELEGRAM NODE / {{ botRunning ? 'ACTIVE' : 'IDLE' }}</small></div>
      </div>
      <nav class="main-nav">
        <span class="nav-label">OPERATIONS</span>
        <RouterLink v-for="item in nav.slice(0, 5)" :key="item.to" :to="item.to" class="nav-item" :class="{ active: route.path === item.to }"><b>{{ item.icon }}</b><span>{{ item.label }}</span></RouterLink>
        <span class="nav-label lower">OBSERVABILITY</span>
        <RouterLink v-for="item in nav.slice(5)" :key="item.to" :to="item.to" class="nav-item" :class="{ active: route.path === item.to }"><b>{{ item.icon }}</b><span>{{ item.label }}</span></RouterLink>
      </nav>
      <div class="sidebar-foot"><span><i class="pulse-dot"></i> {{ eventsConnected ? 'EVENT STREAM' : 'POLLING MODE' }}</span><button @click="session.logout">SIGN OUT</button></div>
    </aside>
    <main class="main-stage">
      <header class="topbar">
        <div class="breadcrumb"><span>TELEGRAM /</span><strong>{{ nav.find((item) => item.to === route.path)?.label ?? t('brand.console') }}</strong></div>
        <div class="top-actions"><button class="text-button" @click="toggleLocale">{{ locale === 'zh' ? 'EN' : '中' }}</button><button class="icon-button" title="Refresh" @click="queryClient.invalidateQueries()">↻</button><button class="avatar">TR</button></div>
      </header>
      <div class="page-frame"><RouterView /></div>
    </main>
  </div>
</template>

