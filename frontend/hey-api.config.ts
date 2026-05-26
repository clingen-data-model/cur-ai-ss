/* Hey API configuration for generating TypeScript client from FastAPI OpenAPI schema
 * This generates a type-safe API client with all endpoints, models, and schemas
 * from your FastAPI backend.
 *
 * Usage:
 *   pnpm api:generate
 *
 * Then import and use the client:
 *   import { Client } from '@/api/generated'
 *   const client = new Client({ BASE: 'http://localhost:8000' })
 *   await client.papers.listPapers()
 */
import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: './src/api/generated',
    format: 'prettier',
  },
  plugins: ['@hey-api/sdk'],
})
