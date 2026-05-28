import apiClient from './client'

export type RecoveryLanguage = 'russian' | 'english'

export interface GeneratePhraseResponse {
  phrase: string
  lang: RecoveryLanguage
  confirmation_indices: number[]
}

export interface ConfirmPhrasePayload {
  phrase: string
  lang: RecoveryLanguage
  confirmation_indices: number[]
  confirmation_words: string[]
}

export interface PhraseStatusResponse {
  recovery_phrase_set: boolean
  lang: RecoveryLanguage | null
}

export interface ResetPasswordPayload {
  email: string
  phrase: string
  new_password: string
  new_password_confirm: string
}

export const recoveryApi = {
  status() {
    return apiClient.get<PhraseStatusResponse>('/v1/recovery/phrase/status')
  },
  generate(lang: RecoveryLanguage) {
    return apiClient.post<GeneratePhraseResponse>(
      '/v1/recovery/phrase/generate',
      { lang },
    )
  },
  confirm(payload: ConfirmPhrasePayload) {
    return apiClient.post<{ message: string }>(
      '/v1/recovery/phrase/confirm',
      payload,
    )
  },
  regenerate(password: string) {
    return apiClient.post<GeneratePhraseResponse>(
      '/v1/recovery/phrase/regenerate',
      { password },
    )
  },
  resetPassword(payload: ResetPasswordPayload) {
    return apiClient.post<{ message: string }>(
      '/v1/recovery/reset-password',
      payload,
    )
  },
  requestWipe(email: string) {
    return apiClient.post<{ message: string }>(
      '/v1/recovery/wipe-request',
      { email },
    )
  },
  confirmWipe(email: string, code: string) {
    return apiClient.post<{ message: string }>(
      '/v1/recovery/wipe-confirm',
      { email, code },
    )
  },
}
