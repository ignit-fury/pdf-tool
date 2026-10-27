---
phase: 07-exports
plan: "04"
subsystem: integrated-export-verification
requirements-completed: [EXPO-01, EXPO-02, EXPO-03, EXPO-04, EXPO-05]
completed: 2026-10-27
---

# Phase 7 Plan 4 — Integrated export proof

Actual browser downloads, observed request boundaries, independent native output and
applicable regressions verify the local Export workstation. Detailed evidence/limits
are in 07-G6-RESULTS.md; automated oracles are in 07-04-GATE-SUMMARY.md.

All five requirements have reachable actions with truthful execution labels. PNG/JPEG/split
stay local; compression/flatten/text formats use current materialized bytes in isolated
workers. Exports preserve working bytes and Undo. Downsample preparation shows exact
Before/After and downloads the same returned bytes. Text formats share one bounded
RunIndex/block model, with additive metadata reusable by Phase 8.

Root added exports tests to the standard npm glob. Independent review resolved one
mask-identity blocker and six warnings; both direct nested graphics-state masks and
ordinary mask aliases remain untouched. No new runtime package or expanded limits.
Native source-baseline cross-engine disagreements remain disclosed rather than hidden.

Browser evidence includes physical DPI/ZIP contents, mixed style/page changes in every
format, preview identities, cancellation, signatures/passwords, safe refusals and 320/760 px
focus/layout. G3 release checks, literal G4 specimen and Linux HEIC confinement remain
open. Final local goal verification owns the phase verdict; no deployment occurred.
