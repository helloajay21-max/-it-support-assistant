#!/bin/bash
# create_service_principal.sh
# Creates a service principal for GitHub Actions — same pattern as MCP-Project
#
# Usage:
#   chmod +x scripts/create_service_principal.sh
#   ./scripts/create_service_principal.sh

SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-00000000-0000-0000-0000-000000000000}"
RESOURCE_GROUP="${RESOURCE_GROUP:-your-resource-group}"
SP_NAME="it-support-github-sp"

echo "Creating service principal: $SP_NAME"

az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP" \
  --sdk-auth

echo ""
echo "✅ Copy the entire JSON above as the AZURE_CREDENTIALS GitHub secret."
