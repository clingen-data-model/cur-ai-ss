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

// Reads are open, but every mutating endpoint is behind HTTPBearer. Supplying `auth`
// lets the generated SDK attach the token to exactly those operations that declare
// the security scheme. Returning undefined simply omits the header.
client.setConfig({
  baseUrl,
  responseStyle: 'data',
  throwOnError: true,
  auth: () => getAccessToken() ?? undefined,
})
