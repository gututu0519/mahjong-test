"""本机交互式批次与原版入口选择器。"""
from datetime import datetime
import json
from pathlib import Path
import re

from reader import _file_bytes, _unlinked


def _pick(labels, title, instruction, multiple):
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        raise ValueError("本机缺少 Tk 图形选择器。可在命令行指定源目录，用 --add 添加同版补抓，用 --entry 指定入口。") from None
    try:
        window = tk.Tk()
    except tk.TclError:
        raise ValueError("无法打开图形选择器。请在命令行指定源目录，按需使用 --add 或 --entry。") from None
    selected = []
    try:
        window.title(title)
        window.geometry(f"{min(840, window.winfo_screenwidth() - 50)}x{min(450, window.winfo_screenheight() - 80)}")
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        ttk.Label(frame, text=instruction, wraplength=680).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        items = tk.Listbox(frame, selectmode="extended" if multiple else "browse",
                           exportselection=False, activestyle="dotbox")
        items.grid(row=1, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=items.yview)
        vertical.grid(row=1, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=items.xview)
        horizontal.grid(row=2, column=0, sticky="ew")
        items.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        for label in labels:
            items.insert("end", " ".join(label.splitlines()))
        def confirm(event=None):
            indexes = items.curselection()
            if indexes:
                selected.extend(indexes)
                window.quit()
        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="取消", command=window.quit).pack(side="left", padx=5)
        accept = ttk.Button(actions, text="使用所选项", command=confirm, state="disabled")
        accept.pack(side="left")
        items.bind("<<ListboxSelect>>", lambda event: accept.configure(state="normal" if items.curselection() else "disabled"))
        if not multiple:
            items.bind("<Double-Button-1>", confirm)
        window.bind("<Escape>", lambda event: window.quit())
        window.bind("<Return>", confirm)
        window.protocol("WM_DELETE_WINDOW", window.quit)
        items.focus_set()
        window.mainloop()
    finally:
        window.destroy()
    return selected


def select_entries(entries: list[str]) -> str | None:
    """仅传入已脱敏的候选入口，返回用户选中的原字符串。"""
    if len(entries) <= 1:
        return entries[0] if entries else None
    selected = _pick(entries, "选择原版游戏入口", "此抓取中有多个候选页面。请选择要转换的游戏入口。", False)
    return entries[selected[0]] if selected else None


def _index_file(folder):
    manifest = folder / "manifest.json"
    if manifest.is_file():
        return manifest
    return next((p for p in folder.iterdir() if p.suffix.lower() == ".har" and p.is_file()), None)


_SID = re.compile(r"[0-9a-f]{32}")
_REF = re.compile(r"([0-9a-f]{32})\.capture-ref\.json")


def _old_batch(ref):
    match = _REF.fullmatch(ref.name)
    archive = ref.parent.parent
    if not match or archive.name.lower() != "captures":
        raise ValueError("旧批次索引应位于 captures 下的游戏目录中。")
    sid = match[1]
    data = json.loads(_file_bytes(ref, 1024))
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data != {"schema": 1, "sid": sid}:
        raise ValueError("旧批次索引与文件名不匹配。")
    # 目录仅从本索引的固定位置和已核对的批次 ID 推导。
    batch = archive / sid
    _unlinked(batch)
    if not batch.is_dir():
        raise ValueError("索引对应的旧抓取批次目录不存在。")
    return batch


def expand_source(path: Path, *, interactive=True) -> list[Path]:
    """识别总目录、游戏目录、平铺批次与旧批次索引。合并多批须显式选择。"""
    path = Path(path).absolute()
    batches = {}

    def remember(batch, label):
        _unlinked(batch)
        index = _index_file(batch) if batch.is_dir() else None
        if index is None:
            return False
        _unlinked(index)
        # 同一旧批次可能同时从平铺目录和游戏索引被发现，优先显示游戏名。
        if batch not in batches or '/' in label:
            batches[batch] = (index.stat().st_mtime, label, batch)
        return True

    def read_child(child, label, *, allow_group):
        try:
            if _REF.fullmatch(child.name):
                remember(_old_batch(child), label[:-len(".capture-ref.json")])
                return
            _unlinked(child)
            if not child.is_dir() or remember(child, label):
                return
            if allow_group and not _SID.fullmatch(child.name):
                for item in child.iterdir():
                    if _SID.fullmatch(item.name) or _REF.fullmatch(item.name):
                        read_child(item, label + '/' + item.name, allow_group=False)
        except (ValueError, OSError):
            return

    try:
        _unlinked(path)
        if _REF.fullmatch(path.name):
            path = _old_batch(path)
        if not path.is_dir() or _index_file(path):
            return [path]
        for child in path.iterdir():
            read_child(child, child.name, allow_group=True)
    except OSError:
        raise ValueError("无法读取所选抓取路径，请选择可访问的批次目录或 HAR 文件。") from None
    if not batches:
        raise ValueError("此目录未找到带 manifest.json 或 HAR 的已保存批次。请直接选择抓取批次。")
    choices = sorted(batches.values(), key=lambda item: (-item[0], item[1].casefold()))
    if len(batches) == 1:
        return [choices[0][2]]
    if not interactive:
        raise ValueError("目录中包含多个抓取批次，请指定具体批次或索引文件，用 --add 显式合并。")
    labels = [f"{datetime.fromtimestamp(stamp):%Y-%m-%d %H:%M}    {label}" for stamp, label, _ in choices]
    selected = _pick(labels, "选择抓取批次",
                     "选择一个批次。要合并同一游戏、同一版本的补抓，请按住 Ctrl 点选多个批次，或按 Shift 连选。", True)
    return [choices[i][2] for i in selected]
