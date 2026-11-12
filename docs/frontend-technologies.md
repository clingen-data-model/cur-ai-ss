# Frontend technologies

A tour of the libraries and tools behind the React SPA in `frontend/`, five sentences each. Explanations come from `frontend/README.md` and the source under `frontend/src/`. Links go to each project's homepage.

## Core

### [React 19](https://react.dev)
1. React is the UI library, and every component in `src/` is a React function component.
2. `main.tsx` mounts the app with `createRoot` inside `React.StrictMode`.
3. Components re-render when their state, props or context change.
4. Hooks like `useState` and `useMemo` hold local UI state and derived values.
5. Server data does not live in React state here. It lives in the React Query cache.

### [TypeScript](https://www.typescriptlang.org)
1. TypeScript adds static types to the whole codebase, in strict mode.
2. `tsc -b` runs before `vite build`, so a type error fails the build.
3. The generated API client carries the backend's types into the frontend.
4. A renamed or removed endpoint therefore shows up as a compile error, not a runtime 404.
5. `@/*` path aliases are configured in `tsconfig.json` and mirrored in Vite.

### [Vite](https://vite.dev)
1. Vite is the dev server and production bundler.
2. `pnpm dev` serves with hot reload on port 8501.
3. `pnpm build` produces the static `dist/` folder that nginx serves.
4. Its `base` option, set from `VITE_BASE_PATH`, rewrites asset URLs for the `/v2/` prefix.
5. It also exposes that prefix as `import.meta.env.BASE_URL`, which the router uses.

## Routing and data

### [TanStack Router](https://tanstack.com/router)
1. The router maps URLs to page components and renders them inside the root layout's `<Outlet />`.
2. Routes are declared by hand in `routeTree.ts`, since the codegen plugin isn't installed.
3. A `basepath` makes it work under `/v2`.
4. The dashboard's `validateSearch` turns `?status=` and `?worked_by=` into typed filter state.
5. Registering the router type makes `<Link>` and `useParams` type-checked everywhere.

### [TanStack Query](https://tanstack.com/query)
1. Query caches server responses by query key, such as `['occurrences', paperId]`.
2. `useQuery` reads from the cache and fetches when data is missing or stale.
3. `useMutation` runs writes, then calls `invalidateQueries` so affected data refetches.
4. `staleTime` is 5 minutes on most reads, and task queries poll with `refetchInterval`.
5. A `MutationCache` handler in `main.tsx` refreshes the snapshot list after any tagged edit.

### [TanStack Table](https://tanstack.com/table)
1. Table is a headless library that handles sorting, filtering and row expansion without rendering any markup.
2. Pages define `ColumnDef[]` arrays describing each column.
3. `ui/data-table.tsx` turns those definitions into real `<table>` elements.
4. The Occurrences tab uses it with expandable rows for patient and variant detail panels.
5. `PapersTable`, `GeneTable` and the unassociated-items tabs share the same wrapper.

### [Hey API openapi-ts](https://heyapi.dev/openapi-ts)
1. This tool generates the typed API client from the backend's OpenAPI schema.
2. `bin/generate-api-spec` dumps the FastAPI schema to `api-spec.json`.
3. `pnpm api:generate` then writes `src/api/generated/` with the SDK functions, types and fetch client.
4. `openapi-ts.config.ts` sets `responseStyle: 'data'`, so calls resolve to the body.
5. The output is gitignored and rebuilt by `pnpm build`, so never edit it by hand.

### [FastAPI](https://fastapi.tiangolo.com)
1. FastAPI is the Python backend the SPA talks to.
2. It builds an OpenAPI schema automatically from its Pydantic models and routes.
3. That schema is the single source of truth for the frontend's types.
4. In production nginx proxies `/api/` to it, so the browser sees one origin.
5. It issues the JWTs that `lib/auth.tsx` stores and replays as bearer tokens.

## UI and styling

### [Tailwind CSS v4](https://tailwindcss.com)
1. Tailwind provides utility classes like `px-6` and `text-muted-foreground`, applied directly in JSX.
2. v4 has no JS config file; everything lives in `index.css`.
3. An `@theme inline` block maps CSS variables like `--primary` to utilities like `bg-primary`.
4. The variables hold ClinGen's blue and teal palette.
5. It runs through the `@tailwindcss/vite` plugin during dev and build.

### [Base UI](https://base-ui.com)
1. Base UI supplies unstyled, accessible behaviour for dialogs, selects, popovers and tooltips.
2. It handles focus trapping, keyboard navigation and popover positioning.
3. It ships no styles, so the project's own Tailwind classes provide the look.
4. The project uses it instead of Radix, so new components must come from shadcn's base registry.
5. About 13 files import it, mostly under `components/ui/`.

