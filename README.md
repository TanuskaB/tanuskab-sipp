# Serverless Image Processing Platform

This project lets users upload an image from a small web frontend, stores it in Azure Blob Storage, and processes it with Azure Functions. The processed image is resized, compressed, and optionally converted to grayscale.

## How It Works

1. The frontend sends an image to the Azure Function HTTP endpoint at `/api/upload`.
2. The function saves the file into the `input-images` blob container.
3. A blob-triggered Azure Function processes the image.
4. The processed result is written to the `processed-images` blob container.
5. The frontend polls the processed container and shows the finished image.

## Project Structure

```text
.
├── function_app/
│   ├── function_app.py
│   ├── host.json
│   ├── local.settings.json.example
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── scripts/
│   └── setup_azure.sh
└── tests/
    └── test_processing.py
```

## Prerequisites

- Python 3.11 recommended
- `pip`
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local)
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- An Azure Storage connection string for local development

## Build And Run Locally

### 1. Install the Function App dependencies

```bash
cd function_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure local settings

```bash
cp local.settings.json.example local.settings.json
```

Then edit `function_app/local.settings.json` and set both:

- `AzureWebJobsStorage`
- `AzureStorageConnectionString`

to the same Azure Storage connection string.

### 3. Start the Azure Function locally

From `function_app/`:

```bash
func start
```

The upload endpoint will be available at:

```text
http://localhost:7071/api/upload
```

### 4. Point the frontend at the local function

Edit `frontend/app.js` and set:

```js
uploadUrl: "http://localhost:7071/api/upload"
```

You can leave `processedContainerUrl` pointing at your Azure blob container if you want the frontend to preview processed results from storage.

### 5. Start the frontend

In a second terminal:

```bash
cd frontend
python3 -m http.server 8080
```

Then open:

```text
http://localhost:8080
```

## Run Tests

From the repo root:

```bash
python3 -m pip install pytest Pillow
python3 -m pytest tests/ -v
```

## Experiments

Three experiments are included in `tests/test_processing.py` to measure real performance characteristics of the pipeline. Run them with:

```bash
py tests/test_processing.py experiments
```

### Experiment 1 — Image Processing Time

Times the processing pipeline across four image sizes (5 runs each) and reports average, min, and max latency alongside input/output file sizes.

| Image Size | Avg Time |
|---|---|
| Small (320×240) | ~2 ms |
| Medium (800×600) | ~11 ms |
| Large (1600×1200) | ~39 ms |
| XLarge (3200×2400) | ~95 ms |

Processing time scales with pixel count. A 3200×2400 image takes roughly 47× longer than a 320×240 image.

### Experiment 2 — Concurrent Uploads

Simulates 12 simultaneous image uploads using a thread pool and compares total wall-clock time against serial processing.

| Mode | Speedup |
|---|---|
| Serial (1 worker) | 1.00× |
| 2 workers | ~1.44× |
| 4 workers | ~1.89× |
| 8 workers | ~2.21× |

In production, Azure Functions automatically provisions a separate instance per concurrent request, making the speedup closer to fully linear (12 requests → ~12× faster) without any manual configuration.

### Experiment 3 — Serverless vs VM

Models the latency and cost trade-off between the serverless (Azure Functions) approach and an always-on VM.

| Approach | Cold Start | Idle Cost | Scales Automatically |
|---|---|---|---|
| Serverless | ~800 ms (first request only) | None | Yes |
| VM | None (always warm) | Fixed hourly rate | No (manual) |

The cold start penalty only applies to the very first request after an idle period. All subsequent warm requests match VM latency exactly — but the VM pays a fixed hourly cost even at zero load.

## Deploy To Azure

### 1. Provision Azure resources

```bash
bash scripts/setup_azure.sh
```

This script creates:

- a resource group
- a storage account
- the `input-images` container
- the `processed-images` container
- a Linux Azure Function App

It also prints the storage connection string and generated Function App name.

### 2. Set local settings for deployment and local testing

```bash
cp function_app/local.settings.json.example function_app/local.settings.json
```

Paste the connection string printed by the setup script into:

- `AzureWebJobsStorage`
- `AzureStorageConnectionString`

### 3. Publish the Azure Function

```bash
cd function_app
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
```

After deployment, your upload endpoint will look like:

```text
https://<YOUR_FUNCTION_APP_NAME>.azurewebsites.net/api/upload
```

### 4. Deploy the frontend

Deploy the `frontend/` folder with Azure Static Web Apps or any static hosting service.

After that, update `frontend/app.js` with:

- `uploadUrl`: your deployed Azure Function URL
- `processedContainerUrl`: your public `processed-images` blob container URL

## Image Processing Rules

- Images are resized so their longest side is at most `800px`
- Output is saved as JPEG with quality `85`
- If the filename ends with `_gray`, the image is converted to grayscale

Example:

- `photo.jpg` -> resized and compressed
- `photo_gray.jpg` -> resized, compressed, and converted to grayscale

## Notes

- The frontend is a plain static app in `frontend/`
- The backend logic lives in `function_app/function_app.py`
- The local settings file contains secrets and should not be committed

## Image Processing Website:
link: https://thankful-water-060a3030f.7.azurestaticapps.net
