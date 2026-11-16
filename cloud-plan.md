# Free CI/CD and Terraform plan

This plan adds continuous delivery and Terraform to the current project without
requiring AKS or another paid cloud service.

The target lab environment is:

```text
GitHub repository
       |
       +--> GitHub-hosted runner: CI
       |       - install dependencies
       |       - run tests
       |       - validate Terraform
       |
       +--> self-hosted Windows runner: CD
               - Docker Desktop Kubernetes
               - Docker
               - kubectl
               - Terraform
```

The self-hosted runner must be installed on the same Windows machine as Docker
Desktop Kubernetes. A GitHub-hosted runner cannot reach a Kubernetes cluster
running on your local computer.

## 1. Decide what each file owns

Use one tool as the owner of each environment:

| File or directory | Keep? | Responsibility |
|---|---|---|
| `docker-compose.yml` | Keep | Local development with a locally built image |
| `docker-compose.deploy.yml` | Optional | Single-machine Docker deployment from Docker Hub |
| `k8s/` | Temporary during migration | Existing manual Kubernetes deployment |
| `terraform/` | Add | Kubernetes resources used by CD |
| `.github/workflows/` | Replace/update | CI and CD automation |

Do not manage the same Kubernetes Deployment, Service, PVC, ConfigMap, or
Namespace with both Terraform and `kubectl apply`. Terraform must become the
single owner of those resources.

Keep `docker-compose.yml` because it is useful for development. Keep
`docker-compose.deploy.yml` only if a Docker Compose server is still needed.
It is not used by the Kubernetes CD pipeline.

Keep the files in `k8s/` until Terraform has been tested successfully. After
the migration, stop applying them. They can then be removed or moved to a
reference directory, but they must not be used by the CD pipeline.

## 2. Prepare the self-hosted CD runner

Install the GitHub Actions self-hosted runner on the Windows machine that runs
Docker Desktop.

Install and verify:

```powershell
docker --version
kubectl version --client
terraform version
python --version
```

Enable Kubernetes in Docker Desktop and verify the runner's Windows account can
use the correct context:

```powershell
kubectl config use-context docker-desktop
kubectl get nodes
```

The node must be `Ready`.

The runner must be online whenever a deployment is expected. Do not run
untrusted pull requests on this runner. A self-hosted runner has access to the
local Docker daemon, Kubernetes cluster, and any configured secrets.

## 3. Add Terraform files

Create these files:

```text
terraform/
  versions.tf
  provider.tf
  variables.tf
  main.tf
  outputs.tf
```

Terraform should manage the following resources:

- Namespace `rag-chatbot`
- ConfigMap `rag-config`
- PersistentVolumeClaim `rag-data`
- Qdrant Service and StatefulSet
- API Deployment and Service
- UI Deployment and Service

Do not initially manage `rag-secrets` with Terraform. Kubernetes Secret values
would be stored in Terraform state. Instead, create or update that Secret in
the CD job from the repository's encrypted GitHub secrets.

### `terraform/versions.tf`

Declare the Kubernetes provider:

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
    }
  }
}
```

### `terraform/provider.tf`

Configure Terraform for the local Docker Desktop cluster:

```hcl
provider "kubernetes" {
  config_path    = pathexpand("~/.kube/config")
  config_context = "docker-desktop"
}
```

This provider configuration is for the free local lab. A future cloud
environment should use its provider and authentication method instead of
committing credentials.

### `terraform/variables.tf`

Define the image as a deployment input:

```hcl
variable "image" {
  description = "Application image used by the API and UI deployments"
  type        = string
}
```

Use a commit-specific tag such as `rag-chatbot:<github-sha>`, not `latest`.

### `terraform/main.tf`

Move the resource definitions from the current Kubernetes files into Terraform:

| Existing file | Terraform resources |
|---|---|
| `k8s/00-namespace.yaml` | `kubernetes_namespace` |
| `k8s/10-configmap.yaml` | `kubernetes_config_map` |
| `k8s/20-qdrant.yaml` | `kubernetes_service` and `kubernetes_stateful_set` |
| `k8s/25-data-pvc.yaml` | `kubernetes_persistent_volume_claim` |
| `k8s/30-api.yaml` | API `kubernetes_deployment` and `kubernetes_service` |
| `k8s/40-ui.yaml` | UI `kubernetes_deployment` and `kubernetes_service` |

Preserve the current settings when moving them:

- Namespace: `rag-chatbot`
- API port: `8000`
- UI port: `8501`
- Qdrant URL: `http://qdrant:6333`
- API readiness and liveness path: `/v1/health`
- UI readiness path: `/_stcore/health`
- API data mount: `/app/data`
- Qdrant storage mount: `/qdrant/storage`
- Existing CPU and memory requests/limits

