# Local Environment Setup — IT Support Assistant

## Windows (PowerShell)

Run once to set local environment variables for development:

```powershell
.\scripts\set_env.ps1 `
  -OpenAIKey "sk-..." `
  -DockerUser "your-dockerhub-username" `
  -DockerToken "dckr_pat_..."
```

Open a **new terminal** after running so values take effect.

---

## GitHub Repository Secrets

Go to: **GitHub Repo → Settings → Secrets and variables → Actions**

Add these as **Secrets** (New repository secret):

| Secret Name | Value | How to get |
|-------------|-------|-----------|
| `AZURE_CREDENTIALS` | Full JSON from `create_service_principal.sh` | `./scripts/create_service_principal.sh` |
| `DOCKERHUB_USERNAME` | `your-dockerhub-username` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | `dckr_pat_...` | Docker Hub → Account Settings → Security → Access Tokens |
| `RESOURCE_GROUP` | `your-resource-group` | Set in your Azure environment |
| `WEBAPP_NAME` | `your-webapp-name` | Created by `create_azure_resources.sh` |
| `OPENAI_API_KEY` | `sk-...` | OpenAI API key |

---

## Quick Start (full setup from scratch)

```bash
# 1. Login to Azure
az login

# 2. Create Azure App Service web app
chmod +x scripts/create_azure_resources.sh
./scripts/create_azure_resources.sh

# 3. Create service principal → copy JSON as AZURE_CREDENTIALS secret
chmod +x scripts/create_service_principal.sh
./scripts/create_service_principal.sh

# 4. Add all secrets to GitHub (see table above)

# 5. Push to main → CI/CD deploys automatically
git push origin main
```
