import apiClient from './client'

export const meApi = {
  exportUrl(): string {
    // Скачивание идёт прямо через браузер с access_token из header'а —
    // вместо этого endpoint выдаёт ZIP, который axios сохраняет в blob.
    return '/v1/me/export'
  },
  async downloadExport(): Promise<Blob> {
    const resp = await apiClient.get('/v1/me/export', { responseType: 'blob' })
    return resp.data as Blob
  },
  deleteAccount(password: string) {
    return apiClient.delete<{ message: string }>('/v1/me/account', {
      data: { password },
    })
  },
}
