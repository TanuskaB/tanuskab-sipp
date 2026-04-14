// ---------------------------------------------------------------------------
// Configuration — update these after running setup_azure.sh
// ---------------------------------------------------------------------------
const CONFIG = {
  // Azure Function URL for the HTTP-triggered upload endpoint
  // e.g. "https://serverless-img-func.azurewebsites.net/api/upload"
  uploadUrl: "http://localhost:8080/",

  // Base URL of the processed-images blob container (public read)
  // e.g. "https://serverlessimgstorage.blob.core.windows.net/processed-images"
  processedContainerUrl: "https://happy-forest-04234cd0f.7.azurestaticapps.net/",

  pollIntervalMs: 2000,
  pollTimeoutMs: 30000,
};
// ---------------------------------------------------------------------------

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const uploadBtn = document.getElementById("upload-btn");
const statusBar = document.getElementById("status-bar");
const gallery = document.getElementById("gallery");
const emptyMsg = document.getElementById("empty-msg");
const optGray = document.getElementById("opt-gray");

let selectedFile = null;

// --- File selection ---

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) selectFile(fileInput.files[0]);
});

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith("image/")) selectFile(file);
});

function selectFile(file) {
  selectedFile = file;
  uploadBtn.disabled = false;
  setStatus(`Selected: ${file.name} (${formatBytes(file.size)})`, false);
}

// --- Upload ---

uploadBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  uploadBtn.disabled = true;
  setStatus("Uploading…", false);

  try {
    const blobName = buildBlobName(selectedFile.name, optGray.checked);
    await uploadToFunction(selectedFile, blobName);
    setStatus("Uploaded. Waiting for processing…", false);
    await pollForResult(blobName);
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
    uploadBtn.disabled = false;
  }
});

async function uploadToFunction(file, blobName) {
  const formData = new FormData();
  formData.append("file", file, blobName);

  const res = await fetch(CONFIG.uploadUrl, { method: "POST", body: formData });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed (${res.status}): ${text}`);
  }
}

// --- Poll for processed result ---

async function pollForResult(blobName) {
  if (!CONFIG.processedContainerUrl) {
    setStatus("Processed! (Set processedContainerUrl in app.js to preview results.)", false);
    addGalleryPlaceholder(blobName);
    return;
  }

  const url = `${CONFIG.processedContainerUrl}/${encodeURIComponent(blobName)}`;
  const deadline = Date.now() + CONFIG.pollTimeoutMs;

  while (Date.now() < deadline) {
    await sleep(CONFIG.pollIntervalMs);
    const res = await fetch(url, { method: "HEAD" });
    if (res.ok) {
      setStatus(`Done! Processed in ~${Math.round((CONFIG.pollTimeoutMs - (deadline - Date.now())) / 1000)}s`, false);
      addGalleryItem(blobName, url);
      selectedFile = null;
      uploadBtn.disabled = true;
      return;
    }
  }

  throw new Error("Processing timed out after 30 seconds.");
}

// --- Gallery ---

function addGalleryItem(name, url) {
  emptyMsg.style.display = "none";
  const item = document.createElement("div");
  item.className = "gallery-item";
  item.innerHTML = `
    <img src="${url}" alt="${name}" loading="lazy" />
    <div class="img-label">${name}</div>
    <a href="${url}" download="${name}">Download</a>
  `;
  gallery.prepend(item);
}

function addGalleryPlaceholder(name) {
  emptyMsg.style.display = "none";
  const item = document.createElement("div");
  item.className = "gallery-item";
  item.innerHTML = `
    <div style="height:150px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:.8rem;">No preview</div>
    <div class="img-label">${name}</div>
  `;
  gallery.prepend(item);
}

// --- Helpers ---

function buildBlobName(originalName, grayscale) {
  const dot = originalName.lastIndexOf(".");
  const base = dot !== -1 ? originalName.slice(0, dot) : originalName;
  const ext = dot !== -1 ? originalName.slice(dot) : ".jpg";
  return grayscale ? `${base}_gray${ext}` : `${base}${ext}`;
}

function setStatus(msg, isError) {
  statusBar.textContent = msg;
  statusBar.classList.remove("hidden", "error");
  if (isError) statusBar.classList.add("error");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
