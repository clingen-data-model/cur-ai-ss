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
| Image | `pdf-parsing/server:<base>-<commit>`: docling-serve's CUDA image (base tag in `infrastructure/pdf-parsing/base-tag`, pulled from ghcr.io through the `ghcr` remote repository, since Cloud Run pulls only from Artifact Registry or Docker Hub) plus the layout override, see below. Built and rolled by `.github/workflows/pdf-parsing-image.yml` on a push to `main` touching its inputs; the stack creates the service on the stock base image and ignores the image after |
| Exchange bucket | `clingen-caa-pdf-parsing-exchange`: private, objects deleted after a day. The PDF and the converted document pass through it (below). The VM's service account reads, writes and signs URLs for it (it holds `serviceAccountTokenCreator` on itself for V4 signing); the operators in `var.invokers` hold the same role on that account, so a laptop can sign as it through an impersonating application-default login |
| Client | `lib/misc/pdf/remote.py`: per PDF, upload to the bucket, two signed URLs, one small `POST /v1/convert/source` with a Google identity token, the bundle pulled from the bucket, both objects deleted |
| Switch | `PDF_PARSING_SERVICE_URL` and `PDF_PARSING_EXCHANGE_BUCKET` (`lib/core/environment.py`): set, `parse_content` converts PDFs remotely; unset, locally. DOCX supplements stay local either way. `env.j2` sets both since 2026-11-02 |
| Rehearsal | `uv run python -m lib.bin.parse_remote_test paper.pdf --url ... --bucket ...` parses into a temporary `CAA_ROOT` and deletes it; `--compare-local` runs the in-process converter beside it, `--keep` leaves the files |

The service URL is a terraform output (`terraform output service_url`).
Callers need `roles/run.invoker`: the stack grants it to the VM's service
account and to the operators in `var.invokers`; from a laptop the client
falls back to `gcloud auth print-identity-token`. Signing the bucket URLs
from a laptop needs application-default credentials that impersonate the
VM's account:

    gcloud auth application-default login \
        --impersonate-service-account=dev-caa@clingen-caa.iam.gserviceaccount.com

### The bucket as the medium

Neither the PDF nor the document travels in an HTTP body. Cloud Run caps
both request and response at 32 MiB for HTTP/1, and the document with its
figure crops embedded at scale 4 was 22 MiB for the largest local paper
(paper 2, a 5.9 MiB PDF) -- the response, not the request, was the limit
that mattered. So the worker uploads the PDF to the exchange bucket, signs
a read URL for it and a write URL for the result, and posts only those two
and the options to `/v1/convert/source` (an `http` source and a `put`
target). The service fetches the PDF, converts, and uploads the bundle --
a zip holding `content.json` -- to the write URL; the response is a
117-byte summary. The worker pulls the bundle and deletes both objects;
the bucket's one-day lifecycle rule sweeps anything a crash leaves.

One quirk, handled in `unwrap_multipart`: docling-jobkit's put target
uploads as a multipart form (`files={"file": ...}`), and a signed PUT
stores the body verbatim, so the object is the zip inside a form envelope,
with the boundary in the object's content type. docling-serve also has a
native Google Cloud Storage target that would remove the envelope, at the
price of giving the service its own bucket credentials instead of a signed
URL.

Verified from dev-caa against the live service on 2026-11-02: paper 109
in 16 s end to end (14 s on the server), a 3.2 MB bundle, the same
document as the in-body call returned; through the full client, papers
109 and 126 in 17 and 22 s with identical tables, figures and words.

### Versions

docling-serve v1.38.2 locks docling 2.142.1 (as `docling-slim`, the same
code without the CPU-only extras), the version `pyproject.toml` pins, so the
service runs the same layout and table models the worker would. Keep the two
together: the first service release, v1.23.0, was taken for a docling 2.82.0
build and actually locked 2.102.1, and the day's comparison of its output
against the VM's showed paragraph splits, caption links and a merged table
header that were all the newer docling, not the GPU. The document schema is
the same (`1.10.0`) in every docling-core up to the newest, so a newer
docling-serve's JSON also loads in an older docling-core; the pin is about
model parity, not about reading the response. To bump: read the release's
`uv.lock` on GitHub for its `docling-slim` version, pin docling to that,
check the `cu128` image exists for the tag (some releases have none), set
`infrastructure/pdf-parsing/base-tag`, and run the test suite -- docling's
geometry conventions move between versions (2.142 put rotated-page text
boxes in the displayed frame, where 2.82 had them in user space). The push
builds and rolls the new image; deploy the VM after it so the worker's
docling-core matches.