Both application Deployments must use the Terraform variable:

```hcl
image             = var.image
image_pull_policy = "IfNotPresent"
```

`IfNotPresent` is correct for this lab because the image is built locally on
the same Docker daemon used by Docker Desktop Kubernetes.

Every resource must declare its namespace explicitly or reference the
Terraform namespace resource so Terraform creates resources in the correct
namespace.

### `terraform/outputs.tf`

Expose useful local verification values:

```hcl
output "namespace" {
  value = kubernetes_namespace.rag.metadata[0].name
}

output "api_service" {
  value = "rag-api"
}

output "ui_service" {
  value = "rag-ui"
}
```

Use the actual Terraform resource names chosen in `main.tf`.

## 4. Protect Terraform state

Add these entries to `.gitignore`:

```gitignore
.terraform/
*.tfstate
*.tfstate.*
.terraform.tfstate.lock.info
```

Commit `.terraform.lock.hcl` after `terraform init`; it records provider
checksums and should not be ignored.

For this single-machine lab, the default local Terraform state is sufficient.
Do not run two CD jobs concurrently against the same local state. A real team
environment should use a remote backend with locking.

## 5. Bootstrap, initialize, and test Terraform manually

Run these commands from the repository root on the self-hosted runner:

```powershell
terraform -chdir=terraform init
terraform -chdir=terraform fmt -recursive
terraform -chdir=terraform validate
```

For the first migration, import the existing namespace into Terraform so the
same resource is not created by both `kubectl` and Terraform:

```powershell
terraform -chdir=terraform import kubernetes_namespace.rag rag-chatbot
```

Use the actual Terraform resource address if a different name is chosen in
`main.tf`. If starting with a completely empty cluster instead, bootstrap the
namespace once with:

```powershell
terraform -chdir=terraform apply -target=kubernetes_namespace.rag
```

The `-target` command is only for this one-time bootstrap. Normal deployments
must use a full `terraform apply`.

Create or update `rag-secrets` after the namespace exists and before checking
the application rollout:

```powershell
$env:GROQ_API_KEY = "your-real-groq-key"
$env:APP_API_KEYS = "your-app-api-key"
$env:RAG_API_KEY = "your-rag-api-key"

kubectl -n rag-chatbot create secret generic rag-secrets `
  --from-literal=GROQ_API_KEY="$env:GROQ_API_KEY" `
  --from-literal=APP_API_KEYS="$env:APP_API_KEYS" `
  --from-literal=RAG_API_KEY="$env:RAG_API_KEY" `
  --dry-run=client -o yaml | kubectl apply -f -
```

Build the image before applying:

```powershell
docker build -t rag-chatbot:manual .
terraform -chdir=terraform plan -var 'image=rag-chatbot:manual'
terraform -chdir=terraform apply -var 'image=rag-chatbot:manual'
```

Verify the result:

```powershell
kubectl -n rag-chatbot get pods
kubectl -n rag-chatbot get services
kubectl -n rag-chatbot rollout status deployment/rag-api
kubectl -n rag-chatbot rollout status deployment/rag-ui
```

The Terraform-managed Deployments should reference `rag-config` and
`rag-secrets`, just as the current Kubernetes manifests do. The Secret is
created outside Terraform so its values are not written to Terraform state.

## 6. Change the current GitHub Actions workflow

The current
`.github/workflows/runner-test.yaml` is not a complete CI/CD pipeline. It:

- Runs only on pushes to `with-k8s`
- Requires the self-hosted runner even for tests
- Checks the local Kubernetes context
- Installs dependencies and runs tests
- Builds an image but does not deploy it

Replace it with two jobs in one workflow, or create:

```text
.github/workflows/ci-cd.yaml
```

### CI job

The CI job should run on a GitHub-hosted Ubuntu runner for pull requests and
pushes. It should:

1. Check out the repository.
2. Set up Python 3.11.
3. Install `requirements.txt`.
4. Run `pytest -q`.
5. Run `terraform fmt -check -recursive`.
6. Run `terraform init`.
7. Run `terraform validate`.
8. Run `terraform plan`.
9. Build the Docker image as a build validation.

