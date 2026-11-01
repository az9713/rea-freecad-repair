# Why this workbench exists

The investigation used public source and documented APIs. No private model,
installed-app inventory or local executable was used as public evidence. This
release is an in-app extension, not a claim of binary reverse engineering.

## Pinned source

FreeCAD **1.1.4**, commit `4fd3bf320d9566a27e60069fc8387448aaa3a094`.
`public-source/manifest.json` records file hashes and immutable URLs. The relevant
readable mechanisms are the native dependency graph commands in `CommandDoc.cpp`
and kernel validity/shape access in `TopoShapePyImp.cpp`. Source access made binary
instrumentation unnecessary for this bounded project.

## Existing capabilities versus the delivered change

| Existing mechanism | What it covers | What TopoIntent adds |
|---|---|---|
| [Native dependency graph](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Std_DependencyGraph.md) | Visual object dependencies; archived official docs say graph is not editable | Explicit face-level boundary/normal/area/volume predicates; reasons each candidate fails |
| [Nxt](https://github.com/obelisk79/FreeCAD-Nxt) | Experimental feature-story UI, rollback and selected sketch repair workflows | Uniqueness-gated reference rebinding with an inspectable geometric contract; not a replacement for Nxt |
| [Topological Naming V2, PR #31040](https://github.com/FreeCAD/FreeCAD/pull/31040) | Proposed naming/matching and element history; open draft at audit | A small application-level design-intent layer, not a new naming algorithm |
| Existing undo | Reverses stored document operations | A repair is explicitly accepted only after fresh geometry validation, and still creates an ordinary undo step |

The draft PR's status is time-bound evidence from October 31, 2026, not a promise
about a future release. It must not be described as a guaranteed 26.3 feature.

## Narrow meaning of diagnosis and repair

The workbench diagnoses changes to **axis-aligned outer planar boundary faces**
of a **single valid solid**. The user declares face-area and solid-volume ratio
intervals. The matcher evaluates every face against every predicate and refuses
zero or multiple matches. It does not reconstruct an unrecorded causal history.
For `Part::Box`, an isolated transient document can vary one dimension, providing
a genuine counterfactual without editing the original source.

The delivered repair rebinds the workbench's `Support` LinkSub, or a caller-specified
single native consumer LinkSub through the adapter API. It does not cut/rebuild
geometry, guess a nearest face, automatically alter sketches, repair arbitrary
constraints, or prove complete design intent. A valid solid with an unwanted shape
is still possible if the user's declared predicates are incomplete.

## Release evidence

The integration suite must create actual OpenCASCADE BReps: a dimension edit,
controlled face-order renumbering, a Boolean-fused coplanar split, a stale preview,
a deliberately failing consumer and a saved/reopened FCStd document. Unit JSON
fixtures are useful for policy edge cases but cannot establish kernel integration.
The build script refuses a verified release without a passing native report.
