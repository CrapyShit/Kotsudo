# Minimal shelf-safe snippet to open Maya commandPort for Python
# Copy into a shelf button (Python) or run in the Script Editor.

import maya.cmds as cmds

PORT = 7002
HOST = "127.0.0.1"

names = [f"{HOST}:{PORT}", f":{PORT}"]

try:
    existing = cmds.commandPort(q=True) or []
    print("[open_port] existing:", existing)
except Exception as e:
    existing = []
    print("[open_port] query failed:", e)

# Attempt graceful close in both forms (ignore errors)
for n in names:
    try:
        cmds.commandPort(name=n, cl=True)
    except Exception:
        pass

opened = False
for n in names:  # explicit host first, then shorthand
    try:
        cmds.commandPort(name=n, sourceType="python")
        print(f"[open_port] opened {n}")
        opened = True
        break
    except Exception as e:
        print(f"[open_port] open failed for {n} -> {e}")

if not opened:
    print(f"[open_port] FAILED to open any of {names}")
else:
    print("[open_port] Ready: send files from VS Code task 'Send current file to Maya'")
