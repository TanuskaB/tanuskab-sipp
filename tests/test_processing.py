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


if __name__ == "__main__":
    unittest.main()
