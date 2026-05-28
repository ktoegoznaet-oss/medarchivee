import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 10_000,
  // refresh-токен лежит в HttpOnly cookie — браузер должен слать её автоматически.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean }

type AuthHooks = {
  getAccessToken: () => string | null
  setAccessToken: (token: string | null) => void
  onAuthLost: () => void
}

let hooks: AuthHooks | null = null

export function attachAuthHooks(h: AuthHooks): void {
  hooks = h
}

apiClient.interceptors.request.use((config) => {
  const token = hooks?.getAccessToken() ?? null
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

let refreshInFlight: Promise<string | null> | null = null

async function tryRefresh(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = axios
      .create({ baseURL, withCredentials: true })
      .post<{ access_token: string }>('/v1/auth/refresh')
      .then((resp) => {
        const newToken = resp.data.access_token
        hooks?.setAccessToken(newToken)
        return newToken
      })
      .catch(() => {
        hooks?.setAccessToken(null)
        return null
      })
      .finally(() => {
        refreshInFlight = null
      })
  }
  return refreshInFlight
}

apiClient.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const status = error.response?.status
    const original = error.config as RetriableRequestConfig | undefined
    if (!original || status !== 401 || original._retry) {
      return Promise.reject(error)
    }
    // Никогда не пытаемся освежить токен прямо на /auth/refresh — это создаст цикл.
    if (original.url?.endsWith('/v1/auth/refresh')) {
      return Promise.reject(error)
    }
    original._retry = true
    const newToken = await tryRefresh()
    if (!newToken) {
      hooks?.onAuthLost()
      return Promise.reject(error)
    }
    const next: AxiosRequestConfig = { ...original }
    next.headers = { ...(original.headers as object), Authorization: `Bearer ${newToken}` }
    return apiClient.request(next)
  },
)

export default apiClient
