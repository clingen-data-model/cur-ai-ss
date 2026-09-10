# Curation AI Assistant

A web-based tool for extracting and curating genetic evidence from scientific papers. This system uses AI agents to automatically extract patient information, genetic variants, and phenotypes from research PDFs, then links them to standard databases (HPO ontology). Researchers can review, edit, and validate the extracted data through an interactive interface.

## What It Does

**Automated Evidence Extraction**
- Upload a scientific paper (PDF) describing genetic cases
- AI agents extract: patients, their phenotypes, genetic variants, and family relationships
- Variants are harmonized to standard genomic coordinates and enriched with annotations
- Phenotypes are automatically linked to HPO (Human Phenotype Ontology) terms

**Interactive Curation**
- Review extracted data in a clean, organized UI
- Edit and correct patient demographics, variants, and phenotype mappings
- Validate HPO term assignments with confidence scores
- View supporting evidence directly from the paper

**Pipeline Architecture**
- **Backend API**: FastAPI server managing data storage and retrieval
- **Streamlit UI**: The current dashboard for browsing papers and curating data
- **React SPA**: Its replacement, in progress — served alongside it under `/v2`
- **Background Worker**: Runs extraction agents in sequence, updating progress in real-time
- **SQLite Database**: Stores papers, patients, variants, phenotypes, and all extracted data

## Quick Start

### Prerequisites

