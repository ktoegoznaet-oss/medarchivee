import apiClient from './client'
import type { Ticket, TicketDetail, TicketStatus, TicketType } from './tickets'
import type { RegistrationMode } from './auth'

export interface DailyCount {
  date: string
  count: number
}

export interface DashboardStats {
  users_total: number
  users_active_7d: number
  users_active_30d: number
  users_blocked: number
  users_new_7d: number
  tickets_total: number
  tickets_new: number
  uploads_size_bytes: number
  activity_by_day: DailyCount[]
}

export type UserRole = 'user' | 'admin'
export type UserStatus = 'active' | 'blocked' | 'deleted'

export interface AdminUser {
  id: number
  email: string
  username: string
  role: UserRole
  status: UserStatus
  email_verified: boolean
  recovery_phrase_set: boolean
  created_at: string
  last_login_at: string | null
}

export interface UsersListResponse {
  users: AdminUser[]
  total: number
}

export type InviteStatus = 'active' | 'used' | 'revoked' | 'expired'

export interface Invite {
  id: number
  code: string
  created_by_admin_id: number
  created_at: string
  expires_at: string
  used_by_user_id: number | null
  used_by_email: string | null
  used_at: string | null
  revoked_at: string | null
  note: string | null
  status: InviteStatus
}

export const adminApi = {
  dashboard() {
    return apiClient.get<DashboardStats>('/v1/admin/dashboard')
  },
  // Users
  listUsers(search = '', limit = 100, offset = 0) {
    return apiClient.get<UsersListResponse>('/v1/admin/users', {
      params: { search: search || undefined, limit, offset },
    })
  },
  setUserStatus(userId: number, status: UserStatus) {
    return apiClient.patch<AdminUser>(`/v1/admin/users/${userId}/status`, { status })
  },
  setUserRole(userId: number, role: UserRole) {
    return apiClient.patch<AdminUser>(`/v1/admin/users/${userId}/role`, { role })
  },
  // Invites
  listInvites() {
    return apiClient.get<{ invites: Invite[] }>('/v1/admin/invites')
  },
  createInvite(note?: string) {
    return apiClient.post<{ invite: Invite }>('/v1/admin/invites', { note })
  },
  revokeInvite(id: number) {
    return apiClient.delete<Invite>(`/v1/admin/invites/${id}`)
  },
  // Tickets
  listTickets(statusFilter?: TicketStatus, typeFilter?: TicketType) {
    return apiClient.get<{ tickets: Ticket[] }>('/v1/admin/tickets', {
      params: {
        status_filter: statusFilter || undefined,
        type_filter: typeFilter || undefined,
      },
    })
  },
  getTicket(id: number) {
    return apiClient.get<TicketDetail>(`/v1/admin/tickets/${id}`)
  },
  setTicketStatus(id: number, status: TicketStatus) {
    return apiClient.patch<Ticket>(`/v1/admin/tickets/${id}/status`, { status })
  },
  addTicketComment(id: number, body: string, isInternal: boolean) {
    return apiClient.post(`/v1/admin/tickets/${id}/comments`, {
      body,
      is_internal: isInternal,
    })
  },
  // Settings
  getRegistrationMode() {
    return apiClient.get<{ mode: RegistrationMode }>(
      '/v1/admin/settings/registration-mode',
    )
  },
  setRegistrationMode(mode: RegistrationMode) {
    return apiClient.patch<{ mode: RegistrationMode }>(
      '/v1/admin/settings/registration-mode',
      { mode },
    )
  },
  getLimits() {
    return apiClient.get<{ ai_daily_limit: number; user_quota_bytes: number }>(
      '/v1/admin/settings/limits',
    )
  },
  setLimits(payload: { ai_daily_limit?: number; user_quota_bytes?: number }) {
    return apiClient.patch<{ ai_daily_limit: number; user_quota_bytes: number }>(
      '/v1/admin/settings/limits',
      payload,
    )
  },
  amIAdmin() {
    return apiClient.get('/v1/admin/me')
  },
}
