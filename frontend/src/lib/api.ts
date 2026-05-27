import { OpenAPI } from '@/api/generated'

if (!import.meta.env.VITE_API_URL) {
  throw new Error('VITE_API_URL environment variable is not set. Set it in .env.local or as an environment variable.')
}

OpenAPI.BASE = import.meta.env.VITE_API_URL
