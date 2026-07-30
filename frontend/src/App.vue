<script setup lang="ts">
import { onMounted } from 'vue'
import { useSessionStore } from './stores/session'
import LoginView from './components/LoginView.vue'
import AppShell from './components/AppShell.vue'

const session = useSessionStore()
onMounted(() => session.check())
</script>

<template>
  <div v-if="!session.ready" class="boot-screen">
    <div class="boot-mark"><span></span><span></span><span></span></div>
    <p>INITIALIZING RELAY CONSOLE</p>
  </div>
  <LoginView v-else-if="!session.authenticated" />
  <AppShell v-else />
</template>

