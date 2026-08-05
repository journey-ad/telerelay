const MEDIA_PREFIX = '/telegram-media/'
const RANGE_PATTERN = /^bytes=(\d+)-(\d*)$/
const RANGE_RESPONSE_TIMEOUT_MS = 20_000

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

function responseFor(bytes, total, mimeType, start, requestedEnd) {
  const end = start + bytes.byteLength - 1
  const headers = new Headers({
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-store, no-cache, must-revalidate',
    'Content-Length': String(bytes.byteLength),
    'Content-Type': mimeType || 'video/mp4',
  })
  if (total !== null && total !== undefined) {
    headers.set('Content-Range', `bytes ${start}-${Math.min(end, requestedEnd)}/${total}`)
  }
  return new Response(bytes, { status: 206, headers })
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (!url.pathname.startsWith(MEDIA_PREFIX)) return
  event.respondWith(
    (async () => {
      const token = decodeURIComponent(url.pathname.slice(MEDIA_PREFIX.length))
      const client = event.clientId ? await self.clients.get(event.clientId) : null
      if (!client) return new Response('Media client is unavailable', { status: 503 })
      const range = request.headers.get('Range')
      const match = range ? RANGE_PATTERN.exec(range) : null
      const start = match ? Number(match[1]) : 0
      const requestedEnd = match && match[2] ? Number(match[2]) : start + 512 * 1024 - 1
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(requestedEnd) || requestedEnd < start) {
        return new Response('Invalid byte range', { status: 416 })
      }
      const channel = new MessageChannel()
      const response = new Promise((resolve) => {
        const timer = setTimeout(() => {
          channel.port1.close()
          resolve(new Response('Telegram media request timed out', { status: 504 }))
        }, RANGE_RESPONSE_TIMEOUT_MS)
        channel.port1.onmessage = (message) => {
          clearTimeout(timer)
          channel.port1.close()
          const value = message.data
          if (value.type === 'telegram-range-error') {
            resolve(new Response(value.message || 'Telegram media unavailable', { status: 502 }))
            return
          }
          if (value.type === 'telegram-range-response') {
            resolve(responseFor(value.bytes, value.total, value.mimeType, start, requestedEnd))
          }
        }
      })
      client.postMessage(
        { type: 'telegram-range', token, offset: start, limit: Math.min(512 * 1024, requestedEnd - start + 1) },
        [channel.port2],
      )
      return response
    })(),
  )
})
