function hueToRgb(p: number, q: number, hue: number): number {
  const value = ((hue % 1) + 1) % 1
  if (value < 1 / 6) return p + (q - p) * 6 * value
  if (value < 1 / 2) return q
  if (value < 2 / 3) return p + (q - p) * (2 / 3 - value) * 6
  return p
}

function channelHex(value: number): string {
  return Math.round(value * 255)
    .toString(16)
    .padStart(2, '0')
}

export function hashColor(value: string): string {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }

  const hue = (hash >>> 0) % 360
  const saturation = 0.58 + (((hash >>> 8) & 0xff) / 255) * 0.12
  const lightness = 0.36 + (((hash >>> 16) & 0xff) / 255) * 0.06
  const q = lightness * (1 + saturation)
  const p = 2 * lightness - q
  const normalizedHue = hue / 360

  return `#${channelHex(hueToRgb(p, q, normalizedHue + 1 / 3))}${channelHex(
    hueToRgb(p, q, normalizedHue),
  )}${channelHex(hueToRgb(p, q, normalizedHue - 1 / 3))}`
}
