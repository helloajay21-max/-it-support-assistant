<#
PowerShell helper — set local Windows environment variables for development.

Usage:
  .\scripts\set_env.ps1 -OpenAIKey "sk-..." -DockerUser "helloajay21" -DockerToken "dckr_pat_..."

After running, open a NEW terminal to pick up the new values.
#>
param(
  [string]$OpenAIKey    = "",
  [string]$DockerUser   = "helloajay21",
  [string]$DockerToken  = "",
  [string]$ResourceGroup = "Ajay-Practice",
  [string]$WebApp       = "it-support-ajay-001",
  [string]$SubscriptionId = "cf9cf236-9d67-496c-97b1-5485d32f0dd3",
  [string]$SqliteDbPath = "data/tickets.db"
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
setx SQLITE_DB_PATH $SqliteDbPath | Out-Null

Write-Host ""
Write-Host "Local env vars set. Open a NEW terminal to use them." -ForegroundColor Cyan
Write-Host ""
Write-Host "Reminder: Add these as GitHub repository secrets:" -ForegroundColor Yellow
Write-Host "  AZURE_CREDENTIALS, DOCKERHUB_USERNAME, DOCKERHUB_TOKEN, RESOURCE_GROUP, WEBAPP_NAME, OPENAI_API_KEY"
