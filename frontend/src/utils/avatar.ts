const graphemeSegmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' })

function firstGrapheme(value: string): string {
  return graphemeSegmenter.segment(value)[Symbol.iterator]().next().value?.segment ?? ''
}

export function avatarInitials(value: string, fallback = 'TG'): string {
  const words = value.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return fallback

  const initials =
    words.length > 1
      ? `${firstGrapheme(words[0])}${firstGrapheme(words[words.length - 1])}`
      : Array.from(graphemeSegmenter.segment(words[0]), ({ segment }) => segment)
          .slice(0, 2)
          .join('')

  return initials.toLocaleUpperCase() || fallback
}
