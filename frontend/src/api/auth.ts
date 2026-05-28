import apiClient from './client'

export type UserRole = 'user' | 'admin'

export interface UserPublic {
  id: number
  email: string
  username: string
  role: UserRole
  email_verified: boolean
  created_at: string
}

export type RegistrationMode = 'closed' | 'invite_only' | 'open'

export interface RegisterPayload {
  email: string
  username: string
  password: string
  password_confirm: string
  terms_accepted: boolean
  privacy_accepted: boolean
  medical_disclaimer_accepted: boolean
  invite_code?: string
}

export interface LoginPayload {
  email_or_username: string
  password: string
  remember_me: boolean
}

export interface LoginResponse {
  access_token: string
  token_type: 'Bearer'
  user: UserPublic
}

export interface RegisterResponse {
  user: UserPublic
  message: string
}

export interface VerifyEmailPayload {
  user_id: number
  code: string
}

export const authApi = {
  getRegistrationMode() {
    return apiClient.get<{ mode: RegistrationMode }>('/v1/auth/registration-mode')
  },
  register(payload: RegisterPayload) {
    return apiClient.post<RegisterResponse>('/v1/auth/register', payload)
  },
  verifyEmail(payload: VerifyEmailPayload) {
    return apiClient.post<{ user: UserPublic }>('/v1/auth/verify-email', payload)
  },
  resendVerification(userId: number) {
    return apiClient.post<{ message: string }>('/v1/auth/resend-verification', {
      user_id: userId,
    })
  },
  login(payload: LoginPayload) {
    return apiClient.post<LoginResponse>('/v1/auth/login', payload)
  },
  refresh() {
    return apiClient.post<{ access_token: string }>('/v1/auth/refresh')
  },
  logout() {
    return apiClient.post<{ message: string }>('/v1/auth/logout')
  },
  me() {
    return apiClient.get<UserPublic>('/v1/auth/me')
  },
}
