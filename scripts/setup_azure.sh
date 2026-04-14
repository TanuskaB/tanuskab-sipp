#!/usr/bin/env bash
# setup_azure.sh — Provision all Azure resources for the Serverless Image Processing Platform
# Usage: bash scripts/setup_azure.sh
# Prerequisites: Azure CLI installed and logged in (`az login`)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
RESOURCE_GROUP="serverlessimgrg"
LOCATION="eastus"
STORAGE_ACCOUNT="imgstorage$RANDOM"   # must be globally unique
FUNCTION_APP="serverlessimgfunc$RANDOM"
PYTHON_VERSION="3.11"
# ───────────────────────────────────────────────────────────────────────────────

echo "==> Creating resource group: $RESOURCE_GROUP"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output table

echo ""
echo "==> Creating storage account: $STORAGE_ACCOUNT"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output table

# Fetch the connection string for later use
CONN_STRING=$(az storage account show-connection-string \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query connectionString \
  --output tsv)

echo ""
echo "==> Creating blob containers"
az storage container create \
  --name "input-images" \
  --account-name "$STORAGE_ACCOUNT" \
  --connection-string "$CONN_STRING" \
  --output table

az storage container create \
  --name "processed-images" \
  --account-name "$STORAGE_ACCOUNT" \
  --connection-string "$CONN_STRING" \
  --public-access blob \
  --output table

echo ""
echo "==> Creating Function App: $FUNCTION_APP (consumption plan, Python $PYTHON_VERSION)"
az functionapp create \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT" \
  --consumption-plan-location "$LOCATION" \
  --runtime python \
  --runtime-version "$PYTHON_VERSION" \
  --functions-version 4 \
  --os-type linux \
  --output table

echo ""
echo "==> Setting app settings on Function App"
az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    "AzureStorageConnectionString=$CONN_STRING" \
  --output table

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                   Setup Complete!                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║ Resource Group : $RESOURCE_GROUP"
echo "║ Storage Account: $STORAGE_ACCOUNT"
echo "║ Function App   : $FUNCTION_APP"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║ Next steps:"
echo "║  1. Copy the connection string below into:"
echo "║     function_app/local.settings.json  (for local dev)"
echo "║  2. Deploy the function:"
echo "║     cd function_app && func azure functionapp publish $FUNCTION_APP"
echo "║  3. Deploy the frontend to Azure Static Web Apps via the portal"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Connection string (keep secret):"
echo "$CONN_STRING"
