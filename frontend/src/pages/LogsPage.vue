<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { request } from '../api/client'
import { useEvents } from '../composables/useEvents'

const { t } = useI18n()
const filter = ref('')
const logsQuery = useQuery({ queryKey: ['logs'], queryFn: () => request<{lines:string[]}>('/api/v1/logs?lines=600'), refetchInterval: 10000 })
const live = ref<string[]>([])
useEvents((event) => { if (event.type === 'log' && event.payload.message) live.value = [...live.value, String(event.payload.message)].slice(-500) })
const lines = computed(() => [...(logsQuery.data.value?.lines ?? []), ...live.value].filter(line => !filter.value || line.toLowerCase().includes(filter.value.toLowerCase())).slice(-800))
function level(line: string) { const text = line.toLowerCase(); if (text.includes('error')) return 'error'; if (text.includes('warning') || text.includes('flood')) return 'warning'; if (text.includes('info')) return 'info'; return '' }
</script>

<template><section><header class="page-heading"><div><p class="eyebrow">OBSERVABILITY / LIVE TAIL</p><h1>{{ t('logs.title') }}</h1><p>{{ t('logs.subtitle') }}</p></div><button class="ghost-button" @click="logsQuery.refetch()">{{ t('common.refresh') }} ↻</button></header><article class="panel"><div class="form-grid"><label class="full">FILTER STREAM<input v-model="filter" placeholder="error, queue, rule name…"></label></div></article><div class="log-view" style="margin-top:13px"><p v-for="(line,index) in lines" :key="index + line" class="log-line" :class="level(line)">{{ line }}</p><p v-if="!lines.length" class="empty-state">WAITING FOR LOG SIGNAL…</p></div></section></template>

