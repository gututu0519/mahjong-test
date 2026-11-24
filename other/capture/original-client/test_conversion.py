"""在临时目录中验证真实转换入口、可交互的静态预览及失败结果。"""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
import zlib

from convert import convert
from gui import expand_source

TOOL = Path(__file__).resolve().parent
ORIGIN = "https://capture-fixture.invalid/board/"
HTML = b"""<!doctype html><title>Fixture</title><link rel="stylesheet" href="main.css">
<link rel="icon" href="saved.png"><button id="game">0</button><script src="main.js"></script>"""
SCRIPT = b"""var button=document.getElementById("game");
button.onclick=function(){button.textContent=String(Number(button.textContent)+1);};"""
CSS = b"button { background-image: url(plain.png); }"
PIXELS = (b"\xff\x00\x00\xff", b"\x00\xff\x00\x80", b"\x00\x00\xff\x00", b"\x21\x43\x65\x90")
PLAIN_SCAN = b"\0" + PIXELS[0] + PIXELS[1] + b"\0" + PIXELS[2] + PIXELS[3]
ADAM7_SCAN = b"\0" + PIXELS[0] + b"\0" + PIXELS[1] + b"\0" + PIXELS[2] + PIXELS[3]


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def sample_png(interlaced):
    # 两行两列分别编码为普通扫描线或三个非空的 Adam7 遍次。
    header = struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, int(interlaced))
    scan = ADAM7_SCAN if interlaced else PLAIN_SCAN
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(scan)) + chunk(b"IEND", b"")


def har_record(name, mime, body):
    content = {"mimeType": mime}
    if body is not None:
        content.update(size=len(body), encoding="base64", text=base64.b64encode(body).decode("ascii"))
    return {"request": {"method": "GET", "url": ORIGIN + name}, "response": {"status": 200, "content": content}}


def records():
    return [
        har_record("index.html", "text/html", HTML),
        har_record("main.js", "application/javascript", SCRIPT),
        har_record("main.css", "text/css", CSS),
        har_record("plain.png", "image/png", sample_png(False)),
        har_record("saved.png", "image/png", sample_png(True)),
    ]


@contextmanager
def preview(output):
    # 使用当前导出自己的启动脚本和随机回环端口，结束时仅回收本次 Popen 持有的子进程。
    # Windows venv 的 python.exe 会转发给另一 PID。预览仅用标准库，直接持有宿主解释器句柄。
    interpreter = Path(sys.base_prefix) / "python.exe" if os.name == "nt" else Path(sys.executable)
    command = [str(interpreter), str(output / "preview.py"), "--no-browser"]
    with subprocess.Popen(command, cwd=output, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL) as process:
        owner = output / f"预览进程-{process.pid}.json"
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError("临时预览提前退出")
                try:
                    record = json.loads(owner.read_bytes())
                except (FileNotFoundError, json.JSONDecodeError):
                    time.sleep(0.03)
                    continue
                address = urlsplit(record["url"])
                if (record["pid"] != process.pid or Path(record["cwd"]) != output or
                        Path(record["launcher"]) != output / "preview.py" or address.scheme != "http" or
                        address.hostname != "127.0.0.1" or address.port != record["port"]):
                    raise AssertionError("临时预览进程归属不匹配")
                yield record["url"]
                return
            raise AssertionError("临时预览未就绪")
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