### [shadcn/ui](https://ui.shadcn.com)
1. shadcn/ui is a collection of component source files you copy into your repo, not a runtime package.
2. `pnpm dlx shadcn@latest add <name>` writes them into `components/ui/`.
3. This project uses the `base-nova` style, configured in `components.json`.
4. Once copied, the files are yours to edit freely.
5. After adding one, check that the CLI didn't write `import { cn } from "cn"`, which should be `@/lib/utils`.

### [class-variance-authority](https://cva.style), [clsx](https://github.com/lukeed/clsx) and [tailwind-merge](https://github.com/dcastil/tailwind-merge)
1. These three build the class strings in the UI primitives.
2. CVA declares typed variants, such as `variant` and `size` on `Button`.
3. clsx joins class names conditionally.
4. tailwind-merge resolves conflicts, so a passed-in `p-4` beats a default `p-2`.
5. The `cn()` helper in `lib/utils.ts` combines clsx and tailwind-merge.

### [lucide-react](https://lucide.dev)
1. Lucide is the SVG icon set.
2. Icons are imported as React components, for example `FileText` or `CircleAlert`.
3. They size and colour through Tailwind classes.
4. It is the most-imported package in the app.
5. shadcn is configured to use it through `iconLibrary: "lucide"`.

### [sonner](https://sonner.emilkowal.ski)
1. Sonner shows toast notifications.
2. `<Toaster>` is mounted once in the root layout.
3. Components call `toast.success(...)` or `toast.error(...)` from mutation callbacks.
4. Error toasts use `apiErrorMessage` to show the backend's `detail` text.
5. `next-themes` is imported only by the sonner wrapper, to match its theme.

## State

### [Zustand](https://github.com/pmndrs/zustand)
1. Zustand is a small global store for client-only state.
2. `stores/ui.ts` defines `useUIStore` with a menu open flag and toggle functions.
3. Nothing in `src/` imports it yet.
4. Server data goes through React Query instead, and auth goes through Context.
5. It is available if shared UI state outgrows `useState`.

## Documents and visualisation

### [react-pdf](https://github.com/wojtekmaj/react-pdf) (on [pdf.js](https://mozilla.github.io/pdf.js/))
1. react-pdf renders PDFs in React using Mozilla's pdf.js.
2. `PdfViewer` and `PaperMetadataTab` use it, and evidence highlights are drawn as overlays on the text layer.
3. `PdfHighlightProvider` supplies the boxes, fetched from `POST /papers/{id}/highlight`.
4. There must be exactly one `pdfjs-dist` in the tree, so import `pdfjs` from `react-pdf`.
5. The pdf.js worker currently loads from a CDN, which is a runtime dependency on cdnjs.

### [react-markdown](https://github.com/remarkjs/react-markdown) with [remark-gfm](https://github.com/remarkjs/remark-gfm), [rehype-raw](https://github.com/rehypejs/rehype-raw) and [rehype-sanitize](https://github.com/rehypejs/rehype-sanitize)
1. react-markdown renders markdown strings as React elements.
2. remark-gfm adds GitHub-style tables and task lists.
3. rehype-raw lets literal HTML such as `<mark>` render as elements, which highlights matched evidence quotes.
4. rehype-sanitize strips unsafe HTML before it reaches the DOM.
5. `DocumentEvidenceViewer` and `PedigreeTab` use this stack.

### [React Flow](https://reactflow.dev) and [dagre](https://github.com/dagrejs/dagre)
1. React Flow (`@xyflow/react`) draws interactive node-and-edge graphs.
2. `TaskDAG` uses it to show the extraction pipeline.
3. React Flow doesn't lay out graphs, so dagre computes each node's position.
4. Dagre runs first on the dependency graph, then React Flow renders the result.
5. The graph reflects the backend's task dependency model, where finishing a task queues its successors.

## Tooling

### [pnpm](https://pnpm.io)
1. pnpm installs the JavaScript dependencies.
2. `pnpm-lock.yaml` pins exact versions.
3. Scripts like `dev`, `build`, `lint` and `type-check` run through it.
4. `prebuild` runs automatically before `build` and triggers API client generation.
5. `pnpm dlx` runs one-off tools like the shadcn CLI.

### [ESLint](https://eslint.org)
1. ESLint lints the TypeScript and TSX files.
2. The flat config in `eslint.config.js` enables the TypeScript rules.
3. It also enables `react-hooks/rules-of-hooks` as an error.
4. `react-hooks/exhaustive-deps` is a warning.
5. The generated client and build output are excluded, and CI does not run it, so run `pnpm lint` yourself.
