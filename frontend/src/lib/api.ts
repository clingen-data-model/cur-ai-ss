/* API client setup
 * This initializes the Hey API generated client for communication with your FastAPI backend.
 *
 * Usage:
 *   import { client } from '@/lib/api'
 *   const papers = await client.papers.listPapers()
 *
 * Once you run `pnpm api:generate`, this will import the generated client.
 * For now, this is a placeholder that you can use to set up the client instance.
 */

// TODO: Once you run `pnpm api:generate`, import and configure the generated client here
// import { Client } from '@/api/generated'

// export const client = new Client({
//   BASE: import.meta.env.VITE_API_URL || 'http://localhost:8000',
// })

export const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
