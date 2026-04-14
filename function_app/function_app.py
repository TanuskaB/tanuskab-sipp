import logging
import time
import io
import azure.functions as func
from PIL import Image

app = func.FunctionApp()

MAX_DIMENSION = 800
JPEG_QUALITY = 85


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
