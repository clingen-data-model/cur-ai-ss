import { client } from '@/api/generated/client.gen'

const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

client.setConfig({ baseUrl, responseStyle: 'data', throwOnError: true })
