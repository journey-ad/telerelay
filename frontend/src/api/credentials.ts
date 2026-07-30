const CREDENTIALS_KEY = 'telerelay.basic'

export function authorization(): string | undefined {
  const encoded = sessionStorage.getItem(CREDENTIALS_KEY)
  return encoded ? `Basic ${encoded}` : undefined
}

export function setCredentials(username: string, password: string): void {
  sessionStorage.setItem(CREDENTIALS_KEY, btoa(`${username}:${password}`))
}

export function clearCredentials(): void {
  sessionStorage.removeItem(CREDENTIALS_KEY)
}
