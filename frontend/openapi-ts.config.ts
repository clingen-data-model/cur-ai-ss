import { defineConfig } from '@hey-api/openapi-ts'

export default defineConfig({
  input: './api-spec.json',
  output: './src/api/generated',
  plugins: [
    '@hey-api/client-fetch',
    {
      name: '@hey-api/typescript',
      enums: 'javascript',
    },
    {
      name: '@hey-api/sdk',
      // Must match the responseStyle the client is configured with in
      // src/lib/api.ts. The generator's default is 'fields', which types every
      // call as `{ data, error, request, response }` -- a shape the configured
      // client never returns. That mismatch is not cosmetic: it makes
      // `query.data?.data` type-check and be undefined at runtime, which is how
      // the pipeline progress bars ended up permanently empty, and it is why
      // call sites had grown `Array.isArray(...)` guards to recover a type the
      // SDK was already returning.
      responseStyle: 'data',
    },
  ],
})
