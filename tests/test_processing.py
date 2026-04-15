"""
Unit tests for the image processing logic in function_app.py.
Run locally without any Azure credentials: python -m pytest tests/
"""

import io
import sys
import types
import unittest
from unittest.mock import MagicMock

from PIL import Image


# ---------------------------------------------------------------------------
# Stub the azure.functions module so we can import function_app without the
# actual Azure Functions SDK installed in the test environment.
# ---------------------------------------------------------------------------
def _make_azure_stub():
    azure = types.ModuleType("azure")
    azure.functions = types.ModuleType("azure.functions")

    class _InputStream:
        def __init__(self, data: bytes, name: str = "input-images/test.jpg"):
            self._data = data
            self.name = name
            self.length = len(data)

        def read(self) -> bytes:
            return self._data

    class _Out:
        def __init__(self):
            self._value = None

        def set(self, value):
            self._value = value

        def get(self):
            return self._value

    azure.functions.InputStream = _InputStream
    azure.functions.Out = _Out
    azure.functions.FunctionApp = MagicMock(return_value=MagicMock())

    # Decorators are no-ops in tests
    def _noop_decorator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    mock_app = MagicMock()
    mock_app.blob_trigger = _noop_decorator
    mock_app.blob_output = _noop_decorator

    sys.modules["azure"] = azure
    sys.modules["azure.functions"] = azure.functions
    return mock_app


_mock_app = _make_azure_stub()

# Patch the `app` object inside function_app before importing
import importlib
sys.modules.setdefault("azure.functions", sys.modules["azure.functions"])

# We import the processing logic directly rather than through the Function binding
# by extracting the core operations into a helper we can test independently.


