# Setup

Evidence Aggregator runs at the Linux command line and depends on access to multiple required and optional external resources. The following document walks you through how to configure your local software and external cloud environment to perform a full-featured execution of an EvAgg [pipeline app](README.md#pipeline-apps).

## Install software prerequisites

- **Python** 3.12 or above
- **git**
- **uv**.  Follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/) 
- **make** [optional] only for [development tasks](README.md#pre-pr-checks)

## Clone the repository

Create and enter a local clone of this repository in your runtime environment:

```bash
git clone https://github.com/clingen-data-model/cur-ai-ss
cd cur-ai-ss
```

## Install Dependencies
```bash
uv sync
uv pip install -e .
```

Test installation by running the following. You should see a help message displayed providing usage for the `run_evagg_app` command.

```bash
uv run run_evagg_app -h
```

## Running the linting/tests
```bash
make ci
```

To run a specific test
```bash
uv run pytest test/evagg/test_io.py::test_csv_output_warning
```

## Running with a single PMID
```bash
OPENAI_API_KEY=API_KEY
OPENAI_DEPLOYMENT=gpt-5-mini
uv run run_evagg_app lib/config/caa.yaml  -o pmid:36704923 gene_symbol:FICD
```

