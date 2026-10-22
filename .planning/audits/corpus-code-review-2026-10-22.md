# Corpus compatibility code review

Read-only independent review of the compatibility changes against `49f0074`,
including new regressions and the corpus edit auditor. Final implementation:
`5457863`.

Critical findings: none. One important finding was corrected and independently
rechecked: raw Type1/CFF font planning selected bundled metrics without always
forcing the writer to select the bundled target. The writer now treats the
resolved substitution key as authoritative. The reviewer confirmed a new Type0
resource and a replacement `Tf` selecting it in the actual 012084 fixture.

The regression was strengthened to check the output font resource as well as
independently extracted full-page text. It failed before the handoff correction
and passed afterward. The affected corpus edit audit was discarded as final
evidence and restarted for all 217 files on the corrected pipeline.

No further introduced defects were found in standard-font metrics, physical-part
clustering, glyphless-operator correlation, worker/font-state caches, preflight
refusals, syntax-error translation or disposable full-rewrite preview validation.

Review exclusions, accepted as explicit limits of the report:

- Editing is sampled; only the read audit covers every page.
- Corpus outputs receive syntax, rendering and normalized text checks, without
  individual source/output pixel comparisons. The separate three renderer gates
  prove their own limited fixture cases.
- Known stream boundaries, shared operators, Type3 fonts and missing Unicode
  mappings remain named refusals rather than a promise of universal editability.
- Final audit conclusions depend on the final, single-revision per-file report.

Earlier design-hook triage: the side-tab accent border was removed/softened in
`b387cf0`. This corpus task changes no CSS. No suppressions were added and that
reported finding is not left open.
