# Local Environment Setup — AI Operations Assistant Using Agentic AI

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
| `ADMIN_EMAIL` | `helloajay21@gmail.com` | Admin inbox for approval links and VPN copy emails |
| `ADMIN_PASSWORD` | `your-admin-password` | Admin login password for Ajay Kumar |
| `APP_BASE_URL` | `https://your-webapp.azurewebsites.net` | Base URL used for approval links |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server host |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | `your-mailbox@gmail.com` | SMTP login username |
| `SMTP_PASSWORD` | `app-password-without-spaces` | SMTP app password / relay password |
| `SMTP_FROM_EMAIL` | `your-mailbox@gmail.com` | Sender mailbox used by the app |
| `SMTP_USE_TLS` | `true` | Enable STARTTLS |
| `SMTP_USE_SSL` | `false` | Set `true` for direct SSL on port 465 |
| `VPN_RESET_BASE_URL` | `https://selfservice.techcorp.com/reset-vpn` | Reset link used in notification emails |

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

# 4. Add all secrets to GitHub (see table above), including ADMIN_EMAIL, ADMIN_PASSWORD, APP_BASE_URL, and SMTP_*

# 5. Push to main → CI/CD deploys automatically
git push origin main
```
