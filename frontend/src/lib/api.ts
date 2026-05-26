import { OpenAPI } from '@/api/generated'

export const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

OpenAPI.BASE = apiUrl
