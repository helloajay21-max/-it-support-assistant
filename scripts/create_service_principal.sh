#!/bin/bash
# create_service_principal.sh
# Creates a service principal for GitHub Actions — same pattern as MCP-Project
#
# Usage:
#   chmod +x scripts/create_service_principal.sh
#   ./scripts/create_service_principal.sh

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-cf9cf236-9d67-496c-97b1-5485d32f0dd3}"
RESOURCE_GROUP="${RESOURCE_GROUP:-Ajay-Practice}"
SP_NAME="it-support-github-sp"

echo "Creating service principal: $SP_NAME"

az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  --sdk-auth

echo ""
echo "✅ Copy the entire JSON above as the AZURE_CREDENTIALS GitHub secret."
