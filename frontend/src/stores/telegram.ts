import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  telegramApi,
  type TelegramBindingCode,
  type TelegramBindingStatus,
  type TelegramNotificationsUpdate,
} from '@/api/telegram'

export const useTelegramStore = defineStore('telegram', () => {
  const binding = ref<TelegramBindingStatus | null>(null)
  const bindingCode = ref<TelegramBindingCode | null>(null)
  const loading = ref(false)

  async function fetchBinding(): Promise<TelegramBindingStatus> {
    loading.value = true
    try {
      const { data } = await telegramApi.getBinding()
      binding.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function generateCode(): Promise<TelegramBindingCode> {
    const { data } = await telegramApi.generateCode()
    bindingCode.value = data
    return data
  }

  function clearCode(): void {
    bindingCode.value = null
  }

  async function unbind(): Promise<void> {
    await telegramApi.unbind()
    binding.value = { ...(binding.value as TelegramBindingStatus), bound: false }
    bindingCode.value = null
  }

  async function updateSettings(
    payload: TelegramNotificationsUpdate,
  ): Promise<TelegramBindingStatus> {
    const { data } = await telegramApi.updateNotifications(payload)
    binding.value = data
    return data
  }

  async function sendTestMessage(): Promise<boolean> {
    const { data } = await telegramApi.sendTest()
    return data.delivered
  }

  function reset(): void {
    binding.value = null
    bindingCode.value = null
    loading.value = false
  }

  return {
    binding,
    bindingCode,
    loading,
    fetchBinding,
    generateCode,
    clearCode,
    unbind,
    updateSettings,
    sendTestMessage,
    reset,
  }
})
