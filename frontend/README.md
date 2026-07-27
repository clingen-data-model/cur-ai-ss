# Frontend

React + TypeScript frontend using TanStack Router and Tailwind CSS.

## Setup

```bash
pnpm install
```

## Development

```bash
pnpm dev
```

## Building

```bash
pnpm build
pnpm preview
```

## API Integration

### Generate API Specification

To generate the OpenAPI schema from the backend:

```bash
../bin/generate-api-spec
```

This creates `api-spec.json` with the complete API specification. Useful for:
- Type generation with tools like OpenAPI Generator
- API documentation
- Frontend integration planning

The spec is generated from the FastAPI code without requiring the backend server to be running.
