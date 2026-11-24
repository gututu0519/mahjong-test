"""将用户选择的抓取交给匹配的原版客户端适配器，或恢复可独立提供的静态页面。"""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

from known import match_known, write_launcher
from reader import read_capture
from static_client import export_static
from gui import expand_source, select_entries

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_OUTPUT = REPO / "other" / "diagnostics" / "original-clients"
LABELS = {
    "adapter_ready": "已导出匹配现有游戏服务的原版客户端",
    "static_candidate": "已导出静态客户端，等待浏览器验收",
    "needs_capture": "抓取资料需要补全",
    "needs_adapter": "需要适配该游戏或处理原版资源",
    "choose_entry": "需要选择游戏入口",
    "choose_batch": "需要选择同一游戏的抓取批次",
}


def choose_source():
    title = "选择原始抓取数据文件夹"
    try:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
        try:
            return filedialog.askdirectory(parent=window, title=title, mustexist=True)
        finally:
            window.destroy()
    except Exception as exc:
        if not isinstance(exc, (ImportError, RuntimeError)) and type(exc).__name__ != "TclError":
            raise
        if os.name != "nt":
            raise ValueError("本机缺少图形文件夹选择器，请在命令行指定抓取目录。") from None
        command = (
            "Add-Type -AssemblyName System.Windows.Forms\n"
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
            "$form = New-Object Windows.Forms.FolderBrowserDialog\n"
            "$form.Description = '选择原始抓取数据文件夹'\n"
            "$form.ShowNewFolderButton = $false\n"
            "if ($form.ShowDialog() -eq 'OK') { [Console]::Write($form.SelectedPath) }"
        )
        import base64
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        return subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", encoded],
                              check=True, capture_output=True).stdout.decode("utf-8-sig")


def write_result(output, report):
    status = report["status"]
    next_step = {
        "adapter_ready": "双击“启动原版游戏.cmd”。首次在新电脑运行时，先按项目说明配置 Node.js 和本地试玩数据库。",
        "static_candidate": "双击“预览静态客户端.cmd”。从原版入口实际操作并确认结果。关闭预览控制台即可结束该实例。",
        "needs_capture": "按下方原因补抓同一游戏、同一版本。保留原版入口以及依赖的响应正文，重新选择批次。",
        "needs_adapter": "查看下方具体原因。需要处理版本、图片、协议或规则时，保留原始抓取以便接入。",
        "choose_entry": "重新打开工具选择入口，或在命令行使用 --entry 指定下列候选。",
        "choose_batch": "重新选择其中一款游戏的批次。补抓只能和同一游戏、同一版本的批次一起导入。",
    }[status]
    lines = [report["title"], "", report.get("detail", ""), "", next_step]
    if report.get("entries") and status == "choose_entry":
        lines += ["", "候选入口", *report["entries"]]
    for gap in report.get("blockers", []):
        lines.append(str(gap))
    if report.get("warnings"):
        lines += ["", "采集记录", *report["warnings"]]
    lines += ["", "资源校验、缺口与记录数见同目录的“转换结果.json”。"]
    (output / "转换说明.txt").write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    (output / "转换结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def convert(sources, parent, entry=None, choose_entry=None):
    if not sources:
        raise ValueError("请选择至少一个抓取文件夹。")
    resolved = [s.resolve(strict=True) for s in sources]
    if len(set(resolved)) != len(sources):
        raise ValueError("重复选择了同一份抓取。")
    parent = parent.resolve()
    for source in resolved:
        source_dir = source if source.is_dir() else source.parent if source.name == "manifest.json" else None
        if source_dir is not None and parent.is_relative_to(source_dir):
            raise ValueError("请选择抓取目录以外的输出位置。")
    rows, warnings, counts = [], [], []
    for i, source in enumerate(sources, 1):
        batch, notes = read_capture(source)
        counts.append(len(batch))
        rows.extend(batch)
        warnings.extend(f"第 {i} 份抓取：{note}" for note in notes)
    methods = Counter(row["method"] if row["method"] in
                      {"GET","HEAD","POST","PUT","DELETE","PATCH","OPTIONS"} else "other" for row in rows)
    inventory = {"successful_responses": sum(200 <= r["status"] < 300 for r in rows),
                 "indexed_response_bodies": sum(r["has_body"] for r in rows),
                 "http_methods": dict(methods),
                 "websocket_records": sum(r["url"].lower().startswith(("ws:","wss:")) for r in rows)}
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / ("原版客户端-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:10])
    with tempfile.TemporaryDirectory(prefix=".convert-", dir=parent) as staging:
        output = Path(staging) / "result"
        output.mkdir()
        match = match_known(rows, REPO)
        if match and match["verified"]:
            write_launcher(output, REPO, match)
            report = {**match, "status": "adapter_ready"}
        elif match:
            report = {**match, "status": match.get("status", "needs_capture")}
        else:
            report = export_static(rows, output, entry)
            if report["status"] == "choose_entry" and choose_entry:
                selection = choose_entry(report["entries"])
                if selection:
                    report = export_static(rows, output, selection)
            if report["status"] == "static_candidate":
                shutil.copy2(HERE / "preview.py", output / "preview.py")
                shutil.copy2(HERE / "preview.cmd", output / "预览静态客户端.cmd")
        status = report["status"]
        if status not in LABELS:
            raise ValueError("适配器返回了无法识别的转换状态。")
        report.update(schema=1, title=LABELS[status], input_records=counts, input_inventory=inventory, warnings=warnings)
        write_result(output, report)
        output.rename(final)
    return final, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="抓取目录或含正文的 HAR 文件。省略时弹出文件夹选择器")
    parser.add_argument("--add", action="append", type=Path, default=[], help="合并同一游戏、同一版本的补抓批次，可重复")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出父目录，每次生成一个新目录")
    parser.add_argument("--entry", help="多入口的独立静态游戏，填报告中选择的入口")
    parser.add_argument("--json", action="store_true", help="输出机器可读的结果位置和状态")
    args = parser.parse_args(argv)
    interactive = args.source is None
    try:
        if interactive:
            chosen = choose_source()
            if not chosen:
                return 0
            sources = expand_source(Path(chosen))
            if not sources:
                return 0
        else:
            sources = expand_source(args.source, interactive=False)
        for extra in args.add:
            sources.extend(expand_source(extra, interactive=False))
        destination, report = convert(sources, args.output, args.entry,
                                      select_entries if interactive else None)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"转换未完成。{exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"output": str(destination), "status": report["status"]}, ensure_ascii=False))
    else:
        print(report["title"])
        print(report.get("detail", ""))
        print("结果目录", destination)
        for candidate in report.get("entries", [])[:15]:
            print("候选入口", candidate)
    if interactive and os.name == "nt":
        os.startfile(destination)
    return 0 if report["status"] in ("adapter_ready", "static_candidate") else 2


if __name__ == "__main__":
    raise SystemExit(main())