class TestConversion(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        folder = Path(root.name)
        self.source = folder / "input" / "capture.har"
        self.source.parent.mkdir()
        self.output = folder / "result"

    def write(self, entries):
        self.source.write_text(json.dumps({"log": {"version": "1.2", "entries": entries}}), encoding="utf-8")

    def test_game_groups_and_legacy_references(self):
        archive = self.output.parent / 'captures'
        group = archive / 'PG-123-游戏甲'
        old = archive / ('a' * 32)
        new = group / ('b' * 32)
        for batch in [old, new]:
            batch.mkdir(parents=True)
            (batch / 'manifest.json').write_text('{}')
        ref = group / (old.name + '.capture-ref.json')
        ref.write_text(json.dumps({'schema': 1, 'sid': old.name}))
        self.assertEqual(expand_source(ref), [old])
        pick_all = lambda labels, *_: list(range(len(labels)))
        with patch('gui._pick', side_effect=pick_all) as picker:
            self.assertCountEqual(expand_source(group), [old, new])
            self.assertCountEqual(expand_source(archive), [old, new])
            self.assertTrue(all(group.name in label for label in picker.call_args.args[0]))
        with self.assertRaisesRegex(ValueError, '多个抓取批次'):
            expand_source(group, interactive=False)
        ref.write_text(json.dumps({'schema': 1, 'sid': old.name, 'path': '../elsewhere'}))
        self.assertEqual(expand_source(group, interactive=False), [new])
        with self.assertRaises(ValueError):
            expand_source(ref)

    def test_cli_accepts_group_with_single_legacy_batch(self):
        archive = self.output.parent / 'captures'
        group = archive / 'PP-123-游戏乙'
        group.mkdir(parents=True)
        old = archive / ('c' * 32)
        old.mkdir()
        self.write(records())
        (old / 'batch.har').write_bytes(self.source.read_bytes())
        (group / (old.name + '.capture-ref.json')).write_text(json.dumps({'schema': 1, 'sid': old.name}))
        result = subprocess.run([sys.executable, str(TOOL / 'convert.py'), str(group), '--output',
                                 str(self.output), '--json'], capture_output=True,
                                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'static_candidate')

    def test_script_creates_game_canvas(self):
        home = har_record("index.html", "text/html", b'<html><body><script src="main.js"></script></body></html>')
        script = har_record("main.js", "application/javascript",
                            b'var c=document.createElement("canvas");document.body.appendChild(c);c.getContext("2d");')
        unrelated = {"request": {"method": "GET", "url": "wss://other-tab.invalid/stream"},
                     "response": {"status": 101}, "_resourceType": "websocket"}
        self.write([home, script, unrelated])
        output, result = convert([self.source], self.output)
        self.assertEqual(result["status"], "static_candidate")
        self.assertEqual(len(list((output/"client").rglob("*.js"))), 1)
        unrelated["request"]["url"] = "wss://capture-fixture.invalid/stream"
        self.write([home, script, unrelated])
        _, result = convert([self.source], self.output)
        self.assertEqual(result["status"], "needs_adapter")

    def test_cli_and_http(self):
        self.write(records())
        original = self.source.read_bytes()
        result = subprocess.run(
            [sys.executable, str(TOOL / "convert.py"), str(self.source), "--output", str(self.output), "--json"],
            check=True, capture_output=True, text=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        )
        reply = json.loads(result.stdout)
        output = Path(reply["output"])
        self.assertEqual(reply["status"], "static_candidate")
        report = json.loads((output / "转换结果.json").read_bytes())
        self.assertEqual(report["resource_count"], 5)
        self.assertEqual(self.source.read_bytes(), original)
        files = {item["file"]: item for item in report["resources"]}
        with preview(output) as url:
            http = build_opener(ProxyHandler({}))
            for name, expected in [("index.html", HTML), ("main.js", SCRIPT), ("main.css", CSS),
                                   ("saved.png", sample_png(True)), ("plain.png", None)]:
                with self.subTest(name=name), http.open(url.rsplit("/", 1)[0] + "/" + name, timeout=4) as res:
                    self.assertEqual(res.status, 200)
                    served = res.read()
                    item = files["board/" + name]
                    self.assertEqual(len(served), item["output_bytes"])
                    self.assertEqual(hashlib.sha256(served).hexdigest(), item["output_sha256"])
                    if expected is not None:
                        self.assertEqual(served, expected)
                    else:
                        self.assertEqual(item["source_sha256"], hashlib.sha256(sample_png(False)).hexdigest())
                        self.assertNotEqual(served, sample_png(False))
                        self.assertEqual(served[28], 1)
                        # 此用例的 PNG 只含 IHDR、IDAT、IEND，逐通道验证四个 RGBA 像素。
                        self.assertEqual(served[37:41], b"IDAT")
                        size = struct.unpack_from(">I", served, 33)[0]
                        self.assertEqual(zlib.decompress(served[41:41+size]), ADAM7_SCAN)

    def test_incomplete_conflicting_and_no_entry(self):
        for reason, entries, status in [
            ("缺少脚本正文", [records()[0], har_record("main.js", "application/javascript", None), *records()[2:]], "needs_capture"),
            ("冲突版本", [*records(), har_record("main.js", "application/javascript", b"void 0;")], "needs_adapter"),
            ("缺入口", records()[1:], "needs_capture"),
        ]:
            with self.subTest(reason=reason):
                self.write(entries)
                original = self.source.read_bytes()
                output, report = convert([self.source], self.output)
                self.assertEqual(report["status"], status)
                self.assertFalse((output / "client").exists())
                self.assertFalse((output / "preview.py").exists())
                self.assertEqual(self.source.read_bytes(), original)

    def test_browser_interaction(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("未安装 Playwright")
        with sync_playwright() as pw:
            if not Path(pw.chromium.executable_path).is_file():
                self.skipTest("未安装 Playwright Chromium")
            self.write(records())
            output, report = convert([self.source], self.output)
            self.assertEqual(report["status"], "static_candidate")
            with preview(output) as url, pw.chromium.launch() as browser:
                context = browser.new_context(service_workers="block")
                page = context.new_page()
                errors, failed, external = [], [], []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.on("requestfailed", lambda req: failed.append(urlsplit(req.url).path))
                page.on("response", lambda res: failed.append(res.status) if res.status >= 400 else None)
                def local_only(route):
                    if urlsplit(route.request.url).netloc == urlsplit(url).netloc:
                        route.continue_()
                    else:
                        external.append(urlsplit(route.request.url).hostname)
                        route.abort()
                context.route("**/*", local_only)
                page.goto(url, wait_until="networkidle")
                button = page.get_by_role("button", name="0")
                button.click()
                self.assertEqual(page.get_by_role("button", name="1").text_content(), "1")
                self.assertEqual([errors, failed, external], [[], [], []])


if __name__ == "__main__":
    unittest.main(verbosity=2)
