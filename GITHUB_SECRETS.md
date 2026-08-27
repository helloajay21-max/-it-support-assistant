# GitHub Secrets Setup — IT Support Assistant
# Same pattern as MCP-Project

Go to: GitHub Repo → Settings → Secrets and variables → Actions → New repository secret

| Secret Name | Value |
| --- | --- |
| `AZURE_CREDENTIALS` | JSON from `./scripts/create_service_principal.sh` |
| `DOCKERHUB_USERNAME` | your Docker Hub username |
| `DOCKERHUB_TOKEN` | your Docker Hub access token |
| `RESOURCE_GROUP` | your Azure resource group |
| `WEBAPP_NAME` | your Azure App Service web app name |
| `OPENAI_API_KEY` | `sk-...` |
| `ADMIN_EMAIL` | admin inbox that receives approval links and VPN copy emails, e.g. `helloajay21@gmail.com` |
| `APP_BASE_URL` | Full URL of your Azure web app, e.g. `https://your-webapp.azurewebsites.net` |
| `SMTP_HOST` | `smtp.gmail.com` or your SMTP server |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | SMTP login username |
| `SMTP_PASSWORD` | SMTP app password / relay password |
| `SMTP_FROM_EMAIL` | sender mailbox used by the app |
| `SMTP_USE_TLS` | `true` |
| `VPN_RESET_BASE_URL` | `https://selfservice.techcorp.com/reset-vpn` |

The workflow now applies both the Azure runtime settings and the VPN email settings on every deploy, so keep these secrets current.
