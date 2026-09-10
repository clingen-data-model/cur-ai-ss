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
    '@hey-api/sdk',
  ],
})
