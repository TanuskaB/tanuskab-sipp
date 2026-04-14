# Serverless Image Processing Platform

Azure-based platform that automatically resizes, compresses, and optionally converts images to grayscale the moment they are uploaded — no server management required.

## Architecture

```
User → Frontend (Static Web App)
         │
         ▼
    Azure Blob Storage  (input-images container)
         │
         │  BlobTrigger
         ▼
    Azure Function  (Python)
    ─ Resize to max 800 px
    ─ JPEG compress @ 85 %
    ─ Grayscale (if filename ends with _gray)
         │
         ▼
    Azure Blob Storage  (processed-images container)
         │
         ▼
      User downloads result
```

## Prerequisites

- Python 3.10+
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- Azure CLI — install on Ubuntu/Debian:
  ```bash
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
  az login
  ```
- An Azure account (Student / Free Tier works)

## Local Development

### 1. Install dependencies

```bash
cd function_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure local settings

```bash
cp local.settings.json.example local.settings.json
# Edit local.settings.json and fill in your storage connection string
```

### 3. Run the function locally

```bash
func start
```

The function listens for new blobs in `input-images`. Use Azure Storage Explorer or `az storage blob upload` to drop test images in.

### 4. Run the frontend locally

```bash
cd ../frontend
# Any static file server works:
python -m http.server 8080
```

Open `http://localhost:8080`. Update `CONFIG.uploadUrl` in `app.js` to point at your local function endpoint.

## Run Tests

```bash
pip install pillow pytest
pytest tests/ -v
```

## Deploy to Azure

### 1. Provision resources

```bash
bash scripts/setup_azure.sh
```

This creates the resource group, storage account, blob containers, and Function App. Copy the printed connection string.

### 2. Create `local.settings.json`

```bash
cp function_app/local.settings.json.example function_app/local.settings.json
# Paste the connection string from step 1
```

### 3. Deploy the function

```bash
cd function_app
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
```

### 4. Deploy the frontend

In the Azure Portal:
1. Create an **Azure Static Web App** resource.
2. Connect it to your GitHub repo (or upload the `frontend/` folder directly).
3. Copy the Static Web App URL and update `CONFIG.processedContainerUrl` in `frontend/app.js`.

## Image Operations

| Trigger | Operation |
|---|---|
| Any upload | Resize (max 800 px, aspect preserved) + JPEG compress @ 85 % |
| Filename ends with `_gray` | Additionally converts to grayscale |

Example: upload `sunset_gray.jpg` → processed image is grayscale + resized.

## Project Structure

```
├── function_app/
│   ├── function_app.py           # Azure Function (BlobTrigger)
│   ├── host.json
│   ├── requirements.txt
│   └── local.settings.json.example
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── scripts/
│   └── setup_azure.sh            # One-shot Azure provisioning
└── tests/
    └── test_processing.py        # Unit tests (no Azure needed)
```
