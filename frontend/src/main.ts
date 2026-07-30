import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'

import App from './App.vue'
import { i18n } from './i18n'
import { router } from './router'
import './styles.css'

createApp(App)
  .use(createPinia())
  .use(router)
  .use(i18n)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: {
        queries: { staleTime: 2500, retry: 1, refetchOnWindowFocus: false },
      },
    },
  })
  .mount('#app')

