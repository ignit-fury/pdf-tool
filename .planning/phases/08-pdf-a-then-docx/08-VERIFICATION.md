---
phase: 08-pdf-a-then-docx
verified: "2026-10-29"
status: external_gate_pending
plans_complete_locally: 6
plans_total: 6
---

# Phase 8 verification

All six implementation plans are delivered and verified locally. The phase's
explicit hosted-CI criterion remains open. Evidence: `08-G7-RESULTS.md`,
`08-G7A-RESULTS.md`, plan summaries and checked-in executable gates.

| Goal / requirement | Evidence | Status |
|---|---|---|
| EXPO-06: native PDF/A-2b, fixture corpus in CI | Sixteen actual outputs validate with authenticated veraPDF; fixed twelve-positive floor, 31 frozen inputs, native fidelity and negative controls. Mandatory CI job authored. | Local pass; hosted CI unobserved |
| G7b: ceiling before implementation | `60dd243`, `DOCX-CEILING.md`, prior to engine modules | Pass |
| EXPO-07: direct OOXML from shared model | Opt-in image/fact model; one RunIndex/projection; fixed ZIP/XML/relationships, bounded package; actual heading/emphasis/image/table downloads | Pass locally |
| EXPO-08: current document-specific pre-conversion warning | Actual three/four-page reviews, facts/page/count disclosures; separate Convert; source/full-snapshot/policy binding rechecked in worker | Pass locally |
| DOCX independently cuttable | Literal isolated deletion, startup/capability/refusal; 134 non-DOCX export/G6/G7a tests, 22 client tests/build; unconditional-import negative control | Pass locally |
| Existing editor/history/privacy | Exact source/current bytes before/after, Undo invalidation, explicit upload disclosure and safe notices | Pass locally |
| Cancellation, stale state, accessibility | Held actual responses suppressed; unit binding controls; 320/760px focus/wrapping and capability=false | Pass locally |

The complete selected Python regression is covered by 754 sandbox passes and a
26-test OS rerun resolving six sandbox-only failures (760 unique tests selected,
39 deselected). All 147 client tests, 38-file strict typing, build, license gates
and Unicode data verification pass. Native renderer differences that match source
baselines remain disclosed, not relabeled as cross-engine passes.

## Review and remaining work

`08-REVIEW.md` records the primary-agent integration review. Confirmed earlier
independent PDF/A findings are fixed; that independent review was interrupted by
usage limits and is not represented as a completed independent phase-wide audit.

Hosted G7a CI, Word/Acrobat observations, G3 Linux/container/CDN, G4 literal contract
specimens and production HEIC confinement remain open. No public deployment or
release approval is implied. No further numbered feature phase is defined in the
current roadmap; remaining work is verification/release preparation under the
user's no-deployment instruction.
