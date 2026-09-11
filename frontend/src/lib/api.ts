import { client } from '@/api/generated/client.gen'

/* Base URL every API call and API-served asset URL is built from.
 *
 * Set to '/api' by the VM build so requests stay same-origin behind nginx; unset in
 * local dev, where the API runs on its own port. Exported because paper thumbnails and
 * PDFs are plain <img>/pdf.js URLs rather than SDK calls, and they have to resolve
 * against the same origin as the SDK or they 404 under the '/v2' prefix.
 */
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
  baseUrl: API_BASE_URL,
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

/* Upload a paper with real progress.
 *
 * The generated SDK is fetch-based, and fetch exposes no upload-progress event, so a
 * large PDF on a slow link sits behind an indeterminate spinner with nothing moving.
 * This is the one call that needs XMLHttpRequest, whose `upload.onprogress` reports
 * bytes sent. Everything else should keep using the generated client.
 *
 * It deliberately mirrors what the SDK does for this operation (PUT /papers, bearer
 * auth, multipart with Content-Type left to the browser so it sets the boundary) and
 * re-fires the 401 handlers by hand, because the response interceptor above is
 * installed on the generated client and an XHR never passes through it. Without that
 * an expired token would fail an upload with a bare "Upload failed" instead of
 * clearing the session.
 */
export interface UploadProgress {
  loaded: number
  total: number
  /** 0-100, or null when the browser cannot compute a total. */
  percent: number | null
}

export interface UploadPaperBody {
  gene_symbol: string
  uploaded_file: File
  supplement_file?: File | null
}

export function uploadPaper(
  body: UploadPaperBody,
  onProgress?: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('gene_symbol', body.gene_symbol)
    form.append('uploaded_file', body.uploaded_file)
    if (body.supplement_file) form.append('supplement_file', body.supplement_file)

    const xhr = new XMLHttpRequest()
    xhr.open('PUT', `${API_BASE_URL}/papers`)

    const token = getAccessToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

    xhr.upload.onprogress = (event) => {
      onProgress?.({
        loaded: event.loaded,
        total: event.total,
        percent: event.lengthComputable
          ? Math.round((event.loaded / event.total) * 100)
          : null,
      })
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(xhr.responseText ? JSON.parse(xhr.responseText) : null)
        } catch {
          resolve(null)
        }
        return
      }
      if (xhr.status === 401) unauthorizedHandlers.forEach((handler) => handler())
      reject(new Error(errorDetail(xhr) ?? `Upload failed (${xhr.status})`))
    }

    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.ontimeout = () => reject(new Error('Upload timed out'))
    xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))

    signal?.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

/** FastAPI puts the human-readable reason in `detail`; fall back to raw text. */
function errorDetail(xhr: XMLHttpRequest): string | null {
  try {
    const parsed = JSON.parse(xhr.responseText)
    if (typeof parsed?.detail === 'string') return parsed.detail
  } catch {
    /* not JSON */
  }
  return xhr.responseText || null
}
