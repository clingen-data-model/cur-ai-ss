/* Extracts a human-readable message from a thrown API error.
 *
 * The generated client's `throwOnError` throws the parsed JSON response body
 * directly (see api/generated/client/client.gen.ts), not an Error instance --
 * so it's either FastAPI's HTTPException shape ({detail: string}) or a
 * pydantic validation error ({detail: [{msg, loc, type}, ...]}), e.g. the
 * "testing_methods must contain at most two items" model_validator. */
interface ApiErrorBody {
  detail?: string | { msg?: string }[]
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as ApiErrorBody | undefined)?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const messages = detail.map((d) => d.msg).filter((msg): msg is string => !!msg)
    if (messages.length > 0) return messages.join('; ')
  }
  return fallback
}
