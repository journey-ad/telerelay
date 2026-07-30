<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { json, request } from '../api/client'
import { useEvents } from '../composables/useEvents'

const { t } = useI18n()
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
const queryClient = useQueryClient()
const chartElement = ref<HTMLElement>()
let chart: ReturnType<typeof echarts.init> | undefined

const statusQuery = useQuery({ queryKey: ['bot-status'], queryFn: () => request<any>('/api/v1/bot/status'), refetchInterval: 4000 })
const statsQuery = useQuery({ queryKey: ['stats', 14], queryFn: () => request<any>('/api/v1/stats?days=14'), refetchInterval: 15000 })
const { recent } = useEvents(() => {
  queryClient.invalidateQueries({ queryKey: ['bot-status'] })
  queryClient.invalidateQueries({ queryKey: ['stats'] })
})

const status = computed(() => statusQuery.data.value ?? { stats: {}, queue: { counts: {} } })
const queueDepth = computed(() => Object.entries(status.value.queue?.counts ?? {}).filter(([key]) => key !== 'completed').reduce((total, [, value]) => total + Number(value), 0))
const metrics = computed(() => [
  { label: t('dashboard.forwarded'), value: status.value.stats?.forwarded ?? 0, hint: 'FORWARDED' },
  { label: t('dashboard.filtered'), value: status.value.stats?.filtered ?? 0, hint: 'FILTERED' },
  { label: t('dashboard.total'), value: status.value.stats?.total ?? 0, hint: 'TOTAL FLOW' },
  { label: t('dashboard.queued'), value: queueDepth.value, hint: status.value.queue?.pause_reason || 'DURABLE QUEUE' },
])

async function control(action: 'start' | 'stop' | 'restart') {
  await request(`/api/v1/bot/${action}`, json('POST'))
  await queryClient.invalidateQueries({ queryKey: ['bot-status'] })
}

function renderChart() {
  if (!chartElement.value || !statsQuery.data.value) return
  chart ??= echarts.init(chartElement.value)
  const daily = statsQuery.data.value.daily ?? []
  chart.setOption({
    backgroundColor: 'transparent',
    animationDuration: 700,
    grid: { left: 36, right: 16, top: 18, bottom: 28 },
    tooltip: { trigger: 'axis', backgroundColor: '#0b1713', borderColor: 'rgba(118,226,188,.25)', textStyle: { color: '#dce9e4', fontSize: 11 } },
    xAxis: { type: 'category', data: daily.map((item: any) => item.date.slice(5)), axisLine: { lineStyle: { color: 'rgba(157,202,185,.15)' } }, axisLabel: { color: '#63756e', fontSize: 9 }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#63756e', fontSize: 9 }, splitLine: { lineStyle: { color: 'rgba(157,202,185,.08)' } } },
    series: [
      { name: t('dashboard.forwarded'), type: 'line', smooth: true, showSymbol: false, data: daily.map((item: any) => item.forwarded), lineStyle: { color: '#76e2bc', width: 2 }, areaStyle: { color: 'rgba(118,226,188,.12)' } },
      { name: t('dashboard.filtered'), type: 'line', smooth: true, showSymbol: false, data: daily.map((item: any) => item.filtered), lineStyle: { color: '#ffb86a', width: 1.5 }, areaStyle: { color: 'rgba(255,184,106,.06)' } },
    ],
  })
}

watch(() => statsQuery.data.value, () => nextTick(renderChart), { deep: true })
const resize = () => chart?.resize()
window.addEventListener('resize', resize)
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>

<template>
  <section>
    <header class="page-heading">
      <div><p class="eyebrow">RELAY OBSERVATORY / LIVE</p><h1>{{ t('dashboard.title') }}</h1><p>{{ t('dashboard.subtitle') }}</p></div>
      <div class="status-banner"><span class="pulse-dot" :class="{ online: status.is_connected }"></span><div><strong>{{ status.is_connected ? t('common.online') : t('common.offline') }}</strong><br />{{ status.is_running ? 'RUNTIME ACTIVE' : 'RUNTIME IDLE' }}</div></div>
    </header>
    <div class="metric-grid"><article v-for="metric in metrics" :key="metric.label" class="metric-card"><span class="metric-label">{{ metric.label }}</span><strong>{{ Number(metric.value).toLocaleString() }}</strong><small>{{ metric.hint }}</small></article></div>
    <div class="content-grid">
      <article class="panel"><div class="panel-heading"><h2>{{ t('dashboard.trend') }}</h2><span>14 DAYS / UTC+8</span></div><div ref="chartElement" style="height: 280px"></div></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('dashboard.control') }}</h2><span>TELETHON RUNTIME</span></div><div class="control-row"><button class="primary-button compact" @click="control('start')">{{ t('common.start') }}</button><button class="ghost-button" @click="control('restart')">{{ t('common.restart') }}</button><button class="danger-button" @click="control('stop')">{{ t('common.stop') }}</button></div><div class="form-section"><div class="health-list"><div v-for="(value, key) in status.queue?.counts" :key="key" class="health-row"><label>{{ String(key).toUpperCase() }}</label><strong>{{ value }}</strong><div class="health-bar"><i :style="{ width: `${Math.min(100, Number(value) * 8)}%` }"></i></div></div><p v-if="!Object.keys(status.queue?.counts ?? {}).length" class="empty-state">QUEUE CLEAR</p></div></div></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('dashboard.ruleHealth') }}</h2><span>{{ statsQuery.data.value?.rules?.length ?? 0 }} RULES</span></div><div class="health-list"><div v-for="rule in statsQuery.data.value?.rules" :key="rule.rule_name" class="health-row"><label>{{ rule.rule_name }}</label><strong>{{ rule.total }}</strong><div class="health-bar"><i :style="{ width: `${Math.min(100, rule.total ? (rule.forwarded / rule.total) * 100 : 0)}%` }"></i></div></div><p v-if="!statsQuery.data.value?.rules?.length" class="empty-state">{{ t('common.noData') }}</p></div></article>
      <article class="panel"><div class="panel-heading"><h2>{{ t('dashboard.recent') }}</h2><span>SSE FEED</span></div><div class="event-list"><div v-for="event in recent.slice(0, 12)" :key="event.at + JSON.stringify(event.payload)" class="event-row"><span class="event-time">{{ new Date(event.at).toLocaleTimeString() }}</span><p>{{ event.type.toUpperCase() }} · {{ event.payload.message ?? event.payload.action ?? JSON.stringify(event.payload) }}</p></div><p v-if="!recent.length" class="empty-state">WAITING FOR SIGNAL…</p></div></article>
    </div>
  </section>
</template>
