## Install software prerequisites

- **Python** 3.12 or above
- **git**
- **uv**.  Follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/) 
- **make** [optional] only for [development tasks](README.md#pre-pr-checks)

## Generate an OpenAI api key
- Go to the OpenAI Dashboard:
https://platform.openai.com/account/api-keys
- Log in to your OpenAI account (or create one if needed).
- Click “Create new secret key”.
- Give it a name (optional, but helpful if you use multiple keys).
- Copy the generated key and store it somewhere secure. You will not be able to view it again after closing the dialog. If you lose it, you must generate a new one.
- We recommend setting environment variables:

```bash
export OPENAI_API_KEY="your_key_here"
export OPENAI_API_DEPLOYMENT="gpt-5-mini"
```

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

Test installation by running the following. You should see a help message displayed providing usage for the command.

```bash
./bin/extract_single_pdf
```

## Running the linting/tests
```bash
make ci
```

To run a specific test
```bash
uv run pytest test/evagg/test_llm.py
```

## Running the extraction with a PDF

To test the extraction pipeline, download a paper PDF from PubMed. For example,

```bash
curl -L -o pmid_36704923.pdf "https://pmc.ncbi.nlm.nih.gov/articles/PMC9994480/pdf/EMMM-15-e16491.pdf"
```

Then run the extraction (put the path to the file if it is not in the root directory of this project):

```bash
./bin/extract_single_pdf --pdf pmid_36704923.pdf
```

## Running the full application for developments

In three terminals, run the following to start up each service:
```bash
./bin/api
```

```bash
./bin/ui
```

```bash
./bin/worker
```

NOTE: you will need to make sure you OpenAI account has available billing available since the API tokens are not available on the Free tier.