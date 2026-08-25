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

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-00000000-0000-0000-0000-000000000000}"
RESOURCE_GROUP="${RESOURCE_GROUP:-your-resource-group}"
LOCATION="${LOCATION:-centralindia}"
PLAN_NAME="${PLAN_NAME:-your-app-service-plan}"
WEBAPP_NAME="${WEBAPP_NAME:-your-webapp-name}"
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-your-dockerhub-username}"
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

# Resource group
az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --output none 2>/dev/null || true
echo "✅ Resource group: $RESOURCE_GROUP"

# App Service Plan — create if it does not exist
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
        WEBSITES_ENABLE_APP_SERVICE_STORAGE=true \
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
