import cgi
import io
import json
import logging
import os
import time
import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient
from PIL import Image

app = func.FunctionApp()

MAX_DIMENSION = 800
JPEG_QUALITY = 85


@app.route(route="upload", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)

def upload_image(req: func.HttpRequest) -> func.HttpResponse:
    content_type = req.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        return func.HttpResponse(
            json.dumps({"error": "Expected multipart/form-data upload."}),
            status_code=400,
            mimetype="application/json",
        )

    body = req.get_body()
    form = cgi.FieldStorage(
        fp=io.BytesIO(body),
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(len(body)),
        },
        keep_blank_values=True,
    )

    if "file" not in form:
        return func.HttpResponse(
            json.dumps({"error": "Missing file field in form data."}),
            status_code=400,
            mimetype="application/json",
        )

    upload = form["file"]
    file_bytes = upload.file.read() if upload.file else b""
    blob_name = os.path.basename(upload.filename or "")

    if not blob_name:
        return func.HttpResponse(
            json.dumps({"error": "Uploaded file must have a filename."}),
            status_code=400,
            mimetype="application/json",
        )

    if not file_bytes:
        return func.HttpResponse(
            json.dumps({"error": "Uploaded file is empty."}),
            status_code=400,
            mimetype="application/json",
        )

    connection_string = os.environ.get("AzureStorageConnectionString")
    if not connection_string:
        logging.error("AzureStorageConnectionString is not configured.")
        return func.HttpResponse(
            json.dumps({"error": "Storage connection is not configured."}),
            status_code=500,
            mimetype="application/json",
        )

    blob_service = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service.get_container_client("input-images")
    try:
        container_client.create_container()
    except ResourceExistsError:
        pass
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file_bytes, overwrite=True)

    logging.info("Accepted upload for %s (%d bytes)", blob_name, len(file_bytes))

    return func.HttpResponse(
        json.dumps({"message": "Upload accepted.", "blobName": blob_name}),
        status_code=202,
        mimetype="application/json",
    )


@app.blob_trigger(
    arg_name="inputblob",
    path="input-images/{name}",
    connection="AzureStorageConnectionString",
)
@app.blob_output(
    arg_name="outputblob",
    path="processed-images/{name}",
    connection="AzureStorageConnectionString",
)
def process_image(inputblob: func.InputStream, outputblob: func.Out[bytes]):
    name = inputblob.name.split("/")[-1]
    logging.info("Processing image: %s (%d bytes)", name, inputblob.length)
    start = time.time()

    image_data = inputblob.read()
    img = Image.open(io.BytesIO(image_data))

    # Convert palette/RGBA modes so JPEG save works
    if img.mode in ("P", "RGBA"):
        img = img.convert("RGB")

    # Grayscale if filename suffix requests it
    if name.rsplit(".", 1)[0].endswith("_gray"):
        img = img.convert("L").convert("RGB")

    # Resize — maintain aspect ratio, cap longest side at MAX_DIMENSION
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    # Encode to JPEG in memory
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    output_bytes = buf.getvalue()

    outputblob.set(output_bytes)

    elapsed = time.time() - start
    logging.info(
        "Finished %s: %d -> %d bytes in %.2fs",
        name,
        len(image_data),
        len(output_bytes),
        elapsed,
    )
