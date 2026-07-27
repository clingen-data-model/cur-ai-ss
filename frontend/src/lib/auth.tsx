/* Authentication state.
 *
 * Mirrors the Streamlit gate in lib/ui/auth.py: the API issues a JWT from
 * /auth/login, we hold it client-side and replay it as a bearer token. The
 * token is the only source of truth for "signed in" — there is no server-side
 * session and no refresh token, so an expired token simply starts failing and
 * we bounce back to the login screen.
 */
import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMeAuthMeGet, loginAuthLoginPost } from '@/api/generated'
import type { TokenResp, UserResp } from '@/api/generated/types.gen'
import { getAccessToken, setAccessToken, onUnauthorized } from '@/lib/api'

export const MIN_PASSWORD_LENGTH = 8

// Mirrors _EMAIL_RE in lib/models/user.py so the client rejects the same
// addresses the API would.
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

interface AuthContextValue {
  token: string | null
  user: UserResp | null
  isLoading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signOut: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getAccessToken())
  const queryClient = useQueryClient()

  const signOut = useCallback(() => {
    setAccessToken(null)
    setToken(null)
    // Drop every cached response — they were fetched as the previous user.
    queryClient.clear()
  }, [queryClient])

  // A 401 from any endpoint means the token is expired or revoked. Clearing it
  // here re-renders the guard, which sends the user to /login.
  useEffect(() => onUnauthorized(signOut), [signOut])

  // Resolves the token into a user. A 401 is handled by the interceptor above,
  // so there is no point retrying it.
  const { data: user, isLoading } = useQuery({
    queryKey: ['auth', 'me', token],
    queryFn: () => getMeAuthMeGet(),
    enabled: token !== null,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  // The SDK's static return type is the full response envelope, but the client is
  // configured with responseStyle: 'data', so at runtime this is the body. The rest
  // of the app casts the same way (see hooks/usePaperPatients.ts).
  const signIn = useCallback(async (email: string, password: string) => {
    const result = (await loginAuthLoginPost({
      body: { email, password },
    })) as unknown as TokenResp
    setAccessToken(result.access_token)
    setToken(result.access_token)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        user: (user as UserResp | undefined) ?? null,
        // Only "loading" while we have a token but have not yet resolved it.
        isLoading: token !== null && isLoading,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}

/** Pull the FastAPI `detail` string out of a thrown error, else a fallback. */
export function errorDetail(err: unknown, fallback: string): string {
  const detail = (err as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  const message = (err as { message?: unknown })?.message
  if (typeof message === 'string') return message
  return fallback
}
