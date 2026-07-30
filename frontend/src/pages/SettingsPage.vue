<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { downloadFile, json, request } from '../api/client'

const { t } = useI18n()
const client = useQueryClient()
const configQuery = useQuery({ queryKey: ['config'], queryFn: () => request<any>('/api/v1/config') })
const authQuery = useQuery({ queryKey: ['telegram-auth'], queryFn: () => request<any>('/api/v1/telegram-auth'), refetchInterval: 1800 })
const rawConfig = ref('')
const authValue = ref('')
const importInput = ref<HTMLInputElement>()
watch(() => configQuery.data.value, value => { if (value) rawConfig.value = JSON.stringify(value.config, null, 2) }, { immediate: true })
const waitingLabel = computed(() => ({ waiting_phone: 'PHONE NUMBER', waiting_code: 'LOGIN CODE', waiting_password: '2FA PASSWORD' } as Record<string,string>)[authQuery.data.value?.state] ?? '')
const saveConfig = useMutation({ mutationFn: () => request('/api/v1/config', json('PUT', { config: JSON.parse(rawConfig.value) })), onSuccess: () => client.invalidateQueries({ queryKey: ['config'] }) })
async function startAuth() { await request('/api/v1/telegram-auth/start', json('POST')); await authQuery.refetch() }
async function submitAuth() { const state = authQuery.data.value?.state; const kind = state === 'waiting_phone' ? 'phone' : state === 'waiting_code' ? 'code' : 'password'; await request(`/api/v1/telegram-auth/${kind}`, json('POST', { value: authValue.value })); authValue.value = ''; await authQuery.refetch() }
async function clearSession() { await request('/api/v1/telegram-auth/session', json('DELETE')); await authQuery.refetch() }
async function importConfig(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (!file) return; const data = new FormData(); data.append('file', file); await request('/api/v1/config/import', { method: 'POST', body: data }); await configQuery.refetch() }
function exportConfig() { return downloadFile('/api/v1/config/export', 'telerelay-config.yaml') }
</script>

<template><section><header class="page-heading"><div><p class="eyebrow">NODE CONFIGURATION / LOCAL</p><h1>{{ t('settings.title') }}</h1><p>{{ t('settings.subtitle') }}</p></div></header><div class="content-grid"><article class="panel"><div class="panel-heading"><h2>TELEGRAM SESSION</h2><span>{{ configQuery.data.value?.runtime?.session_type?.toUpperCase() }}</span></div><div class="status-banner"><span class="pulse-dot" :class="{online:authQuery.data.value?.state==='success'}"></span><div><strong>{{ authQuery.data.value?.state ?? 'unknown' }}</strong><br>{{ authQuery.data.value?.user_info || authQuery.data.value?.error || 'No authenticated user' }}</div></div><div v-if="waitingLabel" class="form-section"><label>{{ waitingLabel }}<input v-model="authValue" :type="authQuery.data.value?.state==='waiting_password'?'password':'text'"></label><button class="primary-button compact" @click="submitAuth">SUBMIT ↗</button></div><div class="form-section control-row"><button class="primary-button compact" @click="startAuth">START AUTH</button><button class="danger-button" @click="clearSession">CLEAR SESSION</button></div></article><article class="panel"><div class="panel-heading"><h2>BACKUP</h2><span>YAML / MAX 1 MIB</span></div><p style="color:var(--muted);font-size:12px;line-height:1.7">Export the active rule configuration or replace it from a validated YAML file.</p><div class="control-row"><button class="ghost-button" type="button" @click="exportConfig">EXPORT YAML</button><button class="ghost-button" @click="importInput?.click()">IMPORT YAML</button><input ref="importInput" type="file" accept=".yaml,.yml" style="display:none" @change="importConfig"></div></article></div><article class="panel" style="margin-top:13px"><div class="panel-heading"><h2>ADVANCED CONFIGURATION</h2><span>JSON VIEW / SAVED AS YAML</span></div><textarea v-model="rawConfig" rows="22" style="font-family:ui-monospace,SFMono-Regular,monospace;font-size:11px"></textarea><p v-if="saveConfig.error.value" class="form-error">{{ saveConfig.error.value.message }}</p><div class="control-row" style="margin-top:14px;justify-content:flex-end"><button class="primary-button compact" @click="saveConfig.mutate()">{{ t('common.save') }} ↗</button></div></article></section></template>