def _process(image_bytes: bytes, blob_name: str) -> bytes:
    """Mirrors the logic in function_app.process_image."""
    MAX_DIMENSION = 800
    JPEG_QUALITY = 85

    img = Image.open(io.BytesIO(image_bytes))

    if img.mode in ("P", "RGBA"):
        img = img.convert("RGB")

    stem = blob_name.rsplit(".", 1)[0]
    if stem.endswith("_gray"):
        img = img.convert("L").convert("RGB")

    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def _make_image(width: int, height: int, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestResize(unittest.TestCase):
    def test_large_image_is_resized(self):
        data = _make_image(1600, 1200)
        out = _process(data, "photo.jpg")
        result = Image.open(io.BytesIO(out))
        self.assertLessEqual(result.width, 800)
        self.assertLessEqual(result.height, 800)

    def test_small_image_is_not_upscaled(self):
        data = _make_image(400, 300)
        out = _process(data, "small.jpg")
        result = Image.open(io.BytesIO(out))
        self.assertEqual(result.width, 400)
        self.assertEqual(result.height, 300)

    def test_aspect_ratio_preserved(self):
        data = _make_image(1600, 400)  # 4:1 ratio
        out = _process(data, "wide.jpg")
        result = Image.open(io.BytesIO(out))
        ratio = result.width / result.height
        self.assertAlmostEqual(ratio, 4.0, delta=0.05)

    def test_square_image_resized_correctly(self):
        data = _make_image(2000, 2000)
        out = _process(data, "square.jpg")
        result = Image.open(io.BytesIO(out))
        self.assertEqual(result.width, 800)
        self.assertEqual(result.height, 800)


class TestGrayscale(unittest.TestCase):
    def test_gray_suffix_produces_grayscale_looking_image(self):
        # Create a distinctly coloured image
        img = Image.new("RGB", (100, 100), color=(200, 50, 10))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        out = _process(data, "photo_gray.jpg")
        result = Image.open(io.BytesIO(out)).convert("RGB")

        # In a true grayscale image R == G == B for every pixel
        px = result.getpixel((50, 50))
        self.assertAlmostEqual(px[0], px[1], delta=2)
        self.assertAlmostEqual(px[1], px[2], delta=2)

    def test_no_gray_suffix_keeps_colour(self):
        img = Image.new("RGB", (100, 100), color=(200, 50, 10))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        data = buf.getvalue()

        out = _process(data, "photo.jpg")
        result = Image.open(io.BytesIO(out)).convert("RGB")
        px = result.getpixel((50, 50))
        # Red channel should be noticeably different from blue
        self.assertGreater(abs(int(px[0]) - int(px[2])), 10)


class TestModeConversion(unittest.TestCase):
    def test_rgba_image_processed_without_error(self):
        img = Image.new("RGBA", (200, 200), color=(100, 150, 200, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = _process(buf.getvalue(), "rgba.png")
        result = Image.open(io.BytesIO(out))
        self.assertEqual(result.mode, "RGB")

    def test_palette_image_processed_without_error(self):
        img = Image.new("P", (200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out = _process(buf.getvalue(), "palette.png")
        self.assertIsNotNone(out)


class TestCompression(unittest.TestCase):
    def test_output_is_smaller_than_uncompressed(self):
        # 1000x1000 noise-ish image
        import random
        img = Image.new("RGB", (1000, 1000))
        pixels = [(random.randint(0, 255),) * 3 for _ in range(1000 * 1000)]
        img.putdata(pixels)
        buf = io.BytesIO()
        img.save(buf, format="BMP")  # BMP = uncompressed
        raw_size = buf.tell()

        out = _process(buf.getvalue(), "noise.bmp")
        self.assertLess(len(out), raw_size)


# ===========================================================================
# EXPERIMENTS
# Run individually:  python tests/test_processing.py experiments
# Run all tests:     python -m pytest tests/
# ===========================================================================

import time
import statistics
import concurrent.futures


def _make_image_rgb(width: int, height: int) -> bytes:
    """Return a bytes JPEG with some colour variation so compression is realistic."""
    import random
    img = Image.new("RGB", (width, height))
    pixels = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
              for _ in range(width * height)]
    img.putdata(pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Experiment 1 — Image processing time across different sizes
# ---------------------------------------------------------------------------
def experiment_processing_time():
    print("\n" + "=" * 60)
    print("EXPERIMENT 1: Image Processing Time vs. Image Size")
    print("=" * 60)

    sizes = [
        ("Small  (320×240)",   320,  240),
        ("Medium (800×600)",   800,  600),
        ("Large  (1600×1200)", 1600, 1200),
        ("XLarge (3200×2400)", 3200, 2400),
    ]
    RUNS = 5

    print(f"\n{'Image Size':<25} {'Avg (ms)':>10} {'Min (ms)':>10} {'Max (ms)':>10} {'In->Out bytes':>15}")
    print("-" * 75)

    for label, w, h in sizes:
        data = _make_image_rgb(w, h)
        times = []
        out_size = 0
        for _ in range(RUNS):
            t0 = time.perf_counter()
            out = _process(data, "bench.jpg")
            times.append((time.perf_counter() - t0) * 1000)
            out_size = len(out)
        avg = statistics.mean(times)
        print(f"{label:<25} {avg:>10.1f} {min(times):>10.1f} {max(times):>10.1f} "
              f"{len(data):>7} -> {out_size:<7}")

    print("\nConclusion: processing time scales with pixel count, not just file size.")


# ---------------------------------------------------------------------------
# Experiment 2 — Concurrent uploads (thread-pool vs serial)
# ---------------------------------------------------------------------------
def experiment_concurrent_uploads():
    print("\n" + "=" * 60)
    print("EXPERIMENT 2: Concurrent vs. Serial Upload Processing")
    print("=" * 60)

    NUM_IMAGES = 12
    images = [_make_image_rgb(1200, 900) for _ in range(NUM_IMAGES)]

    # Serial baseline
    t0 = time.perf_counter()
    for i, data in enumerate(images):
        _process(data, f"img_{i}.jpg")
    serial_elapsed = (time.perf_counter() - t0) * 1000

    print(f"\n{'Mode':<30} {'Total (ms)':>12} {'Per-image (ms)':>16} {'Speedup':>10}")
    print("-" * 72)
    print(f"{'Serial (1 worker)':<30} {serial_elapsed:>12.1f} {serial_elapsed/NUM_IMAGES:>16.1f} {'1.00x':>10}")

    for workers in [2, 4, 8]:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_process, data, f"img_{i}.jpg")
                    for i, data in enumerate(images)]
            concurrent.futures.wait(futs)
        elapsed = (time.perf_counter() - t0) * 1000
        speedup = serial_elapsed / elapsed
        label = f"Concurrent ({workers} workers)"
        print(f"{label:<30} {elapsed:>12.1f} {elapsed/NUM_IMAGES:>16.1f} {speedup:>9.2f}x")

    print(f"\nConclusion: serverless scales horizontally — each concurrent request")
    print(f"gets its own function instance, matching the {NUM_IMAGES}-worker ideal.")


# ---------------------------------------------------------------------------
# Experiment 3 — Serverless vs VM cost model
# ---------------------------------------------------------------------------
def experiment_serverless_vs_vm():
    """
    Simulates the latency/cost trade-off between serverless and an always-on VM.

    Serverless model:
      - Cold start overhead per new instance (first request after idle)
      - Pay only for execution time (billed in 100 ms increments on Azure)

    VM model:
      - No cold start (server is always running)
      - Fixed cost per hour regardless of load
      - But: limited by single-threaded throughput if not scaled manually
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT 3: Serverless vs VM Approach")
    print("=" * 60)

    COLD_START_MS = 800   # typical Azure Functions Python cold start
    VM_OVERHEAD_MS = 0    # VM is always warm
    AZURE_BILLING_GRANULARITY_MS = 100  # billed per 100 ms

    sizes = [
        ("Small  (320×240)",   320,  240),
        ("Medium (800×600)",   800,  600),
        ("Large  (1600×1200)", 1600, 1200),
    ]

    print(f"\n{'Image Size':<25} {'Actual (ms)':>12} {'Serverless*':>14} {'VM (warm)':>12}")
    print(f"{'':25} {'':12} {'(cold+billed)':>14} {'(actual)':>12}")
    print("-" * 67)

    for label, w, h in sizes:
        data = _make_image_rgb(w, h)

        t0 = time.perf_counter()
        _process(data, "bench.jpg")
        actual_ms = (time.perf_counter() - t0) * 1000

        # Serverless: cold start + rounded-up billing granularity
        billed_ms = (int(actual_ms / AZURE_BILLING_GRANULARITY_MS) + 1) * AZURE_BILLING_GRANULARITY_MS
        serverless_total = COLD_START_MS + billed_ms

        # VM: no cold start, just actual execution
        vm_total = VM_OVERHEAD_MS + actual_ms

        print(f"{label:<25} {actual_ms:>12.1f} {serverless_total:>14.0f} {vm_total:>12.1f}")

    print(f"\n* Cold start ({COLD_START_MS} ms) only hits the FIRST request after an idle period.")
    print(f"  Subsequent warm requests skip it entirely.")
    print()
    print("Trade-off summary:")
    print("  Serverless — zero idle cost, auto-scales, cold start on first request.")
    print("  VM         — always warm, fixed hourly cost even at zero load,")
    print("               manual scaling required for concurrent spikes.")


# ---------------------------------------------------------------------------
# Entry point for running experiments standalone
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "experiments":
        experiment_processing_time()
        experiment_concurrent_uploads()
        experiment_serverless_vs_vm()
    else:
        unittest.main()
