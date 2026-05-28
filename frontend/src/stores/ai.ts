import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  aiApi,
  type AIConversationFull,
  type AIConversationSummary,
  type AIMessage,
  type AISendMessagePayload,
  type AISettings,
  type AISettingsUpdate,
} from '@/api/ai'

export const useAIStore = defineStore('ai', () => {
  const settings = ref<AISettings | null>(null)
  const conversations = ref<AIConversationSummary[]>([])
  const currentConversation = ref<AIConversationFull | null>(null)
  const messages = ref<AIMessage[]>([])
  const isWaitingForResponse = ref(false)

  async function fetchSettings(): Promise<AISettings> {
    const { data } = await aiApi.getSettings()
    settings.value = data
    return data
  }

  async function updateSettings(payload: AISettingsUpdate): Promise<AISettings> {
    const { data } = await aiApi.updateSettings(payload)
    settings.value = data
    return data
  }

  async function fetchConversations(): Promise<void> {
    const { data } = await aiApi.listConversations(false)
    conversations.value = data
  }

  async function createConversation(): Promise<AIConversationFull> {
    const { data } = await aiApi.createConversation()
    currentConversation.value = data
    messages.value = []
    // Обновим список — новая беседа должна появиться сверху.
    await fetchConversations()
    return data
  }

  async function openConversation(conversationId: number): Promise<void> {
    const summary = conversations.value.find((c) => c.id === conversationId)
    if (summary) {
      currentConversation.value = {
        id: summary.id,
        title: summary.title,
        is_archived: summary.is_archived,
        created_at: summary.created_at,
        updated_at: summary.updated_at,
      }
    }
    const { data } = await aiApi.listMessages(conversationId)
    messages.value = data
  }

  async function sendMessage(payload: AISendMessagePayload): Promise<void> {
    if (!currentConversation.value) {
      throw new Error('no_current_conversation')
    }
    isWaitingForResponse.value = true
    try {
      const { data } = await aiApi.sendMessage(
        currentConversation.value.id,
        payload,
      )
      currentConversation.value = data.conversation
      messages.value.push(data.user_message, data.assistant_message)
      // Заголовок мог только что появиться — обновим список.
      const idx = conversations.value.findIndex(
        (c) => c.id === data.conversation.id,
      )
      if (idx >= 0) {
        conversations.value[idx] = {
          ...conversations.value[idx],
          title: data.conversation.title,
          updated_at: data.conversation.updated_at,
          last_message_preview: data.assistant_message.content.slice(0, 100),
        }
      }
    } finally {
      isWaitingForResponse.value = false
    }
  }

  async function archiveConversation(conversationId: number): Promise<void> {
    await aiApi.archiveConversation(conversationId)
    conversations.value = conversations.value.filter(
      (c) => c.id !== conversationId,
    )
    if (currentConversation.value?.id === conversationId) {
      currentConversation.value = null
      messages.value = []
    }
  }

  function reset(): void {
    settings.value = null
    conversations.value = []
    currentConversation.value = null
    messages.value = []
    isWaitingForResponse.value = false
  }

  return {
    settings,
    conversations,
    currentConversation,
    messages,
    isWaitingForResponse,
    fetchSettings,
    updateSettings,
    fetchConversations,
    createConversation,
    openConversation,
    sendMessage,
    archiveConversation,
    reset,
  }
})
