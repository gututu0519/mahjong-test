"""用原件及产物的摘要识别项目已适配的客户端版本。"""
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


PROFILES = json.loads(Path(__file__).with_name("adapters.json").read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(repo, game):
    source = repo / "games" / game
    spec = PROFILES[game]
    index = json.loads((source / spec["index"]).read_bytes())
    raw, output = spec["source"], spec["output"]
    expected, published = {}, {}
    rows = index[spec["rows"]]
    if not rows:
        raise ValueError("适配清单为空")
    for item in rows:
        location = urlsplit(item[raw["field"]])
        host = raw["host"] or location.hostname
        key = host, "/" + location.path.lstrip("/")
        if not host or key in expected:
            raise ValueError("适配清单存在重复或缺少来源主机")
        expected[key] = item[raw["sha256"]]
        published[item[output["field"]]] = item[output["sha256"]]
    for name in output["derived_rows"]:
        for item in index[name]:
            published[item[output["field"]]] = item[output["sha256"]]
    published.update(spec["bridges"])
    return expected, published


def read_published(root, relative, sha):
    logical = PurePosixPath(relative)
    if logical.is_absolute() or ".." in logical.parts or "\\" in relative or ":" in relative:
        raise ValueError("项目索引包含无效相对路径")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("项目客户端缺少索引文件")
    data = path.read_bytes()
    if digest(data) != sha:
        raise ValueError("项目客户端文件与已登记版本不一致")
    return data


def match_known(rows, repo):
    """输入只读流中必须有同版完整资源，命中游戏名本身仅供识别。"""
    repo = Path(repo)
    grouped = {}
    for row in rows:
        url = urlsplit(row["url"])
        if url.scheme in ("http", "https") and row.get("method") == "GET" and row["status"] == 200:
            grouped.setdefault((url.hostname, url.path), []).append(row)
    paths = {path for _, path in grouped}
    candidates = [game for game, spec in PROFILES.items() if "/" + spec["entry"] in paths]
    if not candidates:
        return None
    if len(candidates) != 1:
        return {"game": "multiple", "verified": False, "status":"choose_batch",
                "candidates": candidates, "detail": "含多个已登记游戏，请分别转换。"}
    game = candidates[0]
    spec = PROFILES[game]
    result = {"game": game, "verified": False, "source_verified": False, "needs_adapter": True,
              "entry": "/" + spec["entry"], "known_gaps": spec["known_gaps"]}
    try:
        expected, published = inventory(repo, game)
        matched = 0
        conflicts, missing = [], []
        for key, sha in expected.items():
            variants = set()
            for row in grouped.get(key, []):
                if row.get("has_body", True):
                    try:
                        variants.add(digest(row["read"]()))
                    except (OSError, ValueError):
                        continue
            if not variants:
                missing.append(key[1].lstrip("/"))
            elif variants == {sha}:
                matched += 1
            else:
                conflicts.append(key[1].lstrip("/"))
        result.update(expected_sources=len(expected), matched_sources=matched, missing_sources=len(missing),
                      conflicting_sources=len(conflicts), missing_paths=missing, conflicting_paths=conflicts,
                      indexed_outputs=len(published), exported_files=0)
        if missing or conflicts:
            result["detail"] = f"登记的 {len(expected)} 项原件中，{matched} 项匹配，{len(missing)} 项缺失或无法校验，{len(conflicts)} 项内容摘要不一致。需要补齐同版原件或复核差异。"
            return result
        result["source_verified"] = True
        root = repo / "games" / game / "frontend"
        for name, sha in published.items():
            read_published(root, name, sha)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result["detail"] = "读取原件或校验项目适配产物失败。错误类型 " + type(exc).__name__
        return result
    if spec["blocking"] or not spec["client_root_env"]:
        result["status"] = "needs_adapter"
        result["detail"] = f"所选抓取与登记的 {matched} 项原件一致。"+ "".join(spec["blocking"] + spec["known_gaps"])
        return result
    result.update(verified=True, needs_adapter=False, detail=f"所选抓取与登记版本的全部 {matched} 个原件一致。导出使用本项目已适配的同版客户端与本地试玩服务。索引以外的资源及玩法仍需实际浏览器验收。")
    return result


def write_launcher(output, repo, match):
    """导出目录由上层事务建立。client 只含已核验的可服务资源。"""
    if not match or not match.get("verified") or match["game"] not in PROFILES:
        raise ValueError("缺少同版原件核验结果")
    output, repo = Path(output), Path(repo).resolve()
    game = match["game"]
    if not PROFILES[game]["client_root_env"] or PROFILES[game]["blocking"]:
        raise ValueError("当前适配器尚未启用")
    source = repo / "games" / game / "frontend"
    _, published = inventory(repo, game)
    dest = output / "client"
    dest.mkdir(exist_ok=False)
    for name, sha in published.items():
        data = read_published(source, name, sha)
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    profile = PROFILES[game]
    index = json.loads((repo / "games" / game / profile["index"]).read_bytes())
    source_spec, output_spec = profile["source"], profile["output"]
    records = []
    for item in index[profile["rows"]]:
        url = urlsplit(item[source_spec["field"]])
        name = item[output_spec["field"]]
        records.append({"source_host": source_spec["host"] or url.hostname,
                        "source_path": "/" + url.path.lstrip("/"), "source_sha256": item[source_spec["sha256"]],
                        "file": name, "output_sha256": published[name], "output_bytes": (dest/name).stat().st_size})
    mapped = {r["file"] for r in records}
    extras = [{"file": name, "output_sha256": sha} for name, sha in published.items() if name not in mapped]
    evidence = {"game": game, "project_index": profile["index"], "resources": records,
                "derived_or_bridge_files": extras}
    (output/"来源索引.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    probe = next((p for p in published if p.endswith(".png")), PROFILES[game]["entry"])
    spec = {"game": game, "repo": str(repo), "env": PROFILES[game]["client_root_env"],
            "probe": "/" + probe, "probe_sha256": published[probe]}
    (output / "project-launch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "launch-original.ps1").write_text(POWERSHELL, encoding="utf-8-sig")
    batch = '@echo off\r\n"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch-original.ps1"\r\nif errorlevel 1 pause\r\n'
    (output / "启动原版游戏.cmd").write_bytes(batch.encode("ascii"))
    match["exported_files"] = len(published)


POWERSHELL = r"""param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'project-launch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$game = [string]$spec.game
$repo = (Resolve-Path -LiteralPath $spec.repo).Path
$registry = Get-Content -LiteralPath (Join-Path $repo 'other/capture/original-client/adapters.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$profile = $registry.PSObject.Properties[$game].Value
if ($game -notmatch '^[a-z0-9-]+$' -or $profile.client_root_env -notmatch '^GTT_[A-Z0-9_]+_CLIENT_ROOT$' -or $profile.blocking.Count -gt 0) {
    throw '当前游戏尚未登记可用的启动适配器。'
}
$client = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'client')).Path
$instance = (Resolve-Path -LiteralPath (Join-Path $repo "games/$game/instance")).Path
$runtime = Join-Path $repo 'other/runtime/server'
$node = (Get-Command node -CommandType Application | Select-Object -First 1).Source
$config = $env:GTT_PG_CONFIG
if (-not $config) {
    $config = Join-Path $repo "other/diagnostics/$game/postgres.json"
}
if (-not $config -or -not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw '请先用 GTT_PG_CONFIG 指定本游戏可用的本地试玩 PostgreSQL 路由配置，再双击启动。'
}
$routing = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
$schema = $game.Replace('-', '_')
$source = @($routing.sources | Where-Object { $_.kind -eq 'local' -and $_.schema -eq $schema })
if ($source.Count -ne 1 -or $routing.driver -ne 'postgres' -or $routing.isolated -ne $true) {
    throw '选择的配置必须是含本游戏唯一 local 路由的隔离试玩 PostgreSQL 配置。'
}
$database = [string]$source[0].path
if (-not [IO.Path]::IsPathRooted($database)) {
    $database = Join-Path (Split-Path (Resolve-Path -LiteralPath $config).Path -Parent) $database
}
$env:GTT_PG_CONFIG = (Resolve-Path -LiteralPath $config).Path
$env:GTT_WORKSPACE_ROOT = $repo
[Environment]::SetEnvironmentVariable($profile.client_root_env, $client, 'Process')
& $node (Join-Path $repo 'other/tooling/build.mjs')
if ($LASTEXITCODE -ne 0) { throw '项目构建失败，请检查 Node.js 和项目构建依赖。' }
$tcp = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$tcp.Start()
try { $port = $tcp.LocalEndpoint.Port } finally { $tcp.Stop() }
$origin = "http://127.0.0.1:$port"
$record = Join-Path $PSScriptRoot ('run-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $record
$arguments = @('dist/cli.js','service','--service-dir',('"'+$instance+'"'),'--database',('"'+$database+'"'),'--port', "$port")
$process = Start-Process -FilePath $node -ArgumentList $arguments -WorkingDirectory $runtime -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $record 'service.log') -RedirectStandardError (Join-Path $record 'service-error.log')
$started = $process.StartTime.ToUniversalTime().Ticks
try {
$processDetails = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $process.Id)
@{chat=$env:CODEX_THREAD_ID;game=$game;repo=$repo;cwd=$runtime;command=$processDetails.CommandLine;pid=$process.Id;created=$process.StartTime.ToString('o');port=$port;client=$client} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $record 'ownership.json') -Encoding UTF8
$ready = $false
$until = (Get-Date).AddSeconds(50)
while ((Get-Date) -lt $until) {
    $process.Refresh()
    if ($process.HasExited) { throw "游戏服务未能启动，查看 $record/service-error.log" }
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        if (@($listeners | Where-Object { $_.OwningProcess -ne $process.Id -or $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) {
            throw '该端口已由其他进程使用，本次取消打开。'
        }
        try { $health = Invoke-RestMethod -Uri "$origin/health" -TimeoutSec 2 -MaximumRedirection 0 } catch { $health = $null }
        if ($health.service_id -eq $game -and $health.status -eq 'ok') { $ready = $true; break }
    }
    Start-Sleep -Milliseconds 300
}
if (-not $ready) { throw "本地游戏服务未就绪，查看 $record/service-error.log" }
$clientProbe = [Net.WebClient]::new()
$hash = [Security.Cryptography.SHA256]::Create()
try {
    $bytes = $clientProbe.DownloadData($origin + $spec.probe)
    $fingerprint = [BitConverter]::ToString($hash.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()
} finally { $clientProbe.Dispose(); $hash.Dispose() }
if ($fingerprint -cne $spec.probe_sha256) { throw '运行中的客户端资源指纹与导出版本不一致。' }
$session = Invoke-RestMethod -Method Post -Uri "$origin/api/v1/games/$game/launch" -ContentType 'application/json' -Body '{"language":"en"}' -MaximumRedirection 0
$url = [uri]::new([uri]$origin, [string]$session.launch_url)
if ($session.game_id -ne $game -or $url.Scheme -ne 'http' -or $url.Host -ne '127.0.0.1' -or $url.Port -ne $port) { throw '本地会话未能取得本游戏入口。' }
@{origin=$origin;entry="$origin/";game=$game;port=$port;client=$client;pid=$process.Id} | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $record 'ready.json') -Encoding UTF8
Write-Host "本次导出的客户端已经启动，固定玩家入口 $origin/ ，游戏 $game，资料在 $record"
if (-not $NoBrowser) { Start-Process -FilePath $url.AbsoluteUri }
} catch {
    $failure = $_
    $actual = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($actual -and $actual.StartTime.ToUniversalTime().Ticks -eq $started -and $actual.Path -eq $node) {
        $process.Kill()
        $null = $process.WaitForExit(3000)
    }
    throw $failure
}
"""
