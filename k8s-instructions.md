# Kubernetes instructions

These commands deploy the chatbot from the manifests in [`k8s/`](k8s/).
They require a working Kubernetes cluster, `kubectl`, Docker, and a Groq API
key. The manifests use `ClusterIP` services, so the application is accessed
with port-forwarding.

The manifests were written for a local Kubernetes cluster such as Docker
Desktop Kubernetes. They also work with K3s when the cluster has a default
storage class and the application image is available to the K3s nodes.

## 1. Select and verify the cluster

```powershell
kubectl config get-contexts
kubectl config use-context <context-name>
kubectl config current-context
kubectl get nodes
```

For K3s, run these commands against the K3s kubeconfig. If `kubectl config
current-context` reports that no context is set, configure `KUBECONFIG` for the
same user that runs the commands or the GitHub Actions runner.

## 2. Create the namespace and secrets

```powershell
kubectl apply -f k8s/00-namespace.yaml
```

Set the required values in the current PowerShell session:

```powershell
$env:GROQ_API_KEY = "<your-groq-api-key>"
$env:APP_API_KEYS = ""
$env:RAG_API_KEY = ""
```

Create or update the Kubernetes Secret without committing it:

```powershell
kubectl -n rag-chatbot create secret generic rag-secrets `
  --from-literal=GROQ_API_KEY="$env:GROQ_API_KEY" `
  --from-literal=APP_API_KEYS="$env:APP_API_KEYS" `
  --from-literal=RAG_API_KEY="$env:RAG_API_KEY" `
  --dry-run=client -o yaml | kubectl apply -f -
```

Set `APP_API_KEYS` and `RAG_API_KEY` when API authentication is enabled.
Never commit a generated Secret manifest or a real API key.

## 4. Deploy the application

Apply the resources in dependency order:

```powershell
kubectl apply -f k8s/10-configmap.yaml
kubectl apply -f k8s/20-qdrant.yaml
kubectl apply -f k8s/25-data-pvc.yaml
kubectl apply -f k8s/30-api.yaml
kubectl apply -f k8s/40-ui.yaml
```

Check rollout and storage status:

```powershell
kubectl -n rag-chatbot get pvc
kubectl -n rag-chatbot get pods -w
kubectl -n rag-chatbot rollout status statefulset/qdrant
kubectl -n rag-chatbot rollout status deployment/rag-api
kubectl -n rag-chatbot rollout status deployment/rag-ui
```

Press `Ctrl+C` to stop watching pods after the workloads are ready.

## 5. Access the API and UI

Open separate terminals and keep these port-forwards running:

```powershell
kubectl -n rag-chatbot port-forward svc/rag-api 8000:8000
kubectl -n rag-chatbot port-forward svc/rag-ui 8501:80
```

Use the application at:

- UI: <http://localhost:8501>
- API documentation: <http://localhost:8000/docs>
- Health: <http://localhost:8000/v1/health>

Verify the API and ingest documents:

```powershell
curl.exe http://localhost:8000/v1/health
curl.exe -X POST http://localhost:8000/v1/ingest
```

If `APP_API_KEYS` is configured, include the API key:

```powershell
curl.exe -H "X-API-Key: <your-api-key>" http://localhost:8000/v1/health
```

## 6. Inspect logs and troubleshoot

```powershell
kubectl -n rag-chatbot get all
kubectl -n rag-chatbot logs statefulset/qdrant
kubectl -n rag-chatbot logs deployment/rag-api
kubectl -n rag-chatbot logs deployment/rag-ui
kubectl -n rag-chatbot describe pod <pod-name>
kubectl -n rag-chatbot get events --sort-by=.lastTimestamp
```

If an API or UI pod is stuck in `ImagePullBackOff`, verify that the image
`houssein2eba/rag-chatbot:local` exists on the node. If a PVC remains
`Pending`, inspect the available storage classes:

```powershell
kubectl get storageclass
kubectl -n rag-chatbot describe pvc rag-data
```

## 7. Stop or remove the deployment

Stop the port-forwards with `Ctrl+C`. To remove the workloads while keeping
the namespace:

```powershell
kubectl delete -f k8s/40-ui.yaml
kubectl delete -f k8s/30-api.yaml
kubectl delete -f k8s/25-data-pvc.yaml
kubectl delete -f k8s/20-qdrant.yaml
kubectl delete -f k8s/10-configmap.yaml
```

To remove the namespace and its remaining resources:

```powershell
kubectl delete namespace rag-chatbot
```

Deleting the namespace also deletes its Secret and persistent data according
to the storage provisioner's reclaim policy.
