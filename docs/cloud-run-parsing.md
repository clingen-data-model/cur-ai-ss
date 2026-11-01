# PDF parsing on a Cloud Run GPU

Status, 2026-11-01: the service exists and a rehearsal of the worker's parse
through it works end to end. The worker still parses locally; nothing in the
deployment points at the service yet.

## Why

PDF Parsing is the one step of the pipeline that runs models of our own:
Docling's layout, table-structure and OCR models, on the CPU of the dev-caa
VM (`c4a-standard-2`, no GPU). On the dev-caa task history (51 completed PDF
Parsing tasks, measured from `started_at` to the row's last update, which
includes the vision table-correction calls) the step takes a median of 3.2
minutes per paper, 12 minutes at the slowest; CLAUDE.md records 15 minutes
for a 44-page supplement. Every
other step is an API call to a model provider, so this is where the VM's
size shows, and it is also the reason the VM cannot be any smaller.

docling-serve is the Docling project's HTTP server around the same
`DocumentConverter` the worker calls, published as a CUDA image. Cloud Run
runs a container with an NVIDIA L4 and scales it to zero between requests,
so the GPU costs nothing while no paper is being parsed.

## What exists

| Piece | Where |
| --- | --- |
| Terraform stack: Artifact Registry proxy, service account, Cloud Run service, invoker grants | `infrastructure/terraform/pdf-parsing/` (state prefix `pdf-parsing`) |
| Service | `pdf-parsing`, `us-east4`, one L4, 8 CPU / 32 GiB, max 1 instance, 2 conversions at once per instance, requests held up to 5 minutes, zonal redundancy off |
| Image | `docling-serve-cu128:v1.23.0` from ghcr.io through the `ghcr` remote repository (Cloud Run pulls only from Artifact Registry or Docker Hub) |
| Exchange bucket | `clingen-caa-pdf-parsing-exchange`: private, objects deleted after a day. The VM's service account can read, write and sign URLs for it (it holds `serviceAccountTokenCreator` on itself for V4 signing). Not used by the client yet: see item 4 below |
| Client | `lib/misc/pdf/remote.py`: one `POST /v1/convert/file` per PDF, Google identity token, document JSON back |
| Switch | `PDF_PARSING_SERVICE_URL` (`lib/core/environment.py`): set, `parse_content` converts PDFs remotely; unset, locally. DOCX supplements stay local either way |
| Rehearsal | `uv run python -m lib.bin.parse_remote_test paper.pdf --url ...` parses into a temporary `CAA_ROOT` and deletes it; `--compare-local` runs the in-process converter beside it, `--keep` leaves the files |

The service URL is a terraform output (`terraform output service_url`).
Callers need `roles/run.invoker`: the stack grants it to the VM's service
account and to the operators in `var.invokers`; from a laptop the client
falls back to `gcloud auth print-identity-token`.

### Versions

docling-serve v1.23.0 bundles docling 2.82.0, the version `pyproject.toml`
pins, so the service runs the same layout and table models the worker would.
The document schema is the same (`1.10.0`) in every docling-core up to the
newest, so a newer docling-serve's JSON also loads in the pinned
docling-core; the pin is about model parity, not about reading the response.
Bump `var.image_tag` together with the docling pin, and check the
`cu128` image exists for the tag first (some releases have none).

### What the worker keeps doing

Only the converter call moves. The worker still crops tables and figures
(`write_tables_and_images`), writes `words.json` (docling-parse, no model),
runs table correction and builds `anchored.md`/`anchors.json`. Figures come
back embedded in the document, already cropped at scale 4. Page renders do
not come back (one is ~20 MB at that scale); the client renders the pages
that carry a table with the same pypdfium2 backend so `TableItem.get_image`
crops them as before.

## Rehearsal results

Paper 106 (6 pages, 5 tables, 4 figures), service warm:

| | Cloud Run L4 | Laptop (M-series, MPS) |
| --- | --- | --- |
| Conversion | 23.9 s on the server, 26 s request, 28.5 s with token and client | 9.2 s |
| Tables, figures, words | 5, 4, 5915 | 5, 4, 5915 |
| Table and figure crops | identical pixel sizes | |
| Text blocks / anchors | 354 / 208 | 337 / 234 |

A 32-page, 6 MB PDF: 32 s on the server, 38 s for the request. Against the
3 to 12 minutes the VM takes, with the vision correction still to add on
either side.

The text-block difference is the OCR engine, not the GPU: docling picks an
engine automatically, `ocrmac` on a Mac and `rapidocr` on the server (the
server's log says so at boot). The remote output has a few more one-letter
blocks from figure OCR and splits two paragraphs differently. The venv has
`rapidocr` and no other Linux engine, so the VM uses `rapidocr` as well; the
server should match the VM more closely than the laptop does. Confirm by
running the rehearsal with `--compare-local` on the VM, or with a paper the
VM parsed and the files still on disk.

Cold start, from a scaled-to-zero service to the first answered request, is
about 5 minutes (image pull, then model load; a revision rollout takes the
same). The service takes two conversions at once on its one instance; the
worker sends one at a time until `TASK_CONCURRENCY[PDF_PARSING]` in
`lib/bin/worker.py` is raised, a cap set for Docling on the VM's CPU.

## Open before switching the worker

1. **The layout override is not on the server.** `lib/misc/pdf/layout.py`
   patches Docling's post-processor so a multi-panel figure survives as one
   picture instead of its best-scoring panel (paper 116, 2026-10-22).
   docling-serve runs stock Docling. Options: a derived image
   (`FROM docling-serve-cu128`, plus a `sitecustomize.py` that installs the
   override, built by Cloud Build since the laptop has no docker) or a
   docling plugin. Until then a paper whose figures depend on it should be
   parsed locally; the rehearsal on paper 116 would show the difference.
2. **OCR parity with the VM**, above.
3. **Sync or async.** The client holds one request open for the whole
   conversion, up to the server's `DOCLING_SERVE_MAX_SYNC_WAIT` of five
   minutes, ten times the longest conversion seen so far. docling-serve
   also has `/v1/convert/file/async` with polling; it would survive a
   dropped connection, at the cost of a poll loop and task bookkeeping on
   the worker. The 30-minute PDF Parsing lease (`lease_timeout_s`) covers
   the sync wait with room for the cold start.
4. **Request size.** The PDF goes in the request body. Cloud Run's HTTP/1
   limit is 32 MB. The exchange bucket is there for the alternative: upload
   the PDF, hand the service a signed URL as an `http_sources` entry of
   `/v1/convert/source`, and optionally have it put the result bundle back
   to a signed URL rather than hold the response open (docling-serve's
   presigned-URL target). Both the client and the terraform grants are in
   place for the worker to sign as its own service account.
5. **Retries and the cold start.** The first request after idle waits ~5
   minutes inside the same call; the worker's retry (`MAX_RETRIES`) covers a
   failed one. Whether to keep `min_instance_count` at 0 (free when idle)
   or pay for one warm L4 is a cost choice; parsing is bursty, so zero.
6. **The VM.** Once parsing is remote, the VM has no model to run, and the
   `c4a-standard-2` is sized for Docling. Revisit after the switch.
7. **Quota.** Cloud Run grants 3 L4s per region on first use with zonal
   redundancy off; `max_instances` stays below that.

## Switching

Set `PDF_PARSING_SERVICE_URL` in `infrastructure/ansible/templates/env.j2` to the
terraform output and deploy. `remote.py` reads the identity token from the
GCE metadata server on the VM, as the VM's service account, which the stack
already allows to invoke. To go back, unset it and deploy.
