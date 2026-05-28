import apiClient from './client'

export interface TelegramBindingStatus {
  bound: boolean
  telegram_user_id: number | null
  telegram_username: string | null
  bound_at: string | null
  notifications_enabled: boolean
  notify_medications: boolean
  notify_visits: boolean
  notify_daily_summary: boolean
  notify_health_tips: boolean
}

export interface TelegramBindingCode {
  code: string
  expires_at: string
  bot_username: string
  deep_link: string
}

export interface TelegramNotificationsUpdate {
  notifications_enabled?: boolean
  notify_medications?: boolean
  notify_visits?: boolean
  notify_daily_summary?: boolean
  notify_health_tips?: boolean
}

export const telegramApi = {
  getBinding() {
    return apiClient.get<TelegramBindingStatus>('/v1/telegram/binding')
  },
  generateCode() {
    return apiClient.post<TelegramBindingCode>('/v1/telegram/binding/code')
  },
  unbind() {
    return apiClient.delete<void>('/v1/telegram/binding')
  },
  updateNotifications(payload: TelegramNotificationsUpdate) {
    return apiClient.patch<TelegramBindingStatus>(
      '/v1/telegram/binding/notifications',
      payload,
    )
  },
  sendTest() {
    return apiClient.post<{ delivered: boolean }>('/v1/telegram/binding/test')
  },
}
