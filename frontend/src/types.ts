export type ChatRef = string | number

export interface SessionInfo {
  authenticated: boolean
  auth_required: boolean
  session_type: 'user' | 'bot'
  language: string
  active_account_id?: string | null
}

export interface TelegramAccount {
  id: string
  label: string
  display_name: string
  username: string
  telegram_user_id?: number | null
  created_at: string
  active: boolean
  authenticated: boolean
  connected: boolean
  status: 'connected' | 'authenticated' | 'needs_auth'
  avatar_version?: string | null
}

export interface TelegramPreviewChat {
  id: number
  title: string
  kind: 'private' | 'bot' | 'group' | 'supergroup' | 'channel'
  username?: string | null
  is_self: boolean
  verified: boolean
  inline_avatar?: string | null
}

export interface TelegramPreviewDialog extends TelegramPreviewChat {
  archived: boolean
  pinned: boolean
  unread_count: number
  unread_mentions_count: number
  last_message?: {
    id: number
    chat_id: number
    date?: string | null
    text: string
    media_type: string
    preview: string
    outgoing: boolean
  } | null
}

export interface TelegramPreviewMessage {
  id: number
  chat_id: number
  date?: string | null
  sender: {
    id?: number | null
    name: string
    username?: string | null
  }
  text: string
  media?: {
    type: string
    file_name?: string | null
    mime_type?: string | null
    size?: number | null
    duration?: number | null
    width?: number | null
    height?: number | null
    is_visual_media: boolean
    has_thumbnail: boolean
    inline_thumbnail?: string | null
    poll?: {
      question: string
      options: Array<{ text: string; voters: number; chosen: boolean; correct: boolean }>
      results_visible: boolean
      total_voters: number
      multiple_choice: boolean
      quiz: boolean
      closed: boolean
      solution?: string | null
    } | null
  } | null
  reply_to?: {
    message_id: number
    sender_name?: string | null
    text: string
    media_type?: string | null
  } | null
  forward?: {
    from_id?: number | null
    from_name: string
    date?: string | null
  } | null
  grouped_id?: number | null
  edited_at?: string | null
  outgoing: boolean
  post_author?: string | null
  views?: number | null
  reactions: Array<{ label: string; count: number; chosen: boolean }>
  service_action?: string | null
}

export interface TelegramPreviewDialogsPage {
  account_id: string
  folder: 'main' | 'archived'
  items: TelegramPreviewDialog[]
  next_cursor?: string | null
}

export interface TelegramPreviewMessagesPage {
  account_id: string
  chat: TelegramPreviewChat
  query?: string | null
  items: TelegramPreviewMessage[]
  next_before_id?: number | null
}

export interface ForwardingRule {
  name: string
  enabled: boolean
  source_chats: ChatRef[]
  target_chats: ChatRef[]
  filters: {
    mode: 'whitelist' | 'blacklist'
    keywords: string[]
    regex_patterns: string[]
    media_types: string[]
    max_file_size: number
    min_file_size: number
  }
  ignore: { user_ids: number[]; keywords: string[] }
  forwarding: {
    preserve_format: boolean
    add_source_info: boolean
    delay: number
    force_forward: boolean
    hide_sender: boolean
    deduplicate: boolean
    deduplicate_window: number
  }
}

export interface ButtonRule {
  name: string
  enabled: boolean
  source_chats: ChatRef[]
  button_texts: string[]
  match_mode: 'exact' | 'contains' | 'regex'
  delay: number
  click_all_matches: boolean
}

export interface BotStatus {
  is_connected?: boolean
  is_running?: boolean
  stats?: { forwarded?: number; filtered?: number; total?: number }
  queue?: { counts?: Record<string, number>; pause_reason?: string }
}

export interface Stats {
  daily: Array<{ date: string; forwarded: number; filtered: number; total?: number }>
  rules: Array<{ rule_name: string; total: number; forwarded: number; filtered?: number }>
}

export interface HistoryItem {
  id: number
  forwarded_at: string
  rule_name: string
  source_chat_name?: string
  source_chat_id: number
  sender_name?: string
  sender_username?: string
  content?: string
  media_type?: string
}

export interface HistoryPage {
  items: HistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface ExportChat {
  label: string
  chat_id: number
}
export interface ExportTask {
  id: number
  name: string
  chat_id: number
  chat_title?: string
  initial_start_at?: string | null
  formats: string[]
  subdirectory: string
  schedule_type: 'hourly' | 'daily' | 'weekly'
  minute: number
  hour: number
  weekday: number
  timezone: string
  all_history: boolean
  enabled: boolean
  next_run_at?: string | null
}

export interface ExportRun {
  id: number
  started_at: string
  run_type: string
  chat_title?: string
  chat_id?: number
  status: string
  message_count: number
  files: string[]
}

export interface ExportJob {
  id: string
  status: string
  processed: number
  total?: number
  phase?: string
  files: string[]
  error?: string
}

export interface TelegramAuth {
  state: string
  error?: string
  user_info?: string
  account_id?: string | null
}
export interface AppConfig {
  config: Record<string, unknown>
  runtime: { session_type: string }
}
export interface RelayEvent {
  type: string
  payload: Record<string, unknown>
  at: string
}
