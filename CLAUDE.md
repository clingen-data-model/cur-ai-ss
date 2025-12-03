# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for package management and `make` for common development tasks:

- **Run all CI checks**: `make ci` or `make` (default target) - runs linting, tests, and security checks
- **Run tests**: `make test` - runs pytest with coverage report
- **Run linting**: `make lint` - runs flake8 and mypy
- **Run type checking**: `make type` - runs mypy only
- **Run security checks**: `make sec` - runs bandit security linter
- **Run single test file**: `uv run pytest test/path/to/test_file.py`
- **Install dependencies**: `uv sync` (after making changes to pyproject.toml)

## Architecture Overview

Evidence Aggregator is a modular pipeline system for querying, filtering, and aggregating genetic variant publication evidence using AI. The architecture follows a dependency injection pattern with YAML-based configuration.

### Core Architecture

**Pipeline Apps**: The main entry point is `run_evagg_app <config.yaml>` which instantiates and runs pipeline applications. Apps implement the `IEvAggApp` protocol with an `execute()` method.

**Dependency Injection System**: The `lib.di` module provides a container that instantiates objects from YAML specifications. YAML configs use the `di_factory` key to specify the class/module to instantiate, with parameters passed as keyword arguments.

**Component Protocols**: The system is built around four main interfaces:
- `IGetPapers`: Search and retrieve papers (e.g., from PubMed)
- `IExtractFields`: Extract structured data from papers using AI
- `IWriteOutput`: Output results in various formats (JSON, tables)
- `IEvAggApp`: Top-level application orchestrator

### Key Modules

- `lib/evagg/`: Core library with main components and interfaces
- `lib/evagg/app.py`: Main pipeline applications (`PaperQueryApp`, `SinglePMIDApp`)
- `lib/evagg/library/`: Paper retrieval implementations (rare disease databases, single papers)
- `lib/evagg/content/`: Content extraction using AI (prompt-based, cached variants)
- `lib/evagg/ref/`: Reference data providers (NCBI, HPO, Mutalyzer)
- `lib/evagg/llm/`: AI model interfaces (Azure OpenAI)
- `lib/di.py`: Dependency injection container
- `lib/config/`: YAML pipeline configurations

### Configuration Pattern

YAML specs follow this structure:
```yaml
# Resources (singletons, reusable objects)
resource_name:
  di_factory: module.ClassName
  param: value

# App definition
di_factory: lib.evagg.AppClass
app_param: "{{resource_name}}"  # Reference to resource
other_param: value
```

The DI system resolves `{{resource_name}}` references and handles nested object instantiation recursively.

### Testing

Tests are organized under `test/` mirroring the `lib/` structure. The project uses pytest with coverage reporting and includes unit tests for core functionality.