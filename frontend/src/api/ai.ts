import apiClient from './client'

export type AIProvider = 'gemini'

export type AIComplexity = 'child' | 'family_doctor' | 'professor' | 'dry_facts'

export type AITone =
  | 'close_person'
  | 'good_friend'
  | 'funny_colleague'
  | 'professional'
  | 'encyclopedia'

export type AIDataAccessMode = 'manual' | 'full'

export type AIMessageRole = 'user' | 'assistant'

export interface AISettings {
  id: number
  user_id: number
  preferred_provider: AIProvider
  complexity_level: AIComplexity
  tone: AITone
  data_access_mode: AIDataAccessMode
  created_at: string
  updated_at: string
}

export interface AISettingsUpdate {
  preferred_provider?: AIProvider
  complexity_level?: AIComplexity
  tone?: AITone
  data_access_mode?: AIDataAccessMode
}

export interface AIConversationSummary {
  id: number
  title: string
  is_archived: boolean
  created_at: string
  updated_at: string
  last_message_preview: string | null
}

export interface AIConversationFull {
  id: number
  title: string
  is_archived: boolean
  created_at: string
  updated_at: string
}

export interface AttachedData {
  include_profile: boolean
  analysis_ids: number[]
}

export interface AIMessage {
  id: number
  conversation_id: number
  role: AIMessageRole
  content: string
  attached_data: AttachedData | null
  safety_event_type: string | null
  provider: string | null
  model: string | null
  tokens_used: number | null
  created_at: string
}

export interface AISendMessagePayload {
  message: string
  attached_data?: AttachedData
  override_tone?: AITone
  override_complexity?: AIComplexity
}

export interface AISendMessageResponse {
  conversation: AIConversationFull
  user_message: AIMessage
  assistant_message: AIMessage
}

export const aiApi = {
  getSettings() {
    return apiClient.get<AISettings>('/v1/ai/settings')
  },
  updateSettings(payload: AISettingsUpdate) {
    return apiClient.patch<AISettings>('/v1/ai/settings', payload)
  },
  listConversations(includeArchived = false) {
    return apiClient.get<AIConversationSummary[]>('/v1/ai/conversations', {
      params: { include_archived: includeArchived },
    })
  },
  createConversation() {
    return apiClient.post<AIConversationFull>('/v1/ai/conversations')
  },
  listMessages(conversationId: number) {
    return apiClient.get<AIMessage[]>(
      `/v1/ai/conversations/${conversationId}/messages`,
    )
  },
  sendMessage(conversationId: number, payload: AISendMessagePayload) {
    return apiClient.post<AISendMessageResponse>(
      `/v1/ai/conversations/${conversationId}/messages`,
      payload,
    )
  },
  archiveConversation(conversationId: number) {
    return apiClient.post<void>(
      `/v1/ai/conversations/${conversationId}/archive`,
    )
  },
  deleteConversation(conversationId: number) {
    return apiClient.delete<void>(`/v1/ai/conversations/${conversationId}`)
  },
}
