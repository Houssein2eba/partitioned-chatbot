# Docker-only deployment

This branch is the first stage of the learning path. It runs the complete
application with Docker Compose on one machine. Kubernetes, CI/CD, and
Terraform are introduced in later branches.

## Prerequisites

- Docker Desktop with Compose v2
- A Groq API key

## Configure

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `GROQ_API_KEY`. For local learning, leave `APP_API_KEYS` empty. To enable
API authentication, set both `APP_API_KEYS` and `RAG_API_KEY`.

Add supported documents to `data/`:

- PDF
- DOCX
- TXT
- Markdown

## Start the stack

```powershell
docker compose up -d --build
```

This starts three containers from [`docker-compose.yml`](docker-compose.yml):

| Container | Port | Role |
|---|---:|---|
| `qdrant` | 6333 | Stores document vectors and payloads |
| `api` | 8000 | FastAPI, ingestion, retrieval, and Groq calls |
| `ui` | 8501 | Streamlit web interface |

The API container waits for Qdrant to become healthy. The Docker image installs
the dependencies and downloads the local embedding model during the build.

## Build the knowledge base

```powershell
curl.exe -X POST http://localhost:8000/v1/ingest
```

This reads files from `data/`, extracts text, creates overlapping chunks,
embeds them locally, and stores them in Qdrant.

## Use the application

- UI: <http://localhost:8501>
- API documentation: <http://localhost:8000/docs>
- Health: <http://localhost:8000/v1/health>

Ask through the API:

```powershell
curl.exe -X POST http://localhost:8000/v1/chat `
  -H "Content-Type: application/json" `
  -d '{\"question\":\"What is this document about?\"}'
```

Use the CLI from the host if Python dependencies are installed:

```powershell
python -m scripts.chat "What is this document about?"
```

## Operations

```powershell
docker compose ps
docker compose logs -f
docker compose down
```

`docker compose down` keeps the named Qdrant volume. To remove the stored
vectors as well:

```powershell
docker compose down -v
```

## Learning boundary

Docker Compose provides one-machine container orchestration. This branch does
not create cloud infrastructure, deploy to multiple machines, autoscale, or
run automated deployment pipelines. Those capabilities are added incrementally
in the next branches.
