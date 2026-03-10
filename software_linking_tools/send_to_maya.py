#!/usr/bin/env python3
"""
Send a Python file to Autodesk Maya via commandPort for execution.

Prereqs in Maya (run once per session):
- Execute `maya_link_startup.py` in Maya to open commandPort :7002 and start debugpy.

Usage:
  python send_to_maya.py <path-to-script.py> [--host 127.0.0.1] [--port 7002]

Notes:
- This sender does NOT stream the whole file; it sends a small one-liner that tells Maya to run the file via runpy.run_path().
- Any print/traceback happens inside Maya's Script Editor output.
- Exit codes: 0=OK, 2=bad input, 3=cannot connect, 4=send error.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from typing import Tuple

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7002


def build_payload(target_path: str) -> bytes:
    # Use repr() to safely quote Windows backslashes; Maya executes this as Python code.
    p = repr(os.path.abspath(target_path))
    code = (
        "import runpy, sys; "
        f"sys.__dict__.setdefault('__file__', {p}); "
        f"runpy.run_path({p}, run_name='__main__')\n"
    )
    return code.encode("utf-8")


def resolve_target(path_arg: str) -> str:
    p = os.path.abspath(path_arg)
    if not os.path.isfile(p):
        raise FileNotFoundError(p)
    return p


def send_to_maya(host: str, port: int, payload: bytes, timeout: float = 3.0) -> Tuple[bool, str]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
    except OSError as exc:
        return False, f"Could not connect to Maya commandPort at {host}:{port} — {exc}"

    try:
        s.sendall(payload)
        # Maya's commandPort executes on receipt; no explicit terminator beyond newline.
        return True, "Sent successfully"
    except OSError as exc:
        return False, f"Failed to send to Maya: {exc}"
    finally:
        try:
            s.shutdown(socket.SHUT_WR)
        except Exception:
            pass
        s.close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Send a Python file to Maya's commandPort for execution")
    ap.add_argument("script", help="Path to the Python script to run inside Maya")
    ap.add_argument("--host", default=DEFAULT_HOST, help="Maya host (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="Maya commandPort (default: 7002)")
    ap.add_argument("--timeout", type=float, default=3.0, help="Socket timeout seconds (default: 3.0)")

    args = ap.parse_args(argv)

    try:
        target = resolve_target(args.script)
    except FileNotFoundError:
        sys.stderr.write(f"[send_to_maya] File not found: {args.script}\n")
        return 2

    payload = build_payload(target)
    ok, msg = send_to_maya(args.host, args.port, payload, timeout=args.timeout)
    if not ok:
        sys.stderr.write(f"[send_to_maya] {msg}\n")
        return 3 if "connect" in msg.lower() else 4

    sys.stdout.write(f"[send_to_maya] Sent {target} to Maya at {args.host}:{args.port}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
