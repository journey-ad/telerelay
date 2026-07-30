<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuery } from '@tanstack/vue-query'
import { request } from '../api/client'

const { t } = useI18n()
const rule = ref('')
const keyword = ref('')
const appliedRule = ref('')
const appliedKeyword = ref('')
const page = ref(1)
const rulesQuery = useQuery({ queryKey: ['rules'], queryFn: () => request<any[]>('/api/v1/rules') })
const queryKey = computed(() => ['history', appliedRule.value, appliedKeyword.value, page.value])
const historyQuery = useQuery({ queryKey, queryFn: () => { const params = new URLSearchParams({ page: String(page.value), page_size: '20' }); if (appliedRule.value) params.set('rule_name', appliedRule.value); if (appliedKeyword.value) params.set('keyword', appliedKeyword.value); return request<any>(`/api/v1/history?${params}`) } })
const pages = computed(() => Math.max(1, Math.ceil((historyQuery.data.value?.total ?? 0) / 20)))
function search() { page.value = 1; appliedRule.value = rule.value; appliedKeyword.value = keyword.value.trim() }
</script>

<template><section><header class="page-heading"><div><p class="eyebrow">MESSAGE LEDGER / SQLITE</p><h1>{{ t('history.title') }}</h1><p>{{ t('history.subtitle') }}</p></div></header><article class="panel"><form class="form-grid" @submit.prevent="search"><label>RULE<select v-model="rule"><option value="">{{ t('common.all') }}</option><option v-for="item in rulesQuery.data.value" :key="item.name" :value="item.name">{{ item.name }}</option></select></label><label>KEYWORD<input v-model="keyword" :placeholder="t('common.search')"></label><div class="full control-row"><button class="primary-button compact">{{ t('common.search') }} ↗</button><button type="button" class="ghost-button" @click="rule='';keyword='';search()">RESET</button></div></form></article><article class="panel table-panel" style="margin-top:13px"><div class="panel-heading"><h2>RESULT SET</h2><span>{{ historyQuery.data.value?.total ?? 0 }} RECORDS</span></div><div class="table-wrap"><table class="data-table"><thead><tr><th>TIME</th><th>RULE</th><th>SOURCE</th><th>SENDER</th><th>CONTENT</th><th>MEDIA</th></tr></thead><tbody><tr v-for="item in historyQuery.data.value?.items" :key="item.id"><td>{{ item.forwarded_at }}</td><td><strong>{{ item.rule_name }}</strong></td><td>{{ item.source_chat_name || item.source_chat_id }}</td><td>{{ item.sender_name }}<br><span v-if="item.sender_username">@{{ item.sender_username }}</span></td><td style="max-width:420px;white-space:pre-wrap">{{ item.content }}</td><td><span class="tag">{{ item.media_type || 'text' }}</span></td></tr></tbody></table><p v-if="!historyQuery.data.value?.items?.length" class="empty-state">{{ t('common.noData') }}</p></div><div class="control-row" style="margin-top:18px;justify-content:flex-end"><button class="ghost-button" :disabled="page<=1" @click="page--">← PREV</button><span class="tag">{{ page }} / {{ pages }}</span><button class="ghost-button" :disabled="page>=pages" @click="page++">NEXT →</button></div></article></section></template>

