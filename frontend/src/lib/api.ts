import { OpenAPI } from '@/api/generated'

export const apiUrl = import.meta.env.VITE_API_URL
if (!apiUrl) {
  throw new Error('VITE_API_URL environment variable is not set. Set it in .env.local or as an environment variable.')
}

OpenAPI.BASE = apiUrl
