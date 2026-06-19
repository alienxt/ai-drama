import axios, { AxiosError } from 'axios';
import { appMessage } from './appMessage';
import type { PageResult } from './types';

export type ApiResponse<T> = {
  success: boolean;
  data: T;
  error: null | { code: string; message: string; details?: Record<string, unknown> };
  traceId?: string;
};

const tokenKey = 'ai-drama-token';
const tokenCookie = 'ai-drama-token';

function writeTokenCookie(token: string) {
  document.cookie = `${tokenCookie}=${encodeURIComponent(token)}; path=/; max-age=2592000; SameSite=Lax`;
}

export const tokenStore = {
  get: () => {
    const token = localStorage.getItem(tokenKey);
    if (token) {
      writeTokenCookie(token);
    }
    return token;
  },
  set: (token: string) => {
    localStorage.setItem(tokenKey, token);
    writeTokenCookie(token);
  },
  clear: () => {
    localStorage.removeItem(tokenKey);
    document.cookie = `${tokenCookie}=; path=/; max-age=0; SameSite=Lax`;
  },
};

export const http = axios.create({
  baseURL: '/api',
  timeout: 20000,
});

http.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown>;
    if (body && body.success === false) {
      const message = body.error?.message || '请求失败';
      appMessage.error(message);
      throw new Error(message);
    }
    return response;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    const status = error.response?.status;
    const shouldRelogin = status === 401 || status === 403;
    const message =
      error.response?.data?.error?.message ||
      (shouldRelogin ? '登录已过期，请重新登录' : error.message || '请求失败');
    appMessage.error(message);
    if (shouldRelogin) {
      tokenStore.clear();
      if (location.pathname !== '/login') {
        location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export async function apiGet<T>(url: string): Promise<T> {
  const response = await http.get<ApiResponse<T>>(url);
  return response.data.data;
}

export async function apiGetPage<T>(
  url: string,
  page: number,
  size: number,
  params: Record<string, string | number | boolean | string[] | undefined> = {},
): Promise<PageResult<T>> {
  const response = await http.get<ApiResponse<PageResult<T>>>(url, {
    params: { page, size, ...params },
    paramsSerializer: {
      indexes: null,
    },
  });
  return response.data.data;
}

export async function apiPost<T>(url: string, payload?: unknown): Promise<T> {
  const response = await http.post<ApiResponse<T>>(url, payload);
  return response.data.data;
}

export async function apiPut<T>(url: string, payload?: unknown): Promise<T> {
  const response = await http.put<ApiResponse<T>>(url, payload);
  return response.data.data;
}

export async function apiPatch<T>(url: string, payload?: unknown): Promise<T> {
  const response = await http.patch<ApiResponse<T>>(url, payload);
  return response.data.data;
}

export async function apiDelete<T>(url: string): Promise<T> {
  const response = await http.delete<ApiResponse<T>>(url);
  return response.data.data;
}