The backend is docling-parse (docling's default) on both sides since the
2.142 bump. The pypdfium2 backend the pipeline had used reports whole
lines as text cells, so TableFormer put every row of a table in its first
column and the vision judge was rebuilding nearly every table from its
image (30 of 31 across the local test papers); with word cells the grids
parse right and the judge rebuilds fewer (3 of the 8 tables of papers
105, 109 and 113 on 2026-11-02, for split superscripts and a doubled
header, against 8 of 8 before).

### Building the image

Nothing is built anywhere but in Cloud Build. The workflow stages the
Dockerfile, `layout.py` and `sitecustomize.py`, submits them to Cloud Build
as the `pdf-parsing-builder` account, and updates the service's image. It
runs on a push to `main`, or by hand from the Actions tab (workflow
dispatch), authenticated through workload identity federation: the run's
GitHub OIDC token is exchanged for the builder account, with terraform
limiting that to this repository's `main` branch. No key or secret exists
anywhere, and no operator holds build rights.

### What the worker keeps doing

Only the conversion moves. The worker still crops tables and figures
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
same). The service takes two conversions at once on its one instance, and
the worker's PDF Parsing cap (`TASK_CONCURRENCY` in `lib/bin/worker.py`)
is 2 while the service is configured, 1 otherwise, so two papers parse
together. A third would queue at Cloud Run with the lease running.

## Open before switching the worker

1. **The layout override must be on the server.** `lib/misc/pdf/layout.py`
   patches Docling's post-processor so a multi-panel figure survives as one
   picture instead of its best-scoring panel (paper 116, 2026-10-22).
   Stock docling-serve lacks it, and it matters: run with and without the
   override on the 13 local papers (2026-11-01), three differ, each by one
   figure that stock Docling cuts down to a panel (paper 105 page 8, 135k
   to 65k points of area; 109 page 11, 236k to 79k; 113 page 2, 131k to
   20k). Hence the derived image, `infrastructure/pdf-parsing/`: docling-
   serve's image plus a `sitecustomize.py` that installs the override at
   interpreter start, built by Cloud Build into the stack's own repository
   (above). **Confirmed 2026-11-02** once the stack was applied and the
   workflow built `server:v1.23.0-c4b4043` (revision `pdf-parsing-00002`):
   papers 105, 109 and 113 through the service give the figures on pages
   8, 11 and 2 whole (135k, 236k and 131k points), every other picture
   within a few points of the local override run, in 14 to 21 s each. The
   first build attempt failed at `gcloud builds submit`: it reads the
   staging bucket's metadata before uploading, which the builder's
   objectAdmin grant does not cover, hence its Bucket Viewer grant.
2. **OCR parity with the VM**, above.
3. **Sync or async.** The client holds one request open for the whole
   conversion, up to the server's `DOCLING_SERVE_MAX_SYNC_WAIT` of five
   minutes, ten times the longest conversion seen so far. docling-serve
   also has `/v1/convert/source/async` with polling; it would survive a
   dropped connection, at the cost of a poll loop and task bookkeeping on
   the worker, and the bundle already lands in the bucket either way. The
   30-minute PDF Parsing lease (`lease_timeout_s`) covers the sync wait
   with room for the cold start. Not needed to switch.
4. **Request and response size.** Settled by the bucket, above.
5. **Retries and the cold start.** The first request after idle waits ~5
   minutes inside the same call; the worker's retry (`MAX_RETRIES`) covers a
   failed one. Whether to keep `min_instance_count` at 0 (free when idle)
   or pay for one warm L4 is a cost choice; parsing is bursty, so zero.
6. **The VM.** Once parsing is remote, the VM has no model to run, and the
   `c4a-standard-2` is sized for Docling. Revisit after the switch.
7. **Quota.** Cloud Run grants 3 L4s per region on first use with zonal
   redundancy off; `max_instances` stays below that.

## Switching

`infrastructure/ansible/templates/env.j2` sets `PDF_PARSING_SERVICE_URL` and
`PDF_PARSING_EXCHANGE_BUCKET` to the terraform outputs; deploying switches
the worker over. `remote.py` reads the identity token from the GCE metadata
server on the VM and signs URLs as the VM's service account, which the
stack allows to invoke and to sign. To go back, unset both and deploy.
