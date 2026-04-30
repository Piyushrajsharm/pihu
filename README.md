# Pihu — Modular AI Assistant Platform

Pihu is a modular, production-oriented prototype for a multi-modal AI assistant platform. It combines a Python backend, a React + Vite frontend, support for local and cloud LLM providers, RAG (retrieval-augmented generation), TTS/STT pipelines, telemetry and observability, and deployment tooling (Docker, Terraform).

This repository intentionally excludes large model binaries and node artifacts; see **Models & Data** below for how to obtain them.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture & Code Layout](#architecture--code-layout)
- [Quickstart (Dev)](#quickstart-dev)
- [Running Tests](#running-tests)
- [Models & Data](#models--data)
- [Deployment](#deployment)
- [Recommended Workflow](#recommended-workflow)
- [Security & Secrets](#security--secrets)
- [Contributing](#contributing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

Pihu is built to be a flexible research and engineering workspace for building agent-style assistants. The codebase is structured so teams can iterate on models, connectors, safety policies, and UIs independently.

Use-cases include:
- Local or private-hosted LLM research and experimentation.
- Conversational assistants with speech (TTS/STT) and multi-turn context.
- Embedded systems with on-device inference (where models can be mounted externally).


## Key Features

- Backend services and REST API (see `api/` and `main.py`).
- Frontend UI (Vite + React) in `frontend/`.
- LLM abstraction providers under `llm/` for local and cloud backends.
- RAG support and context retrieval (`context_rag_engine.py`).
- Telemetry and observability helpers (`telemetry_logger.py`, `infra/`).
- Security and policy modules in `security/`.
- CI workflow and tests (GitHub Actions config under `.github/workflows/`).
- Docker + docker-compose and Terraform scaffolding in `Dockerfile.backend`, `docker-compose.yml`, and `terraform/`.


## Architecture & Code Layout

- `main.py` — project entrypoint / orchestrator (backend launch in development).
- `api/` — REST endpoints and API wiring (`api/app.py`).
- `frontend/` — client application (Vite + React).
- `llm/` — LLM provider interfaces and implementations.
- `scripts/` — helper scripts (model download, setup, etc.).
- `security/` — policy, secret redaction, sandboxing helpers.
- `tests/` — pytest-based test suite.

Refer to those folders for implementation details and to extend with new connectors.


## Quickstart (Dev)

Prerequisites:
- Python 3.10+ (3.11 recommended)
- Node.js 18+ (for frontend)
- Git
- Docker (optional, for containerized local dev)

Windows (PowerShell) quickstart:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# Edit .env to provide secrets and configuration
pytest -q
```

Frontend (in separate terminal):

```powershell
cd frontend
npm install
npm run dev
```

Run backend (simple dev run):

```powershell
# from repo root
python main.py
```

Or use Docker Compose for a more production-like environment:

```powershell
docker compose up --build
```


## Running Tests

Run the full pytest suite locally:

```bash
pytest -q
```

CI will run the test matrix via `.github/workflows/ci.yml`.


## Models & Data

Large model weights, TTS models and node artifacts are intentionally excluded from this repository to keep the git history small.

- To download recommended model weights and artifacts, use `download_model.py` or the helper scripts in `scripts/`.
- Store big binaries outside git (S3, artifact storage, or use Git LFS). See `scripts/setup_e2b.py` and `download_model.py` for automation hooks.


## Deployment

- Docker: `Dockerfile.backend` and `docker-compose.yml` provide local containerization.
- Cloud: `terraform/` contains Terraform samples (e.g., ECS). Review and adapt the Terraform files before applying to your environment.
- CI/CD: use GitHub Actions and configure repository secrets (AWS keys, model storage URLs, etc.).


## Recommended Workflow

- Work on feature branches: `feature/<short-desc>`.
- Follow conventional commit messages: `feat:`, `fix:`, `docs:`, `chore:`.
- Run tests locally before pushing.
- Open pull requests against `main` and request at least one review.


## Security & Secrets

- Never commit secrets. Use `.env` (see `.env.example`) and GitHub Secrets for CI.
- The repo includes a policy engine under `security/` — review it before enabling any plugins or execution of third-party code.


## Contributing

- Read the developer guide in `CONTRIBUTING.md` (create one if it doesn't exist).
- Add unit tests for new functionality and run `pytest`.
- Use small, focused PRs and describe the rationale in the PR body.


## Troubleshooting

- If you see missing model errors, verify model artifacts were downloaded and paths in `config.py` are correct.
- If Docker builds fail, check that Docker Desktop is running and that required local files are present.


## License

This repository does not include a License file by default. Add a `LICENSE` (e.g., MIT or Apache-2.0) to make usage terms explicit.


## Where to get help

- Open an issue in this repository.
- For urgent infra questions, check the `infra/` and `terraform/` folders and the `README` sections within.


---

_This README was added by a project maintainer to document repository structure, dev and deployment workflows, and best practices._
