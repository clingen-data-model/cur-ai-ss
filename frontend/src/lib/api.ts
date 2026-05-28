import { client } from '@/api/generated/client.gen'

if (!import.meta.env.VITE_API_URL) {
  throw new Error('VITE_API_URL environment variable is not set. Set it in .env.local or as an environment variable.')
}

client.setConfig({ baseUrl: import.meta.env.VITE_API_URL, responseStyle: 'data', throwOnError: true })
