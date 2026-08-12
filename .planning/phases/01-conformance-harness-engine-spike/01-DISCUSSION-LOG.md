# Phase 1: Conformance Harness + Engine Spike - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-12
**Phase:** 1-Conformance Harness + Engine Spike
**Areas discussed:** Corpus sourcing

---

## Area Selection

Four gray areas were presented. The user selected one.

| Area | Description | Selected |
|------|-------------|----------|
| Corpus sourcing | Where 100–300 real-world PDFs come from; the privacy and licensing edge around invoices and contracts | ✓ |
| Corpus storage | In-repo vs git-lfs vs external bucket; near-permanent, sets clone time and CI cost | |
| CI environment | Where the harness runs; pinning renderer versions so an antialiasing change doesn't read as a regression | |
| Spike code disposition | Throwaway proof vs first draft of the Phase 2/3 modules | |

---

## Corpus Sourcing

### Q1 — Where do the 100–300 corpus documents come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Two-tier: public in-repo + private tier | Public tier committed and run on every PR; private tier of real invoices/contracts fetched from a secret bucket, never committed. Most setup work; only option that keeps the repo shareable AND tests the actual target documents | ✓ |
| Public corpora only | govdocs1, veraPDF corpus, pdf.js test suite, PDF Association files. Legally clean, fully reproducible. Skews toward files collected *because* they're pathological, and toward government forms over commercial invoices | |
| Public + generated invoices | Public corpora plus invoices generated through several producers (LaTeX, Word, Chrome, InDesign, wkhtmltopdf). Legally clean, fills the gap. Covers ~5 producers where the wild has hundreds | |
| Public + your own real documents | Single tier, scrubbed. Simplest setup, genuinely representative. Requires doing redaction work before any redaction tooling exists — and naive scrubbing leaves text in the content stream and metadata | |

**User's choice:** Two-tier.
**Notes:** Driven by the tension named up front — the roadmap wants weighting toward invoices and contracts, and those are precisely the documents carrying third-party personal data in a repo that may not stay private.

### Q2 — What happens when the private tier isn't available?

| Option | Description | Selected |
|--------|-------------|----------|
| Private blocks on main, skipped on fork PRs | Public gates every PR; private additionally gates main and release. Nothing ships with a private-tier regression, outside contribution still works. Cost: two CI configs, failures surface at merge rather than on the causing PR | ✓ |
| Public gates, private reports only | Always green-able by anyone; private tier is a canary rather than a wall. Risk: a regression visible only in private documents can merge while CI is green | |
| Private tier always required | One code path, strongest guarantee. Only credential-holders get a green build; a fresh clone is non-functional until the bucket is wired up | |

**User's choice:** Private blocks on main, skipped on fork PRs.
**Notes:** Consequence recorded in CONTEXT.md — the harness must treat an absent private tier as a normal state rather than an error.

### Q3 — How do the ~14 structural categories split across tiers?

| Option | Description | Selected |
|--------|-------------|----------|
| Every category needs public coverage | Public holds ≥1 example of each category; private adds volume, never unique categories. Fork PRs exercise every code path. More sourcing effort — Type3 and CID-keyed CFF are uncommon — but all are findable publicly | ✓ |
| Private-only categories allowed | Less sourcing work now. Those code paths validate only where credentials exist; combined with skip-on-fork, an untested branch sits behind a green PR and fails at merge | |
| Public = structural, private = volume | Same code-path guarantee, but a sharper rule for where a new document belongs as the corpus grows over years | |

**User's choice:** Every category needs public coverage.
**Notes:** Follows directly from Q2's skip-on-fork behavior.

### Q4 — How is category membership recorded and kept honest?

| Option | Description | Selected |
|--------|-------------|----------|
| Manifest + independent verifier | Manifest declares categories; CI probes each file and fails on a wrong label or a category at zero. The prober must do plain structural inspection and must NOT reuse the interpreter it exists to test, or the check is circular | ✓ |
| Auto-detect, no manifest | Labels can never drift. Loses the record of why a document was added — pruning for size can silently delete the only Type3 example | |
| Manifest only, no verification | Least work. Labels quietly stop matching reality; a corpus with wrong coverage claims is worse than one making none | |

**User's choice:** Manifest + independent verifier.

---

## Claude's Discretion

Three areas were offered and not selected. Defaults and leanings recorded in CONTEXT.md:

- **Corpus storage** — lean: public tier via git-lfs; private tier as an external bucket with a
  checked-in manifest of names, hashes, and categories so the shape stays reviewable. Flagged for
  revisit before the first document is committed, since git history keeps blobs forever.
- **CI environment** — lean: GitHub Actions, three renderers plus qpdf and pdfcpu in a pinned
  container image, with renderer versions pinned explicitly.
- **Spike code disposition** — lean: throwaway proofs, but keep the TJ-refit prototype's test cases
  and measured results as Phase 3 acceptance fixtures.

## Deferred Ideas

- Corpus growth from user-reported bad files — belongs with Phase 4 (first public exposure)
- Corpus size floor per category — revisit once true scarcity of Type3 / CID-keyed CFF is known
- Failure triage workflow (engine bug vs legitimately malformed input) — premature before an engine exists
- Redistribution licensing check for public-tier documents — a task inside this phase, not a user decision
