# Phase 1: Conformance Harness + Engine Spike - Context

**Gathered:** 2026-08-12
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a **verification apparatus** and settles **two unproven bets**. It produces no
product code, deliberately.

Delivered: a two-tier corpus of real-world PDFs; a three-engine differential rasterizer running in
CI with a masked-diff assertion; structural validation on every engine output; a decision on whether
`playa-pdf` can decode encodings and glyph geometry on real documents; a TJ-refit prototype proving
the one algorithm no library provides; an AGPL lockfile gate; and a one-page data-flow retention map
written before any infrastructure is selected.

Requirements: ENG-01 through ENG-07. Gate G0.

The reason this comes first: nearly every failure in this domain is *silent* — the output opens
without error and is wrong. Retrofitting a corpus after the rewrite engine exists means every prior
release was unvalidated.

</domain>

<decisions>
## Implementation Decisions

### Corpus Sourcing

- **D-01:** Two-tier corpus — public tier committed to the repo, private tier never committed.
  The public tier runs on every PR. The private tier holds real invoices and contracts, is fetched
  from a bucket via CI secrets, and exists locally for the maintainer. Chosen because the roadmap
  requires weighting toward invoices and contracts, and those are exactly the documents that carry
  third-party personal data and cannot be committed to a repo that may not stay private.

- **D-02:** The private tier gates `main` and release branches; it is skipped where credentials are
  absent (fork PRs, fresh clones). Nothing ships with a private-tier regression, and outside
  contribution still works. Accepted cost: two CI configurations, and a class of failure that
  surfaces at merge rather than on the PR that caused it. The harness must therefore handle a
  partially-absent corpus gracefully rather than erroring — absence is a normal state, not a fault.

- **D-03:** Every structural category must have public-tier coverage. At least one public example
  of each of: subset fonts, Type0/Identity-H, symbolic fonts, Type3, CID-keyed CFF, `/Contents`
  arrays, inline images, Form XObjects, annotation appearance streams, justified and right-aligned
  text, tables, an OCR'd scan, vector-outlined text, encrypted files, malformed files. The private
  tier adds volume and real-world messiness, **never unique categories**. This guarantees a fork PR
  exercises every engine code path — no branch is validated only on the maintainer's machine.
  Follows directly from D-02: private-only categories plus skip-on-fork means an untested branch
  can sit behind a green PR.

- **D-04:** Category membership is recorded in a manifest and verified independently in CI. Each
  document declares its categories; a CI script probes the file and fails if a declared category is
  absent, or if any category has dropped to zero documents. **The prober must do plain structural
  inspection (e.g. does any font resource have `Subtype /Type0`) and must NOT reuse the
  content-stream interpreter it exists to validate** — reusing it makes the check circular and it
  proves nothing. This also preserves the record of *why* a document was added, so pruning the
  corpus for size cannot silently delete the only Type3 example.

### Claude's Discretion

The user reviewed these areas and chose not to discuss them. Defaults noted; the planner has
latitude, but should honor the stated leanings.

- **Corpus storage.** Not discussed. Sizing implication is real — 300 PDFs is plausibly 200MB–2GB,
  and git history keeps blobs forever. Default lean: the public tier via git-lfs rather than raw
  git objects, and the private tier as an external bucket with a checked-in manifest of names,
  hashes, and categories so the *shape* of the private corpus is reviewable even when the bytes
  are not. Revisit before the first document is committed — this decision is near-permanent.

- **CI environment.** Not discussed. Default lean: GitHub Actions with the three renderers plus
  `qpdf` and `pdfcpu` in a pinned container image. Renderer versions must be pinned explicitly —
  an upgrade that changes antialiasing would light up every diff simultaneously and read as a
  regression in our own code.

- **Spike code disposition.** Not discussed. Default lean: treat the `playa-pdf` validation and the
  TJ-refit prototype as throwaway proofs, judged on whether they answer the question rather than on
  code quality — but keep the TJ-refit prototype's *test cases and measured results*, since those
  become Phase 3's acceptance fixtures regardless of whether the code survives.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase definition and requirements
- `.planning/ROADMAP.md` — Phase 1 section: goal, the five success criteria, Gate G0, and the
  "Deviations from the research sequence" note
