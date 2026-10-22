"""Material slot matching (Unreal side), offline (plain python).

    py tests/offline_materials_test.py
"""
import os
import sys

sys.modules.setdefault("unreal", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rig_builder import materials  # noqa: E402

records = [{"name": "M_Murakami_Body"}, {"name": "M_Murakami_Head"}, {"name": "M_Murakami"}]
assert materials._match(records, "M_Murakami_Body")["name"] == "M_Murakami_Body"          # exact
assert materials._match(records, "m_murakami_head")["name"] == "M_Murakami_Head"          # case
assert materials._match(records, "M_Murakami_Body_001")["name"] == "M_Murakami_Body"      # importer suffix
assert materials._match(records, "M_Murakami_Other")["name"] == "M_Murakami"              # longest prefix
assert materials._match(records, "lambert1") is None
print("OFFLINE MATERIALS OK")
