import { client } from '@/api/generated/client.gen'

const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TOKEN_KEY = 'caa.access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

const unauthorizedHandlers = new Set<() => void>()

/** Subscribe to 401s. Returns an unsubscribe fn. */
export function onUnauthorized(handler: () => void): () => void {
  unauthorizedHandlers.add(handler)
  return () => unauthorizedHandlers.delete(handler)
}

// Reads are open, but every mutating endpoint is behind HTTPBearer. Supplying `auth`
// lets the generated SDK attach the token to exactly those operations that declare
// the security scheme. Returning undefined simply omits the header.
client.setConfig({
  baseUrl,
  responseStyle: 'data',
  throwOnError: true,
  auth: () => getAccessToken() ?? undefined,
})

// Tokens last ACCESS_TOKEN_EXPIRE_MINUTES (24h by default) and there is no refresh,
// so a session will eventually start 401ing mid-use. Catch it centrally and let the
// auth layer clear the token, rather than surfacing a confusing "save failed" toast.
//
// /auth/login is exempt: a 401 there means bad credentials, and the form reports it.
client.interceptors.response.use((response, request) => {
  if (response.status === 401 && !request.url.endsWith('/auth/login')) {
    unauthorizedHandlers.forEach((handler) => handler())
  }
  return response
})
