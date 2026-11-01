# TopoIntent — a face reference that can explain its intent

An **in-app FreeCAD workbench** for investigating a narrow but consequential
failure: `Face6` still exists after an upstream change, but it is no longer the
outer plane the designer meant to reference.

TopoIntent captures an explicit geometric contract, explains every candidate,
and rebinds only when **one** face passes all checks. For a `Part::Box`, an isolated
counterfactual can test a dimension change without editing the original source.

[Interactive explanation](https://az9713.github.io/rea-freecad-repair/) ·
[Installable ZIP](https://github.com/az9713/rea-freecad-repair/releases/latest) ·
[Investigation and comparison](investigation/COMPARISON.md)

## What changes inside FreeCAD

| Before | With TopoIntent |
|---|---|
| A stale face number may silently name a different existing face | The captured reference output clears when that face violates declared intent |
| The user manually guesses a replacement | The analyzer lists normal, boundary, area and volume checks for every face |
| A coplanar split tempts an arbitrary nearest-face guess | Multiple matches are refused; no repair is selected |
| A preview can become stale while the model changes | Commit rechecks the source fingerprint and the candidate |
| A dimension hypothesis requires editing the working model | A box-only probe evaluates a separate transient document |

This is **a bounded source/API investigation and extension**, not a claim that
binary reverse engineering was needed. FreeCAD's public source and APIs provided
the necessary mechanisms. It complements native naming and dependency tools.

## Install and use

1. Download `TopoIntent-0.1.0-workbench.zip` from Releases.
2. Extract its `TopoIntent` folder into your FreeCAD user `Mod` directory. You can
   find that directory from the FreeCAD Python console with
   `FreeCAD.getUserAppDataDir()`. Keep the `InitGui.py` directly inside `TopoIntent`.
3. Restart FreeCAD and select the **TopoIntent** workbench.
4. Select one axis-aligned outer planar face of one valid solid. Choose
   **Capture boundary-face intent** and review the area/volume ratio limits.
5. Edit the source. Select `TopoIntentReference` in the model tree and choose
   **Explain and preview validated repair**. Inspect per-face rejection reasons,
   highlight the unique candidate, then explicitly accept if appropriate.
6. **Probe an isolated box counterfactual** works for a captured `Part::Box` only.
   It varies Length, Width or Height in a separate transient document.

The release includes four synthetic FCStd examples in `examples/`. For the
renumbering example, open `renumber-before-review.FCStd`, select its captured
reference and analyze it. `ambiguous-split-refused.FCStd` demonstrates refusal.
Every accepted rebind is a native document undo step. Enable document undo before
capture or repair; the adapter refuses transactional operations otherwise.

### Native consumer API

The UI repairs the workbench reference's `Support`. A script can rebind another
single `App::PropertyLinkSub` consumer of the same source:

```python
from topointent.freecad_adapter import analyze, repair_reference
preview = analyze(captured_reference)
repair_reference(captured_reference, preview, consumer, property_name="Support")
```

Cross-document links, multi-subelement properties and LinkSub lists are refused.
Consumer recompute must succeed and produce a valid non-null shape when it has
a Shape property; otherwise the transaction is aborted and the old binding
restored. Native consumer behavior still depends on that feature's own semantics.

Verification completed on the acquired portable host: **14 policy tests, 7 native
integration checks, and 7 native Qt GUI checks passed**. Offscreen 3D rendering
was unavailable; the geometry and widget checks are explicit in the reports.

## Reproduce the verification

The core needs Python 3.9+ and no third-party packages:

```powershell
python -m unittest discover -s tests -p test_core.py -v
```

To acquire a separate **official portable FreeCAD 1.1.4** inside this checkout:

```powershell
$env:TEMP = "$PWD/.runtime/tmp"
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
python scripts/acquire_freecad.py
./scripts/run_portable.ps1
python scripts/build.py --candidate
python scripts/stage_install_test.py
./scripts/run_portable.ps1 -Gui -Script tests/gui_smoke.FCMacro
python scripts/build.py
```

The acquisition script verifies the publisher's SHA-256 before extraction, using
a pinned SHA-256-verified standalone upstream 7zr executable (no installer). The
launcher redirects HOME, USERPROFILE, AppData, FreeCAD preferences and XDG/cache
locations into `.runtime`, passes explicit user/system config paths, and runs the
headless host. It does not use an installed FreeCAD profile. The archive is about
418 MB; the extracted runtime is substantially larger and remains untracked.

`artifacts/integration-results.json` records actual host results; the separate
`artifacts/gui-results.json` verifies actual offscreen Qt workbench registration,
capture and analysis dialogs, acceptance and ambiguity refusal. Offscreen Qt
cannot create a valid OpenGL context here: these tests verify native widgets and
kernel/document behavior, not 3D viewport rendering. The website
publishes the same report as `docs/evidence.json`. The build refuses a verified
release if the six native scenarios are incomplete or failing. Unit fixtures alone
are never counted as FreeCAD integration. All HTML is in `docs/` for GitHub Pages.

## Supported contract and limits

Supported: one valid solid, axis-aligned outer planar boundary faces, explicit
area/volume ratio intervals, unique-match diagnosis and transactional LinkSub
repair. The normal and boundary predicates are relational to the current source's
world-space bounds; arbitrary rotated geometry is deliberately unsupported.

Not implemented: arbitrary topological naming, sketch/constraint repair, curved
or internal face matching, general-history counterfactual cloning, reconstruction
of unrecorded edit history, or proof of full human design intent. Shape validity
plus numerical invariants can still accept an unwanted design if those invariants
are too weak. Complete candidate evidence is shown so the user can judge that gap.

Existing [native dependency graphs](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Std_DependencyGraph.md),
experimental [Nxt](https://github.com/obelisk79/FreeCAD-Nxt), and the
[Topological Naming V2 proposal](https://github.com/FreeCAD/FreeCAD/pull/31040) overlap
parts of this space. See the comparison for why this project does not duplicate a
whole naming engine or claim those projects lack features that were never tested.

Original work: MIT. Collected unmodified FreeCAD source: its own LGPL license.
See [NOTICE.md](NOTICE.md). No proprietary binary, private inventory, user document
or portable FreeCAD runtime is distributed in this repository/release.
