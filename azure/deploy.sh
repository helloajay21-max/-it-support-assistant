#!/usr/bin/env bash
# =============================================================================
# Azure Container Apps Deployment Script for IT Support Assistant
# =============================================================================
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Docker installed
#   - .env file configured with API keys
# Usage:
#   chmod +x azure/deploy.sh
#   ./azure/deploy.sh
# =============================================================================

set -euo pipefail

# ── Configuration — edit these values ────────────────────────────────────────
RESOURCE_GROUP="it-support-assistant-rg"
LOCATION="eastus"
ACR_NAME="itsupportacr$(date +%s | tail -c 6)"  # Unique registry name
APP_NAME="it-support-assistant"
ENVIRONMENT_NAME="it-support-env"
IMAGE_TAG="latest"

# Load environment variables
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
    echo "✅ Loaded .env configuration"
else
    echo "⚠️  No .env file found. Ensure environment variables are set."
fi

echo ""
echo "=========================================="
echo "  IT Support Assistant — Azure Deployment"
echo "=========================================="
echo "Resource Group : $RESOURCE_GROUP"
echo "Location       : $LOCATION"
echo "ACR Name       : $ACR_NAME"
echo "App Name       : $APP_NAME"
echo ""

# ── Step 1: Create Resource Group ─────────────────────────────────────────────
echo "🔵 [1/7] Creating resource group..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output table

# ── Step 2: Create Azure Container Registry ───────────────────────────────────
echo "🔵 [2/7] Creating Azure Container Registry..."
az acr create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$ACR_NAME" \
    --sku Basic \
    --admin-enabled true \
    --output table

# ── Step 3: Build and push Docker image ───────────────────────────────────────
echo "🔵 [3/7] Building and pushing Docker image to ACR..."
az acr build \
    --registry "$ACR_NAME" \
    --image "$APP_NAME:$IMAGE_TAG" \
    --file ../Dockerfile \
    ../

# ── Step 4: Get ACR credentials ───────────────────────────────────────────────
echo "🔵 [4/7] Retrieving ACR credentials..."
ACR_LOGIN_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)
echo "   ACR Login Server: $ACR_LOGIN_SERVER"

# ── Step 5: Create Container Apps Environment ────────────────────────────────
echo "🔵 [5/7] Creating Container Apps environment..."
az containerapp env create \
    --name "$ENVIRONMENT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output table

# ── Step 6: Deploy Container App ─────────────────────────────────────────────
echo "🔵 [6/7] Deploying Container App..."

# Build environment variable args
ENV_VARS="LOG_LEVEL=INFO ENABLE_FILE_LOG=false"
[ -n "${AZURE_OPENAI_ENDPOINT:-}" ] && ENV_VARS="$ENV_VARS AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT"
[ -n "${AZURE_OPENAI_API_KEY:-}" ]  && ENV_VARS="$ENV_VARS AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY"
[ -n "${AZURE_OPENAI_DEPLOYMENT:-}" ] && ENV_VARS="$ENV_VARS AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT"
[ -n "${AZURE_OPENAI_API_VERSION:-}" ] && ENV_VARS="$ENV_VARS AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION"
[ -n "${OPENAI_API_KEY:-}" ]        && ENV_VARS="$ENV_VARS OPENAI_API_KEY=$OPENAI_API_KEY"
[ -n "${OPENAI_MODEL:-}" ]          && ENV_VARS="$ENV_VARS OPENAI_MODEL=$OPENAI_MODEL"

az containerapp create \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --environment "$ENVIRONMENT_NAME" \
    --image "$ACR_LOGIN_SERVER/$APP_NAME:$IMAGE_TAG" \
    --registry-server "$ACR_LOGIN_SERVER" \
    --registry-username "$ACR_NAME" \
    --registry-password "$ACR_PASSWORD" \
    --target-port 8501 \
    --ingress external \
    --min-replicas 1 \
    --max-replicas 3 \
    --cpu 1.0 \
    --memory 2.0Gi \
    --env-vars $ENV_VARS \
    --output table

# ── Step 7: Get Application URL ──────────────────────────────────────────────
echo "🔵 [7/7] Retrieving application URL..."
APP_URL=$(az containerapp show \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query "properties.configuration.ingress.fqdn" \
    -o tsv)

echo ""
echo "=========================================="
echo "  ✅ Deployment Complete!"
echo "=========================================="
echo "  🌐 Application URL: https://$APP_URL"
echo "  📊 Resource Group:  $RESOURCE_GROUP"
echo "  📦 Container Registry: $ACR_LOGIN_SERVER"
echo ""
echo "  To view logs:"
echo "  az containerapp logs show --name $APP_NAME --resource-group $RESOURCE_GROUP --follow"
echo ""
echo "  To delete all resources:"
echo "  az group delete --name $RESOURCE_GROUP --yes --no-wait"
echo "=========================================="
