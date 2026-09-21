/* The one place pdfjs-dist's worker script URL is decided.
 *
 * react-pdf (PaperMetadataTab's embedded viewer), PdfViewer (the evidence
 * "View in PDF" sheet) and react-pdf-highlighter's own PdfLoader all
 * `import ... from 'pdfjs-dist'` -- the bare specifier resolves to one shared
 * module instance, so `GlobalWorkerOptions.workerSrc` is a single global
 * regardless of which file touches it. Previously each set it separately, at
 * their own point in the module graph: two different CDN hosts, one of them
 * still using the pre-v4 `.js` worker filename pdfjs-dist 4.x no longer ships
 * (only `.mjs`, confirmed by that URL 404ing), racing to overwrite each other
 * and react-pdf's own default of `'pdf.worker.mjs'` (a relative path that
 * 404s against this app's URLs too). Whichever assignment happened to run
 * last silently broke PDF rendering everywhere pdfjs is used, not just in the
 * file that set the wrong one -- and "last" depended on unrelated
 * import-order changes elsewhere, which is why it could look like it broke
 * for no reason.
 *
 * react-pdf-highlighter's PdfLoader adds a second wrinkle: it re-applies
 * `GlobalWorkerOptions.workerSrc` itself on every mount, from its own
 * `workerSrc` prop (default: a *different*, third CDN URL) -- see
 * PdfViewer.tsx, which passes PDF_WORKER_SRC explicitly so that reset lands
 * on the same URL as everything else instead of silently diverging.
 */
import * as pdfjs from 'pdfjs-dist'

export const PDF_WORKER_SRC = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`

// Also apply it immediately, for consumers (react-pdf's Document/Page) that
// have no per-instance workerSrc prop of their own to pass PDF_WORKER_SRC to.
// Import this from main.tsx, after the `routeTree` import -- see the comment
// there for why the ordering matters.
pdfjs.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC
