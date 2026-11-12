# Local Kubernetes deployment

These manifests target the Docker Desktop Kubernetes context. They intentionally
do not include public ingress, DNS, cert-manager, or cloud-provider resources.

## Build the local image

```powershell
docker build -t rag-chatbot:local .
```

The API and UI deployments use `imagePullPolicy: Never`, so Kubernetes uses
this local image and does not contact a registry.

## Create the namespace and secret

```powershell
kubectl apply -f k8s/00-namespace.yaml

kubectl -n rag-chatbot create secret generic rag-secrets `
  --from-literal=GROQ_API_KEY="$env:GROQ_API_KEY" `
  --from-literal=APP_API_KEYS="$env:APP_API_KEYS" `
  --from-literal=RAG_API_KEY="$env:RAG_API_KEY" `
  --dry-run=client -o yaml | kubectl apply -f -
```

Load the three values from your local `.env` without printing them:

```powershell
$env:GROQ_API_KEY = (Select-String -Path .env -Pattern '^GROQ_API_KEY=').Line.Substring(13)
$env:APP_API_KEYS = (Select-String -Path .env -Pattern '^APP_API_KEYS=').Line.Substring(14)
$env:RAG_API_KEY = (Select-String -Path .env -Pattern '^RAG_API_KEY=').Line.Substring(12)
```

Do not commit the generated Secret YAML or real credentials.

## Deploy

```powershell
kubectl apply -f k8s/10-configmap.yaml
kubectl apply -f k8s/20-qdrant.yaml
kubectl apply -f k8s/25-data-pvc.yaml
kubectl apply -f k8s/30-api.yaml
kubectl apply -f k8s/40-ui.yaml
kubectl -n rag-chatbot get pods
```

## Access locally

```powershell
kubectl -n rag-chatbot port-forward svc/rag-api 8000:8000
kubectl -n rag-chatbot port-forward svc/rag-ui 8501:80
```

Use the API at `http://localhost:8000` and the UI at
`http://localhost:8501`. Ingest documents with `/v1/upload` or the UI.
