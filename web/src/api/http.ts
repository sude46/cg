import axios, { AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios'
import type { ApiEnvelope, ApiErrorBody } from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api'

/** 统一错误对象：解包后端的 { code, error, request_id, retry_after } */
export class ApiError extends Error {
  code: number
  requestId?: string
  retryAfter?: number

  constructor(message: string, code: number, requestId?: string, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.requestId = requestId
    this.retryAfter = retryAfter
  }
}

/* ---------- access token 存放：内存（XSS 面最小化），刷新后原地更新 ---------- */
let accessToken: string | null = null
export const setAccessToken = (t: string | null) => {
  accessToken = t
}
export const getAccessToken = () => accessToken

const REFRESH_KEY = 'cg_refresh_token'
export const getRefreshToken = () => localStorage.getItem(REFRESH_KEY)
export const setRefreshToken = (t: string | null) => {
  if (t) localStorage.setItem(REFRESH_KEY, t)
  else localStorage.removeItem(REFRESH_KEY)
}

export const http = axios.create({ baseURL: BASE_URL, timeout: 10000 })

/* ---------- 请求拦截：携带 access token（refresh 调用自带头则不覆盖） ---------- */
http.interceptors.request.use((config) => {
  const t = getAccessToken()
  if (t && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${t}`
  }
  return config
})

/* ---------- 401 刷新队列：并发请求挂起，刷新成功统一重放 ---------- */
type RetryableConfig = AxiosRequestConfig & { _retried?: boolean }
let refreshing: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const rt = getRefreshToken()
  if (!rt) throw new ApiError('登录已过期', 401)
  const res = await http.post<ApiEnvelope<{ access_token: string; refresh_token?: string }>>(
    '/users/refresh',
    {},
    { headers: { Authorization: `Bearer ${rt}` }, _retried: true } as RetryableConfig,
  )
  const data = res.data.data
  setAccessToken(data.access_token)
  // 轮换后必须保存新的 refresh；Redis 降级时后端不返回新 refresh，则保留旧的
  if (data.refresh_token) setRefreshToken(data.refresh_token)
  return data.access_token
}

function forceLogout() {
  setAccessToken(null)
  setRefreshToken(null)
  if (!window.location.hash.includes('/login')) {
    window.location.hash = '#/login'
  }
}

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const { response, config } = error
    if (!response) {
      return Promise.reject(new ApiError('网络异常，请检查连接', -1))
    }
    const body = (response.data || {}) as Partial<ApiErrorBody> & { message?: string }
    const status = response.status
    const cfg = (config || {}) as RetryableConfig

    // 429 限流：读出 retry_after，交给调用方做提示
    if (status === 429) {
      return Promise.reject(
        new ApiError(body.error || '操作太频繁，请稍后再试', 429, body.request_id, body.retry_after),
      )
    }

    // 401：尝试静默刷新后重放原请求（登录/注册/刷新自身除外）
    const url = cfg.url || ''
    const isAuthApi =
      url.includes('/users/login') || url.includes('/users/register') || url.includes('/users/refresh')
    if (status === 401 && !cfg._retried && !isAuthApi) {
      cfg._retried = true
      try {
        refreshing = refreshing ?? refreshAccessToken().finally(() => (refreshing = null))
        await refreshing
        return http(cfg)
      } catch (e) {
        forceLogout()
        return Promise.reject(e)
      }
    }

    if (status === 401) forceLogout()
    return Promise.reject(
      new ApiError(body.error || body.message || `请求失败 (${status})`, body.code ?? status, body.request_id),
    )
  },
)

/** 解包统一信封：成功 { code:200, data, message }，失败已在拦截器里抛 ApiError */
export async function unwrap<T>(p: Promise<AxiosResponse<ApiEnvelope<T>>>): Promise<T> {
  const res = await p
  return res.data.data
}
