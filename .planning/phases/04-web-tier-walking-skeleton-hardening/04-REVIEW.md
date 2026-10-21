# Phase 4 final code review — 2026-10-21

An independent read-only reviewer inspected transport, worker isolation, Linux syscall
restrictions, browser state/rendering, geometry, recipe fitting and rewrite/font paths.
Three Important correctness issues were reproduced and fixed before the local commit.

| Finding | Resolution | Regression evidence |
|---|---|---|
| Raw password headers reject Unicode and normalize whitespace | Shared client UTF-8/base64 encoder; bounded strict server decoder; legacy compatibility | Real encrypted Unicode HTTP open/classify; exact whitespace/control round trip; malformed/oversized encoding refusal; client Headers test |
| Quote text-showing replacement loses implicit state changes | Named refusal at preview and direct rewrite before mutation; scans every touched operator | Both quote operators, with and without following text; unchanged source and no output |
| Shaping truncates multi-character clusters or overwrites shared CID Unicode | Per-op and grouped-face plan checks, runtime preflight and defensive subset shaper | Combining accent refuses before output; conflicting shared glyph refuses; ordinary text/precomposed accents remain supported |

The reviewer rechecked the fixes and reported no remaining Important findings in them;
their focused run passed 25 tests. The controller also reran renderer/font gates and the
broader non-corpus suite; final results are in `04-VERIFICATION.md`.

The broader rerun exposed a pre-existing time-sensitive CLI test: qpdf's modification ID
changes between otherwise identical saves. Inspection found differences only in the second
trailer ID. The test now normalizes that one value and compares all remaining bytes,
including the original source ID; runtime output behavior was not changed for this test.

This review does not substitute for the unexecuted Linux/container, live CDN and public
sign-off checks. Those remain explicit release gates.