- **Python** 3.12 or above
- **git**
- **uv** — [installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- **make** (optional, for development tasks)
- **OpenAI API key** with available billing (the free tier doesn't work)
- **Node** 24 (see `.node-version`) and **pnpm** 12 — only needed to work on the React frontend

### Set Up OpenAI API Key

1. Go to [OpenAI API Dashboard](https://platform.openai.com/account/api-keys)
2. Log in or create an account
3. Click “Create new secret key”
4. Copy the key and set environment variables:

```bash
export OPENAI_API_KEY="your_key_here"
# Model names are '<provider>/<model>'; the prefix is required.
export EXTRACTION_MODEL="openai/gpt-5.6-luna"
export VLM_MODEL="openai/gpt-5.6-sol"
```

### Install and Run

```bash
# Clone the repository
git clone https://github.com/clingen-data-model/cur-ai-ss
cd cur-ai-ss

# Install dependencies
uv sync
uv pip install -e .
```

## Development

### Testing & Linting

```bash
make ci                                    # Run all checks (linting, type checking, tests)
make test                                  # Run tests with coverage report
uv run pytest test/models/test_converters.py  # Run a specific test file
```

### Running the Full Application

Start the backend, UI, and worker in separate terminals:

**Terminal 1 — Backend API** (runs on `http://localhost:8000`)
```bash
./bin/api
```

**Terminal 2 — Frontend UI** (runs on `http://localhost:8501`)
```bash
./bin/ui
```

**Terminal 3 — Background Worker** (processes extraction jobs)
```bash
./bin/worker
```

**Terminal 4 — React frontend** (optional, runs on `http://localhost:8501`)
```bash
cd frontend
pnpm install
pnpm dev
```

Note that `./bin/ui` (Streamlit) and `pnpm dev` (Vite) both bind port 8501, so run one or
the other locally. See `frontend/README.md` for the frontend toolchain and its
dependencies.

### Example: Extract Evidence from a Paper with MASP1 Gene

Try extracting genetic evidence from a real paper on MASP1 (Mannan-binding lectin-associated serine protease 1):

**Step 1: Download the paper**
```bash
# PMID: 26419238 — “MASP1 variants and complications of mannose-binding lectin deficiency”
curl -L -o masp1_paper.pdf “https://pmc.ncbi.nlm.nih.gov/articles/PMC4657649/pdf/12882_2015_Article_208.pdf”
```

**Step 2: Upload via the UI**
1. Open the Streamlit dashboard: `http://localhost:8501`
2. Go to the **Dashboard** page
3. Click “Upload Paper” and select `masp1_paper.pdf`
4. Enter a name (e.g., “MASP1 Variants - Kidney Disease”)

**Step 3: Watch extraction progress**
- The background worker automatically starts processing the paper
- Extraction pipeline runs: Paper → Patients → Variants → HPO Phenotypes
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
- Serves the frontend and manages database access
- CORS configured for Streamlit UI

**Streamlit UI** (`lib/ui/streamlit_app.py`)
- Dashboard: Browse papers and view extraction status
- Paper pages: Edit patients, variants, phenotypes, and HPO assignments
- PDF viewer: Highlight and view supporting evidence
- Still the primary UI, served at `/`

**React SPA** (`frontend/`)
- React 19 + TypeScript, built with Vite, styled with Tailwind v4 and shadcn/ui
- TanStack Router for type-safe file-based routing, TanStack Query for server state
- Calls the API through a client generated from the FastAPI OpenAPI schema, so a backend
  schema change becomes a frontend type error rather than a runtime 404
- In-progress replacement for the Streamlit UI; deployed in parallel under `/v2`
- Architecture and a description of every JavaScript dependency: `frontend/README.md`

**Background Worker** (`lib/bin/worker.py`)
- Polls database for papers awaiting extraction
- Runs extraction agents in a task-based pipeline
- Updates paper status as work progresses
- Uses database leases to prevent concurrent processing

### Extraction Pipeline

Each uploaded paper flows through these automated extraction steps:

1. **Paper Extraction** — Parse PDF, extract metadata and tables
2. **Patient Extraction** — Identify patients and their demographics
3. **Variant Extraction** — Extract genetic variant information
4. **Variant Harmonization** — Normalize to standard genomic coordinates
5. **Variant Enrichment** — Add annotations (SpliceAI, SIFT, etc.)
6. **Phenotype Extraction** — Extract phenotypic descriptions
7. **HPO Linking** — Match phenotypes to HPO ontology terms
8. **Patient-Variant Linking** — Associate variants with patients and inheritance info

### Data Models

All entities are defined with **Pydantic** (serialization) and **SQLAlchemy ORM** (database):

- **Paper** — Research paper with extraction status
- **Patient** — Extracted patient demographics and clinical info
- **Phenotype** — Extracted phenotypes with HPO matching candidates
- **Variant** — Extracted, harmonized, and enriched genetic variants
- **PatientVariantLink** — Associations between patients and their variants

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
| `/` | Streamlit UI on `127.0.0.1:8001` | Proxied, with WebSocket upgrade for `/_stcore/stream` |
| `/api/` | FastAPI on `127.0.0.1:8000` | Proxied; the `/api` prefix is stripped before it reaches FastAPI |
| `/v2/` | `frontend/dist/` on disk | Static files. Unknown paths fall back to `/v2/index.html` so the SPA router can resolve deep links |

The API, Streamlit UI, and worker run as systemd **user** services (`api`, `ui`,
`worker`) under the `caa` user. TLS is a Let's Encrypt wildcard managed by certbot on the
VM, renewed twice-daily by cron via a Porkbun DNS-01 challenge.

Deploying pulls `main` from GitHub onto the VM, syncs Python dependencies, writes `.env`
from GCP Secret Manager, builds the React SPA, then restarts the services:

```bash
ansible-playbook -i dev-caa.us-east4-a.clingen-caa, infrastructure/ansible/playbook.yml
```

That direct form only works from inside the VPC. The VPC has **no port-22 ingress
rule** (`infrastructure/terraform/shared/network.tf` opens only 80, 443, and ICMP), so
SSH to the public IP times out from anywhere else. Reach it over an IAP TCP-forwarding
tunnel instead, with an inventory file that sets a `ProxyCommand`:

```ini
# inventory.ini
[all]
dev-caa.us-east4-a.clingen-caa ansible_ssh_common_args='-o ProxyCommand="gcloud compute start-iap-tunnel dev-caa 22 --listen-on-stdin --project=clingen-caa --zone=us-east4-a"'
```

```bash
ansible-playbook -i inventory.ini infrastructure/ansible/playbook.yml
```

Note also that ports 80 and 443 are allowlisted to Broad internal ranges plus two
hardcoded addresses, so **the site is not reachable from an arbitrary network** — being
unable to load it is usually a firewall rule, not an outage. Verify a deploy from the VM
itself (its own IP is allowlisted) or from the Broad network.

The frontend build step runs after `.env` is written, because regenerating the OpenAPI
spec imports the FastAPI app and therefore needs a valid environment. It builds with
`VITE_BASE_PATH=/v2/` and `VITE_API_URL=/api`; see `frontend/README.md` for what those
control and for the build's known caveats.

Deploy a specific ref with `-e git_version=<ref>`, preview with `--check`, or run
`--tags certbot` to touch only TLS and nginx without restarting the app. The playbook
header documents every variable and the one-time Secret Manager setup.

For more details, see `CLAUDE.md` in the repository.
