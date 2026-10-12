"""The pinned Blender Lab MCP server still installs, starts and lists its tools.

Runs the exact command from live-session/mcp.json (uvx, a full commit pin and
--exclude-newer, so dependency resolution is reproducible) and speaks MCP over
stdio: initialize, notifications/initialized, tools/list. No Blender is
needed; the tools only report that they cannot reach the add-on when called,
and listing them does not call them (#484).

    python tests/check_mcp_server.py            # needs uv on PATH and network
    python tests/check_mcp_server.py --timeout 600

Exit codes: 0 the server answered tools/list with at least one tool, 1 it did
not (install, start or protocol failure), 2 usage.
"""
from __future__ import annotations

import argparse
import json
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "live-session" / "mcp.json"


def _reader(stream, out: queue.Queue):
    for line in iter(stream.readline, b""):
        out.put(line)
    out.put(None)


def handshake(command: list[str], timeout: float) -> list[str]:
    """Tool names from tools/list; raises RuntimeError on any failure."""
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    lines: queue.Queue = queue.Queue()
    threading.Thread(target=_reader, args=(proc.stdout, lines), daemon=True).start()
    err: list[bytes] = []
    threading.Thread(target=lambda: err.extend(iter(proc.stderr.readline, b"")),
                     daemon=True).start()

    def send(msg: dict):
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    def reply(req_id: int) -> dict:
        while True:
            try:
                line = lines.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError(f"no reply to request {req_id} within {timeout:.0f}s")
            if line is None:
                tail = b"".join(err[-20:]).decode("utf-8", "replace")
                raise RuntimeError(f"server exited (code {proc.poll()}) before replying:\n{tail}")
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # not a JSON-RPC line
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise RuntimeError(f"request {req_id} failed: {msg['error']}")
                return msg["result"]

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "bdt-check-mcp-server", "version": "1"}}})
        info = reply(1).get("serverInfo", {})
        print(f"initialize: {info.get('name')} {info.get('version')}")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        return [t["name"] for t in reply(2).get("tools", [])]
    finally:
        proc.kill()
        proc.wait()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--timeout", type=float, default=300.0,
                   help="seconds to wait for each reply (the first run builds the server)")
    p.add_argument("--config", type=Path, default=CONFIG,
                   help="mcp.json to check (default: live-session/mcp.json)")
    a = p.parse_args(argv)
    servers = json.loads(a.config.read_text(encoding="utf-8"))["mcpServers"]
    failed = False
    for name, server in servers.items():
        exe = shutil.which(server["command"])
        if exe is None:
            print(f"ERROR: {server['command']!r} is not on PATH", file=sys.stderr)
            return 1
        try:
            tools = handshake([exe, *server["args"]], a.timeout)
        except RuntimeError as exc:
            print(f"ERROR: server {name!r}: {exc}", file=sys.stderr)
            failed = True
            continue
        if not tools:
            print(f"ERROR: server {name!r} listed no tools", file=sys.stderr)
            failed = True
            continue
        print(f"server {name!r}: {len(tools)} tools ({', '.join(sorted(tools)[:5])}, ...)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
