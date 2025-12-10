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
- We recommend setting an environment variable:
```bash
export OPENAI_API_KEY="your_key_here"
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
OPENAI_DEPLOYMENT=gpt-5-nano
uv run run_evagg_app  --pmid 36704923 --gene-symbol FICD
```

