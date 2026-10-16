# Curation AI Assistant

A web-based tool for extracting and curating genetic evidence from scientific papers. This system uses AI agents to automatically extract patient information, genetic variants, and phenotypes from research PDFs, then links them to standard ontologies (HPO for phenotypes, MONDO for diseases). Researchers can review, edit, and validate the extracted data through an interactive interface.

## What It Does

**Automated Evidence Extraction**
- Upload a scientific paper (PDF) describing genetic cases
- AI agents extract: patients, their phenotypes, genetic variants, and family relationships
- Variants are harmonized to standard genomic coordinates and enriched with annotations
- Phenotypes are automatically linked to HPO (Human Phenotype Ontology) terms, and the paper's disease to MONDO
- Anything an agent could not settle is raised as a flag for the curator, and repeated flags are merged into one

**Interactive Curation**
- Review extracted data in a clean, organized UI
- Edit and correct patient demographics, variants, and phenotype mappings
- Validate HPO term assignments with confidence scores
- View supporting evidence directly from the paper

**Pipeline Architecture**
- **Backend API**: FastAPI server managing data storage and retrieval
- **React SPA**: The UI for browsing papers and curating data, served at the site root
- **Background Worker**: Runs the extraction agents as a task pipeline, updating progress in real-time
- **SQLite Database**: Stores papers, patients, variants, phenotypes, and all extracted data

## Quick Start

### Prerequisites

