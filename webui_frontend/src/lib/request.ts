import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

const configuredBaseUrl = (import.meta.env.VITE_API_BASE as string | undefined)?.trim()

const api = axios.create({
  baseURL: configuredBaseUrl ? configuredBaseUrl.replace(/\/$/, '') : '',
  timeout: 30000,
})

type ApiErrorPayload = {
  detail?: string
  message?: string
}

export function normalizeError(error: unknown): never {
  if (axios.isAxiosError<ApiErrorPayload>(error)) {
    const axiosError = error as AxiosError<ApiErrorPayload>
    const message =
      axiosError.response?.data?.detail ??
      axiosError.response?.data?.message ??
      axiosError.message ??
      'Request failed'
    throw new Error(message)
  }

  if (error instanceof Error) {
    throw error
  }

  throw new Error('Unknown request failure')
}

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  try {
    const { data } = await api.request<T>(config)
    return data
  } catch (error) {
    normalizeError(error)
  }
}

export function apiGet<T>(url: string, config?: Omit<AxiosRequestConfig, 'method' | 'url'>): Promise<T> {
  return request<T>({ ...config, method: 'GET', url })
}

export function apiPost<T>(
  url: string,
  data?: unknown,
  config?: Omit<AxiosRequestConfig, 'method' | 'url' | 'data'>,
): Promise<T> {
  return request<T>({ ...config, method: 'POST', url, data })
}

export { api }
