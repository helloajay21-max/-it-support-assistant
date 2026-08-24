#!/bin/bash
# create_azure_resources.sh — provision Azure App Service for IT Support Assistant
# Matches the same pattern as MCP-Project
#
# Usage:
#   chmod +x scripts/create_azure_resources.sh
#   ./scripts/create_azure_resources.sh
#
# Or with custom values:
#   WEBAPP_NAME=my-app ./scripts/create_azure_resources.sh

set -euo pipefail

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-cf9cf236-9d67-496c-97b1-5485d32f0dd3}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Ajay-Practice}"
LOCATION="${LOCATION:-centralindia}"
PLAN_NAME="${PLAN_NAME:-mcp-app-plan}"          # reuse existing plan from MCP-Project
WEBAPP_NAME="${WEBAPP_NAME:-it-support-ajay-001}"
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-helloajay21}"
IMAGE_NAME="it-support-assistant"

echo "══════════════════════════════════════════════"
echo "  IT Support Assistant — Azure Setup"
echo "══════════════════════════════════════════════"
echo "  Subscription : $SUBSCRIPTION_ID"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location     : $LOCATION"
echo "  App Plan     : $PLAN_NAME"
echo "  Web App      : $WEBAPP_NAME"
echo "  Docker Image : $DOCKERHUB_USERNAME/$IMAGE_NAME:latest"
echo ""

az account set --subscription "$SUBSCRIPTION_ID"

# Resource group (likely already exists — Ajay-Practice)
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --output none 2>/dev/null || true
echo "✅ Resource group: $RESOURCE_GROUP"

# App Service Plan — reuse existing mcp-app-plan if it exists
PLAN_EXISTS=$(az appservice plan show -g "$RESOURCE_GROUP" -n "$PLAN_NAME" --query name -o tsv 2>/dev/null || echo "")
if [ -z "$PLAN_EXISTS" ]; then
    az appservice plan create -g "$RESOURCE_GROUP" -n "$PLAN_NAME" --is-linux --sku B1 --output none
    echo "✅ App Service Plan created: $PLAN_NAME"
else
    echo "✅ Reusing existing App Service Plan: $PLAN_NAME"
fi

# Create Web App for Containers
az webapp create \
    -g "$RESOURCE_GROUP" \
    -p "$PLAN_NAME" \
    -n "$WEBAPP_NAME" \
    --deployment-container-image-name "${DOCKERHUB_USERNAME}/${IMAGE_NAME}:latest" \
    --output none
echo "✅ Web App created: $WEBAPP_NAME"

# App settings
az webapp config appsettings set \
    -g "$RESOURCE_GROUP" \
    -n "$WEBAPP_NAME" \
    --settings \
        WEBSITES_PORT=8501 \
        SQLITE_DB_PATH=/home/data/tickets.db \
        OPENAI_MODEL=gpt-4o-mini \
        LOG_LEVEL=INFO \
    --output none
echo "✅ App settings configured"

# Get URL
URL=$(az webapp show -g "$RESOURCE_GROUP" -n "$WEBAPP_NAME" --query defaultHostName -o tsv)

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Azure resources ready!"
echo "  🌐 App URL: https://$URL"
echo "══════════════════════════════════════════════"
echo ""
echo "Next: Create a service principal and add GitHub secrets."
echo "Run: ./scripts/create_service_principal.sh"
