export interface SearchableChat {
  id: number | string
  title: string
  username?: string | null
}

export function chatMatches(chat: SearchableChat, term: string): boolean {
  const query = term.trim().toLowerCase()
  if (!query) return true
  const withoutAt = query.replace(/^@/, '')

  return [chat.id, chat.title, chat.username]
    .filter((value) => value !== null && value !== undefined)
    .some((value) => {
      const text = String(value).toLowerCase()
      return text.includes(query) || text.includes(withoutAt)
    })
}
