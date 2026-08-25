<#
PowerShell helper — set local Windows environment variables for development.

Usage:
  .\scripts\set_env.ps1 -OpenAIKey "sk-..." -DockerUser "your-dockerhub-username" -DockerToken "dckr_pat_..."

After running, open a NEW terminal to pick up the new values.
#>
param(
  [string]$OpenAIKey    = "",
  [string]$DockerUser   = "your-dockerhub-username",
  [string]$DockerToken  = "",
  [string]$ResourceGroup = "your-resource-group",
  [string]$WebApp       = "your-webapp-name",
  [string]$SubscriptionId = "00000000-0000-0000-0000-000000000000",
  [string]$SqliteDbPath = "data/tickets.db",
  [string]$AdminEmail   = "helloajay21@gmail.com"
)

if ($OpenAIKey -ne "") {
  setx OPENAI_API_KEY $OpenAIKey | Out-Null
  Write-Host "Set OPENAI_API_KEY" -ForegroundColor Green
}
if ($DockerUser -ne "") {
  setx DOCKERHUB_USERNAME $DockerUser | Out-Null
  Write-Host "Set DOCKERHUB_USERNAME = $DockerUser" -ForegroundColor Green
}
if ($DockerToken -ne "") {
  setx DOCKERHUB_TOKEN $DockerToken | Out-Null
  Write-Host "Set DOCKERHUB_TOKEN" -ForegroundColor Green
}
if ($ResourceGroup -ne "") {
  setx RESOURCE_GROUP $ResourceGroup | Out-Null
  Write-Host "Set RESOURCE_GROUP = $ResourceGroup" -ForegroundColor Green
}
if ($WebApp -ne "") {
  setx WEBAPP_NAME $WebApp | Out-Null
  Write-Host "Set WEBAPP_NAME = $WebApp" -ForegroundColor Green
}
if ($SubscriptionId -ne "") {
  setx AZURE_SUBSCRIPTION_ID $SubscriptionId | Out-Null
  Write-Host "Set AZURE_SUBSCRIPTION_ID" -ForegroundColor Green
}

setx IMAGE_NAME "it-support-assistant" | Out-Null
setx OPENAI_MODEL "gpt-4o-mini" | Out-Null
setx WEBSITES_PORT "8501" | Out-Null
setx WEBSITES_ENABLE_APP_SERVICE_STORAGE "true" | Out-Null
setx SQLITE_DB_PATH $SqliteDbPath | Out-Null
setx ADMIN_EMAIL $AdminEmail | Out-Null

Write-Host ""
Write-Host "Local env vars set. Open a NEW terminal to use them." -ForegroundColor Cyan
Write-Host ""
Write-Host "Reminder: Add these as GitHub repository secrets:" -ForegroundColor Yellow
Write-Host "  AZURE_CREDENTIALS, DOCKERHUB_USERNAME, DOCKERHUB_TOKEN, RESOURCE_GROUP, WEBAPP_NAME, OPENAI_API_KEY, ADMIN_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_USE_TLS, VPN_RESET_BASE_URL"
