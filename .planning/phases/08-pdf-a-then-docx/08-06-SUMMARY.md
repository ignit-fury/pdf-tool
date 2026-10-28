---
phase: 08-pdf-a-then-docx
plan: "06"
subsystem: docx-client-and-integrated-verification
requirements: [EXPO-06, EXPO-07, EXPO-08]
completed: "2026-10-29"
---

# 08-06 — Reviewed DOCX export and independent removal

Implementation commit: `9b66eb9`.

The export panel now offers DOCX with separate Review and Convert actions.
Selecting the format performs only metadata capability lookup. Review uploads the
current bytes and shows fixed, document-specific facts, supported table count and
the written fidelity ceiling. Conversion requires a current review bound to
session, byte identity, revision and options, and sends its three digests/policy
fields. Review never generates a download. No CSS or runtime dependency changed.

The controller validates review shape, source SHA-256, page/count facts, binary
ZIP artifact MIME/name/envelope and memory admission. Cancellation, invalidation
and disposal clear reviews and revoke URLs; late results cannot publish. Focus
moves to review/results and returns to Review after cancellation. Capability
failure disables DOCX alone. Five new controller tests and all prior tests pass.

Literal writer removal occurs only in a scratch copy. Startup and text export
survive; capability is false and DOCX returns 503. Injecting an unconditional
import makes this proof fail. With the module absent, **134 Python export/G6/G7a
tests, 22 client export tests and production build pass**. The checkout is intact.
CI assigns both complete gate files to the mandatory authenticated G7a job; the
ordinary regression job explicitly excludes those two files only.

Actual local Chromium journeys cover review then conversion, current four-page
bytes after local page insertion, source/history preservation, Undo invalidation,
held-response review/conversion cancellation, Unicode-password input, signature
disclosure, clean single-column output, capability=false and 320/760px focus/layout.
Five actual DOCX downloads pass ZIP CRC/XML checks; headings/emphasis/table/image
and conservative column fallback are inspected. macOS textutil reads actual output.

Final verification: 754 broad Python passes with six sandbox-denied OS checks;
the complete affected files then pass all 26 tests outside the sandbox. All 147
client tests, strict typing (38 files), build, license closures/negative controls
and Unicode data check pass. The integrated G7a/removal command passes all seven
tests. Detailed commands, counts and limits: `08-G7-RESULTS.md`.

## Self-Check: PASSED locally; external gates retained

No deployment. Hosted G7a CI, Word/Acrobat observations, G3 Linux/container/CDN,
G4 literal contract specimens and production HEIC confinement remain unproved.
G7b remains the pre-implementation ceiling commit `60dd243`. No manifest,
success floor, renderer tolerance or export scope was weakened.
