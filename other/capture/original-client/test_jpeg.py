"""回归原 JPEG 引用的本地跳转、同目录名称冲突及像素完整性。"""
import hashlib
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

from convert import convert
from jpeg_interlace import convert_jpeg
from test_conversion import har_record, preview, sample_png

try:
    from PIL import Image
except ImportError:
    Image = None


def sample_jpeg(**options):
    image = Image.frombytes("RGB", (3, 2), bytes([0,0,0, 255,0,0, 0,255,0,
                                                  0,0,255, 200,110,57, 255,255,255]))
    raw = io.BytesIO()
    image.save(raw, format="JPEG", **options)
    return raw.getvalue()


@unittest.skipIf(Image is None, "未安装可选的 JPEG 解码依赖 Pillow")
class TestJpeg(unittest.TestCase):
    def test_original_address_redirect_and_pixels(self):
        jpeg = sample_jpeg()
        original = Image.open(io.BytesIO(jpeg))
        html = (b'<button id="game">0</button><script src="game.js"></script>'
                b'<img src="assets/photo.jpg?v=2"><img src="assets/PHOTO.PNG">'
                b'<img src="assets/Photo.jpg.png">')
        script = b'document.getElementById("game").onclick=function(){this.textContent="1";};'
        png = sample_png(True)
        entries = [har_record("index.html", "text/html", html), har_record("game.js", "text/javascript", script),
                   har_record("assets/photo.jpg?v=2", "image/jpeg", jpeg),
                   har_record("assets/PHOTO.PNG", "image/png", png), har_record("assets/Photo.jpg.png", "image/png", png)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture = root / "source" / "capture.har"
            capture.parent.mkdir()
            capture.write_text(json.dumps({"log":{"entries":entries}}), encoding="utf-8")
            output, report = convert([capture], root / "output")
            self.assertEqual(report["status"], "static_candidate")
            renamed = report["redirects"]["/board/assets/photo.jpg"]
            self.assertTrue(renamed.endswith(".png"))
            self.assertNotIn(renamed.casefold(), {"board/assets/photo.png", "board/assets/photo.jpg.png"})
            self.assertFalse((output / "client/board/assets/photo.jpg").exists())
            self.assertEqual((output / "client/board/index.html").read_bytes(), html)
            self.assertEqual((output / "client/board/game.js").read_bytes(), script)
            self.assertEqual((output / "client/board/assets/PHOTO.PNG").read_bytes(), png)
            self.assertEqual((output / "client/board/assets/Photo.jpg.png").read_bytes(), png)
            with preview(output) as base:
                endpoint = urlsplit(base)
                http = HTTPConnection(endpoint.hostname, endpoint.port, timeout=4)
                try:
                    http.request("GET", "/board/assets/photo.jpg?v=2")
                    redirect = http.getresponse()
                    self.assertEqual(redirect.status, 302)
                    self.assertEqual(redirect.getheader("Location"), "/" + renamed)
                    redirect.read()
                    http.request("GET", "/" + renamed)
                    response = http.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.getheader("Content-Type"), "image/png")
                    served = response.read()
                finally:
                    http.close()
            self.assertEqual(served[28], 1)
            image = Image.open(io.BytesIO(served))
            self.assertEqual((image.format, image.size, image.mode), ("PNG", original.size, original.mode))
            self.assertEqual(image.convert("RGBA").tobytes(), original.convert("RGBA").tobytes())
            asset = next(a for a in report["resources"] if a["file"] == renamed)
            self.assertEqual(asset["source_sha256"], hashlib.sha256(jpeg).hexdigest())
            self.assertEqual(asset["output_sha256"], hashlib.sha256(served).hexdigest())
            self.assertEqual(asset["rgba_sha256"], hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest())

    def test_unverified_orientation_and_color(self):
        exif = Image.Exif()
        exif[274] = 6
        for label, options in [("EXIF", {"exif":exif}), ("ICC", {"icc_profile":b"test profile"})]:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, label):
                convert_jpeg(sample_jpeg(**options))
