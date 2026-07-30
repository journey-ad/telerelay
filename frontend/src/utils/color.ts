export interface HashedColor {
  background: string
  foreground: '#000000' | '#ffffff'
}

function getHashOfString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash)
}

function normalizeHash(hash: number, min: number, max: number): number {
  return Math.floor((hash % (max - min)) + min)
}

function hslToHex(h: number, s: number, l: number): string {
  const saturation = s / 100
  const lightness = l / 100
  const a = saturation * Math.min(lightness, 1 - lightness)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const color = lightness - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
    return Math.round(255 * color)
      .toString(16)
      .padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

function relativeLuminance(background: string): number {
  const [red, green, blue] = [1, 3, 5].map(
    (index) => Number.parseInt(background.slice(index, index + 2), 16) / 255,
  )
  const linearChannel = (value: number): number =>
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  return 0.2126 * linearChannel(red) + 0.7152 * linearChannel(green) + 0.0722 * linearChannel(blue)
}

const SATURATION_RANGE: [number, number] = [35, 65]
const LIGHTNESS_RANGE: [number, number] = [68, 80]

export function hashColor(value: string): HashedColor {
  const hash = getHashOfString(value)
  const h = normalizeHash(hash, 0, 360)
  const s = normalizeHash(hash, SATURATION_RANGE[0], SATURATION_RANGE[1])
  const l = normalizeHash(hash, LIGHTNESS_RANGE[0], LIGHTNESS_RANGE[1])

  const background = hslToHex(h, s, l)
  const luminance = relativeLuminance(background)
  const blackContrast = (luminance + 0.05) / 0.05
  const whiteContrast = 1.05 / (luminance + 0.05)

  return {
    background,
    foreground: blackContrast >= whiteContrast ? '#000000' : '#ffffff',
  }
}
