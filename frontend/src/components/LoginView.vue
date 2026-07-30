<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '../stores/session'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const session = useSessionStore()
const username = ref('')
const password = ref('')
const submitting = ref(false)

async function submit() {
  submitting.value = true
  try {
    await session.login(username.value, password.value)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="login-screen">
    <div class="login-grid"></div>
    <section class="login-panel">
      <div class="brand-lockup">
        <div class="signal-logo"><i></i><i></i><i></i></div>
        <div><span class="brand-kicker">{{ t('brand.kicker') }}</span><strong>{{ t('brand.name') }}</strong></div>
      </div>
      <div class="login-copy">
        <p class="eyebrow">NODE ACCESS / 01</p>
        <h1>{{ t('login.title') }}</h1>
        <p>{{ t('login.subtitle') }}</p>
      </div>
      <form @submit.prevent="submit">
        <label>{{ t('login.username') }}<input v-model="username" autocomplete="username" required /></label>
        <label>{{ t('login.password') }}<input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="session.error" class="form-error">{{ t('login.failed') }} · {{ session.error }}</p>
        <button class="primary-button wide" :disabled="submitting">
          <span>{{ submitting ? 'AUTHENTICATING…' : t('login.submit') }}</span><b>↗</b>
        </button>
      </form>
      <div class="login-foot"><span class="pulse-dot"></span> LOCAL CONTROL PLANE <span>v2.0</span></div>
    </section>
  </main>
</template>

