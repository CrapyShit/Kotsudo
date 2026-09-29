"""Shelf entry point for the Kotsudo Maya tools -- always runs the latest code.

Maya keeps imported Python modules for the whole session, so pressing a shelf
button that only does ``import rig_tagger_tool`` keeps running the code that
was loaded when Maya started, even after the files changed. This launcher
reloads every Kotsudo module (dependencies first) before opening the tool.

Shelf button (Python):

    import sys, importlib
    sys.path.insert(0, r"E:\\Kotsudo\\Semantic_Rigging_System\\tools\\maya")
    importlib.invalidate_caches()   # see files added since Maya started
    import kotsudo_launcher; importlib.reload(kotsudo_launcher); kotsudo_launcher.launch()
"""

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

# Dependencies before the modules that import them.
MODULES = ("export_rig_manifest", "export_test_poses", "rig_tagger_tool")


def reload_all():
    """Reload the Kotsudo modules; returns the freshly loaded tagger module."""
    for path in (HERE, REPO):
        if path not in sys.path:
            sys.path.insert(0, path)
    importlib.invalidate_caches()   # modules added since Maya started
    # The shared validator lives in the Unreal-side package; drop it so the
    # exporter imports the current version.
    for name in [m for m in sys.modules if m == "rig_builder" or m.startswith("rig_builder.")]:
        del sys.modules[name]
    loaded = {}
    for name in MODULES:
        module = sys.modules.get(name)
        loaded[name] = importlib.reload(module) if module else importlib.import_module(name)
    print("[Kotsudo] Reloaded: {} (from {})".format(", ".join(MODULES), HERE))
    return loaded["rig_tagger_tool"]


def launch():
    """Reload everything, then open the Rig Tagger."""
    reload_all().show_rig_tagger_tool()
