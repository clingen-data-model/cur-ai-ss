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
- **Frontend UI**: Streamlit dashboard for browsing papers and curating data
- **Background Worker**: Runs extraction agents in sequence, updating progress in real-time
- **SQLite Database**: Stores papers, patients, variants, phenotypes, and all extracted data

## Quick Start

### Prerequisites

- **Python** 3.12 or above
- **git**
- **uv** — [installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- **make** (optional, for development tasks)
- **OpenAI API key** with available billing (the free tier doesn't work)

### Set Up OpenAI API Key

1. Go to [OpenAI API Dashboard](https://platform.openai.com/account/api-keys)
2. Log in or create an account
3. Click “Create new secret key”
4. Copy the key and set environment variables:

```bash
export OPENAI_API_KEY=”your_key_here”
export OPENAI_API_DEPLOYMENT=”gpt-5-mini”
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

Start the backend, frontend, and worker in three separate terminals:

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

**Frontend UI** (`lib/ui/streamlit_app.py`)
- Dashboard: Browse papers and view extraction status
- Paper pages: Edit patients, variants, phenotypes, and HPO assignments
- PDF viewer: Highlight and view supporting evidence

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

For more details, see `CLAUDE.md` in the repository.
