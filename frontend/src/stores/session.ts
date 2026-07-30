import { defineStore } from 'pinia'
import { clearCredentials, request, setCredentials } from '../api/client'

interface SessionInfo {
  authenticated: boolean
  auth_required: boolean
  session_type: 'user' | 'bot'
  language: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    ready: false,
    authenticated: false,
    authRequired: false,
    sessionType: 'user' as 'user' | 'bot',
    error: '',
  }),
  actions: {
    async check() {
      try {
        const data = await request<SessionInfo>('/api/v1/session')
        this.authenticated = data.authenticated
        this.authRequired = data.auth_required
        this.sessionType = data.session_type
        this.error = ''
      } catch {
        this.authenticated = false
      } finally {
        this.ready = true
      }
    },
    async login(username: string, password: string) {
      setCredentials(username, password)
      try {
        await this.check()
        if (!this.authenticated) throw new Error('Authentication failed')
      } catch (error) {
        clearCredentials()
        this.error = error instanceof Error ? error.message : 'Authentication failed'
        throw error
      }
    },
    logout() {
      clearCredentials()
      this.authenticated = false
    },
  },
})