CI must not use production secrets and must not deploy.

### CD job

The CD job should:

1. Run only after CI succeeds.
2. Run only for a push to `main`.
3. Use the self-hosted Windows runner.
4. Check Docker, `kubectl`, and Terraform.
5. Confirm the `docker-desktop` context and a `Ready` node.
6. Build `rag-chatbot:<github-sha>`.
7. Create or update `rag-secrets` from encrypted GitHub secrets.
8. Run `terraform apply -auto-approve` with the commit image tag.
9. Wait for API and UI rollouts.
10. Run a health check.

Use `shell: cmd` for Windows `run` steps because the runner's PowerShell
execution policy previously blocked generated `.ps1` files.

The CD job should use commands equivalent to:

```yaml
- name: Build image
  shell: cmd
  run: docker build -t rag-chatbot:${{ github.sha }} .

- name: Apply secret
  shell: cmd
  env:
    GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
    APP_API_KEYS: ${{ secrets.APP_API_KEYS }}
    RAG_API_KEY: ${{ secrets.RAG_API_KEY }}
  run: >
    kubectl -n rag-chatbot create secret generic rag-secrets
    --from-literal=GROQ_API_KEY=%GROQ_API_KEY%
    --from-literal=APP_API_KEYS=%APP_API_KEYS%
    --from-literal=RAG_API_KEY=%RAG_API_KEY%
    --dry-run=client -o yaml | kubectl apply -f -

- name: Apply Terraform
  shell: cmd
  run: >
    terraform -chdir=terraform apply -auto-approve
    -var image=rag-chatbot:${{ github.sha }}

- name: Wait for rollout
  shell: cmd
  run: |
    kubectl -n rag-chatbot rollout status deployment/rag-api --timeout=180s
    kubectl -n rag-chatbot rollout status deployment/rag-ui --timeout=180s
```

Store `GROQ_API_KEY`, `APP_API_KEYS`, and `RAG_API_KEY` as GitHub Actions
secrets. Do not use `echo` to display them. Configure the CD job to run only
on the trusted `main` branch.

## 7. Decide what to do with the Kubernetes YAML

Do not delete the YAML before Terraform works.

After a successful Terraform deployment:

1. Stop applying `k8s/10-configmap.yaml`, `20-qdrant.yaml`,
   `25-data-pvc.yaml`, `30-api.yaml`, and `40-ui.yaml`.
2. Compare `terraform plan` with the existing cluster.
3. Remove the YAML files or move them to `k8s/reference/` if they are useful
   for learning.
4. Update `k8s/README.md` to say that Terraform is now the deployment path.

Keep `k8s/00-namespace.yaml` only as reference if desired; Terraform should
own the namespace after migration as well.

Never run both of these as part of the same CD deployment:

```powershell
kubectl apply -f .\k8s
terraform apply
```

## 8. Deployment verification

The CD job is successful only when all of these checks pass:

```powershell
kubectl -n rag-chatbot get pods
kubectl -n rag-chatbot get pvc
kubectl -n rag-chatbot rollout status deployment/rag-api --timeout=180s
kubectl -n rag-chatbot rollout status deployment/rag-ui --timeout=180s
```

For local access, use port forwarding:

```powershell
kubectl -n rag-chatbot port-forward svc/rag-api 8000:8000
kubectl -n rag-chatbot port-forward svc/rag-ui 8501:80
```

Then check:

```powershell
curl.exe http://localhost:8000/v1/health
```

## 9. Rollback

Because each deployment uses a commit-specific image tag, rollback is
repeatable:

```powershell
terraform -chdir=terraform apply -auto-approve `
  -var 'image=rag-chatbot:<known-good-commit-sha>'
```

Alternatively, restore the previous commit and let the normal CI/CD workflow
run again.

Do not use `latest` for the Kubernetes Deployment image. It makes rollback and
incident investigation ambiguous.

## 10. Final repository state

The intended end state is:

```text
.github/workflows/ci-cd.yaml
terraform/
  versions.tf
  provider.tf
  variables.tf
  main.tf
  outputs.tf
k8s/                  # reference only, or removed after migration
docker-compose.yml    # local development
docker-compose.deploy.yml  # optional single-server deployment
```

This gives the project:

- Free local Kubernetes
- Automated CI on pull requests
- Automated CD after merging to `main`
- Terraform-managed Kubernetes resources
- Commit-based image versions
- Repeatable deployment and rollback
- No cloud provider or AKS cost
