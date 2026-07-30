import { ApiError } from './client'
import { authorization } from './credentials'

export async function downloadFile(path: string, fallbackName = 'download'): Promise<void> {
  const headers = new Headers()
  const auth = authorization()
  if (auth) headers.set('Authorization', auth)
  const response = await fetch(path, { headers })
  if (!response.ok) {
    throw new ApiError(response.status, `http_${response.status}`, response.statusText)
  }

  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quotedName = disposition.match(/filename="([^"]+)"/i)?.[1]
  const filename = encodedName ? decodeURIComponent(encodedName) : (quotedName ?? fallbackName)
  const objectUrl = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}
