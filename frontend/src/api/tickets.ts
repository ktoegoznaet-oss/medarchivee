import apiClient from './client'

export type TicketType = 'bug' | 'suggestion' | 'question' | 'other'
export type TicketStatus = 'new' | 'in_progress' | 'resolved' | 'rejected'

export interface CreateTicketPayload {
  type: TicketType
  title: string
  description: string
  url?: string | null
  user_agent?: string | null
  screen_size?: string | null
}

export interface TicketAttachment {
  id: number
  original_filename: string
  mime_type: string
  size_bytes: number
  created_at: string
}

export interface TicketComment {
  id: number
  ticket_id: number
  author_user_id: number
  body: string
  is_internal: boolean
  created_at: string
}

export interface Ticket {
  id: number
  user_id: number
  type: TicketType
  title: string
  description: string
  status: TicketStatus
  url: string | null
  user_agent: string | null
  screen_size: string | null
  created_at: string
  updated_at: string
  attachments: TicketAttachment[]
}

export interface TicketDetail extends Ticket {
  comments: TicketComment[]
}

export const ticketsApi = {
  create(payload: CreateTicketPayload, screenshot?: File | null) {
    const form = new FormData()
    form.append('payload', JSON.stringify(payload))
    if (screenshot) {
      form.append('screenshot', screenshot)
    }
    return apiClient.post<Ticket>('/v1/tickets', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  listMine() {
    return apiClient.get<{ tickets: Ticket[] }>('/v1/tickets/mine')
  },
  get(id: number) {
    return apiClient.get<TicketDetail>(`/v1/tickets/${id}`)
  },
  addComment(id: number, body: string) {
    return apiClient.post<TicketComment>(`/v1/tickets/${id}/comments`, { body })
  },
  attachmentUrl(ticketId: number, attachmentId: number): string {
    return `/api/v1/tickets/${ticketId}/attachments/${attachmentId}`
  },
}
