#!/usr/bin/env bash
# =============================================================
# create_roadmap_issues.sh
# Creates all Kotsudo roadmap issues in CrapyShit/Kotsudo.
# Requires the GitHub CLI (gh) to be authenticated:
#   gh auth login
# Then run:
#   bash software_linking_tools/create_roadmap_issues.sh
# =============================================================

set -e
REPO="CrapyShit/Kotsudo"

echo "Creating Phase 1 issues (Pipeline Completion — June 2026)..."

gh issue create --repo "$REPO" \
  --title "[Phase 1 · W1] Spline IK Module" \
  --body "## Week 1 — Jun 1–8

Implement Spline IK support in the semantic rig builder.

### Tasks
- [ ] Create \`Semantic_Rigging_System/rig_builder/modules/spline_ik_module.py\`
- [ ] Handle curve generation, twist, and control-point mapping
- [ ] Test with a spine chain (5+ joints)
- [ ] Register module type in \`builder.py\` dispatch table

### References
- Issue #22 (Rig Manifest system)
- Issue #7 (UE Spline IK offset on non-straight chains)
- \`Semantic_Rigging_System/rig_builder/modules/ik_module.py\` (reference)"

echo "✅ W1 Spline IK Module created"

gh issue create --repo "$REPO" \
  --title "[Phase 1 · W2] FK Module + IK/FK Switch" \
  --body "## Week 2 — Jun 9–15

Implement FK module and IK/FK blending.

### Tasks
- [ ] Create \`Semantic_Rigging_System/rig_builder/modules/fk_module.py\`
- [ ] Implement IK/FK blend logic (attribute-driven switching)
- [ ] Validate on arm/leg chains
- [ ] Keep switch simple (linear blend) — quaternion upgrade deferred

### References
- Issue #1 (feature checklist)
- Issue #8 (01/12/2025 IK/FK baseline)
- Issue #14 (Base Python Snippet)"

echo "✅ W2 FK Module + IK/FK Switch created"

gh issue create --repo "$REPO" \
  --title "[Phase 1 · W3] Space Switching & Forward-Solve Order" \
  --body "## Week 3 — Jun 16–22

Implement space switching and fix forward-solve execution order.

### Tasks
- [ ] Create \`Semantic_Rigging_System/rig_builder/modules/space_switch_module.py\`
- [ ] Define and enforce explicit execution order in \`builder.py\` (topological sort from manifest dependencies)
- [ ] Test multi-module rigs (spine + arms + legs) for ordering correctness
- [ ] Document ordering rules in code comments

### Blockers to resolve
- Module interference due to uncontrolled solve order (Issues #21, #22)

### References
- \`Semantic_Rigging_System/rig_builder/graph_utils.py\` (extend for topo-sort)"

echo "✅ W3 Space Switching & Forward-Solve Order created"

gh issue create --repo "$REPO" \
  --title "[Phase 1 · W4] Manifest Robustness & Maya Exporter Polish" \
  --body "## Week 4 — Jun 23–29

Finalize and harden the Maya-side manifest export.

### Tasks
- [ ] Finalize \`rig_manifest_export.py\` covering all module types (FK, IK, Spline IK, Space Switch)
- [ ] Add validation step: JSON schema check before export
- [ ] End-to-end test: fresh Maya scene → FBX+manifest → UE import → auto-build rig
- [ ] Fix any issues found during the end-to-end test

### References
- Issue #22 (Rig Manifest system)
- Issue #16 (Pipeline design)"

echo "✅ W4 Manifest Robustness & Maya Exporter Polish created"

echo ""
echo "Creating Phase 2 issues (Integration & Validation — July 2026)..."

gh issue create --repo "$REPO" \
  --title "[Phase 2 · W5] Full Character Test" \
  --body "## Week 5 — Jun 30–Jul 6

Apply the pipeline to a complete biped character.

### Tasks
- [ ] Apply pipeline to a full biped (body + face basics)
- [ ] Document failures and fix edge cases
- [ ] Reintroduce stretch/squash if feasible (Issue #12)

### References
- Issue #12 (Stretch/squash deferred)"

echo "✅ W5 Full Character Test created"

gh issue create --repo "$REPO" \
  --title "[Phase 2 · W6] Animation Round-Trip" \
  --body "## Week 6 — Jul 7–13

Validate the full animation export/import workflow.

### Tasks
- [ ] Export Maya animation → import into UE Control Rig
- [ ] Test animation retake workflow: modify keys on UE-side controls
- [ ] Measure visual parity and iteration time
- [ ] Document findings (failure modes, accuracy, time saved)

### Context
This is the core research question: can an animator make retakes on UE-side without going back to Maya?

### References
- Issue #20 (Project goal: animation retakes on UE5 directly)
- README.md Key questions section"

echo "✅ W6 Animation Round-Trip created"

gh issue create --repo "$REPO" \
  --title "[Phase 2 · W7] Control Rig Polish & UX" \
  --body "## Week 7 — Jul 14–20

Polish the generated rig for animator usability.

### Tasks
- [ ] Control shapes/colors read from manifest
- [ ] Naming template system from DataAsset recipes
- [ ] One-click 'Rebuild Rig' editor utility in UE (Python EditorUtilityWidget or toolbar button)

### References
- Issue #16 (DataAsset recipes)
- Issue #10 (Metadata schema — shape/color fields)"

echo "✅ W7 Control Rig Polish & UX created"

gh issue create --repo "$REPO" \
  --title "[Phase 2 · W8] Evaluation & Metrics" \
  --body "## Week 8 — Jul 21–27

Measure and document results for the thesis.

### Tasks
- [ ] Round-trip timing benchmarks (manual vs automated)
- [ ] Comparison tables: automated pipeline vs manual re-rig vs baked animation
- [ ] Document failure modes and their workarounds
- [ ] Collect final qualitative feedback from contacted studios (if pending responses)
- [ ] Capture screenshots and video demos

### References
- Issue #20 (networking, industry context)
- README.md Methodology section"

echo "✅ W8 Evaluation & Metrics created"

echo ""
echo "Creating Phase 3 issues (Thesis Writing — August–September 2026)..."

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Ch.1 — Introduction & Related Work (Aug 1–10)" \
  --body "## Thesis Writing — Aug 1–10

Draft Introduction and Related Work chapters.

### Tasks
- [ ] Write project outline and chapter structure
- [ ] Introduction: context, motivation, research questions
- [ ] Related Work: survey of rig/animation transfer methods, studio workflows, prior art
- [ ] Cite industry contacts and literature gathered during networking (Issues #19, #20)

### References
- Issue #19 (TIGS, Autodesk × CG World networking)
- Issue #20 (project framing and motivation)"

echo "✅ Thesis Ch.1 Introduction & Related Work created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Ch.2 — Methodology (Aug 11–17)" \
  --body "## Thesis Writing — Aug 11–17

Draft Methodology chapter.

### Tasks
- [ ] Describe pipeline design decisions (FBX + manifest strategy)
- [ ] Explain module architecture and semantic rig system
- [ ] Document Maya-side authoring workflow and tagging conventions
- [ ] Explain UE-side builder logic and DataAsset recipes

### References
- Issue #16 (Current Pipeline Design)
- Issue #22 (Rig Manifest)"

echo "✅ Thesis Ch.2 Methodology created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Ch.3 — Implementation (Aug 18–24)" \
  --body "## Thesis Writing — Aug 18–24

Draft Implementation chapter.

### Tasks
- [ ] Code walkthrough: key scripts and their roles
- [ ] UE5.6 limitations encountered and how they were addressed
- [ ] Design decisions and trade-offs
- [ ] Include diagrams (pipeline flow, module hierarchy)

### References
- \`Semantic_Rigging_System/rig_builder/\` (all files)
- Issue #21 (UE metadata static limitation)"

echo "✅ Thesis Ch.3 Implementation created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Ch.4 — Results (Aug 25–31)" \
  --body "## Thesis Writing — Aug 25–31

Draft Results chapter.

### Tasks
- [ ] Present timing benchmarks from Week 8 evaluation
- [ ] Comparison tables (automated vs manual vs baked)
- [ ] Screenshots and video captures of working demos
- [ ] Analysis of visual parity and animator usability"

echo "✅ Thesis Ch.4 Results created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Ch.5 — Discussion (Sep 1–7)" \
  --body "## Thesis Writing — Sep 1–7

Draft Discussion chapter.

### Tasks
- [ ] Discuss trade-offs (complexity, robustness, iteration speed, data fidelity)
- [ ] Identify the breakpoint where baked animation becomes preferable
- [ ] Assess adoption feasibility for small teams / indie studios
- [ ] Propose future work directions

### References
- Issue #21 (product vs showcase question)"

echo "✅ Thesis Ch.5 Discussion created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Conclusion, Abstract & References (Sep 8–14)" \
  --body "## Thesis Writing — Sep 8–14

Finalize remaining thesis sections.

### Tasks
- [ ] Write Conclusion
- [ ] Write Abstract (last, after all chapters are drafted)
- [ ] Compile full bibliography / references
- [ ] Review consistency across all chapters"

echo "✅ Thesis Conclusion, Abstract & References created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Full Revision Pass (Sep 15–21)" \
  --body "## Thesis Writing — Sep 15–21

Full revision and advisor feedback.

### Tasks
- [ ] Read-through for consistency and clarity
- [ ] Incorporate advisor feedback
- [ ] Fix figures, captions, and formatting
- [ ] Check all references are properly cited"

echo "✅ Thesis Full Revision Pass created"

gh issue create --repo "$REPO" \
  --title "[Phase 3 · Thesis] Final Formatting & Submission (Sep 22–28)" \
  --body "## Thesis Writing — Sep 22–28

Prepare and submit.

### Tasks
- [ ] Final formatting pass (fonts, margins, page numbering, header/footer)
- [ ] Generate PDF / submit to institution
- [ ] Repository cleanup: remove temp files, update README, tag release
- [ ] Archive demo videos and screenshots

### Deliverable
Completed and submitted thesis + clean public repository."

echo "✅ Thesis Final Formatting & Submission created"

echo ""
echo "=============================================="
echo "✅ All 16 roadmap issues created successfully!"
echo "You can now add them to your GitHub Project:"
echo "https://github.com/users/CrapyShit/projects/1/views/4"
echo "=============================================="
