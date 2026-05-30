# Kotsudo — Roadmap (June → September 2026)

> **Goal**: Complete the semantic rigging pipeline (Maya → UE5.6) and deliver a finished research thesis by end of September.

---

## Current State (End of May 2026)

### ✅ Done
- Maya rig authoring workflow: controllers, FK/IK, Spline IK, blendshapes, space-switching, naming conventions (Issue #1, #8)
- Pipeline design documented: FBX + JSON sidecar strategy (Issue #16)
- Metadata schema defined for controllers (Issue #10)
- Python-based Maya export (FBX exporter + JSON exporter) (Issue #9)
- UE5 Python builder prototype: reads JSON, creates Control Rig controls (Issue #9, #15)
- Rig Manifest system: `RIG_MANIFEST` joint carrying full rig JSON in FBX (Issue #22)
- Manifest-first / bone-attribute-fallback detection logic (Issue #22)
- Rigging feature comparison table: Maya vs UE5.6 (Issue #11)
- Maya ↔ UE node equivalence map (Issue #4)
- Industry networking & interviews (TIGS, Autodesk × CG World, LinkedIn outreach) (Issues #19, #20)
- Studio outreach list compiled (Issue #13)

### 🔧 In Progress
- Semantic Rigging System builder (`Semantic_Rigging_System/rig_builder/`)
  - `builder.py`, `context.py`, `graph_utils.py`, `metadata_reader.py`
  - Modules: `ik_module.py`, `rig_module.py`

### ⚠️ Known Blockers / Limitations
- UE metadata is static at import-time; cannot refresh dynamically (Issue #21)
- Forward-solve node order must be explicitly controlled to avoid module interference (Issues #21, #22)
- Spline IK offsets on non-straight chains in UE (Issue #7)
- Stretch/squash deferred (Issue #12)

---

## Phase 1 — Pipeline Completion (June 1 – June 29)

### Week 1 (Jun 1–8): Spline IK Module
- [ ] Implement `spline_ik_module.py` in `rig_builder/modules/`
- [ ] Handle curve generation, twist, and control-point mapping
- [ ] Test with a spine chain (5+ joints)

### Week 2 (Jun 9–15): FK Module + IK/FK Switch
- [ ] Implement `fk_module.py` in `rig_builder/modules/`
- [ ] Implement IK/FK blend logic (attribute-driven switching)
- [ ] Validate on arm/leg chains

### Week 3 (Jun 16–22): Space Switching & Forward-Solve Order
- [ ] Implement `space_switch_module.py`
- [ ] Define and enforce explicit execution order in `builder.py` (topological sort from manifest dependencies)
- [ ] Test multi-module rigs (spine + arms + legs) for ordering correctness

### Week 4 (Jun 23–29): Manifest Robustness & Maya Exporter Polish
- [ ] Finalize Maya-side `rig_manifest_export.py` covering all module types
- [ ] Add validation step: schema check before export
- [ ] End-to-end test: fresh Maya scene → FBX+manifest → UE import → auto-build rig

---

## Phase 2 — Integration & Validation (July 1 – July 27)

### Week 5 (Jun 30–Jul 6): Full Character Test
- [ ] Apply pipeline to a complete biped character (body + face basics)
- [ ] Document failures, fix edge cases
- [ ] Stretch/squash reintroduction if feasible (Issue #12)

### Week 6 (Jul 7–13): Animation Round-Trip
- [ ] Export Maya animation → import into UE Control Rig
- [ ] Test animation retake workflow: modify keys on UE-side controls
- [ ] Measure visual parity and iteration time

### Week 7 (Jul 14–20): Polish & UX
- [ ] Control shapes/colors from manifest
- [ ] Naming template system from DataAsset recipes
- [ ] One-click "Rebuild Rig" editor utility in UE

### Week 8 (Jul 21–27): Evaluation & Metrics
- [ ] Round-trip timing benchmarks (manual vs automated)
- [ ] Document failure modes and their workarounds
- [ ] Collect final qualitative feedback (if possible, from contacted studios)

---

## Phase 3 — Thesis Writing (August 1 – September 28)

### August: Drafting

| Week | Focus |
|------|-------|
| Aug 1–10 | Outline + Introduction + Related Work |
| Aug 11–17 | Methodology chapter (pipeline design, manifest system, module architecture) |
| Aug 18–24 | Implementation chapter (code walkthrough, key decisions, UE limitations) |
| Aug 25–31 | Results chapter (benchmarks, comparison tables, screenshots/videos) |

### September: Revision & Delivery

| Week | Focus |
|------|-------|
| Sep 1–7 | Discussion chapter (trade-offs, limitations, future work) |
| Sep 8–14 | Conclusion + Abstract + References |
| Sep 15–21 | Full revision pass; advisor feedback incorporation |
| Sep 22–28 | Final formatting, submission preparation, repository cleanup |

---

## Stretch Goals (if time permits)

- [ ] Facial rig module (blendshape-driven controls via morph targets)
- [ ] Quaternion-based IK/FK matching (upgraded from simple switch)
- [ ] DataAsset-based recipe system fully in UE (C++ or Blueprint)
- [ ] Open-source release preparation (documentation, examples, licensing cleanup)

---

## File References

| Area | Key Files |
|------|-----------|
| Builder core | `Semantic_Rigging_System/rig_builder/builder.py` |
| Manifest reader | `Semantic_Rigging_System/rig_builder/metadata_reader.py` |
| IK module | `Semantic_Rigging_System/rig_builder/modules/ik_module.py` |
| Graph utilities | `Semantic_Rigging_System/rig_builder/graph_utils.py` |
| Maya stubs | `maya-stubs/` |
| Old/archived scripts | `old_scripts/`, `archive/` |

---

*Last updated: 2026-05-30*
