"""
One-click Maya link starter for VS Code + debugpy + commandPort.

Usage:
- Put this script's contents into a custom Maya shelf button (Python) or run it in the Script Editor.
- It will:
  1) Ensure Autodesk Maya's Python has debugpy installed (using your mayapy path if needed).
  2) Start debugpy listening on localhost:5678.
  3) Open the Maya commandPort on :7002 for receiving code from VS Code via send_to_maya.py.

After running this once per session:
- In VS Code, use the included "Attach to Maya (debugpy 5678)" config to attach the debugger.
- Then send files with `send_to_maya.py <yourfile.py>` and breakpoints will hit.
"""

from __future__ import annotations

import os
import sys
import subprocess
import traceback

import maya.cmds as cmds

# --- Configuration ---
HOST = "127.0.0.1"          # debug host
DEBUGPY_PORT = 5678          # debugpy port to listen on
COMMANDPORT = 7002           # Maya commandPort for Python
MAYAPY_PATH = r"C:\\Program Files\\Autodesk\\Maya2026\\bin\\mayapy.exe"  # Provided by user


def _print(msg: str) -> None:
    try:
        sys.stdout.write(str(msg) + "\n")
    except Exception:
        print(msg)  # Fallback


def ensure_debugpy_installed() -> bool:
    """Try to import debugpy; if missing, attempt to install via mayapy --user.

    Returns True if debugpy can be imported after this call, False otherwise.
    """
    try:
        import debugpy  # type: ignore
        return True
    except Exception:
        pass

    if not os.path.exists(MAYAPY_PATH):
        _print(
            f"[maya_link] debugpy missing and mayapy not found at: {MAYAPY_PATH}\n"
            "Please edit MAYAPY_PATH in maya_link_startup.py or install debugpy manually:\n"
            "  <Maya>/bin/mayapy.exe -m pip install --user debugpy\n"
        )
        return False

    _print("[maya_link] Installing debugpy via mayapy -- this may take a moment...")
    try:
        # Try to ensure pip exists, then install debugpy to the user site for this Maya Python.
        subprocess.run([MAYAPY_PATH, "-m", "ensurepip", "--upgrade"], check=False)
        proc = subprocess.run(
            [MAYAPY_PATH, "-m", "pip", "install", "--user", "--upgrade", "debugpy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        _print(proc.stdout)
    except Exception as exc:
        _print(f"[maya_link] Failed to run mayapy to install debugpy: {exc}")
        _print(traceback.format_exc())
        return False

    # Try import again inside Maya's Python
    try:
        import debugpy  # type: ignore
        return True
    except Exception as exc:
        _print(
            "[maya_link] debugpy still not importable in Maya after installation.\n"
            "Check your PYTHONPATH/site-packages and consider restarting Maya.\n"
            f"Import error: {exc}\n"
        )
        return False


def start_debugpy_listener(host: str = HOST, port: int = DEBUGPY_PORT) -> None:
    try:
        import debugpy  # type: ignore
        try:
            debugpy.listen((host, port))
            _print(f"[maya_link] debugpy listening on {host}:{port} — attach from VS Code.")
        except OSError as listen_err:
            # If already listening or port in use, show a friendly message.
            _print(f"[maya_link] debugpy listen error: {listen_err}. It may already be listening.")
    except Exception as exc:
        _print(f"[maya_link] Could not import debugpy after installation attempt: {exc}")


def open_command_port(port: int = COMMANDPORT, host: str = "127.0.0.1") -> None:
    """Open Maya commandPort for Python with a couple of fallbacks and diagnostics.

    Tries explicit host form first (e.g. '127.0.0.1:7002'), then shorthand (':7002').
    If already open, returns without error.
    """
    try:
        names = [f"{host}:{port}", f":{port}"]

        try:
            existing = cmds.commandPort(q=True) or []
        except Exception as qexc:
            existing = []
            _print(f"[maya_link] commandPort query failed: {qexc}")

        if any(n in existing for n in names):
            _print(f"[maya_link] commandPort already open (existing={existing}).")
            return

        # Try closing any stale instance silently
        for n in names:
            try:
                cmds.commandPort(name=n, cl=True)
            except Exception:
                pass

        last_exc: Exception | None = None
        for n in names:  # explicit host, then shorthand
            try:
                cmds.commandPort(name=n, sourceType="python")
                _print(f"[maya_link] commandPort opened on {n} (sourceType=python).")
                return
            except Exception as exc:
                last_exc = exc
                _print(f"[maya_link] Attempt to open '{n}' failed: {exc}")

        if last_exc is not None:
            _print(f"[maya_link] Failed to open commandPort (tried {names}) — {last_exc}")
    except Exception as exc:
        _print(f"[maya_link] Unexpected failure opening commandPort :{port} — {exc}")


# --- Entry point ---
if __name__ == "__main__" or True:
    ok = ensure_debugpy_installed()
    if ok:
        start_debugpy_listener()
    open_command_port()
    _print("[maya_link] Ready: Attach from VS Code and send files with send_to_maya.py")