- `.planning/REQUIREMENTS.md` — ENG-01 through ENG-07, and the Traceability table
- `.planning/PROJECT.md` — locked decisions, constraints (Licensing, Privacy, Tech stack), and the
  Key Decisions table

### Research — read before planning this phase
- `.planning/research/SUMMARY.md` — §"Implications for Roadmap" (Phase 0 definition and Gate G0),
  §"Risk Register" (Risks #2, #3, #5, #7 are the ones this phase retires), §"Convergent
  Conclusions" #2 (the one licensing rule), §"Gaps to Address"
- `.planning/research/PITFALLS.md` — the conformance-harness recommendation, the ToUnicode-vs-
  Encoding distinction, the `/MissingWidth` default-0 trap, and the "works in one viewer" section
- `.planning/research/STACK.md` — `playa-pdf` viability and the `pdfminer.six` fallback; the AGPL
  entry points; renderer selection (`pypdfium2` for runtime, MuPDF CI-only)
- `.planning/research/ARCHITECTURE.md` — §on differential testing, and the Slice 0a/0b definitions
  that Phase 3 will gate on

### External references named in research
- Mozilla `pdf.js.comparator` — https://github.com/mozilla/pdf.js.comparator — existing
  multi-renderer differential harness; adopt rather than rebuild
- `pdftopdfa` 0.9.0 — https://github.com/iRedPaul/pdftopdfa — working proof of the
  pikepdf + fontTools stack shape, Ghostscript-free
- veraPDF test corpus — https://github.com/veraPDF/veraPDF-corpus — public-tier corpus candidate
- govdocs1 — public forensics corpus, candidate source for public-tier structural coverage

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

None. The repository is greenfield — it contains only `.planning/` and `CLAUDE.md`. No source
code, no dependency manifest, no CI configuration exists yet.

### Established Patterns

None yet. This phase establishes the first ones. Two constraints from PROJECT.md bind any structure
chosen here:

- **The licensing boundary is a directory boundary.** AGPL components (MuPDF, Ghostscript) are
  CI-only and must be reachable only from test/CI code paths, never from anything a served request
  could touch. The research proposes a `sidecars/` directory that deliberately mirrors the license
  boundary.
- **`playa-pdf` decode calls stay confined to one module** so the `pdfminer.six` swap remains a
  contained change. Explicitly do **not** build an abstraction layer for it — a single module
  boundary is the mechanism, not an interface.

### Integration Points

Nothing to integrate with. This phase's output is consumed by Phase 2 (Text Model), which builds
the content-stream interpreter against this corpus and this harness.

</code_context>

<specifics>
## Specific Ideas

- **The AGPL gate is proven, not asserted.** Deliberately add `pdf2docx` — MIT at the top level,
  pulling `PyMuPDF>=1.26.7` transitively — and watch CI go red. A gate that has never fired is not
  known to work.
- **The masked differential diff is the primary correctness assertion for the whole project**, not
  a testing chore. Assert that the three engines *agree with each other*: if all three agreed on the
  input and disagree on the output, something ambiguous was produced even though all three "open"
  the file.
- **Byte-level round-trip comparison is not a valid correctness test.** qpdf-class libraries
  silently repair broken xrefs, so a rewrite legitimately produces a structurally different document
  than the user supplied. The masked image diff is the valid test.
- **The retention map is written before infrastructure is selected**, not after. Queue-carrying-
  payload versus handle-only, and object-store versus tmpfs, are expensive to reverse once chosen.

</specifics>

<deferred>
## Deferred Ideas

- **Corpus growth from user-reported bad files** — every document a user reports as broken gets
  added to the corpus permanently. Raised in research as the mechanism that keeps the harness
  honest over time, but there are no users yet. Belongs with Phase 4 (first public exposure).
- **Corpus size floor per category** — how many documents each category needs before coverage is
  "real" rather than nominal. Deferred; revisit once the public tier is assembled and the true
  scarcity of Type3 and CID-keyed CFF examples is known.
- **Failure triage workflow** — how a corpus failure gets classified as an engine bug versus a
  legitimately malformed input. Premature before there is an engine to blame.
- **Redistribution licensing of public-tier documents** — govdocs1 and veraPDF corpus terms differ.
  Needs a check before committing documents, but is a task inside this phase rather than a decision
  the user needs to make now.

</deferred>

---

*Phase: 1-Conformance Harness + Engine Spike*
*Context gathered: 2026-08-12*