- **Python** 3.12 or above
- **git**
- **uv** — [installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- **Anthropic API key** with available billing — [console.anthropic.com](https://console.anthropic.com/settings/keys).
  An OpenAI key is only needed if you point a model setting at `openai/…`
- **Node** 24 (see `.node-version`) and **pnpm** 12 — only needed to work on the React frontend

### Configure

Settings are read from a `.env` file (or the environment); `template.env` lists them.

```bash
cp template.env .env
```

Set at least these:

```bash
ANTHROPIC_API_KEY="your_key_here"
JWT_SECRET_KEY="a long random string"   # signs login tokens; use a strong value in production

# Model names are '<provider>/<model>'; the prefix is required.
EXTRACTION_MODEL="anthropic/claude-haiku-5-5"   # text extraction agents
VLM_MODEL="anthropic/claude-fable-5-1"          # reads page and table images
```

`CHAT_MODEL` (the chat agent) defaults to `anthropic/claude-opus-5`, so an Anthropic key
is needed whichever providers the other two settings name. `openai/` models also work
(set `OPENAI_API_KEY`); the three model settings may name different providers. A model
whose provider key is missing fails at startup.

### Install and Run

```bash
# Clone the repository
git clone https://github.com/clingen-data-model/cur-ai-ss
cd cur-ai-ss

# Install dependencies
uv sync
uv pip install -e .
```

The API applies database migrations on startup, so there is no separate schema step.

## Development

### Testing & Linting

These are the checks CI runs:

```bash
uv run ruff check lib                      # Lint
uv run ruff format --check lib test        # Formatting
uv run mypy lib                            # Type checking
uv run pytest test --cov=lib --cov-report=term-missing   # Tests with coverage
uv run pytest test/models/test_converters.py             # A specific test file
```

### Running the Full Application

Start the backend, worker and frontend in separate terminals:

**Terminal 1 — Backend API** (runs on `http://localhost:8000`)
```bash
./bin/api
```

**Terminal 2 — Background Worker** (processes extraction jobs)
```bash
./bin/worker
```

**Terminal 3 — React frontend** (runs on `http://localhost:8501`)
```bash
cd frontend
pnpm install
pnpm dev
```

See `frontend/README.md` for the frontend toolchain and its dependencies.

### Example: Extract Evidence from a Paper with MASP1 Gene

Try extracting genetic evidence from a real paper on MASP1 (Mannan-binding lectin-associated serine protease 1):

**Step 1: Download the paper**
```bash
# PMID: 26419238 — "MASP1 variants and complications of mannose-binding lectin deficiency"
curl -L -o masp1_paper.pdf "https://pmc.ncbi.nlm.nih.gov/articles/PMC4657649/pdf/12882_2015_Article_208.pdf"
```

**Step 2: Upload via the UI**
1. Open the dashboard: `http://localhost:8501`
2. Click "Upload Paper" and select `masp1_paper.pdf`
3. Enter a name (e.g., "MASP1 Variants - Kidney Disease")

**Step 3: Watch extraction progress**
- The background worker automatically starts processing the paper
- The pipeline runs from the PDF through patients, variants and phenotypes to ontology links (see the steps below)
- Monitor progress in the UI dashboard

**Step 4: Review and curate**
1. Click the paper in the dashboard to open it
2. Review extracted patients and their phenotypes
3. Correct HPO term assignments if needed
4. Verify variant information
5. Save your edits

## Project Architecture

### Core Components

**Backend API** (`lib/api/app.py`)
- FastAPI server with PDF upload, data storage, and retrieval endpoints
- Manages database access; nginx serves the built frontend alongside it in production
- CORS configured for the SPA's dev server

**React SPA** (`frontend/`)
- React 19 + TypeScript, built with Vite, styled with Tailwind v4 and shadcn/ui
- TanStack Router for type-safe file-based routing, TanStack Query for server state
- Calls the API through a client generated from the FastAPI OpenAPI schema, so a backend
  schema change becomes a frontend type error rather than a runtime 404
- The only UI (it replaced Streamlit): dashboard, paper pages for editing patients,
  families and segregation, variants and phenotypes, and the PDF evidence viewer; served
  at the site root
- Architecture and a description of every JavaScript dependency: `frontend/README.md`

**Background Worker** (`lib/bin/worker.py`)
- Polls database for papers awaiting extraction
- Runs extraction agents in a task-based pipeline
- Updates paper status as work progresses
- Uses database leases to prevent concurrent processing

### Extraction Pipeline

Each uploaded paper flows through these automated steps, run by the worker as tasks:

1. **Paper Extraction** — Parse the PDF; extract metadata, text and tables (a vision model
   rebuilds tables the parser garbled)
2. **Patient Extraction** — Identify patients, demographics and proband status
3. **Pedigree Description** — Describe family relationships
4. **Variant Extraction** — Extract genetic variant information
5. **Variant Harmonization** — Normalize variants to standard genomic coordinates
6. **Variant Annotation** — Add annotations (SpliceAI, etc.)
7. **Phenotype Extraction and HPO Linking** — Extract phenotypes and match them to HPO terms
8. **Patient-Variant Occurrences** — Link patients to their variants, with inheritance and
   testing info; evaluate compound-heterozygous pairs
9. **Segregation and MONDO Linking** — Extract and compute segregation evidence per family;
   link the paper's disease to MONDO
10. **Extraction Verification** — Runs once everything else has settled, and merges flags
    that raise the same decision more than once

Per-patient, per-family and per-variant steps fan out and run concurrently. Output files are
stored as JSON next to the PDF.

### Data Models

All entities are defined with **Pydantic** (serialization) and **SQLAlchemy ORM** (database):

- **Paper** — Research paper with extraction status
- **Family** and **Pedigree** — Family structure and consanguinity, with the paper's pedigree description
- **Patient** — Extracted patient demographics and clinical info
- **Phenotype** — Extracted phenotypes with HPO matching candidates
- **Variant** — Extracted, harmonized, and annotated genetic variants
- **PatientVariantOccurrence** — Associations between patients and their variants
- **Segregation evidence and analysis** — Per-family evidence from the paper and the computed result
- **Flag** — A decision an agent could not settle, for a curator to resolve
- **Evidence** — Text blocks and citations from the paper supporting each extracted value

See `lib/models/` for full model definitions and `CLAUDE.md` for code patterns.

### Database

- **Engine**: SQLite with foreign key constraints
- **Location**: `{CAA_ROOT}/sqllite/app.db` (default `CAA_ROOT=/var/caa`)
- **Migrations**: Alembic under `migrations/versions/`

## Deployment

Everything runs on a single GCP VM (`dev-caa`, defined in
`infrastructure/terraform/dev`) behind nginx, which terminates TLS and routes by path:

| Path | Served by | Notes |
| --- | --- | --- |
| `/api/` | FastAPI on `127.0.0.1:8000` | Proxied; the `/api` prefix is stripped before it reaches FastAPI |
| `/` | `frontend/dist/` on disk | Static files. Unknown paths fall back to `/index.html` so the SPA router can resolve deep links. |

The API and worker run as systemd **user** services (`api`, `worker`) under the `caa`
user. (A host deployed before Streamlit was retired also had a `ui` service; the playbook
stops, disables and removes it.) TLS is a Let's Encrypt wildcard managed by certbot on the
VM, renewed twice-daily by cron via a Porkbun DNS-01 challenge.

Deploying pulls `main` from GitHub onto the VM, syncs Python dependencies, writes `.env`
from GCP Secret Manager, builds the React SPA, then restarts the services:

```bash
ansible-playbook -i dev-caa.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml
```

That direct form needs SSH to the VM's public IP, which works **from the Broad network
(including VPN)**. Port 22 is not opened by this repo's terraform — it is granted by a
Broad org-level firewall policy allowing tcp:22 from Broad's IP ranges, which is why
`gcloud compute firewall-rules list` shows only 80, 443, and ICMP. Inspect the real
picture with:

```bash
gcloud compute instances network-interfaces get-effective-firewalls dev-caa \
  --zone=us-east4-a --project=clingen-caa
```

From any other network SSH times out. That same org policy also allows tcp:22 from the
IAP range (`35.235.240.0/20`), so an IAP TCP-forwarding tunnel works from anywhere and
is the off-VPN option. Use an inventory file that supplies a `ProxyCommand`:

```ini
# inventory.ini
[all]
dev-caa.us-east4-a.clingen-caa ansible_ssh_common_args='-o ProxyCommand="gcloud compute start-iap-tunnel dev-caa 22 --listen-on-stdin --project=clingen-caa --zone=us-east4-a"'
```

```bash
ansible-playbook -i inventory.ini infrastructure/ansible/playbook.yml
```

Ports 80 and 443 are likewise allowlisted to Broad internal ranges plus two hardcoded
addresses in `network.tf`, so **the site is not reachable from an arbitrary network** —
being unable to load it is usually a firewall rule, not an outage. Verify a deploy from
the Broad network, or from the VM itself (its own IP is allowlisted).

The frontend build step runs after `.env` is written, because regenerating the OpenAPI
spec imports the FastAPI app and therefore needs a valid environment. It builds with
`VITE_BASE_PATH=/` and `VITE_API_URL=/api`; see `frontend/README.md` for what those
control and for the build's known caveats.

Deploy a specific ref with `-e git_version=<ref>`, preview with `--check`, or run
`--tags certbot` to touch only TLS and nginx without restarting the app. The playbook
header documents every variable and the one-time Secret Manager setup.

For more details, see `CLAUDE.md` in the repository.
