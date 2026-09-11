# Frontend

React + TypeScript single-page app that is replacing the Streamlit UI. It talks to the
FastAPI backend through a fully generated, typed client.

In production it is served as **static files by nginx under the `/v2/` prefix**, beside
the Streamlit UI which still owns `/`. See [Deployment](#deployment) below.

## Setup

```bash
pnpm install

# One-time per machine: install the shadcn/ui AI skill (gitignored)
pnpm dlx skills add shadcn/ui
```

## Adding a shadcn/ui component

```bash
pnpm dlx shadcn@latest add <name>
```

**Check the diff before committing.** As of shadcn 4.21.0 the CLI fails to
resolve the `utils` alias from `components.json` and writes

```ts
import { cn } from "cn"        // wrong
import { cn } from "@/lib/utils"  // what every other primitive uses
```

then installs an unrelated npm package named `cn` to satisfy the bare specifier.
That package is a genuine clsx + tailwind-merge replacement, so nothing crashes
-- the new component just merges classes with a different engine than the rest
of the app, silently. Repoint the import and `pnpm remove cn`.

Take components from the **base** registry, not `radix`: this project is Base UI
(`components.json` -> `"style": "base-nova"`) and carries no `@radix-ui`
packages, so a Radix component pulls in a second primitive library. The docs URL
is `ui.shadcn.com/docs/components/base/<name>`.

## Development

```bash
pnpm dev          # Vite dev server on http://localhost:8501
pnpm type-check   # tsc --noEmit
pnpm lint         # eslint
pnpm build        # regenerate API client, then tsc -b && vite build -> dist/
pnpm preview      # serve the production build locally
```

`pnpm dev` expects the backend on `http://localhost:8000` (`./bin/api` from the repo
root). The frontend is **not** covered by CI — `.github/workflows/ci-check.yml` runs
Python checks only, so run `pnpm type-check` and `pnpm build` yourself before deploying.

## Architecture

```
src/
  main.tsx              Entry point: QueryClient + RouterProvider, router basepath
  index.css             Tailwind v4 entry, font imports, theme tokens
  routeTree.ts          Route table, hand-written. No TanStack Router codegen
                        plugin is installed, so a new component under routes/
                        must also be registered here to be reachable
  routes/               File-based routes
    __root.tsx          Shared layout: header, footer, AuthGate, Toaster
    index.tsx           Paper list (dashboard)
    login.tsx           Token login, mirrors the Streamlit auth gate
    papers.$paperId.patients.tsx   Paper detail: families, patients, PDF viewer
  components/           Feature components (GeneTable, TaskDAG, PatientDetails, ...)
    ui/                 Vendored shadcn/ui primitives - owned code, edit freely
  api/generated/        Generated API client (gitignored, see below)
  lib/
    api.ts              Client config: base URL, bearer auth, 401 interception
    auth.tsx            AuthProvider / useAuth, token in localStorage
    utils.ts            cn() class merging helper
  hooks/                Data hooks wrapping the generated SDK in React Query
  stores/ui.ts          Zustand store for ephemeral UI state
```

### The API client is generated, not written

`pnpm build` runs a `prebuild` hook that:

1. Runs `../bin/generate-api-spec`, which imports `lib.api.app` and dumps the FastAPI
   OpenAPI schema to `frontend/api-spec.json`. The backend does **not** need to be
   running, but it does read `.env` (via pydantic-settings), so a valid environment is
   required for a build.
2. Runs `pnpm api:generate`, which turns that spec into `src/api/generated/` via
   `@hey-api/openapi-ts`.

Both `api-spec.json` and `src/api/generated/` are gitignored, so **a fresh clone has no
API client until you run `pnpm build`** (or `pnpm api:generate` against an existing
spec). Backend schema changes reach the frontend by rebuilding, and a renamed or removed
endpoint surfaces as a type error rather than a runtime 404.

## Deployment

The Ansible playbook (`infrastructure/ansible/playbook.yml`) builds the SPA on the VM
after syncing Python dependencies and writing `.env`, then nginx serves `dist/` directly.

Two environment variables shape the build, both set by the playbook:

| Variable | Local default | VM value | Purpose |
| --- | --- | --- | --- |
| `VITE_BASE_PATH` | `/` | `/v2/` | Vite `base`. Rewrites every emitted asset URL and is exposed as `import.meta.env.BASE_URL`. |
| `VITE_API_URL` | unset → `http://localhost:8000` | `/api` | Base URL for API calls and API-served assets. Same-origin on the VM, so nginx proxies it and CORS never applies. |

Anything root-relative has to be built from `import.meta.env.BASE_URL`, or it escapes the
prefix and lands on the Streamlit app:

- Navigation uses `<Link>` from TanStack Router, never `<a href="/...">`. The router is
  given `basepath` from `BASE_URL`, so it prefixes links and strips the prefix when
  matching.
- `public/` assets are referenced as `` `${import.meta.env.BASE_URL}clingen-logo.svg` ``
  in TSX, and as `%BASE_URL%clingen-logo.svg` in `index.html` (Vite substitutes it).
- API-served assets (PDF and thumbnail URLs) are built from `API_BASE_URL`, exported by
  `lib/api.ts`, rather than reading `import.meta.env.VITE_API_URL` directly.

### Known deployment caveats

- **The pdf.js worker is loaded from a CDN.** `TwoColumnWithBottomRightPdf.tsx` sets
  `pdfjs.GlobalWorkerOptions.workerSrc` to `//unpkg.com/pdfjs-dist@<version>/...`, so PDF
  rendering depends on unpkg being reachable from the browser. Serving the worker from
  our own bundle would remove that third-party runtime dependency.
- **The main chunk is ~1.4 MB** (~440 kB gzipped) and Vite warns about it. No code
  splitting is configured yet.

## The react-pdf-highlighter patch

`patches/react-pdf-highlighter@8.0.0-rc.0.patch` is a one-line fix applied by pnpm at
install time. It is recorded in `pnpm-lock.yaml` under `patchedDependencies` with a
content hash, and pnpm 12 discovers the `patches/` directory on its own — there is no
`pnpm.patchedDependencies` block in `package.json`, and none is needed.

**Editing the patch changes that hash**, so a patch edit must be followed by a
`pnpm install` that rewrites the lockfile, or the next `pnpm install --frozen-lockfile`
(which is what the deploy runs) will fail.

### What breaks without it

Scroll-to-highlight silently stops working, and the PDF stops scaling to fit its
container. No error is raised and nothing appears in the console — clicking a piece of
evidence just does not move the PDF.

### Why

In `PdfHighlighter.init()` the library creates a **fresh** `EventBus` on every call, but
creates the `PDFViewer` only once:

```js
const eventBus = new pdfjs.EventBus();              // new bus on every init()
this.viewer = this.viewer || new pdfjs.PDFViewer({  // viewer built once, keeps bus #1
  eventBus, ...
});
this.viewer.setDocument(pdfDocument);               // emits `pagesinit` on the viewer's bus
this.attachRef(eventBus);                           // subscribes the listener to the NEW bus
```

`componentWillUnmount` only calls `unsubscribe()`; it never clears `this.viewer`. So on any
**second** `init()` on the same component instance, the viewer still holds bus #1 while the
`pagesinit` listener sits on bus #2. The event fires where nobody is listening.

That matters because `onDocumentReady` — the `pagesinit` handler — is what calls
`handleScaleValue()` and, crucially, `scrollRef(this.scrollTo)`. If it never runs, the
parent is never handed its scroll function. In `TwoColumnWithBottomRightPdf.tsx` that
leaves `scrollToRef.current` at `null`, so `PdfViewer.scrollTo()` is a silent no-op.

### When a second `init()` happens

Two ways, and **only the first is development-only**:

1. **`React.StrictMode`** (`src/main.tsx`) deliberately mounts, unmounts and remounts in
   development, so `componentDidMount` runs twice on the same instance.
2. **`componentDidUpdate` re-runs `init()` whenever the `pdfDocument` prop changes.** This
   happens in production — the same `PdfHighlighter` instance being handed a different
   document takes exactly the same broken path.

The patch's own inline comment cites StrictMode, which is how it was found; the second
case is the one that matters in a deployed build.

### The fix, and what else was possible

```js
this.viewer.eventBus = eventBus;  // re-point the reused viewer at the current bus
```

Two alternatives, both larger and neither attempted:

- **Stop reusing the viewer** (drop the `this.viewer ||` guard). Correct, but throws away
  already-rendered pages on every document change.
- **Stop recreating the bus** — hoist the `EventBus` onto the instance so viewer and
  listener always share one. Probably the right upstream fix, but it changes the
  subscribe/unsubscribe lifecycle rather than one assignment.

Not reported upstream. `8.0.0-rc.0` is a pre-release, so the first thing to check on any
version bump is whether this is still needed — re-test by switching between two papers
in one session and confirming that clicking evidence still scrolls the PDF.

## JavaScript dependencies

Every package in `package.json`, what it does, and where it is used. "Unused" means
declared but not imported anywhere in `src/` yet.

### Runtime dependencies

| Package | What it is | How this app uses it |
| --- | --- | --- |
| `react` | UI library (v19) | Everything. |
| `react-dom` | React's DOM renderer | `main.tsx` mounts the app with `createRoot`. |
| `@tanstack/react-router` | Type-safe router | Route components live in `routes/`, registered by hand in `routeTree.ts` (the codegen plugin is not installed). Given a `basepath` so the app works under `/v2`. |
| `@tanstack/react-query` | Server-state cache | All API reads/mutations: caching, deduping, background refetch, invalidation. Used in 7 files. |
| `@tanstack/react-table` | Headless table logic (no markup) | Sorting/filtering/row models behind `GeneTable` and `ui/data-table`. |
| `@tanstack/react-form` | Form state and validation | **Unused** — no imports yet. |
| `@base-ui/react` | Unstyled, accessible UI primitives | The foundation of the vendored `components/ui/*` (dialog, popover, select, tooltip, …). Used in 13 files. |
| `lucide-react` | SVG icon set | Icons throughout the app — the most-imported package (16 files). |
| `class-variance-authority` | Typed variant → class mapping | Declares size/tone variants on `ui/button`, `ui/badge`, etc. |
| `clsx` | Conditional className joining | Half of the `cn()` helper in `lib/utils.ts`. |
| `tailwind-merge` | Resolves conflicting Tailwind classes | The other half of `cn()`, so a passed-in `className` reliably overrides a default. |
| `tw-animate-css` | Animation utilities for Tailwind v4 | Imported by `index.css`; supplies the enter/exit animations the shadcn primitives expect. |
| `@tailwindcss/vite` | Tailwind v4's Vite plugin | Runs the Tailwind CSS pipeline during dev and build. Registered in `vite.config.ts`. |
| `@fontsource-variable/geist` | Self-hosted Geist variable font | Imported by `index.css`; woff2 files are emitted into `dist/assets/`, so no Google Fonts request. |
| `@fontsource-variable/inter` | Self-hosted Inter variable font | **Unused** — not imported by `index.css`. |
| `sonner` | Toast notifications | `<Toaster>` in `__root.tsx`; success/error toasts on save (6 files). |
| `next-themes` | Theme (light/dark) provider | Only used by `ui/sonner.tsx` to match the toast theme. Despite the name it is framework-agnostic, not Next.js-specific. |
| `cmdk` | Command-menu / filterable list primitive | Backs `ui/command.tsx`, which `ui/combobox.tsx` builds on (e.g. HPO term pickers). |
| `embla-carousel-react` | Carousel engine | Backs `ui/carousel.tsx`, pulled in with the shadcn carousel component. |
| `react-resizable-panels` | Draggable split panes | Backs `ui/resizable.tsx`, used for the paper detail split view. |
| `@xyflow/react` | Interactive node/edge canvas (React Flow) | Renders the extraction task DAG in `TaskDAG.tsx`. |
| `@dagrejs/dagre` | Directed-graph layout algorithm | Computes node positions for that DAG before React Flow draws it — React Flow does not do layout itself. |
| `pdfjs-dist` | Mozilla PDF.js engine | Pinned to exactly `4.4.168` because `react-pdf` and `react-pdf-highlighter` are compiled against that API. Also used directly for Grobid coordinate work. |
| `react-pdf` | React wrapper around PDF.js | Renders paper pages in `TwoColumnWithBottomRightPdf.tsx`. |
| `react-pdf-highlighter` | Highlight overlay for PDF.js pages | Draws evidence highlights on the rendered paper. Pinned to the pre-release `8.0.0-rc.0`, and **patched** — see [The react-pdf-highlighter patch](#the-react-pdf-highlighter-patch). |
| `zustand` | Minimal global state store | `stores/ui.ts`, for UI state that shouldn't live in the URL or the query cache. |
| `zod` | Runtime schema validation | **Unused** — the generated client provides types, and nothing validates at runtime yet. |
| `shadcn` | CLI that vendors shadcn/ui components | A tool, not a library: `pnpm dlx shadcn add <component>` copies source into `components/ui/`. Pinned to `latest`, so it can change under you. |

### Development dependencies

| Package | What it is | How this app uses it |
| --- | --- | --- |
| `vite` | Dev server and bundler | `pnpm dev` (HMR) and `pnpm build`. Owns the `base`/`/v2` rewriting. |
| `@vitejs/plugin-react` | React support for Vite | JSX transform and Fast Refresh. |
| `typescript` | Compiler and type checker | `tsc -b` gates the build; `pnpm type-check` runs it alone. |
| `@types/react`, `@types/react-dom` | React type definitions | Types for the two untyped runtime packages. |
| `@types/node` | Node.js type definitions | Needed because `vite.config.ts` reads `process.env.VITE_BASE_PATH`; enabled via `types: ["node"]` in `tsconfig.node.json`. |
| `@hey-api/openapi-ts` | OpenAPI → TypeScript client generator | Turns `api-spec.json` into `src/api/generated/` (fetch client, types, SDK) per `openapi-ts.config.ts`. |
| `esbuild` | JS/TS transformer and minifier | The minifier for the production build (`build.minify: 'esbuild'`). |
| `tailwindcss` | Utility-first CSS framework (v4) | The styling system; configured in CSS rather than a JS config file. |
| `postcss` | CSS transform pipeline | The pipeline Tailwind and autoprefixer plug into. |
| `autoprefixer` | Adds CSS vendor prefixes | PostCSS plugin for browser compatibility. |
| `eslint` | Linter | `pnpm lint`. |
| `@typescript-eslint/parser` | Lets ESLint parse TypeScript | Required for any TS linting. |
| `@typescript-eslint/eslint-plugin` | TypeScript lint rules | The TS-specific rule set. |
| `eslint-plugin-react-hooks` | Rules of Hooks enforcement | Catches conditional hook calls and missing dependencies. |

## Generated and ignored files

`frontend/.gitignore` excludes several files that look like they should be committed:

- `api-spec.json`, `src/api/generated/` — regenerated by `pnpm build`.
- `vite.config.js`, `vite.config.d.ts` — emitted by `tsc -b` from `vite.config.ts`
  because `tsconfig.node.json` sets `composite: true`. **Vite resolves
  `vite.config.js` before `vite.config.ts`**, so a stale `.js` silently shadows edits to
  the `.ts`. `pnpm build` runs `tsc -b` first and so always regenerates it; running
  `vite build` on its own after editing the config will use the stale file.
- `dist/` — the build output nginx serves.
