"""Repair the known formatted obfuscator output without changing source files."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import re
import subprocess

IDENT = r"[A-Za-z_$][\w$]*"


def repair_source(source):
    # This sentinel is inspected by a regex that expects its original single line.
    source = re.sub(
        r"function\s*\(\s*\)\s*\{\s*return (['\"])newState\1;\s*\}",
        "function(){return 'newState';}", source,
    )
    # Only the obfuscator's custom Base64 decoder uses this alphabet and prefix.
    decoder = re.compile(
        rf"(var (?P<fn>{IDENT}) = function\({IDENT}\) \{{\s*"
        rf"var {IDENT} = ['\"]abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789\+/=['\"];"
        rf"\s*var {IDENT} = '';?.{{0,160}}?)(?P<guard>, {IDENT} = {IDENT} \+ (?P=fn);)",
        re.DOTALL,
    )
    def fix_decoder(match):
        guard = match['guard'][:-1]
        return match[1] + guard + ".toString().replace(/[\\r\\n]/g, '');"
    source = decoder.sub(fix_decoder, source)

    # Limit regex simplification to self-inspecting, once-only callbacks.
    callback = re.compile(
        rf"(?P<indent>^[ \t]*)(?P<head>(?:var |, )(?P<name>{IDENT}) = "
        rf"{IDENT}\(this, function\(\) \{{)(?P<body>.*?)(?P<close>^[ \t]*\}}\);)",
        re.MULTILINE | re.DOTALL,
    )
    def fix_callback(match):
        body = match['body']
        name = re.escape(match['name'])
        if not re.search(rf"return {name}\[.*\]\(\)\[.*\]\({name}\)\[", body):
            return match[0]
        # Obfuscated concatenations of (((.+)+)+)+$ are the known failing guard.
        body = re.sub(
            rf"(^[ \t]*{IDENT}\[[^\n]+?\] = )[^\n;]+ \+ ['\"]\+\$['\"];",
            lambda m: m[1] + "'.+$';", body, flags=re.MULTILINE,
        )
        return match['indent'] + match['head'] + body + match['close']
    return callback.sub(fix_callback, source)


@lru_cache(maxsize=64)
def prepare_module(content):
    repaired = repair_source(content.decode('utf-8-sig')).encode('utf-8')
    validator = Path(__file__).with_name('validate_client_module.cjs')
    try:
        result = subprocess.run(
            ['node', '--max-old-space-size=64', str(validator)],
            input=repaired, capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f'Module validation could not complete: {error}') from error
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace')[:500]
        raise ValueError(f'Module initialization rejected: {detail}')
    return repaired, hashlib.sha256(repaired).hexdigest()
