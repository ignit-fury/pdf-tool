# Phase 8: PDF/A, then DOCX - Research

**Researched:** 2026-08-30
**Domain:** PDF/A-2b conformance + validator-gated CI (EXPO-06); direct OOXML generation from the
Phase 2 run index within a written scope ceiling (EXPO-07/08)
**Confidence:** HIGH on the PDF/A-2b rule set (the complete 144-rule veraPDF PDF/A-2b machine
profile was downloaded and parsed this session — every conformance claim below cites a rule ID and
its verbatim `TEST` expression, not a recollection of the ISO text). HIGH on veraPDF's licence
posture and CLI shape. HIGH on the Phase 3 font output's conformance, because the emitted subset
was actually built and inspected this session rather than reasoned about. MEDIUM on the DOCX
half — the OOXML container shape is well-documented and the ceiling is fixed by D-8.2, but the
font-size clustering thresholds cannot be measured until Phase 7's `engine.blocks` exists, and are
flagged as an Open Question, not asserted.

## Summary

The PDF/A half is smaller than it looks and the DOCX half is exactly as large as the roadmap fears.

**PDF/A.** The single most useful thing done in this session was downloading veraPDF's own
PDF/A-2b validation profile (`PDFA-2B.xml`, 144 rules, flavour `PDFA_2_B`, "Validation rules
against ISO 19005-2:2011, Level B") and parsing every rule's `TEST` expression. That turns "PDF/A
conformance rules that only a validator catches" from a research question into a finite, enumerated
list this document reproduces in full for the clauses that matter. Three results fall straight out
of it. First, **the Phase 3 font pipeline's emitted Type0/CIDFontType2 output is already PDF/A-2b
conformant on every font rule in the profile** — verified not by reading the code and reasoning, but
by calling `engine.fonts.subset_font_for_family()` for real and inspecting the resulting bytes: the subset retains two `cmap` subtables ((0,3) and (3,1)), `/W` is scaled
`*1000/unitsPerEm` at `engine/fonts.py:459` so the ≤1-unit width-consistency tolerance of rule
6.2.11.5-1 is met with ~0.2 units to spare, `/CIDToGIDMap` is written explicitly (6.2.11.3.2-1),
and Identity-H exempts the CIDSystemInfo from the compatibility rule entirely (6.2.11.3.1-1).
Phase 8 should **verify** this, exactly as `08-CONTEXT.md` says, and must not rebuild it. Second,
**PDF/A-2 dropped PDF/A-1's document-info-dictionary ↔ XMP consistency requirement** — there is no
such rule anywhere in the 144, and the PDF Association's own TechNote 0010 confirms a PDF/A-2
reader "shall ignore" the Info dictionary. The brief's assumption here was a PDF/A-1 rule. Third,
the rules that will actually bite are **not** font rules: they are 6.2.2-2 (no inherited
`/Resources` — `inheritedResourceNames == ''`), 6.2.11.8-1 (no `.notdef` reference from any
text-showing operator), 6.1.7.2-1 (no LZWDecode), 6.3.x (annotation appearance streams and `/F`
flags — which the corpus is full of, 13 documents tagged `annotation_appearance_streams`), and
6.6.2.1-1 + 6.6.4-* (the XMP stream and the `pdfaid` identification schema, which pikepdf already
has first-class namespace support for).

**veraPDF is not a licensing problem.** It is dual-licensed GPLv3+ **and MPLv2+** — the taker
chooses. MPL-2.0 is the same licence as `pikepdf`, already a runtime dependency. So veraPDF does
not even need Phase 1's GPL-subprocess carve-out; it clears the bar on the permissive limb of its
own dual licence, and it is never AGPL. Separately, `tools/license_gate.py` scans
`importlib.metadata.distributions()` — Python distributions only — so a Java tool in `Dockerfile.ci`
is invisible to it either way. That is a scope statement worth writing down, not a loophole:
the gate's silence about veraPDF is not the gate approving veraPDF.

**DOCX.** There is no OOXML-generation research finding that will make this easier, and looking for
one is the failure mode. `python-docx` 1.2.0 (MIT, `lxml` + `typing_extensions` only) is the boring
answer and is what `STACK.md` already prescribed; hand-building OOXML into a `zipfile` is the
lazier-looking answer that is actually more code and more ways to emit a file Word silently
repairs. The real content of this phase's DOCX half is **not** the writer — it is (a) writing the
ceiling down first as a `## Decision` document, which is literally the G7b gate, and (b) an
import-graph assertion that makes D-8.5's independent cuttability machine-checkable instead of
aspirational.

**Primary recommendation:** Order the phase G7b-document → veraPDF-in-CI (harness wiring + fixture
corpus + the *unmodified* baseline measurement) → PDF/A conversion (remediate the enumerated,
mechanically-fixable rules; refuse by named rule ID for the rest) → `engine/export/docx.py`
consuming `engine.blocks` → the EXPO-08 warning read off the same `Block` list → the cuttability
assertion. Never widen the D-8.2 ceiling; the profile of failures on real documents is the input to
a *follow-up* phase, not to this one.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-8.1: PDF/A ships before DOCX, and PDF/A is validator-gated.** EXPO-06 and ROADMAP criterion
  1: veraPDF passes at the chosen conformance level (**PDF/A-2b**) across a fixture corpus in CI,
  **not on spot checks**. The roadmap's own justification: a PDF/A file that does not validate is
  worse than no feature. veraPDF is a CI-only tool here; confirm its licence posture against
  ENG-07's gate before wiring it (Phase 1 established that GPL/LGPL tools are permitted only as a
  file-in/file-out subprocess, and AGPL not at all in the runtime).

- **D-8.2: The DOCX scope ceiling is written down before any DOCX work starts, and is itself the
  G7b gate.** ROADMAP criterion 2 states the ceiling verbatim: single-column body text, headings by
  font-size clustering, bold/italic, inline images, ruled tables only, everything else as plain
  paragraphs. Explicitly not: unruled tables, multi-column reading order, header/footer
  reconstruction, round-trip back into the tool. **Writing this ceiling into the phase definition
  is a task, ordered first.**

- **D-8.3: DOCX is generated as OOXML directly from the Phase 2 text model.** EXPO-07 and ROADMAP
  criterion 3. No LibreOffice, no `pdf2docx`, no second extraction path.

- **D-8.4: The pre-conversion warning names what will degrade in *this specific document*.**
  EXPO-08 and ROADMAP criterion 4 — e.g. "3 tables and a 2-column section detected". The roadmap
  notes this is cheap *because the layout analysis already ran*, which means the warning is a
  read of the Phase 7 block-structure layer's own output, not a separate document scan.

- **D-8.5: DOCX must be independently cuttable.** ROADMAP criterion 5: deleting it leaves every
  other export still passing its gate. This is a structural requirement on module boundaries and
  on the test suite, not an aspiration — it should have its own verification.

- **D-8.6: "If we just improved table detection a bit" is the named tripwire.** ROADMAP calls DOCX
  Risk #8: the last feature becomes the longest phase and drags in dependencies that compromise the
  posture built earlier, prevented by one written paragraph. Any plan task that widens the D-8.2
  ceiling is out of scope by construction and belongs in a follow-up phase.

### Claude's Discretion

- OOXML generation approach (hand-built XML into a zip container vs. a permissively-licensed
  library) — subject to the AGPL gate and to D-8.3.
- PDF/A remediation strategy: which non-conformances are fixed automatically (font embedding, colour
  profiles, XMP metadata, transparency) versus refused with a named reason, consistent with the
  project's refuse-visibly discipline (EDIT-04, CLAS-04, FIND-05).
- The PDF/A fixture corpus's composition and size, subject to it being a corpus and not spot checks.
- Font-size clustering algorithm for heading inference.
- How the pre-conversion warning is surfaced in the UI.

### Deferred Ideas (OUT OF SCOPE)

- PDF/A-1b or PDF/A-3 conformance levels — the roadmap chose PDF/A-2b.
- Any widening of the D-8.2 DOCX ceiling — by construction, a follow-up phase.
- DOCX round-trip back into the tool — explicitly excluded.
- DOCX→PDF conversion (CONV-01) — v2.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (verbatim, `REQUIREMENTS.md:118-120`) | Research Support |
|----|-------------|------------------|
| EXPO-06 | "User can export PDF/A, gated on veraPDF passing against a fixture corpus in CI rather than on spot checks" | § *PDF/A-2b: the complete rule set that matters* (the 144-rule profile, parsed this session, with per-rule verdicts against current output); § *Pattern 1* (the remediation pipeline); § *Pattern 2* (veraPDF in CI, licence-cleared, image pinned by digest); § *Pattern 5* (fixture corpus composition, corpus-measured) |
| EXPO-07 | "User can export DOCX, generated as OOXML directly from the text model, within a written scope ceiling: single-column body text, headings by font-size clustering, bold/italic, inline images, ruled tables only" | § *Pattern 6* (`python-docx` 1.2.0 vs hand-built OOXML, decided with the licence closure verified on PyPI this session); § *Pattern 7* (what `engine.blocks` must hand over, read off `07-RESEARCH.md` rather than invented); § *Pattern 8* (font-size clustering, bounded) |
| EXPO-08 | "DOCX export shows a pre-conversion warning naming what will degrade in *this specific document*" | § *Pattern 9* — the warning is a fold over the same `list[Block]` the writer consumes, so it is structurally impossible for it to disagree with what the writer actually did |
| Gate **G7a** | "veraPDF passes at PDF/A-2b across a fixture corpus in CI, not on spot checks" | § *Pattern 2*, § *Pattern 5*, and the `## Validation Architecture` map |
| Gate **G7b** | "The DOCX scope ceiling is written into the phase definition *before* work starts" | § *Pattern 10* — the exact document shape, derived by reading `PLAYA-DECISION.md`, `TJ-REFIT-RESULTS.md` and `G2B-GATE-RESULTS.md` |
| D-8.5 | "DOCX can be cut without touching anything else" | § *Pattern 11* — an import-graph assertion plus an optional-dependency-group boundary, both machine-checkable |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Directives extracted from `CLAUDE.md` that bind this phase specifically. The planner must verify
compliance; none of these is negotiable within Phase 8.

| # | Directive | Source | Binding effect on Phase 8 |
|---|-----------|--------|---------------------------|
| C1 | "No AGPL anywhere in the runtime dependency tree, *including transitively* — CI must fail on AGPL in the resolved lockfile, not top-level metadata." | `CLAUDE.md:38-40` | Any DOCX dependency must be licence-checked on its **resolved closure**, not its top-level metadata. Done for `python-docx` below. |
| C2 | "GPL/LGPL permitted only as a subprocess with a file-in/file-out interface… this keeps Poppler and veraPDF available. AGPL permitted only in CI and dev tooling no served request can reach." | `CLAUDE.md:41-43` | veraPDF is explicitly named as permitted. It is additionally available on the MPL-2.0 limb of its dual licence (see § *veraPDF's licence*), so the subprocess restriction is a belt-and-braces, not the load-bearing argument. |
| C3 | "Known trap: `pdf2docx` is MIT at the top level and pulls `PyMuPDF>=1.26.7` transitively." | `CLAUDE.md:44` | `pdf2docx` is banned. Not researched. Not planned around silently — see § *Out of Scope, restated*. |
| C4 | "**DOCX fidelity**: Best-effort, explicitly not pixel-faithful… Complex layouts will degrade. Sequenced last so it cannot block anything that matters." | `CLAUDE.md:47-51` | The D-8.2 ceiling is a restatement of a project-level constraint, not a phase-local preference. Widening it is a CLAUDE.md violation, not merely a scope creep. |
| C5 | "**Fonts**: Bundled open-license families only (Liberation, Noto, Source, DejaVu or similar), subset and embedded on save." | `CLAUDE.md:26-28` | PDF/A font remediation may only ever embed a **bundled** face. It may never fetch or synthesize a font. This is why unmappable BaseFont names must refuse rather than substitute (D-06). |
| C6 | "**Never claim** 'files never leave your device'… without stating the mechanism." + PRIV-01's per-operation local/server disclosure | `CLAUDE.md:30-37` | PDF/A conversion and DOCX generation are both server-side (pikepdf/fontTools/python-docx are Python). Both must report through PRIV-01's disclosure as server operations. Neither may be labelled local. |
| C7 | "Editing fidelity: Content-stream editing only. No white-box overlays. No reflow across lines or pages." | `CLAUDE.md:23-25` | Constrains PDF/A font remediation: embedding a missing font must not reflow the page. Liberation's metric compatibility (C5's bundled set) is what makes this possible — see § *Pattern 1*. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PDF/A-2b conversion (font embedding, XMP, OutputIntent, structural remediation) | API / Backend (Python engine) | — | Requires `pikepdf` + `fontTools` + the Phase 3 save pipeline. No client-side equivalent exists; `@cantoo/pdf-lib` cannot rewrite content streams (`CLAUDE.md:113-135`, the REWRITE-vs-APPEND table). Server-side, disclosed as such under PRIV-01. |
| PDF/A **validation** (veraPDF) | CI only | — | Not a runtime capability at all. It is a build gate. Putting it in the request path would add a JVM to production for a check the build already made — and would turn a CI-only licence posture into a runtime one. |
| DOCX generation (OOXML assembly) | API / Backend | — | Consumes the server-side `RunIndex`/`engine.blocks`. Client cannot see the run index (Phase 4's model: the browser echoes server-issued boxes, never invents them). |
| Block-structure / reading-order inference | API / Backend — **owned by Phase 7**, consumed here | — | D-7.2 makes `engine/blocks.py` a Phase 7 deliverable. Phase 8 must not re-derive it; re-deriving it is EXPO-05's banned "second extraction path" wearing a hat. |
| Pre-conversion degradation warning (EXPO-08) | API / Backend computes; Browser displays | Browser | The counts come from the same `list[Block]` the writer consumes (server). The SPA only renders them. Splitting this the other way would require shipping the block layer to the browser. |
| Fixture-corpus management for G7a | CI only | — | Reuses `corpus/manifest.json` + `harness/` wiring. Not a runtime concern. |

## Standard Stack

### Core — already pinned; PDF/A adds **zero** new runtime dependencies

| Library | Version | Purpose in Phase 8 | Why standard |
|---------|---------|--------------------|--------------|
| `pikepdf` | 10.11.0 (bundles qpdf 12.3.2 — verified live: `pikepdf.__libqpdf_version__`) | Object-layer surgery for every structural PDF/A remediation; `Pdf.open_metadata()` for the XMP/`pdfaid` stream; `Pdf.save(preserve_pdfa=True, min_version=…)` | Already the write side of the whole engine. `Pdf.save()` carries a first-class `preserve_pdfa: bool = True` parameter — "Ensures that the file is generated in a manner compliant with PDF/A and other stricter variants" (`.venv/…/pikepdf/_core.pyi:2829-2831`) |
| `fontTools` | 4.63.0 | Subsetting for the fonts PDF/A remediation embeds | Already the font pipeline (`engine/fonts.py:388`) |
| `uharfbuzz` | 0.56.0 | Shaped advances when a remediated run must refit | Already `engine/fonts.py:362` |
| `Pillow` | 12.3.0 | **The sRGB ICC profile for the PDF/A OutputIntent.** `ImageCms.createProfile("sRGB")` → 588-byte ICC v4.4, `deviceClass="mntr"`, `colorSpace="RGB "` — measured this session | Already pinned for Phase 7's compress. No ICC asset needs to be vendored, and no new dependency is needed to satisfy rules 6.2.3-1 and 6.2.4.2-1 |
| `playa-pdf` | 1.1.0 | Unchanged — the single read path (EXPO-05) | Already the boundary at `engine/playa_boundary.py` |

### Supporting — new, DOCX-only, and deliberately quarantined

| Library | Version | Licence (verified on PyPI this session) | Purpose | When |
|---------|---------|----------------------------------------|---------|------|
| `python-docx` | 1.2.0 (published 2025-06-16) | MIT (`License :: OSI Approved :: MIT License`) | OOXML writer | EXPO-07 only. Imported by exactly one module. Recommended as an **optional dependency group**, not a core dependency — see § *Pattern 11* |
| `lxml` | ≥3.1.0 (resolves to 6.1.2) | BSD-3-Clause | Transitive, required by `python-docx` | Same quarantine |
| `typing_extensions` | ≥4.9.0 | PSF-2.0 | Transitive, required by `python-docx` | Same quarantine |

`python-docx`'s **entire** resolved closure is `lxml` + `typing_extensions` (PyPI
`requires_dist`, fetched live). No AGPL, no `PyMuPDF`, nothing near it. This is the precise
contrast with `pdf2docx`, whose `requires_dist` lists `PyMuPDF>=1.26.7`.

### CI-only tooling — new

| Tool | Version | Licence | Purpose |
|------|---------|---------|---------|
| veraPDF CLI | Docker image `verapdf/cli:v1.30.2` — digest `sha256:d5ee329657cf9bc4b2400392dd54c7d0a0ce9980ff6fa2da5590eebeec007cdb`, linux/amd64, pushed 2026-06-03, 53.7 MB (Docker Hub registry API, queried this session) | **Dual GPLv3+ / MPLv2+** | The G7a gate. Never in the runtime, never in a served request |

> **Note on the version in `STACK.md`.** `.planning/research/STACK.md:57` names veraPDF "1.31.32".
> The `verapdf/cli` Docker repository has exactly five tags and the newest is `v1.30.2`
> (2026-06-03); the others are `v1.30.1`, `v1.28.2`, `v1.28.1`, `latest`. I could not reconcile
> "1.31.32" with any published Docker tag. Treat `STACK.md`'s number as unverified and pin the
> digest above instead. `[VERIFIED: Docker Hub registry API]`

### Alternatives Considered

| Instead of | Could use | Tradeoff / verdict |
|------------|-----------|--------------------|
| `verapdf/cli` Docker image | veraPDF installer JAR + `default-jre-headless` in `Dockerfile.ci` (what `STACK.md:100` sketched) | The JAR route adds a JRE (~180 MB) to the *harness* image, which every other CI job also builds and pulls, purely to serve one job. A separate pinned image keeps `Dockerfile.ci` unchanged and keeps the JVM out of the image the corpus/harness jobs use. **Recommend the image.** Fallback if the image is unavailable: the JAR, pinned by SHA-256 of the installer. |
| `python-docx` | Hand-built OOXML: `zipfile` + `xml.etree.ElementTree` (both stdlib) | Genuinely viable for `[Content_Types].xml` + `_rels/.rels` + `word/document.xml`. Not viable for `word/styles.xml` — a Word-accepted style part defining Heading 1..N, Normal, and table styles is several hundred lines of XML whose failure mode is Word's silent "unreadable content" repair dialog. `python-docx` bundles a Word-validated `default.docx` template; that template, not the XML serializer, is what you are actually buying. **Recommend `python-docx`, quarantined behind an optional dependency group.** |
| `python-docx` | `docxtpl` 0.20.2 | **LGPL-2.1-only** (PyPI, verified this session) and a template engine, not a document builder. Wrong tool and a worse licence. Rejected. |
| Pillow-generated sRGB | Vendoring an sRGB IEC61966-2.1 v2 ICC file | Adds a binary asset and a licence question for zero benefit at PDF/A-2b, where rule 6.2.4.2-1 accepts any ICC profile with `version < 5.0`. (This would flip at PDF/A-1b, which is stricter about ICC versions — one more reason D-8.1's level choice is load-bearing.) |

**Installation:**

```bash
# DOCX only — quarantined, see Pattern 11
uv add --optional docx "python-docx==1.2.0"

# PDF/A: nothing to install. Every library it needs is already pinned.
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `python-docx` 1.2.0 | PyPI | Project since 2013; 1.2.0 published 2025-06-16 | ~10M/mo class (widely depended on) | `github.com/python-openxml/python-docx` | `[OK]` — "Name starts with 'python-' — classic LLM naming pattern. Name looks like LLM bait but package is established." | **Approved** |
| `lxml` 6.1.2 | PyPI | Project since 2005; 6.1.2 published 2026-08-19 | very high | `github.com/lxml/lxml` | `[OK]` | **Approved** (transitive) |
| `typing_extensions` | PyPI | CPython-adjacent, maintained by the typing council | very high | `github.com/python/typing_extensions` | not scanned separately (stdlib-adjacent) | Approved (transitive) |
| `docxtpl` 0.20.2 | PyPI | — | — | `github.com/elapouya/python-docx-template` | not scanned | **REMOVED** — rejected on licence (LGPL-2.1-only), not on legitimacy |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged `[SUS]`:** none.

Commands run this session: `slopcheck install python-docx lxml` → `2 OK`; and
`curl https://pypi.org/pypi/{python-docx,lxml,docxtpl}/json` for licence and `requires_dist`.
slopcheck's `--json` flag does not exist in the installed version (`slopcheck: error:
unrecognized arguments: --json`); the human-readable output was used instead.

**Provenance note.** `python-docx` was named by `.planning/research/STACK.md:53` before this
session. It is tagged `[VERIFIED]` here because it passes slopcheck, its GitHub org
(`python-openxml`) is the canonical OOXML-for-Python organisation, and its official documentation
is at `python-docx.readthedocs.io` — an authoritative source, not merely registry presence.

## veraPDF's licence — the ENG-07 question, answered

`08-CONTEXT.md` D-8.1 asks this to be confirmed before wiring, and calls it a potential blocker.
It is not one.

**veraPDF is dual-licensed GPLv3+ *and* MPLv2+**, across every component (veraPDF-library,
veraPDF-model, veraPDF-validation, veraPDF-pdfbox-validation — each repository's own
`LICENSE-HEADERS.md` states the dual grant). `[CITED: github.com/veraPDF/veraPDF-library]`
`[VERIFIED: cross-checked across four veraPDF repositories]`

Three independent reasons it clears the gate, in decreasing order of strength:

1. **It is available under MPL-2.0** — the taker chooses which limb of a dual licence to use.
   MPL-2.0 is *the same licence as `pikepdf`*, already a core runtime dependency
   (`CLAUDE.md:70`). No project rule restricts MPL-2.0 in any way. The GPL-subprocess carve-out is
   not needed at all.
2. **Even on the GPL limb, `CLAUDE.md:41-43` names veraPDF explicitly** as a permitted case:
   *"GPL/LGPL permitted only as a subprocess with a file-in/file-out interface … this keeps Poppler
   and veraPDF available."* The Docker-image invocation is exactly file-in/file-out: a volume mount
   in, a report on stdout.
3. **It is never AGPL.** The single prohibition in `CLAUDE.md:38-40` does not engage.

**Scope statement on `tools/license_gate.py` — read this before assuming the gate covers it.**
The gate iterates `importlib.metadata.distributions()` (`tools/license_gate.py:22`) and matches
`("agpl", "affero")` against each distribution's `License` field and `Classifier` entries
(`tools/license_gate.py:17,27-29`). It sees **installed Python distributions only**. A Java tool
running in a separate Docker image is invisible to it. That is correct behaviour — the gate's job
is the *resolved Python lockfile closure*, which is where the `pdf2docx` → `PyMuPDF` trap lives —
but it means **the gate's silence about veraPDF is not the gate approving veraPDF**. The approval
above is a human licence reading, and the planner should record it as such rather than pointing at
a green CI job. `[VERIFIED: read `tools/license_gate.py` in full this session]`

**Corollary for `python-docx`.** Because the gate scans the *installed environment*, an optional
dependency group (§ *Pattern 11*) is only checked if CI installs that extra. The
`license-gate.yml` job must `uv sync --locked --all-extras` (or equivalent) or the DOCX closure
escapes the ENG-07 gate entirely. This is a concrete, easily-missed planning item.

## PDF/A-2b: the complete rule set that matters

Everything in this section comes from veraPDF's own machine-readable validation profile, not from
recollection of the ISO text:

```
curl -sS https://raw.githubusercontent.com/veraPDF/veraPDF-validation-profiles/integration/PDF_A/PDFA-2B.xml
# 116,132 bytes; <profile flavour="PDFA_2_B">;
# name: "PDF/A-2b validation profile"
# description: "Validation rules against ISO 19005-2:2011, Level B"
# 144 <rule> elements across 48 clauses
```

`[VERIFIED: downloaded and parsed this session; the file is the profile veraPDF itself executes]`

Rule counts by clause, so the planner can see the shape of the standard rather than a curated
subset: 6.1.2 (2), 6.1.3 (3), 6.1.4 (1), 6.1.6 (2), 6.1.7.1 (3), 6.1.7.2 (1), 6.1.8 (1), 6.1.9 (1),
6.1.10 (1), 6.1.12 (2), 6.1.13 (10), 6.2.2 (2), 6.2.3 (3), 6.2.4.2 (2), 6.2.4.3 (3), 6.2.4.4 (2),
6.2.5 (6), 6.2.6 (1), 6.2.8 (5), 6.2.8.3 (5), 6.2.9 (3), 6.2.10 (2), **6.2.11.\* (21 — the font
rules)**, 6.3.\* (7), 6.4.\* (8), 6.5.\* (4), 6.6.\* (35 — almost all XMP extension-schema
plumbing), 6.8 (2), 6.9 (4), 6.10 (2), 6.11 (1).

### Three corrections to assumptions in the brief

**1. PDF/A-2 has NO document-info-dictionary ↔ XMP consistency rule.** The brief asks for "XMP
metadata requirements and their required correspondence with the document info dictionary." That
correspondence is **ISO 19005-1 (PDF/A-1) clause 6.7.3** and it was **dropped in ISO 19005-2**. I
searched all 144 rule descriptions for `information dictionary|docinfo|ModDate|CreationDate|Title|
Producer` and got six hits, every one of them an XMP-packet-encoding or extension-schema rule —
none about the Info dictionary. Independently corroborated: the PDF Association's TechNote 0010
("Clarifications of ISO 19005, parts 1-3") states that in PDF/A-2 *a document information
dictionary may be present and a conforming reader shall ignore it*, contrasted against PDF/A-1
where *"whenever Info entries are present, there must be an equivalent entry in the document's
Metadata."* `[VERIFIED: profile search + CITED: pdfa.org TechNote 0010]`

  *Planning consequence:* do **not** plan a docinfo-synchronisation task, and do not reach for
  `pikepdf.Pdf.open_metadata(update_docinfo=True)` for conformance reasons. It remains fine to use
  for tidiness; it is not a gate.

**2. PDF/A-2 does NOT require `/CIDSet` for subset CID fonts.** PDF/A-1 did. Rule 6.2.11.4.2-2's
test is `containsFontFile == false || fontName.search(/[A-Z]{6}\+/) != 0 || containsCIDSet == false
|| cidSetListsAllGlyphs == true` — i.e. *if* a `/CIDSet` is present it must be complete, and
absence passes trivially. `engine/fonts.py` writes no `/CIDSet` (verified: `build_cid_font_descriptor`,
`engine/fonts.py:544-560`, emits exactly `/Type /FontName /Flags /FontBBox /ItalicAngle /Ascent
/Descent /CapHeight /StemV /FontFile2`). **Absence is conformant.** Adding one would create a new
way to fail. `[VERIFIED: profile rule text + read of engine/fonts.py]`

**3. PDF/A-2 permits transparency.** PDF/A-1 banned it outright. The only PDF/A-2b transparency
rules are 6.2.10-1 (blend modes must be ISO-32000-1-defined) and 6.2.10-2 (*"If the document does
not contain a PDF/A OutputIntent, then all Page objects that contain transparency shall include the
Group key…"*). Since the conversion writes an sRGB OutputIntent unconditionally (§ *Pattern 1*),
**6.2.10-2 is satisfied vacuously for every page** and transparency needs no remediation at all.
`[VERIFIED: profile rule text]`

### The font rules, one by one, against `engine/fonts.py`'s actual output

`08-CONTEXT.md` says to *verify rather than rebuild*. This is that verification. Evidence is a live
call made this session, not a reading:

```
uv run --frozen python -c "
from engine.fonts import shape_glyph_names, subset_font_for_family, subset_cid_widths
names = shape_glyph_names('Sans','Regular','Hello, world! 123')
s = subset_font_for_family('Sans','Regular', frozenset(names))
"
# subset tag: BTILCH ; 7,452 bytes
# tables: GDEF GPOS GSUB OS/2 cmap cvt fpgm gasp glyf head hhea hmtx loca maxp name post prep
# cmap subtables: 2  -> (platformID 0, platEncID 3, format 4, 13 mappings)
#                      (platformID 3, platEncID 1, format 4, 13 mappings)
# unitsPerEm 2048 ; numGlyphs 14 ; glyphOrder[0] == '.notdef'
# cid widths: {1: 277.83203125, 2: 277.83203125, ... 13: 722.16796875}
```

| Rule | Verbatim `TEST` from the profile | Emitted output | Verdict |
|------|----------------------------------|----------------|---------|
| 6.2.11.2-1 | `Type == "Font"` | `Type=pikepdf.Name.Font` on both the Type0 and the CIDFont — `engine/fonts.py:642,658` | **PASS** |
| 6.2.11.2-2 | `Subtype == … "Type0" … "CIDFontType2"` | `engine/fonts.py:659` (`Type0`), `:643` (`CIDFontType2`) | **PASS** |
| 6.2.11.2-3 | `Subtype == "Type3" \|\| fontName != null` | `BaseFont` set on both, `engine/fonts.py:644,660`, from `_tagged_base_font_name` `:499` | **PASS** |
| 6.2.11.2-4/5/6 | `isStandard == true \|\| FirstChar/LastChar/Widths…` | `object=PDSimpleFont` — does not apply to a composite font | **N/A** |
| 6.2.11.2-7 | `fontFileSubtype == null \|\| "Type1C" \| "CIDFontType0C" \| "OpenType"` | `/FontFile2` is a plain stream with no `/Subtype` key (`engine/fonts.py:558`) → `null` | **PASS** |
| **6.2.11.3.1-1** | `cmapName == "Identity-H" \|\| …` | `Encoding=/Identity-H` (`engine/fonts.py:661`) short-circuits the whole CIDSystemInfo-compatibility clause. The emitted `Adobe/Identity/0` (`:646-648`) is legal *and irrelevant* here | **PASS (by short-circuit)** |
| **6.2.11.3.2-1** | `Subtype != "CIDFontType2" \|\| CIDToGIDMap != null \|\| containsFontFile == false` | `CIDToGIDMap=pikepdf.Name.Identity` written **explicitly** (`engine/fonts.py:650`). Note the rule needs the key *present*, and PDF's own default would have made it omissible — writing it is what passes | **PASS** |
| 6.2.11.3.3-1 | `CMapName == "Identity-H" \|\| …` (Table 118 allow-list) | Identity-H is on the allow-list, so no CMap embedding needed | **PASS** |
| **6.2.11.4.1-1** | `Subtype == "Type3" \|\| Subtype == "Type0" \|\| renderingMode == 3 \|\| containsFontFile == true` | The descendant `CIDFontType2` carries `/FontFile2` (`engine/fonts.py:558`) | **PASS** |
| 6.2.11.4.1-2 | `renderingMode == 3 \|\| isGlyphPresent == null \|\| isGlyphPresent == true` | Subset is populated from the exact shaped glyph names (`engine/fonts.py:388-419`), so every referenced glyph is present | **PASS** |
| 6.2.11.4.2-2 | `… \|\| containsCIDSet == false \|\| …` | No `/CIDSet` emitted | **PASS (vacuous)** |
| **6.2.11.5-1** | `renderingMode == 3 \|\| … \|\| Math.abs(widthFromFontProgram - widthFromDictionary) <= 1` | `subset_cid_widths` scales `hmtx * 1000.0 / units_per_em` (`engine/fonts.py:461`, upem measured 2048), `build_w_array` rounds once at serialization (`:481`). Worst-case error 0.5, measured example \|278 − 277.832\| = **0.17** | **PASS with ~0.8 units of margin** |
| 6.2.11.6-1 | `isSymbolic == true \|\| (cmap30Present ? nrCmaps > 1 : nrCmaps > 0)` | Descriptor sets `_FLAG_NONSYMBOLIC` (`engine/fonts.py:522`) so the symbolic escape does not apply. **Measured: the subset retains 2 cmap subtables, (0,3) and (3,1); no (3,0)** → `nrCmaps > 0` | **PASS — and this was the one I expected to fail** |
| 6.2.11.6-2/3/4 | — | `object=PDTrueTypeFont` / simple-font rules; do not apply to CIDFontType2 | **N/A** |
| **6.2.11.8-1** | `name != ".notdef"` | **See the finding below. Not structurally guaranteed.** | **AT RISK** |

**Net: 12 PASS, 5 N/A, 1 AT RISK.** The Phase 3 font pipeline is PDF/A-2b conformant on every font
rule except the `.notdef` one, and that one is a pre-existing gap in Phase 3 rather than something
PDF/A introduces.

### Finding: `.notdef` can reach a text-showing operator (rule 6.2.11.8-1)

`engine/fonts.py:449-453`, `subset_cid_widths`'s docstring, asserts:

> *"Starts at GID 1, never 0, so `.notdef` (never referenced by real shaped text — it is never a
> value `shape_cids` can emit) is excluded BY CONSTRUCTION…"*

**Measured false this session:**

```
uv run --frozen python -c "
from engine.fonts import shape_glyph_names
print(shape_glyph_names('Sans','Regular','A\U0001F600B'))
print(shape_glyph_names('Sans','Regular','A中B'))
print(shape_glyph_names('Sans','Regular','AЖB'))"
# ('A', '.notdef', 'B')
# ('A', '.notdef', 'B')
# ('A', 'uni0416', 'B')     <- Cyrillic IS covered; the failure is coverage-specific
```

HarfBuzz returns GID 0 for any character the *bundled* face lacks, and
`shape_glyph_names` (`engine/fonts.py:362-386`) resolves that to the literal name `'.notdef'` with
no filter. That name then flows into `subset_font_for_family`'s glyph set
(`engine/recipe.py:641-643`) and `shape_cids` (`engine/recipe.py:657`) emits CID 0 into the
operand (`engine/rewrite.py:931`). I grepped for a guard: `grep -rn "notdef" engine tests` returns
only `encoding_table.py`'s *read*-side filter (`:262-270`) and these docstrings. There is no
write-side guard. `[VERIFIED: measurement + full-tree grep this session]`

**Reachability.** `run_needs_substitution` (`engine/fonts.py:255`) checks the **original** font's
coverage. Substitution fires precisely when the original lacks the glyph — and then hands the text
to Liberation, whose coverage is never checked. So the reachable path is real: replacement text
containing a character that *both* the original font and the bundled Liberation face lack.

**Two distinct consequences, and the second is not a PDF/A problem:**
- PDF/A-2b: rule 6.2.11.8-1 fails outright — `.notdef` referenced from a text-showing operator.
- Phase 3 itself: `subset_cid_widths` deliberately skips GID 0 (`engine/fonts.py:462`), and
  `embed_type0_font` writes **no `/DW`** (`engine/fonts.py:641-652` — the CIDFont dict is exactly
  `Type, Subtype, BaseFont, CIDSystemInfo, CIDToGIDMap, W, FontDescriptor`). An unlisted CID
  therefore takes PDF's default `/DW` of 1000. That is precisely the failure mode
  `03-CONTEXT.md` D-14 says must not happen — *"`/DW` never silently covers a glyph actually in
  use."*

**Recommendation (lazy, root-cause, one place):** one guard in `shape_glyph_names` — the single
function every substitution path routes through — refusing by name when HarfBuzz returns `.notdef`,
in the same shape as D-06's refuse-by-name. Not a filter that drops the character (that would
silently lose text), and not a per-caller check. This is a Phase 3 correctness fix that Phase 8
merely *discovers*; the planner should size it as a small Wave-0 task with its own regression test,
and should flag to the human that it changes Phase 3 behaviour.

### The rules that will actually bite, ranked by measured incidence

A stratified sample of **25 of the 217 public corpus documents** (seeded `random.seed(8)`, forced
to include the `subset_fonts`, `type0_identity_h`, `annotation_appearance_streams`, `inline_images`,
`type3`, `malformed`, `tables`, `encrypted` and `form_xobjects` categories, then randomly filled),
each scanned to a bound of 25 pages. Deliberately a sample and not a sweep — another researcher was
running concurrently. `[VERIFIED: measured this session; command in § Code Examples]`

| Rank | Rule | What it catches | Measured incidence | Auto-remediable? |
|------|------|-----------------|--------------------|------------------|
| 1 | **6.2.11.4.1-1** | Non-embedded font programs | **6/25 documents (24%)** | **Partly** — 13 of 18 non-embedded font references (72%) map to a bundled Liberation face; the other 5 (`Symbol`×2, `ZapfDingbats`×2, `WPMathA`×1) do not, and must refuse |
| 2 | **6.3.3-1 / 6.3.2-1** | Annotations with no `/AP`, or missing `/F` — *after* applying the rule's own Popup/Link/zero-area-`Rect` exemptions | **5/25 (20%)** | **Partly** — `/F` flag correction is mechanical; synthesizing a missing appearance stream is not |
| 3 | **6.5.1-1** | `/Names /JavaScript` — a hard prohibition | **5/25 (20%)** | **Yes** — deletion is the only conformant outcome and loses nothing archival |
| 4 | **6.6.2.1-1 + 6.6.4-\*** | Missing `/Metadata`, missing `pdfaid` identification schema | 8/25 lack catalog `/Metadata` entirely; **25/25 lack `pdfaid`** | **Yes** — always written by the converter |
| 5 | **6.2.4.3-2/3/4** | Device colour with no OutputIntent | **23/25 have no `/OutputIntents`** | **Yes** — sRGB OutputIntent written unconditionally |
| 6 | **6.1.3-2** | `/Encrypt` in the trailer | **2/25 (8%)** | **No — refuse.** See § *Pattern 3* |
| 7 | 6.2.10-2 | Transparency with no page `/Group` and no OutputIntent | 3/25 pages carry `/Group` | **Vacuous** — the OutputIntent satisfies it |
| 8 | 6.1.7.2-1 | LZWDecode | **0/25** | Yes (`pikepdf` re-encodes), but no corpus evidence it is needed |
| 9 | 6.1.2-1 | Header not `%PDF-1.[0-7]` | **0/25** — sample versions were 1.7×10, 1.4×7, 1.3×4, 1.2×2, 1.5×2 | Yes — `Pdf.save(min_version=…)`, but guard for PDF 2.0 inputs anyway |
| 10 | 6.2.2-2 | Inherited `/Resources` (`inheritedResourceNames == ''`) | **0/25 pages lacked their own `/Resources`** | Yes — push inherited resources down |

The measurement that most changes the plan is #1's second column. `engine.fonts.BASE_FONT_MAPPING`
has 36 entries, and the non-embedded fonts the corpus actually contains are overwhelmingly the
Base-14 names it already covers. The five it does not cover are `Symbol`, `ZapfDingbats` and
`WPMathA` — **exactly the fonts `engine/fonts.py:1-46`'s own docstring says are deliberately absent
because they have no Liberation equivalent, and exactly the case D-06 says must refuse by name.**
The existing refusal policy produces the correct PDF/A behaviour with no new policy invented.

### What the converter must *write* — output intent, ICC, XMP

Everything in this subsection was executed against a real corpus document this session and the
saved output re-opened and inspected. It is a working recipe, not a sketch.

```
uv run --frozen python -c "
import pikepdf; from PIL import ImageCms
pdf = pikepdf.open('corpus/public/govdocs1_000_000009.pdf')
with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as m:
    m['pdfaid:part'] = '2'; m['pdfaid:conformance'] = 'B'
icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
st = pikepdf.Stream(pdf, icc); st.N = 3
pdf.Root.OutputIntents = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(
    Type=pikepdf.Name.OutputIntent, S=pikepdf.Name('/GTS_PDFA1'),
    OutputConditionIdentifier=pikepdf.String('sRGB IEC61966-2.1'),
    Info=pikepdf.String('sRGB IEC61966-2.1'),
    DestOutputProfile=pdf.make_indirect(st)))])
pdf.save('/tmp/pa_out.pdf', min_version='1.7')"
```

Observed on the saved file:

| Check | Rule | Observed |
|-------|------|----------|
| `pdfa_status` round-trips | 6.6.4-1..5 | `'2B'` |
| XMP packet header | 6.6.2.1-2, -3 | `<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>` — **no `bytes=` attribute, no `encoding=` attribute**, so both prohibitions pass without any intervention |
| XMP encoding | 6.6.2.1-5 | UTF-8 BOM `\xef\xbb\xbf` |
| Catalog `/Metadata` | 6.6.2.1-1 | present |
| OutputIntent shape | 6.2.3-1 | `/S /GTS_PDFA1`, `DestOutputProfile` stream with `/N 3` |
| ICC profile header | 6.2.3-1, 6.2.4.2-1 | `deviceClass="mntr"`, `colorSpace="RGB "`, version `04400000` (v4.4 < 5.0) — 588 bytes, from `ImageCms.createProfile("sRGB")` |
| File header | 6.1.2-1, -2 | `%PDF-1.7\n%\xbf\xf7\xa2\xfe` — version in `[0-7]`, and the four binary bytes are all > 127 |
| Trailer `/ID` | 6.1.3-1 | present — qpdf writes it on every save |
| Trailer `/Encrypt` | 6.1.3-2 | absent |
| Post-EOF bytes | 6.1.3-3 | `…startxref\n12265022\n%%EOF\n` — a single trailing EOL, which the rule explicitly permits |

`[VERIFIED: executed and re-opened this session]`

**Trap — `/S` is `/GTS_PDFA1` even for PDF/A-2.** The `1` is not a part number; ISO 19005-2 clause
6.2.2 keeps the `GTS_PDFA1` output-intent subtype that ISO 19005-1 introduced. Writing
`/GTS_PDFA2` produces a file with no *PDF/A* output intent at all, which then cascades into
6.2.4.3-2/3/4 (device colour with no output intent) and 6.2.10-2 (transparency with no group).
One wrong character, five failing rules, and the error message points at colour spaces rather than
at the output intent. `[ASSUMED — the `GTS_PDFA1` constant is consistent across every PDF/A
generator I am aware of and pikepdf's own `pdfa_status` reads the XMP rather than the intent, so I
could not confirm it against the profile itself: no rule in PDFA-2B.xml tests the `/S` value. Flag
for confirmation by the first veraPDF run.]`

**What the four remaining structural writes are.** Beyond the above, a conversion must: strip
`/Names /JavaScript` and any prohibited action (6.5.1-1); correct annotation `/F` flags so `Print`
is set and `Hidden`/`Invisible`/`NoView`/`ToggleNoView` are clear (6.3.2-2); drop `/AcroForm
/NeedAppearances` if true and `/XFA` if present (6.4.1-3, 6.4.2-1); and drop catalog `/AA`,
`/Requirements`, `/Names /AlternatePresentations`, and page `/PresSteps` (6.5.2-1, 6.11-1, 6.10-1,
6.10-2). All are single-key deletions on the object graph — `pikepdf`'s natural idiom, no new
capability.

## PDF/A remediation vs. refusal

`08-CONTEXT.md` leaves this to Claude's discretion, "consistent with the project's refuse-visibly
discipline (EDIT-04, CLAS-04, FIND-05)." The classification below follows one principle, chosen
because it is the one the rest of the codebase already applies: **remediate when the conformant
outcome is unique and loses nothing the user can observe; refuse by named rule ID when the
conformant outcome requires choosing between plausible alternatives, or when it silently discards
something the user would care about.**

### Auto-remediate

| Rule(s) | Action | Why this is not a judgement call |
|---------|--------|----------------------------------|
| 6.6.2.1-1, 6.6.4-* | Write XMP + `pdfaid:part=2`, `pdfaid:conformance=B` | The file is *becoming* a PDF/A. There is exactly one correct value |
| 6.2.4.3-2/3/4, 6.2.10-2 | Write the sRGB OutputIntent | Adds a colour interpretation where the file previously had none stated. Does not change any rendered pixel |
| 6.5.1-1, 6.5.2-1/2 | Delete JavaScript, `/Launch`, `/Movie`, `/Sound`, `/ResetForm`, `/ImportData`, `/Hide`, `/SetOCGState`, `/Rendition`, `/Trans`, `/GoTo3DView`, catalog and page `/AA` | Prohibited outright. There is no conformant file that keeps them. **Must be named in the report** — this is a behaviour change the user can notice |
| 6.11-1, 6.10-1/2, 6.4.2-2 | Delete `/Requirements`, `/AlternatePresentations`, `/PresSteps`, `/NeedsRendering` | Same |
| 6.4.1-3, 6.4.2-1 | Clear `/NeedAppearances`; delete `/XFA` | Same. `/XFA` removal is significant for XFA forms and must be named |
| 6.3.2-1/2 | Add `/F` where missing; set `Print`, clear `Hidden`/`Invisible`/`NoView`/`ToggleNoView` | Mechanical bit manipulation, one correct answer |
| 6.1.2-1 | `Pdf.save(min_version="1.7")` | Verified above |
| 6.1.7.2-1 | Re-encode LZW streams as Flate | `pikepdf` decodes and re-emits; lossless. 0/25 incidence, so cheap insurance |
| **6.2.11.4.1-1** | Embed a bundled Liberation face **for mapped BaseFont names only** | See § *Pattern 1*. 72% of measured non-embedded references |
| 6.2.2-2 | Push inherited `/Resources` down to each page | 0/25 incidence, but see the caveat in § *Pitfall 3* |

### Refuse, by named rule ID

| Rule(s) | Refusal reason string | Why refusal beats remediation |
|---------|----------------------|-------------------------------|
| **6.1.3-2** | `"PDF/A forbids encryption (rule 6.1.3-2); this document is encrypted"` | `pikepdf` *can* open all 2/25 encrypted corpus documents with an empty user password and save them decrypted. **Doing that silently strips a document's access controls.** The user may have permissions restrictions they rely on. This is exactly the "confident wrong answer" posture the project exists to avoid. Offer it as an explicit opt-in, never a default |
| **6.2.11.4.1-1**, unmapped fonts | `"no mapping table entry for BaseFont '/ZapfDingbats'"` — **the string `lookup_bundled_font` already returns** (`engine/fonts.py:216`) | D-06 and `CLAUDE.md:26-28` (bundled families only). Substituting Liberation for `Symbol` or `ZapfDingbats` would render *different glyphs*, not the same glyphs in a different face. 5/18 measured references |
| 6.2.11.4.1-1, `NOEMB` verdicts | Pass through `FontVerdict.reason` verbatim | `engine/encoding_table.py:334,356,489` already produce `"symbolic simple font, not embedded"` and `"Type0 descendant font not embedded"`. **Reuse those strings; do not mint new ones** |
| **6.3.3-1** | `"annotation of subtype /X has no appearance stream (rule 6.3.3-1)"` | Synthesizing an appearance stream means *inventing rendering*. That is Phase 7's flatten problem and it changes pixels by design. 5/25 measured incidence — the second most common blocker, and the one most likely to tempt a shortcut |
| 6.2.11.8-1 | `".notdef glyph referenced by a text-showing operator (rule 6.2.11.8-1)"` | See the `.notdef` finding above. Once the Phase 3 guard exists this becomes unreachable; until then it must be detected, not guessed at |
| 6.1.13-* | Numeric-limit violations | Truncating a real number or splitting an over-long string changes document content |

### The refusal report

`engine/recipe.py`'s `RecipeReport` (`:164`) is the established shape: an all-or-nothing outcome
(`D-11`) with a per-item named reason. PDF/A conversion should return the same shape, with the
rule ID in the reason string. This is deliberate: **when veraPDF later fails a document in CI, the
failing rule ID in the veraPDF report and the rule ID in our own refusal message are the same
string**, so a CI failure and a user-facing refusal are greppable against each other. That property
is free if the reason strings are built from rule IDs, and unrecoverable if they are prose.

Open question the planner must resolve, not assume: **all-or-nothing (D-11's posture) or
partial-with-report?** D-11 chose all-or-nothing for recipes and explicitly deferred `--partial` to
"the phase that has its own evidence." A PDF/A conversion that refuses the whole document because
one of 400 annotations lacks an appearance stream may be the wrong trade. I have no evidence either
way and am not guessing — see § *Open Questions* Q1.

## Architecture Patterns

### System Architecture Diagram

```
                          ┌─────────────────────────────────────────┐
   PDF bytes ────────────►│ engine.index.RunIndex  (Phase 2)        │
   (one parse, EXPO-05)   │  + A-7.1 extension: font_size_pt,       │
                          │    base_font/style, page geometry       │
                          └──────────────┬──────────────────────────┘
                                         │  list[RunRecord]
                                         ▼
                          ┌─────────────────────────────────────────┐
                          │ engine.blocks   (Phase 7, D-7.2)        │
                          │  renderer-agnostic list[Block]  (A-7.2) │
                          └───┬──────────────┬──────────────┬───────┘
                              │              │              │
              ┌───────────────┘              │              └───────────────┐
              ▼                              ▼                              ▼
   ┌────────────────────┐        ┌───────────────────────┐      ┌──────────────────────┐
   │ markdown.py/html.py│        │ export/docx.py        │      │ export/docx_warn.py  │
   │ (Phase 7 — already │        │  EXPO-07              │      │  EXPO-08             │
   │  passing Gate G6)  │        │  python-docx writer   │      │  fold over the SAME  │
   └────────────────────┘        │  ceiling: D-8.2 only  │      │  list[Block]         │
                                 └───────────┬───────────┘      └──────────┬───────────┘
                                             │ .docx                       │ counts
                                             ▼                             ▼
                                        download                    "3 tables and a
                                                                     2-column section
                                                                     detected"

   ── PDF/A path: a different consumer of the same document, never of engine.blocks ──

   PDF bytes ──►┌──────────────────────────┐   refuse (named rule ID)   ┌──────────────┐
                │ export/pdfa.py           ├──────────────────────────► │ PdfaReport   │
                │  1. audit  (rule scan)   │                            │ (RecipeReport│
                │  2. refuse-or-remediate  │                            │  shape)      │
                │  3. font remediation ────┼──► engine.recipe            └──────────────┘
                │       (identity edits)   │    engine.rewrite
                │  4. structural deletes   │    engine.fonts   ← Phase 3, unmodified
                │  5. OutputIntent + XMP   │
                │  6. save(min_version)    │
                └────────────┬─────────────┘
                             │ PDF/A-2b bytes
          ┌──────────────────┴───────────────────┐
          ▼ (runtime)                            ▼ (CI ONLY — never a served request)
      download                        docker run verapdf/cli:v1.30.2
                                        --flavour 2b --format json
                                        exit 0 = pass / 1 = invalid
                                              │
                                              ▼
                                      Gate G7a: fixture corpus,
                                      build fails on regression
```

### Recommended Project Structure

`find . -iname "*pdfa*" -o -iname "*docx*"` under `engine/`, `tools/`, `harness/` returns nothing —
both halves are greenfield inside an established codebase.

```
engine/
├── blocks.py               # PHASE 7 (D-7.2). Phase 8 CONSUMES. Never edits.
└── export/
    ├── pdfa.py             # NEW. EXPO-06. Audit -> refuse-or-remediate -> write -> save.
    │                       #   Imports engine.recipe / engine.rewrite / engine.fonts.
    │                       #   Imports NOTHING from engine.blocks (different consumer).
    ├── docx.py             # NEW. EXPO-07. The ONLY module that imports python_docx.
    │                       #   Imports engine.blocks. Imports nothing from pdfa.py.
    └── docx_warn.py        # NEW. EXPO-08. Or a function inside docx.py -- but see
                            #   Pattern 11: keeping it in the docx.py import subtree is
                            #   what makes `rm engine/export/docx*.py` a complete cut.
harness/
└── verapdf_gate.py         # NEW. G7a. Runs the pinned image over the fixture corpus,
                            #   parses the JSON report, fails on regression.
                            #   Mirrors harness/run_corpus_harness.py's existing shape.
tests/
├── test_pdfa.py            # NEW
├── test_gate_g7a.py        # NEW -- matches test_gate_g2a.py / test_gate_g2b.py precedent
├── test_export_docx.py     # NEW
└── test_docx_cuttable.py   # NEW -- Pattern 11's import-graph assertion
.planning/phases/08-pdf-a-then-docx/
└── DOCX-CEILING.md         # NEW, ORDERED FIRST. This file existing IS Gate G7b.
```

### Pattern 1: PDF/A font remediation is an *identity edit* through the pipeline that already exists

This is the highest-leverage finding on the PDF/A side, and it comes from reading
`engine/encoding_table.py` rather than from designing anything.

A non-embedded font already has a `FontVerdict` that says exactly what to do:

```python
# engine/encoding_table.py:330-337 -- verbatim
if not embedded:
    if symbolic:
        return FontVerdict("NOEMB", False, False, "symbolic simple font, not embedded")
    if _base_font_name(font) in STANDARD_14:
        return FontVerdict("T1-c", True, True)     # editable=True, substitution=True
    return FontVerdict("T1-d", True, True)         # editable=True, substitution=True
```

`substitution=True` means *"route this run through the bundled-font substitution path."* That path
— `plan_recipe` → `lookup_bundled_font` → `subset_font_for_family` → `embed_type0_font` →
`rewrite_run` — already exists, is already tested, and already emits the PDF/A-2b-conformant
Type0/CIDFontType2 output verified in the table above.

**So PDF/A font remediation is: build a recipe whose `new_text` equals each affected run's existing
text, and apply it.** The text does not change; the font does. Concretely:

- `run_needs_substitution` is not even consulted for these — `_resolve_op`
  (`engine/recipe.py:285-299`) enters the substitution branch on
  `verdict.state == "editable_substitution"` **or** `trigger.substitute`, and `T1-c`/`T1-d`
  produce the former.
- D-06's refusal is reused verbatim: `engine/recipe.py:286` calls `lookup_bundled_font`, and
  `:292-295` returns `mapping.reason` as the refusal. That is the `"no mapping table entry for
  BaseFont '/ZapfDingbats'"` string in the refusal table above, produced by code that already
  exists.
- **Layout does not move.** `CLAUDE.md:26-28`'s bundled-family choice is metric compatibility with
  Arial/Times/Courier, and `03-CONTEXT.md` D-07 states the consequence: *"a mapped substitution
  needs no width refitting."* Where a delta does appear, `engine/fit.py` and the proven TJ-refit
  (`TJ-REFIT-RESULTS.md`) absorb it. This satisfies `CLAUDE.md:23-25` (no reflow) directly.
- FONT-04's `/W` assertion and FONT-05's fresh-subset-tag rule apply unchanged, which is exactly
  what `08-CONTEXT.md` predicted: *"the plan should verify rather than rebuild."*

**What is genuinely new, and must be planned:** after substitution, the original non-embedded font
object may still sit in the page `/Resources /Font` dictionary, referenced by nothing. Whether
veraPDF flags an unreferenced non-embedded font is **not something I could determine from the
profile text** — rule 6.2.11.4.1-1's description says *"fonts used for rendering"*, but whether
veraPDF's object model builds a `PDFont` from an unused resource entry or only from `Tf` usage is
an implementation detail of the greenfield parser. See § *Open Questions* Q2; it is resolved by one
cheap experiment, not by more reading.

### Pattern 2: veraPDF in CI — a pinned image, not a JRE in `Dockerfile.ci`

```yaml
# .github/workflows/verapdf.yml (NEW) -- mirrors harness.yml's existing shape
- name: Validate PDF/A fixture corpus at PDF/A-2b
  run: |
    docker run --rm -v "$PWD:/data" \
      verapdf/cli@sha256:d5ee329657cf9bc4b2400392dd54c7d0a0ce9980ff6fa2da5590eebeec007cdb \
      --flavour 2b --format json /data/build/pdfa-fixtures/*.pdf > report.json
    # exit 0 = all conform; exit 1 = at least one does not
```

**CLI surface, verified:**

| Flag | Values | Source |
|------|--------|--------|
| `--flavour` / `-f` | `1a 1b 2a 2b 2u 3a 3b 3u 4 4e 4f ua1 ua2 wt1r wt1a`; `0` or omitted = auto-detect from metadata | docs.verapdf.org/cli/validation |
| `--format` | `text`, `raw`, `html`, `json` — *"Before veraPDF release 1.24 `raw` report was called `xml`… `mrr` report format is deprecated"* | same |
| `--success` / `--passed` | include passed checks (default: failures only) | same |

**Report shape** — failures carry the same `clause`/`testNumber` pair this document has been citing
throughout, which is what makes our refusal strings greppable against veraPDF output:

```xml
<validationReport ... isCompliant="false">
  <details>
    <rule specification="ISO 19005-1:2005" clause="6.6.1" testNumber="1"
          status="failed" passedChecks="0" failedChecks="1">
      <description>…</description><object>PDAction</object><test>…</test>
      <check status="failed"><context>…</context></check>
```

**Exit codes** — *not officially documented*; veraPDF issue #1562 ("cli: documentation for return
codes needed") is **still open**. The values below are reverse-engineered from the source by the
issue reporter and then **confirmed by a veraPDF contributor (`bdoubrov`) in that thread**, and the
first five are additionally asserted by veraPDF's own regression script
`veraPDF-apps/tests/exit-status.sh`:

| Code | Meaning |
|------|---------|
| 0 | All files validated **and conform** |
| 1 | All files validated, **at least one does not conform** |
| 2 | Invalid command line parameters |
| 3 | Out of Java heap space *(the test script notes a "HACK: accept alternative exit code 1 for out-of-memory errors" — so **1 is not unambiguously "invalid"**)* |
| 4 | No files to process |
| 6 | I/O exception |
| 7 | Failed to parse one or more files |
| 8 | Some PDFs encrypted |
| 9–12 | veraPDF/JAXB/multiprocess/interrupt exceptions |
| 5 | does not exist ("for historical reasons") |

`[VERIFIED: github.com/veraPDF/veraPDF-library issue #1562 incl. contributor confirmation; docs.verapdf.org/cli/validation]`

**Planning consequence, and it is not cosmetic:** because exit 1 can also mean OOM, and because
codes 3/6/7/8/9–12 all mean *"the check did not happen"*, `harness/verapdf_gate.py` **must parse
the JSON report's `isCompliant` rather than branch on the exit code alone**. A gate that treats
"non-zero means invalid" will report a JVM heap failure as a conformance regression and send
someone hunting for a bug in the font code. Treat any exit code other than 0 or 1 as *infrastructure
failure*, distinct from *conformance failure*, and fail the build differently.

**Why a separate image rather than `Dockerfile.ci`.** `Dockerfile.ci` is built by both
`harness.yml` and `corpus.yml`. Adding `default-jre-headless` plus the veraPDF installer to it
makes every one of those jobs pull ~180 MB more for a tool they never invoke. A separate pinned
image is smaller, and keeps the existing image's careful version-pinning comment block
(`Dockerfile.ci:9-36`) about renderer-version drift focused on renderers.

### Pattern 3: refusals reuse `RecipeReport`, and reasons are built from rule IDs

Do not invent a report type. `engine/recipe.py:164`'s `RecipeReport` already carries an
all-or-nothing `ok` plus per-item named reasons, and `apply_recipe`'s `_refuse_at`
(`engine/recipe.py:471`) is the established minting site. The PDF/A audit produces the same shape.

The one addition worth making is that every reason string **starts with the veraPDF rule ID**:

```
"6.1.3-2: PDF/A forbids encryption; this document is encrypted"
"6.3.3-1: annotation of subtype /Square has no appearance stream (page 4)"
"6.2.11.4.1-1: no mapping table entry for BaseFont '/ZapfDingbats'"
```

`grep -o '^[0-9.]*-[0-9]*'` over our refusals and over veraPDF's `clause`/`testNumber` attributes
then produces two comparable sets. That is the cheapest possible way to keep the converter's own
model of the standard honest against the validator's, and it costs one prefix.

### Pattern 4: where PDF/A attaches to the Phase 3 save pipeline

PDF/A conversion is **a recipe plus a post-pass**, not a new save path:

```
apply_recipe(pdf_path, identity_edits_for_nonembedded_runs)   # Phase 3, unmodified
        │  (all-or-nothing, D-11; refuses by name via lookup_bundled_font)
        ▼
structural remediation on the open pikepdf handle                # deletions, /F flags
        ▼
OutputIntent + XMP write                                          # Pattern 1's verified recipe
        ▼
pdf.save(min_version="1.7")                                       # preserve_pdfa defaults True
```

Two things this ordering buys, both of which the reverse ordering loses:

1. **Font remediation runs first**, so `apply_recipe`'s D-11 all-or-nothing refusal fires before any
   structural mutation. A document that is going to be refused is refused before it is modified.
2. **The XMP write is last**, after every mutation. `pikepdf`'s `open_metadata()` commits on
   `__exit__`; writing it early and then mutating the object graph risks a stale
   `xmp:MetadataDate`. Not a conformance rule at 2b — just cheap correctness.

`Pdf.save()`'s `preserve_pdfa: bool = True` default (`pikepdf/_core.pyi:2829-2831`, *"Ensures that
the file is generated in a manner compliant with PDF/A and other stricter variants"*) means the
save call needs **no** special argument beyond `min_version`. Do not pass
`object_stream_mode=generate` here reflexively because Phase 7's compress does (A-7.6) — object
streams are legal in PDF/A-2, but they change the byte layout that rules 6.1.7.1-1/-2 and 6.1.9-1
police, and there is no reason to take that risk in the same phase that introduces the validator.
Leave it at `preserve` and let Phase 7 own compression.

### Pattern 5: the G7a fixture corpus — and the trap in "veraPDF passes"

ROADMAP criterion 1 says *"across a fixture corpus in CI, not on spot checks."* Composition, from
`corpus/manifest.json` measured this session (`217` public documents; category counts:
`subset_fonts` 140, `symbolic_fonts` 133, `contents_array` 114, `inline_images` 68,
`type0_identity_h` 33, `form_xobjects` 19, `malformed` 17, `annotation_appearance_streams` 13,
`cid_keyed_cff` 12, `encrypted` 12, `type3` 12, `justified_right_aligned` 3, `tables` 3,
`ocr_scan` 2, `vector_outlined_text` 1):

| Tier | Size | Selection | Assertion |
|------|------|-----------|-----------|
| **A — conversion output must validate** | ~40 documents | Stratified over the categories that map to measured PDF/A risk: all 13 `annotation_appearance_streams`, all 12 `type3`, all 12 `cid_keyed_cff`, all 33 `type0_identity_h` capped at ~10, plus a random tail. **Reuse `corpus/manifest.json`'s existing `categories` field as the selector** — do not add a second manifest | veraPDF `isCompliant="true"` at `--flavour 2b` for every converted output |
| **B — refusals must fire** | the 12 `encrypted` + the 17 `malformed` | Already tagged | The converter refuses, with the expected rule ID in the reason. **Never** silently produces output |
| **C — the validator itself is wired up** | 2–4 files | veraPDF's own PDF/A-2b conformance fixtures, *known-failing* | The gate reports `isCompliant="false"` and a non-zero exit. Proves the gate can fail |

Tier C exists because of the trap: **a converter that refuses every document trivially satisfies
"every emitted PDF/A file validates."** The gate must therefore assert *two* numbers, not one:

```
assert every_converted_output_is_compliant          # the obvious one
assert conversion_success_count >= FLOOR            # the one that stops the gate being vacuous
```

`FLOOR` should be set from the tier-A baseline measured on the *unmodified* corpus before any
remediation code is written — which is why the plan should order "measure the unmodified baseline"
as its own task, before the converter exists. `harness/run_corpus_harness.py`'s existing
before/after structure is the model; do not stand up a parallel one (`08-CONTEXT.md` says so
explicitly).

**Licence precedent for tier C is already established.** `corpus/sources.md:24` records the
veraPDF corpus as **CC BY 4.0** and three of its fixtures are already vendored
(`verapdf_isartor_malformed_trailer.pdf`, `verapdf_inline_image_fixture.pdf`,
`verapdf_type3_font_fixture.pdf`), with the substitution disclosed at `corpus/sources.md:77-84`
per D-04. Adding PDF/A-2b conformance fixtures follows the same path — no new licence question.

### Pattern 6: OOXML — `python-docx`, quarantined

`08-CONTEXT.md` leaves "hand-built XML into a zip container vs. a permissively-licensed library" to
discretion. The honest comparison:

| | Hand-built (`zipfile` + `xml.etree`, both stdlib) | `python-docx` 1.2.0 |
|---|---|---|
| `[Content_Types].xml`, `_rels/.rels`, `word/document.xml` | Genuinely easy — a few dozen lines | Handled |
| `word/styles.xml` defining Normal + Heading 1..N + a table style Word accepts | **The actual cost.** Several hundred lines of XML whose failure mode is Word's silent "unreadable content — recover?" dialog, which is exactly the trust-eroding outcome `PITFALLS.md:426` warns about | Bundled, Word-validated `default.docx` template |
| Inline images (`word/media/` + rels + EMU sizing) | Manual rel-id bookkeeping | `add_picture()` |
| Ruled tables | Manual `tblBorders` | `add_table(style=…)` |
| New runtime dependencies | **0** | 3 (`python-docx`, `lxml`, `typing_extensions`) — all licence-verified above |

**Recommendation: `python-docx`.** The ladder says never add a dependency for what a few lines can
do — but `styles.xml` is not a few lines, and what you are buying is not the XML serializer, it is
a style part Microsoft Word has been validated against. Hand-rolling it inverts the risk this whole
phase exists to control.

**Quarantine it as an optional dependency group**, which is how D-8.5 becomes a `pyproject.toml`
fact rather than a promise:

```toml
[project.optional-dependencies]
docx = ["python-docx==1.2.0"]
```

Then `uv sync --locked` (core) never installs `lxml`, and cutting DOCX is `rm engine/export/docx*.py`
plus deleting four lines. **Consequence the planner must not miss:** `license-gate.yml` currently
runs `uv sync --locked`; with an extra, it must run `uv sync --locked --all-extras` or the DOCX
closure never reaches `tools/license_gate.py` at all. This is the same class of blind spot the
maintainer just found in `client/package-lock.json` — an extra that CI does not install is an
extra CI does not check.

### Pattern 7: what Phase 7's block layer must hand over — and what is *not* there yet

**Read A-7.1 before planning any DOCX task.** `07-CONTEXT.md`'s amendment records that `RunRecord`
carries **no font size and no font identity** today: size lives transiently in
`ClusterAttrs.effective_em` (`engine/clusterer.py:127,152`) and is discarded when `RunRecord` is
built (`engine/clusterer.py:308-315`); `GlyphRecord.font_id` is an opaque per-page-interned integer
with no reverse lookup to `/BaseFont` (`engine/classify_run.py:23-24`). A-7.1's ruling makes
extending the index a **Phase 7 Wave 0 task**.

**Phase 8 therefore depends on a Phase 7 Wave 0 deliverable, not on Phase 7's headline output.**
That is a sharper dependency than "Phase 8 waits on Gate G6" and the planner should state it as
such: if Phase 7 ships Markdown export without the A-7.1 extension, DOCX's heading inference has
nothing to cluster on and the D-8.2 ceiling is unreachable.

The contract Phase 8 needs from `engine.blocks`, expressed as the minimum fields — and A-7.2 has
already ruled the output *renderer-agnostic plain data*, so Phase 8 extends it additively rather
than reshaping it:

| Block field | Used by | Ceiling clause it serves |
|-------------|---------|--------------------------|
| `kind: "heading" \| "paragraph" \| "list_item" \| "table_row" \| "image"` | `docx.py` dispatch | all |
| `level: int \| None` | `add_heading(level=…)` | "headings by font-size clustering" |
| `runs: list[RunRecord]` with `font_size_pt` and bold/italic | run-level formatting | "bold/italic" |
| `bbox` / page geometry | ruled-table cell assignment; column-count detection for the EXPO-08 *warning* | "ruled tables only"; EXPO-08 |
| `column_index` or a page-level column count | **EXPO-08 warning only — never to reorder** | multi-column is *excluded*; detecting it to warn is in scope, acting on it is not |

That last row is the ceiling's sharpest edge and the planner should call it out explicitly: **D-8.4
requires *detecting* a 2-column section in order to say "a 2-column section detected"; D-8.2
forbids *using* that detection to reorder reading order.** Detect, report, do not act.

### Pattern 8: font-size clustering for headings — the lazy version, and its named ceiling

Given `font_size_pt` on `RunRecord` (A-7.1), heading inference is a fold, not an algorithm:

```python
# engine/blocks.py or engine/export/docx.py -- ~15 lines, no dependency
# ponytail: modal-size heuristic; upgrade to k-means/DBSCAN only if corpus evidence
# shows multi-modal body text (mixed 10pt/11pt paragraphs), which nothing measured yet does.
from collections import Counter

def body_size(runs) -> float:
    """The modal font size, weighted by glyph count -- body text is the size most GLYPHS
    are set in, which is not the size most RUNS are set in (headings are short runs)."""
    c = Counter()
    for r in runs:
        c[round(r.font_size_pt, 1)] += len(r.glyphs)
    return c.most_common(1)[0][0]

def heading_level(size: float, body: float, distinct_larger: list[float]) -> int | None:
    if size < body * HEADING_RATIO:          # HEADING_RATIO: see Open Question Q3
        return None
    return min(distinct_larger.index(size) + 1, 3)   # descending sizes -> H1, H2, H3
```

Three properties worth stating, because each prevents a plausible wrong turn:

- **Weight by glyph count, not run count.** A page with 8 headings and 6 body paragraphs has more
  heading *runs* than body runs; it has vastly more body *glyphs*. Counting runs inverts the answer
  on exactly the documents headings matter for.
- **Round to 0.1pt before counting.** `effective_em` is a device-space float (`engine/space_threshold.py:118-122`)
  and 11.000001 vs 10.999999 are the same size to a human and different keys to a `Counter`.
- **Cap at H3.** The ceiling says "headings", not "a document outline". Mapping every distinct
  larger size to its own level manufactures an H7 from a title page.

`HEADING_RATIO` cannot be chosen honestly right now — see § *Open Questions* Q3. It is a
corpus-measured constant, and the corpus has **no `headings` category at all** (A-7.4 measured
this: zero multi-column documents, three `tables`, no headings tag). Both the constant and its
fixture are Wave 0 work.

**Explicitly not researched, per D-8.2/D-8.6 and ROADMAP criterion 2:** unruled-table detection
from whitespace alignment, multi-column reading order, header/footer reconstruction, and
round-trip. Researching these is the risk the phase guards against; each is a follow-up phase's
question, and each would need its own evidence.

### Pattern 9: EXPO-08's warning is a fold over the *same* `list[Block]` the writer consumes

D-8.4's justification is that the warning is "cheap because the layout analysis already ran." Make
that structurally true rather than incidentally true:

```python
def degradation_warning(blocks: list[Block]) -> list[str]:
    """EXPO-08. Reads the SAME list the writer is about to consume -- never a second scan."""
    out = []
    tables = sum(1 for b in blocks if b.kind == "table_row" and b.starts_table)
    if tables:
        out.append(f"{tables} table{'s' if tables != 1 else ''} detected — "
                   "only ruled tables are reconstructed; unruled tables become paragraphs")
    cols = max((b.column_count for b in blocks if b.column_count), default=1)
    if cols > 1:
        out.append(f"a {cols}-column section detected — output will be single-column")
    ...
```

The property that matters: **the warning cannot disagree with what the writer does**, because both
read the same objects. A warning computed from a separate document scan can — and eventually will —
say "3 tables" while the writer emits 2, and that is a bug report about honesty, which is the one
category this product cannot afford. One argument, one source.

The natural place for this is `docx_warn.py` (or a function in `docx.py`); either satisfies
Pattern 11 as long as it sits inside the cuttable subtree. It must **not** live in `engine/blocks.py`
— that would put DOCX-specific vocabulary into a Phase 7 module and break the cut.

### Pattern 10: the G7b artifact — `DOCX-CEILING.md`

`08-CONTEXT.md`: *"G7b is unusual in that it is satisfied by a written paragraph existing before
work starts… the plan should order that task first and make its acceptance criterion a file
assertion."* Reading the three precedent documents, the shared skeleton is:

| Element | `PLAYA-DECISION.md` | `TJ-REFIT-RESULTS.md` | `G2B-GATE-RESULTS.md` |
|---------|--------------------|-----------------------|------------------------|
| `#` title naming the artifact | ✓ | ✓ | ✓ |
| `**Date:**` + `**Requirement:**` front matter | ✓ (`:3-6`) | ✓ | ✓ (`:3-8`) |
| `## Decision` with a **bolded one-line verdict** | ✓ (`:8`) | — (results doc) | ✓ (`:10`, "**GO.**") |
| `## Evidence` **with the date in the heading** | ✓ (`:16`) | ✓ (`:15,34`) | ✓ (`:15`) |
| A verbatim reproduction command | ✓ (`:18`) | ✓ | ✓ (`:19-21`) |
| Tables of measured results | ✓ (`:22-27`) | ✓ (`:34-46`) | ✓ (`:31-41`) |
| `## Why <verdict>` | ✓ (`:69`) | — | ✓ (`:49`) |
| **`## What was NOT tested (explicitly out of scope…)`** | ✓ (`:85`) | ✓ (`:72`) | ✓ (`:73`) |

G7b differs from all three in one way that must be handled deliberately: **it is written *before*
the work, so it has no measurements.** Its evidence is the requirement text itself. The adapted
shape:

```markdown
  # DOCX Scope Ceiling

  **Date:** <written before any DOCX task starts>
  **Requirement:** EXPO-07 / ROADMAP Phase 8 criterion 2 (Gate G7b) / 08-CONTEXT.md D-8.2, D-8.6

  ## Decision

  **The DOCX exporter will attempt exactly the following and nothing else.** <the list, verbatim>

  ## In scope (verbatim from ROADMAP criterion 2)
  - single-column body text
  - headings by font-size clustering
  - bold/italic
  - inline images
  - ruled tables only
  - everything else as plain paragraphs

  ## What is explicitly NOT attempted (explicitly out of scope)
  - unruled tables            - multi-column reading order
  - header/footer reconstruction  - round-trip back into the tool
  <each with the one-line reason, so a future reader does not re-derive a different one>

  ## Why a ceiling rather than a best-effort target
  <Risk #8; PITFALLS.md:418-433; the "if we just improved table detection a bit" tripwire, D-8.6>

  ## How this document is enforced
  <the file assertion below; and: widening this list is a new phase, not a task>
```

**Acceptance criterion, as a file assertion** — this is what makes G7b a gate rather than a note:

```python
# tests/test_gate_g7b.py
CEILING = Path(".planning/phases/08-pdf-a-then-docx/DOCX-CEILING.md")

def test_g7b_ceiling_document_exists_and_names_every_exclusion():
    assert CEILING.exists(), "Gate G7b: the ceiling must be written BEFORE any DOCX work"
    text = CEILING.read_text()
    for clause in ("single-column body text", "font-size clustering", "bold/italic",
                   "inline images", "ruled tables only"):
        assert clause in text
    for excluded in ("unruled tables", "multi-column reading order",
                     "header/footer reconstruction", "round-trip"):
        assert excluded in text
    assert "## Decision" in text and "explicitly out of scope" in text
```

**Order this task first in the plan**, and make the DOCX writer tasks depend on it. That ordering
*is* D-8.2 ("writing this ceiling into the phase definition is a task, ordered first").

### Pattern 11: D-8.5 independent cuttability, made machine-checkable

Three assertions, in increasing cost. The first two run per-commit; the third at the phase gate.

**(a) No reverse dependency — an AST scan.** Nothing outside the DOCX subtree may import from it,
and nothing outside it may import `docx`. This generalizes the same static-scan technique
`07-RESEARCH.md` proposes for EXPO-05 and A-7.5 mandates:

```python
# tests/test_docx_cuttable.py
DOCX_MODULES = {"engine.export.docx", "engine.export.docx_warn"}

def test_nothing_outside_the_docx_subtree_imports_it():
    for path in Path("engine").rglob("*.py"):
        if path.stem.startswith("docx"):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for m in mods:
                assert m != "docx" and not m.startswith("docx."), f"{path}: imports python-docx"
                assert m not in DOCX_MODULES, f"{path}: depends on the cuttable DOCX subtree"
```

**(b) The dependency is optional, not core.** A three-line assertion on `pyproject.toml` that
`python-docx` appears under `[project.optional-dependencies] docx` and **not** under
`[project] dependencies`. This is what makes "cut DOCX" also mean "drop `lxml`", and it is the
half a pure import-graph check misses.

**(c) The literal criterion, at the phase gate only.** ROADMAP criterion 5 is *"deleting it leaves
every other export still passing its gate."* Assert it literally: copy the tree to a tmpdir, delete
`engine/export/docx*.py` and `tests/test_export_docx.py`, run the rest of the suite, expect green.
Expensive (a full suite run) and therefore **not** a per-commit test — but it is the only one that
proves the claim rather than a proxy for it, and (a)+(b) passing while (c) fails is exactly the
interesting case.

`(a)` and `(b)` are cheap enough to run on every commit and will catch 100% of accidental
couplings introduced by an editor's autocomplete. `(c)` catches the ones that are not imports at
all — a shared fixture, a `conftest.py` entry, a CI step that references the module by path.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| Deciding whether a PDF is PDF/A-2b conformant | Your own rule checker | `verapdf/cli:v1.30.2`, `--flavour 2b` | 144 rules, many of them byte-level (`6.1.7.1-2`: "the `endstream` keyword shall be preceded by an EOL marker"). A partial reimplementation that says "conformant" is worse than no feature — the roadmap's own words |
| An sRGB ICC profile for the OutputIntent | Vendoring a binary ICC asset, or synthesizing one | `PIL.ImageCms.createProfile("sRGB")` — Pillow is already pinned | 588 bytes, `mntr`/`RGB `/v4.4, satisfies 6.2.3-1 and 6.2.4.2-1. Measured this session. Zero new dependencies, zero new licence questions |
| The XMP packet + `pdfaid` schema | Emitting RDF/XML by hand | `pdf.open_metadata()` with `m['pdfaid:part']`, `m['pdfaid:conformance']` | pikepdf registers `pdfaid`, `pdfaExtension`, `pdfaProperty`, `pdfaSchema` prefixes (`pikepdf/models/metadata/_constants.py:15-18,37-40`) and emits a packet header with neither `bytes=` nor `encoding=`, which is rules 6.6.2.1-2/-3 satisfied for free |
| Embedding a font to fix 6.2.11.4.1-1 | A new simple-TrueType embedding path | `apply_recipe` with identity edits — Pattern 1 | Phase 3 already emits conformant Type0/CIDFontType2. A second embedding path would need its own `/Widths`, `/FirstChar`, `/LastChar`, `/Encoding` and `cmap` conformance work (rules 6.2.11.2-4/5/6, 6.2.11.6-2), all of which the composite path sidesteps |
| Word-acceptable `styles.xml` | Hand-built OOXML | `python-docx`'s bundled `default.docx` | Pattern 6 |
| Heading detection | k-means / DBSCAN / a layout model | A weighted `Counter` modal size, ~15 lines | Pattern 8. Nothing measured suggests body text is multi-modal |
| Cross-engine validation of the converted output | A new harness | `harness/run_corpus_harness.py` + `harness/masked_diff.py` | `08-CONTEXT.md` says so explicitly: *"Reuse `harness/`'s existing CI wiring rather than standing up a parallel one"* |

**Key insight:** the PDF/A half of this phase adds **zero new runtime dependencies**. Every library
it needs — pikepdf for the object graph, fontTools for subsetting, Pillow for the ICC profile — is
already pinned and already proven on the corpus. The only new artifact is a CI image. That is a
much smaller phase than "PDF/A conversion" sounds like, and the planner should size it accordingly:
the work is in the *audit and refusal classification*, not in the writing.

## Common Pitfalls

### Pitfall 1: branching on veraPDF's exit code alone

**What goes wrong:** the gate reports a JVM out-of-memory failure as a PDF/A conformance
regression, and someone spends a day looking for a bug in the font code.

**Why:** exit 1 nominally means "at least one file does not conform," but veraPDF's own regression
script carries a `HACK: accept alternative exit code 1 for out-of-memory errors`, and codes 3, 6,
7, 8 and 9–12 all mean *the check did not happen* rather than *the check failed*.

**How to avoid:** parse `isCompliant` from the JSON/raw report. Treat exit ∉ {0, 1} as
infrastructure failure and surface it differently from a conformance failure.

**Warning sign:** a CI step whose entire logic is `docker run … && echo ok`.

### Pitfall 2: `/S /GTS_PDFA2`

**What goes wrong:** you write a PDF/A-2 output intent with subtype `/GTS_PDFA2` because the part
number is 2. veraPDF then reports failures in 6.2.4.3-2/3/4 (device colour with no output intent)
and 6.2.10-2 (transparency with no group) — five failing rules, none of which mentions the output
intent, all of which point at colour.

**Why:** `GTS_PDFA1` is the output-intent subtype name introduced by ISO 19005-1 and *retained* by
ISO 19005-2. The `1` is not a part number.

**How to avoid:** `/S = /GTS_PDFA1` for every PDF/A part. Assert it in a unit test so nobody
"corrects" it later.

**Warning sign:** colour-space rule failures on a document that uses no colour.

### Pitfall 3: assuming the inherited-`/Resources` rule does not apply because a sample said 0/25

**What goes wrong:** rule 6.2.2-2 (`inheritedResourceNames == ''`) is skipped as a non-issue, and
it fires on the private corpus tier or on a user's document.

**Why:** my measurement was 25 documents and checked only whether a *page* dictionary carried its
own `/Resources`. Rule 6.2.2-2 is about **any content stream** that references objects — including
Form XObjects, whose `/Resources` inheritance `engine/shared_xobjects.py` exists to handle, and
whose behaviour I did not probe.

**How to avoid:** implement the push-down anyway (it is cheap and idempotent), and let the tier-A
fixture corpus tell you whether it was needed. Do not cite my 0/25 as evidence it is unnecessary —
cite it as evidence it is *not the top priority*.

**Warning sign:** the phrase "the corpus shows this never happens" applied to a 25-document sample.

### Pitfall 4: a G7a gate that passes because the converter refuses everything

**What goes wrong:** "every emitted PDF/A file validates" is trivially true when zero files are
emitted. The gate goes green while the feature does nothing.

**How to avoid:** the two-number assertion in Pattern 5 — compliance *and* a conversion-success
floor measured against an unmodified baseline taken before the converter exists.

**Warning sign:** the conversion success rate is not a number anyone can quote.

### Pitfall 5: `.notdef` reaching the content stream

Covered in full above. Restated here because it is the one *code* defect this research found:
`engine/fonts.py:449-453` asserts by construction something that `shape_glyph_names` measurably
does not guarantee. **Warning sign:** any docstring containing "BY CONSTRUCTION" that is not backed
by a test — this one has `tests/test_fonts.py:705` testing `subset_cid_widths`'s *output* shape, but
nothing testing that `.notdef` never enters its *input*.

### Pitfall 6: DOCX scope creep arriving as a bug report

**What goes wrong:** a user files "the table came out wrong," it is triaged as a defect rather than
as the documented ceiling, and table-detection work starts.

**Why:** `PITFALLS.md:426` — *"Users do not perceive DOCX export as a separate lower-fidelity
feature. They compare it to Acrobat's… and they file it as a bug in your PDF editor."*

**How to avoid:** `DOCX-CEILING.md` exists and is linked from the EXPO-08 warning text. A report
against an excluded capability closes as "outside the documented ceiling — see DOCX-CEILING.md",
which is a *decision*, not a *judgement call*. That is what the written paragraph buys.

**Warning sign:** the literal sentence D-8.6 names — "if we just improved table detection a bit."

## Code Examples

### The corpus pre-flight probe (the measurement this document's numbers come from)

```python
# Reproduces the "rules that will actually bite" table. Stratified sample, bounded scan.
import json, random, pikepdf, collections, os
from engine.fonts import lookup_bundled_font
docs = json.load(open('corpus/manifest.json')); random.seed(8)
pick = lambda cat, n: [d for d in docs if cat in d.get('categories', [])][:n]
sample = []
for cat, n in [('subset_fonts',5),('type0_identity_h',4),('annotation_appearance_streams',4),
               ('inline_images',3),('type3',3),('malformed',3),('tables',3),
               ('encrypted',2),('form_xobjects',3)]:
    for d in pick(cat, n):
        if d not in sample: sample.append(d)
sample += random.sample([d for d in docs if d not in sample], 6)
for d in sample:
    pdf = pikepdf.open(os.path.join('corpus/public', d['filename']))
    for i, page in enumerate(pdf.pages):
        if i >= 25: break                      # bounded: no full-corpus sweep
        res = page.obj.get('/Resources') or {}
        for _, f in (res.get('/Font') or {}).items():
            ...                                # embedded? mapped? -> the table above
```

### Verifying the emitted Type0 font against the font rules

```python
# Source: this session's live call. The evidence behind the 12-PASS/1-AT-RISK table.
from engine.fonts import shape_glyph_names, subset_font_for_family, subset_cid_widths
from fontTools.ttLib import TTFont
import io
names = shape_glyph_names("Sans", "Regular", "Hello, world! 123")
s = subset_font_for_family("Sans", "Regular", frozenset(names))
f = TTFont(io.BytesIO(s.data))
assert len(f["cmap"].tables) > 0                     # rule 6.2.11.6-1 (2 subtables observed)
assert f.getGlyphOrder()[0] == ".notdef"
w = subset_cid_widths(s)                             # scaled *1000/upem at fonts.py:461
assert all(abs(round(v) - v) <= 1 for v in w.values())   # rule 6.2.11.5-1
```

### The `.notdef` reproduction

```python
from engine.fonts import shape_glyph_names
assert shape_glyph_names("Sans", "Regular", "A\U0001F600B") == ("A", ".notdef", "B")
# -> rule 6.2.11.8-1 violation once this reaches a text-showing operator,
#    and /W has no entry for CID 0 (subset_cid_widths starts at GID 1, fonts.py:462)
```

## State of the Art

| Old approach | Current approach | When changed | Impact here |
|--------------|------------------|--------------|-------------|
| Ghostscript for PDF→PDF/A | `pikepdf` + `fontTools`, Ghostscript-free | `pdftopdfa` 0.9.0 (MPL-2.0) proved the shape | `SUMMARY.md:112` already resolved this against ARCHITECTURE.md's sidecar diagram. Ghostscript is AGPL and is not needed |
| PDF/A-1b as the default target | PDF/A-2b | ISO 19005-2:2011 | Transparency permitted, JPEG2000 permitted, `/CIDSet` no longer required, docinfo↔XMP consistency dropped. **Every one of those makes conversion easier**, which is why D-8.1's level choice is load-bearing rather than arbitrary |
| veraPDF PDFBox parser | veraPDF **greenfield** parser | veraPDF consortium: *"support for PDFBox parser is not guaranteed to be available long term"* | Use the default (greenfield). Do not pass a parser flag |
| `mrr` / `xml` report format | `raw` (and `json`) | veraPDF 1.24 | *"`xml` and `mrr` refer to the same report format, and `mrr` is deprecated."* Use `json` |

**Deprecated/outdated in this project's own notes:**
- `.planning/research/STACK.md:57` names veraPDF **1.31.32**. No such Docker tag exists (see § *Standard Stack*). Pin the digest instead.
- `STACK.md:100`'s `apt-get install … default-jre-headless` + "veraPDF installed from its own installer JAR" — superseded by the pinned image, except as the local-dev fallback below.

## Environment Availability

| Dependency | Required by | Available locally | Version | Fallback |
|------------|------------|-------------------|---------|----------|
| `uv` | everything | ✓ | 0.10.4 | — |
| `pikepdf` / `fontTools` / `Pillow` / `uharfbuzz` | the whole PDF/A path | ✓ | 10.11.0 (qpdf 12.3.2) / 4.63.0 / 12.3.0 / 0.56.0 | — |
| `qpdf` CLI | structural check | ✓ | 12.4.0 | — |
| **`docker`** | **the veraPDF gate as specified, and `harness.yml`/`corpus.yml` as they already exist** | **✗ — not installed, daemon not reachable** | — | **CI has it** (both existing workflows run `docker build`). Locally: see below |
| `java` | veraPDF JAR fallback | ✓ | OpenJDK 26.0.1 | — |
| `verapdf` CLI | local iteration | ✗ | — | Install the greenfield JAR — Java is present |
| `python-docx` | EXPO-07 | ✗ (not yet a dependency) | would be 1.2.0 | — |

**Missing dependencies with no fallback:** none.

**Missing with a fallback — and this one shapes the design:** Docker is unavailable on the
development machine, so **the developer cannot run the G7a gate locally as specified.** Iterating
on a PDF/A converter without being able to run the validator is exactly the slow loop this phase
cannot afford. Java 26 *is* available, so the veraPDF JAR is a working local path.

Lazy accommodation, one line, no abstraction: `harness/verapdf_gate.py` reads the validator command
from an env var with the Docker invocation as its default.

```python
VERAPDF = os.environ.get("VERAPDF_CMD", "docker run --rm -v {cwd}:/data verapdf/cli@sha256:d5ee…")
# local: export VERAPDF_CMD="/opt/verapdf/verapdf"
```

Do not build a validator-backend abstraction. One env var covers both callers, and CI never sets it.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥9.1.1 (already configured — `pyproject.toml` `[dependency-groups] dev`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths=["tests"]`, `pythonpath=["."]`, `corpus` marker for full-corpus-sweep tests |
| Quick run command | `uv run --frozen pytest -q -m "not corpus"` |
| Full suite command | `uv run --frozen pytest -q` |
| Type check | `uv run --frozen mypy engine/` (strict; `files = ["engine"]`; zero `# type: ignore`) |
| New mypy override required | `python-docx` ships no `py.typed`; add a **scoped** `[[tool.mypy.overrides]] module = ["docx.*"]` `ignore_missing_imports = true`, matching the existing `fontTools.*` / `uharfbuzz.*` precedent. Never a blanket override |
| Validator (CI) | `docker run --rm -v "$PWD:/data" verapdf/cli@sha256:d5ee329657cf9bc4b2400392dd54c7d0a0ce9980ff6fa2da5590eebeec007cdb --flavour 2b --format json` |
| Validator (local) | `VERAPDF_CMD` env var → the greenfield JAR (Java 26.0.1 present; Docker is **not** available locally) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| **G7b** | The ceiling document exists **before** any DOCX work, names all five in-scope clauses and all four exclusions, and carries a `## Decision` header and an out-of-scope section (`PLAYA-DECISION.md` precedent) | unit (file assertion) | `pytest tests/test_gate_g7b.py::test_g7b_ceiling_document_exists_and_names_every_exclusion -x` | ❌ Wave 0 |
| **G7b** | No plan task widens the ceiling — the four excluded capabilities appear in no module docstring or function name under `engine/export/docx*` | unit, negative case | `pytest tests/test_gate_g7b.py::test_no_docx_module_claims_an_excluded_capability -x` | ❌ Wave 0 |
| EXPO-06 | Emitted Type0/CIDFontType2 satisfies the font rules: `/CIDToGIDMap` present, `cmap` non-empty, `/W` within 1 unit of `hmtx` (rules 6.2.11.3.2-1, 6.2.11.6-1, 6.2.11.5-1) | unit | `pytest tests/test_pdfa.py::test_emitted_type0_font_satisfies_pdfa2b_font_rules -x` | ❌ Wave 0 |
| EXPO-06 | `.notdef` never reaches a text-showing operator — `shape_glyph_names` refuses by name instead of returning `.notdef` (rule 6.2.11.8-1; **the defect measured this session**) | unit, negative case | `pytest tests/test_fonts.py::test_shape_glyph_names_refuses_rather_than_emitting_notdef -x` | ❌ Wave 0 |
| EXPO-06 | Converted output carries XMP with `pdfaid:part=2`/`conformance=B`, packet header has no `bytes=` or `encoding=` attribute (rules 6.6.2.1-1/-2/-3, 6.6.4-*) | unit | `pytest tests/test_pdfa.py::test_output_xmp_declares_pdfa_2b_and_omits_forbidden_attrs -x` | ❌ Wave 0 |
| EXPO-06 | Output intent is `/S /GTS_PDFA1` (**not** `/GTS_PDFA2`) with an `mntr`/`RGB `/v<5.0 ICC profile (rules 6.2.3-1, 6.2.4.2-1) | unit | `pytest tests/test_pdfa.py::test_output_intent_subtype_is_gts_pdfa1_with_srgb_profile -x` | ❌ Wave 0 |
| EXPO-06 | File header is `%PDF-1.[0-7]` + four bytes >127; trailer has `/ID` and no `/Encrypt`; no data after final EOF (rules 6.1.2-1/-2, 6.1.3-1/-2/-3) | unit | `pytest tests/test_pdfa.py::test_saved_file_structure_satisfies_clause_6_1 -x` | ❌ Wave 0 |
| EXPO-06 | Prohibited features deleted: `/Names /JavaScript`, catalog+page `/AA`, `/Requirements`, `/AlternatePresentations`, `/PresSteps`, `/XFA`, `/NeedAppearances` (rules 6.5.1-1, 6.5.2-1/-2, 6.11-1, 6.10-1/-2, 6.4.2-1, 6.4.1-3) | unit | `pytest tests/test_pdfa.py::test_prohibited_features_removed_and_each_removal_reported -x` | ❌ Wave 0 |
| EXPO-06 | Non-embedded **mapped** font is embedded via the identity-edit path; layout does not move (text matrix after the run unchanged) | unit + pixel-diff | `pytest tests/test_pdfa.py::test_nonembedded_base14_font_embedded_without_moving_layout -x` | ❌ Wave 0 |
| EXPO-06 | Non-embedded **unmapped** font refuses, reusing `lookup_bundled_font`'s own reason string (`/ZapfDingbats`, `/Symbol`) | unit, negative case | `pytest tests/test_pdfa.py::test_unmapped_basefont_refuses_by_name_not_substituted -x` | ❌ Wave 0 |
| EXPO-06 | Encrypted input refuses by rule ID; **never** silently saved decrypted (rule 6.1.3-2) | unit, negative case | `pytest tests/test_pdfa.py::test_encrypted_input_refuses_and_never_writes_output -x` | ❌ Wave 0 |
| EXPO-06 | Every refusal reason string begins with a veraPDF `clause-testNumber` ID (Pattern 3) | unit | `pytest tests/test_pdfa.py::test_every_refusal_reason_is_prefixed_with_a_rule_id -x` | ❌ Wave 0 |
| **G7a** | veraPDF reports `isCompliant="true"` at `--flavour 2b` for **every** tier-A fixture's converted output — the corpus assertion, not a spot check | corpus + subprocess | `pytest -m corpus tests/test_gate_g7a.py::test_every_tier_a_conversion_validates_at_pdfa_2b -x` | ❌ Wave 0 |
| **G7a** | Conversion success count ≥ the baseline floor — stops the gate passing vacuously by refusing everything (Pitfall 4) | corpus | `pytest -m corpus tests/test_gate_g7a.py::test_conversion_success_rate_meets_baseline_floor -x` | ❌ Wave 0 |
| **G7a** | The gate can fail: a known-non-conformant veraPDF fixture is reported `isCompliant="false"` | corpus + subprocess, negative case | `pytest -m corpus tests/test_gate_g7a.py::test_gate_detects_a_known_nonconformant_fixture -x` | ❌ Wave 0 |
| **G7a** | Exit codes ∉ {0,1} are surfaced as infrastructure failure, not as a conformance regression (Pitfall 1) | unit (mocked subprocess) | `pytest tests/test_verapdf_gate.py::test_nonvalidation_exit_codes_are_not_reported_as_conformance_failures -x` | ❌ Wave 0 |
| EXPO-07 | DOCX opens as a valid OOXML package: required parts present, `word/document.xml` well-formed | unit | `pytest tests/test_export_docx.py::test_output_is_a_valid_ooxml_package -x` | ❌ Wave 0 |
| EXPO-07 | Headings inferred by font-size clustering on a fixture with a hand-measured size ratio (body vs heading) | unit | `pytest tests/test_export_docx.py::test_heading_level_inferred_from_font_size_ratio -x` | ❌ Wave 0 |
| EXPO-07 | Bold/italic runs carry through to DOCX run formatting | unit | `pytest tests/test_export_docx.py::test_bold_and_italic_survive_to_docx_runs -x` | ❌ Wave 0 |
| EXPO-07 | Inline images placed; ruled table becomes a table | unit | `pytest tests/test_export_docx.py::test_inline_image_and_ruled_table_round_trip -x` | ❌ Wave 0 |
| EXPO-07 | **Ceiling held:** an unruled table and a 2-column page emit plain paragraphs, not a table / not reordered text | unit, negative case | `pytest tests/test_export_docx.py::test_unruled_table_and_multicolumn_degrade_to_paragraphs -x` | ❌ Wave 0 |
| EXPO-07 | No second extraction path — `engine.export.docx` consumes `engine.blocks`, never re-parses (extends A-7.5's scan to the DOCX module) | unit | `pytest tests/test_export_single_path.py::test_docx_reuses_open_run_index_no_second_parse -x` | ❌ Wave 0 |
| EXPO-08 | Warning counts are computed from the **same** `list[Block]` the writer consumes — writer output and warning cannot disagree | unit | `pytest tests/test_export_docx.py::test_warning_counts_match_what_the_writer_actually_emitted -x` | ❌ Wave 0 |
| EXPO-08 | Warning names *this* document's degradations ("3 tables and a 2-column section detected"), not a generic string | unit | `pytest tests/test_export_docx.py::test_warning_names_this_documents_specific_degradations -x` | ❌ Wave 0 |
| EXPO-08 | A document with no degradations produces no warning (negative case — prevents a permanently-on banner) | unit, negative case | `pytest tests/test_export_docx.py::test_clean_document_produces_no_warning -x` | ❌ Wave 0 |
| **D-8.5** | Nothing outside `engine/export/docx*` imports it or imports `docx` (AST scan) | unit | `pytest tests/test_docx_cuttable.py::test_nothing_outside_the_docx_subtree_imports_it -x` | ❌ Wave 0 |
| **D-8.5** | `python-docx` is an optional dependency group, not a core dependency | unit | `pytest tests/test_docx_cuttable.py::test_python_docx_is_optional_not_core -x` | ❌ Wave 0 |
| **D-8.5** | The literal criterion: deleting the DOCX modules leaves the rest of the suite green | corpus (phase gate only) | `pytest -m corpus tests/test_docx_cuttable.py::test_suite_passes_with_docx_modules_deleted -x` | ❌ Wave 0 |
| ENG-07 | The DOCX optional extra is actually scanned by the AGPL gate (`uv sync --locked --all-extras`) | unit | `pytest tests/test_license_gate.py::test_optional_extras_are_installed_before_the_gate_runs -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run --frozen pytest -q -m "not corpus"` — the whole unit tier above,
  including both cheap cuttability assertions (AST scan + `pyproject.toml` check) and the G7b file
  assertion. All run without Docker, so they are green on the local machine where Docker is absent.
- **Per wave merge:** `uv run --frozen pytest -q` (adds the `corpus`-marked veraPDF fixture sweep
  and the delete-and-run cuttability proof) + `uv run --frozen mypy engine/` +
  `uv run --frozen python tools/license_gate.py`.
- **Phase gate:** full suite green, **plus** the real G7a run — `harness/verapdf_gate.py` over the
  complete tier-A/B/C fixture corpus through the pinned image in CI (not the local JAR), and the
  conversion-success floor re-measured and recorded — before `/gsd:verify-work`.

### Wave 0 Gaps

- [ ] **`DOCX-CEILING.md` + `tests/test_gate_g7b.py`** — ordered **first**, before any DOCX task.
      This is the gate, not documentation of it.
- [ ] **The unmodified-baseline measurement** — run veraPDF over the tier-A fixtures *before* the
      converter exists, to establish the success floor Pitfall 4's assertion needs. Cannot be
      recovered later; once the converter exists there is no baseline.
- [ ] `engine/export/pdfa.py`, `tests/test_pdfa.py`, `tests/test_gate_g7a.py`,
      `harness/verapdf_gate.py`, `tests/test_verapdf_gate.py` — none exist
      (`find . -iname "*pdfa*"` returns nothing)
- [ ] `engine/export/docx.py` (+ warning), `tests/test_export_docx.py`,
      `tests/test_docx_cuttable.py` — none exist
- [ ] `.github/workflows/verapdf.yml` — new workflow; `Dockerfile.ci` unchanged
- [ ] `pyproject.toml` — `[project.optional-dependencies] docx`; the scoped `docx.*` mypy override;
      and `license-gate.yml` changed to `uv sync --locked --all-extras`
- [ ] **Fixture gap inherited from A-7.4:** the 217-document corpus has zero multi-column documents,
      three `tables`, and no `headings` category. EXPO-07's heading test and EXPO-08's
      "2-column section detected" test both need constructed fixtures
      (`tools/build_mixed_fixture.py` is the precedent). **If Phase 7 builds these under A-7.4,
      Phase 8 reuses them — the planner should check before duplicating.**
- [ ] **Phase 7 dependency, stated sharply:** A-7.1's `RunRecord` extension (`font_size_pt`, font
      identity/style, page geometry) must have landed. Phase 8's heading inference is unbuildable
      without it, and it is a Phase 7 *Wave 0* item, not a Phase 7 headline deliverable.
- [ ] **Phase 3 defect:** the `.notdef` guard in `shape_glyph_names`. Small, but it changes Phase 3
      behaviour and should be flagged to the maintainer rather than folded in silently.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard control |
|---------------|---------|------------------|
| V2 Authentication | No | No accounts in v1 (`CLAUDE.md:45`) |
| V3 Session Management | Partial | Both exports run inside whatever handle/cache model Phase 4 establishes for PRIV-02. This phase consumes that model, does not define it |
| V4 Access Control | No | No multi-tenant surface |
| V5 Input Validation | **Yes** | Both exports take attacker-controlled PDFs. The PDF/A audit walks the full object graph including `/Annots`, `/Names`, `/AcroForm` — all of which can be deeply nested or cyclic. Bound the traversal with a named ceiling, matching `engine/index.py`'s own `MAX_DOCUMENT_GLYPHS` precedent, rather than recursing freely |
| V6 Cryptography | **Partial — as a refusal, not an implementation** | The encrypted-input case (rule 6.1.3-2) must refuse rather than decrypt. This is a *policy* decision recorded above; no cryptographic code is written in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard mitigation |
|---------|--------|---------------------|
| Zip-bomb / path traversal in a *generated* `.docx` | Tampering | We only write the archive, never read one. `python-docx` builds the container; no user-controlled path ever becomes a zip member name — **assert this if filenames are ever derived from document content** |
| XML entity expansion (XXE / billion laughs) via `lxml` | DoS | `python-docx` writes rather than parses user XML. Its only parse is its own bundled template. Do not extend the module to *read* `.docx` — that is the round-trip capability D-8.2 already excludes, and it is also where the XXE surface would appear |
| Malicious PDF driving unbounded traversal in the PDF/A audit | DoS | V5's named ceiling above |
| Silent decryption of a protected document | Information disclosure | Refuse (rule 6.1.3-2). Recorded as a deliberate refusal, not an oversight |
| veraPDF (a JVM parsing attacker-controlled PDFs) | Elevation / DoS | **CI-only, on fixture corpus documents that are already in the repo.** It never sees user input. If it ever moves into the request path this analysis must be redone |

## Assumptions Log

Every claim in this document tagged `[ASSUMED]`. These need confirmation before becoming locked
decisions.

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | The PDF/A output-intent subtype is `/S /GTS_PDFA1` for PDF/A-2, not `/GTS_PDFA2`. **No rule in `PDFA-2B.xml` tests the `/S` value**, so I could not confirm it against the profile — it is consistent across every PDF/A generator I know of, and pikepdf's `pdfa_status` reads the XMP rather than the intent | § *What the converter must write*, Pitfall 2 | Five rules (6.2.4.3-2/3/4, 6.2.10-2) fail with error messages pointing at colour spaces, not at the output intent. **Resolved for free by the first veraPDF run** — do not spend research time on it, spend one CI run |
| A2 | `python-docx` can express the full D-8.2 ceiling (headings by level, bold/italic runs, inline images, ruled tables) through its documented API | § *Pattern 6* | If a ceiling clause needs raw `w:` XML manipulation, the "boring library" argument weakens. Low risk — these are `python-docx`'s core documented features — but not verified by writing a document this session |
| A3 | veraPDF's own corpus contains usable *known-non-conformant* PDF/A-2b fixtures for tier C | § *Pattern 5* | Tier C needs a different source. Low risk: three veraPDF fixtures are already vendored under CC BY 4.0 (`corpus/sources.md:24`), so the path is established even if the specific files differ |
| A4 | The `verapdf/cli` image's `--flavour 2b` uses the same `PDFA-2B.xml` profile I downloaded from `veraPDF-validation-profiles@integration` | § *PDF/A-2b rule set* | The rule IDs I cite could drift from what CI reports. Low risk (the profile repo is veraPDF's own), but pin the image digest — which the recommendation already does — so the profile is pinned with it |
| A5 | Liberation's advance widths match the Base-14 metrics closely enough for rule 6.2.11.5-1's ≤1-unit tolerance after substitution | § *Pattern 1* | Metric compatibility is D-07's whole premise and `03-CONTEXT.md` states it as settled, but I measured the tolerance only for **Liberation's `/W` against Liberation's own `hmtx`** (0.17 units), not for Liberation against Helvetica's standard widths. The rule compares dict-to-program, so the measured case is the one the rule tests — but a layout-shift regression would show up as a *pixel* diff, not a veraPDF failure. Covered by the pixel-diff test row in the map |

## Open Questions

1. **All-or-nothing conversion, or partial-with-report?**
   - *What we know:* `03-CONTEXT.md` D-11 chose all-or-nothing for recipes and explicitly deferred
     `--partial` to "the phase that has its own evidence." PDF/A conversion reuses `apply_recipe`,
     so it inherits that posture by default.
   - *What's unclear:* whether refusing a 400-page document because one annotation lacks an
     appearance stream is the right trade. 5/25 sampled documents have at least one such
     annotation, so this is not a corner case.
   - *Recommendation:* keep all-or-nothing for **font** remediation (it is one `apply_recipe` call
     and D-11 already governs it), and make the **annotation** case an explicit user-visible
     choice — "convert without these 3 annotations" — rather than either a silent drop or a whole
     -document refusal. Flag for the maintainer; do not decide it in the plan.

2. **Does veraPDF flag a non-embedded font that sits in `/Resources` but is referenced by no
   text-showing operator?**
   - *What we know:* rule 6.2.11.4.1-1's description says *"fonts used for rendering"*, and its
     test is `Subtype == "Type3" || Subtype == "Type0" || renderingMode == 3 || containsFontFile
     == true`. Whether the greenfield parser instantiates a `PDFont` from an unused resource entry
     is an implementation detail not visible in the profile.
   - *Why it matters:* Pattern 1's identity-edit remediation leaves the original font object in
     `/Resources` unless it is explicitly removed, and removing it interacts with
     `remove_unreferenced_resources()`'s shared-`/Resources` caveat (`07-RESEARCH.md` Pitfall 2).
   - *Recommendation:* **one experiment, not more reading.** Convert one document with a
     non-embedded mapped font, run veraPDF both with and without the resource removal, compare.
     Order it early — it decides whether resource cleanup is a required step or an optional tidy.

3. **What is `HEADING_RATIO`?**
   - *What we know:* the algorithm is a modal-size fold (Pattern 8); the threshold is the only free
     parameter.
   - *What's unclear:* its value. The public corpus has **no `headings` category at all** and only
     3 `tables` documents (A-7.4 measured this).
   - *Recommendation:* do not pick a number in the plan. Make it a named module constant with a
     `ponytail:`-style comment, set it from the constructed fixture A-7.4 already requires, and
     record the measurement. A guessed constant that happens to work on one fixture is the worst
     outcome — it looks measured.

4. **Does Phase 7 build the A-7.4 fixtures, or does Phase 8?**
   - *What we know:* A-7.4 assigns multi-column and heading-heavy fixture construction to Phase 7
     Wave 0. Phase 8's EXPO-07/EXPO-08 tests need the same fixtures.
   - *Recommendation:* Phase 8's planner should **check whether they exist before writing a
     fixture-construction task**, and depend on them rather than duplicating. If Phase 7 descopes
     them, Phase 8 inherits the task — but that should be a visible inheritance, not a silent one.

5. **Is the `.notdef` guard a Phase 3 amendment or a Phase 8 task?**
   - *What we know:* it is a Phase 3 correctness defect (`engine/fonts.py:449-453` asserts something
     measurably untrue), discovered by Phase 8 research, with a PDF/A consequence (rule 6.2.11.8-1)
     and a non-PDF/A consequence (`/DW` silently covering an in-use glyph, which D-14 forbids).
   - *Recommendation:* **maintainer's call, not the planner's.** Report it; do not fold a change to
     Phase 3's font pipeline into Phase 8 without a decision.

## Sources

### Primary (HIGH confidence — executed or downloaded and parsed this session)

- `veraPDF-validation-profiles@integration/PDF_A/PDFA-2B.xml` — the complete 144-rule PDF/A-2b
  machine profile. Downloaded (116,132 bytes), parsed, every rule's `description` and `TEST`
  extracted. **This is the source for every rule ID, clause and test expression in this document.**
- Live introspection of the installed environment: `pikepdf 10.11.0` / `libqpdf 12.3.2`,
  `Pdf.save()` signature and `_core.pyi:2820-2845` docstring (`preserve_pdfa`, `min_version`,
  `force_version`, `deterministic_id`), `pikepdf/models/metadata/_constants.py:15-18,37-40`
  (`XMP_NS_PDFA_ID` → prefix `pdfaid`).
- Live execution: the XMP + OutputIntent + `min_version` write recipe, re-opened and inspected
  (`pdfa_status == '2B'`, packet header without `bytes=`/`encoding=`, `/S /GTS_PDFA1`, `/N 3`,
  `%PDF-1.7` + 4 bytes >127, `/ID` present, single trailing EOL).
- Live execution: `PIL.ImageCms.createProfile("sRGB")` → 588 bytes, `deviceClass="mntr"`,
  `colorSpace="RGB "`, version `04400000`.
- Live execution: `engine.fonts.shape_glyph_names` / `subset_font_for_family` /
  `subset_cid_widths` — subset tables, 2 cmap subtables (0,3)+(3,1), upem 2048, `/W` values, and
  the `.notdef` reproduction.
- Corpus measurement: `corpus/manifest.json` category census (217 public documents) and the
  25-document stratified PDF/A pre-flight probe.
- Source read in full: `tools/license_gate.py`, `engine/fonts.py`, `engine/encoding_table.py`
  (font-verdict branches), `engine/recipe.py` (`_resolve_op`, `apply_recipe` substitution wiring),
  `Dockerfile.ci`, `.github/workflows/*.yml`, `pyproject.toml`.
- PyPI JSON API: `python-docx` 1.2.0 (MIT; `requires_dist` = `lxml>=3.1.0`, `typing_extensions>=4.9.0`),
  `lxml` 6.1.2 (BSD-3-Clause), `docxtpl` 0.20.2 (LGPL-2.1-only).
- Docker Hub registry API: `verapdf/cli` tag list and the `v1.30.2` manifest digest.
- `slopcheck install python-docx lxml` → `2 OK`.

### Secondary (MEDIUM-HIGH — official documentation and maintainer statements)

- `docs.verapdf.org/cli/validation` — `--flavour` values, `--format` values, `--success`/`--passed`,
  the `<rule clause= testNumber= status=>` report structure and the `isCompliant` attribute.
- `github.com/veraPDF/veraPDF-library` issue **#1562** — exit codes, reverse-engineered by the
  reporter and **confirmed by contributor `bdoubrov`**; the issue is still open, which is itself the
  finding (exit codes are undocumented).
- `github.com/veraPDF/veraPDF-apps/blob/integration/tests/exit-status.sh` — veraPDF's own regression
  script asserting codes 0/1/2/3/7 and the OOM-returns-1 hack.
- veraPDF licence: dual GPLv3+ / MPLv2+, stated across veraPDF-library, veraPDF-model,
  veraPDF-validation and veraPDF-pdfbox-validation.
- PDF Association **TechNote 0010**, "Clarifications of ISO 19005, parts 1-3" — PDF/A-2 permits a
  document information dictionary and a conforming reader shall ignore it; contrasted with PDF/A-1's
  equivalence requirement.
- `pikepdf.readthedocs.io` metadata topic — `open_metadata()` commit-on-exit semantics,
  `pdfa_status`, and its own warning that the property *"merely tests if the file claims to be
  conformant."*

### Project sources

`.planning/ROADMAP.md` (Phase 8 §, criteria 1-5, Risk #8, ordering constraint 10),
`.planning/REQUIREMENTS.md:117-120,171-173`, `.planning/research/STACK.md`,
`.planning/research/PITFALLS.md:418-433`, `.planning/research/SUMMARY.md:92-104,260`,
`.planning/phases/07-exports/07-RESEARCH.md`, `07-CONTEXT.md` **incl. amendments A-7.1..A-7.6**,
`03-CONTEXT.md` D-11..D-15, `01-.../PLAYA-DECISION.md`, `TJ-REFIT-RESULTS.md`,
`03-.../G2B-GATE-RESULTS.md`, `corpus/sources.md`, `corpus/README.md`, `CLAUDE.md`.

### Not used

No claim in this document rests on a single unverified web search. Where I could not verify
something — the `/S /GTS_PDFA1` constant, veraPDF's treatment of unreferenced fonts — it is in the
Assumptions Log or Open Questions, not asserted in the body.

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| PDF/A-2b rule set | **HIGH** | The actual machine profile veraPDF executes, downloaded and parsed. Not a recollection of ISO text |
| veraPDF licence posture | **HIGH** | Dual GPLv3+/MPLv2+ confirmed across four repositories; MPL-2.0 is already a project-accepted licence |
| veraPDF CLI shape | **HIGH** on flags/report; **MEDIUM-HIGH** on exit codes (officially undocumented; contributor-confirmed + asserted by veraPDF's own test script) |
| Phase 3 font output's conformance | **HIGH** | The subset was built and inspected, not reasoned about. 12 PASS / 5 N/A / 1 AT RISK, each tied to a rule ID and a `file:line` |
| The `.notdef` defect | **HIGH** | Reproduced in three characters, and the absence of a guard confirmed by a full-tree grep |
| Remediate-vs-refuse classification | **MEDIUM-HIGH** | The policy follows existing code (`FontVerdict`, `lookup_bundled_font`, `RecipeReport`); incidence rates are from a 25-document sample, disclosed as such |
| Corpus incidence rates | **MEDIUM** | Stratified 25 of 217, bounded to 25 pages/document, deliberately not a full sweep. Directionally reliable; not precise |
| DOCX library choice | **HIGH** | Licence closure verified live on PyPI; slopcheck clean |
| DOCX heading heuristic | **LOW-MEDIUM** | The algorithm is sound and small; `HEADING_RATIO` is unmeasurable until A-7.1 lands and a fixture exists. Flagged as Open Question Q3, not asserted |
| Cuttability approach | **MEDIUM-HIGH** | The AST-scan technique is the established precedent (A-7.5); the delete-and-run proof is straightforward but unwritten |

**Research date:** 2026-08-30
**Valid until:** ~2026-09-29 for the library/version claims (pikepdf, Pillow, python-docx are all
stable). The `PDFA-2B.xml` rule set tracks ISO 19005-2:2011 and does not move. The `verapdf/cli`
digest is pinned and therefore does not expire — re-verify only when deliberately bumping it.

---

## Implementation Refresh — 2026-10-28

**Authority:** This dated refresh supersedes conflicting implementation/version recommendations above; historical measurements remain historical. **Confidence:** HIGH for inspected code and official CLI documentation; MEDIUM for the proposed conversion envelope until the real corpus gate passes. [VERIFIED: targeted source inspection; official sources R1–R8 below]

### Current constraints and responsibility

- Preserve D-8.1–D-8.6: write the DOCX ceiling first, deliver PDF/A-2b before DOCX, keep veraPDF CI/dev-only, use direct OOXML from the shared model, and keep DOCX removable. No LibreOffice, pdf2docx, second extraction, runtime AGPL, deployment work or container setup. [VERIFIED: 08-CONTEXT.md; CLAUDE.md; current planning scope]
- The backend disposable worker owns PDF/A conversion and DOCX generation; the browser owns the captured-current-bytes request, warnings/acknowledgement and download publication. Keep existing worker admission, scratch, timeout, output limits and fixed public error codes. [VERIFIED: server/app.py:251; server/worker.py:144; engine/export/pdf.py; client/src/exports/controller.mjs:52]
- No new runtime package is recommended. Retain the resolved pikepdf 10.11.0, fonttools 4.63.0 and Pillow 12.3.0 pins. Package installation/slopcheck is therefore not part of this refresh. [VERIFIED: pyproject.toml; recommendation]

### Corrections to historical assumptions

| Historical assumption | Current implementation consequence |
|---|---|
| Phase 7 blocks/heading metadata do not exist yet | DocumentBlocks → PageBlocks → Block already exists, with Span bold/italic, heading_level and ruled-table rows. RunRecord has effective_em, direction, font_name and font_identity. Reuse these, including HEADING_RATIO=1.35 and LARGE_HEADING_RATIO=1.8. [VERIFIED: engine/blocks.py:18–66,179–261; engine/records.py] |
| Missing-glyph handling needs a new font-pipeline fix | The historical CID-0 defect is documented and guarded through has_unmapped_glyph/substitution_unicode_reason and recipe preconditions; verify existing guards rather than duplicating them. [VERIFIED: engine/fonts.py:427–575; engine/recipe.py] |
| The block layer supplies images and exact column counts | Block.kind contains paragraph/heading/list/table only; PageBlocks.warnings contains deduplicated string codes. There are no inline-image records or numeric column-section counts. Do not invent “2-column section” counts from these codes. [VERIFIED: engine/blocks.py:43–66,179–261] |
| A pre-conversion warning is just another current route response | /exports currently returns a finished artifact; operation allowlists exist in API, worker and browser controller. Plan an explicit warning-before-generation/acknowledgement flow bound to the same captured bytes, and preserve stale-result suppression. [VERIFIED: server/app.py:251–269; server/worker.py:205–245; client/src/exports/controller.mjs:52–85] |
| Docker image 1.30.2 is the preferred local validator | Use the official stable 1.30.3 Java CLI installer, without Docker. Existing harness/tests workflows use containers, but adding deployment/container machinery is outside this phase. [CITED: R1,R2; VERIFIED: .github/workflows/harness.yml; .github/workflows/tests.yml] |
| Current pikepdf.pdfa examples work on the project pin | The module was added in 10.14; current documentation is 10.17.0. Its optional extra adds jsonschema/referencing/fontTools, and it explicitly does not embed fonts or convert colour. Do not import it on 10.11.0 or silently upgrade the dependency closure. [CITED: R6] |

### Prescribed PDF/A envelope — narrow, explicit, non-vacuous

The following is a proposed product support policy, deliberately narrower than everything PDF/A-2b permits; it is not a claim that excluded constructs violate the standard. Start with an allowlist and refuse unknown constructs. [ASSUMED: proposed support policy; confirmation required before locking]

1. Support simple PDF 1.x pages containing bounded paths, supported text operators, and ordinary RGB/gray images; include image-only documents. Resolve inherited resources and inspect every relevant used resource, including nested direct containers, with cycle/work/decoded-byte bounds. For the initial release refuse nested Form XObjects unless traversal and their complete resource/content closure are implemented and covered. [ASSUMED: proposed support policy; VERIFIED: existing bounded traversal precedent in engine/export/pdf.py and server/worker.py:75–141]
2. Initially accept text only through explicitly audited embedded TrueType/CIDFontType2 structures, including the existing engine-produced Type0/Identity-H subsets. Check actual font program, embedding permissions, encoding/CIDToGIDMap, used-glyph presence, widths and relevant font-rule predicates; BaseFont names alone prove nothing. Preserve valid embedded programs. [ASSUMED: proposed support policy; VERIFIED: engine/fonts.py:537–779; CITED: R7]
3. Refuse missing fonts, including unembedded Base-14 fonts, unsupported Type1/CFF/Type3/vertical fonts, unknown encodings, missing used glyphs and inconsistent widths. Font subsetting is not a generic font-repair operation. Do not substitute Liberation into an existing font dictionary without rewriting character codes, widths and content together. Existing recipe substitution may be reused in a separately corpus-proven extension, not treated as an identity edit that is automatically safe for every source. [ASSUMED: proposed support policy; VERIFIED: engine/fonts.py; engine/recipe.py; CITED: R7]
4. Limit automatic colour remediation to validated RGB/gray content and a pinned ICC sRGB output profile. Refuse DeviceCMYK, spot/DeviceN, patterns/shadings, unsupported ICC spaces, masks/transparency and other unhandled colour constructs for this initial policy; assigning sRGB is not a CMYK-to-RGB conversion. Do not overwrite an incompatible existing intent and claim colour preservation. [ASSUMED: proposed support policy; CITED: R6,R7]
5. Refuse annotations/forms/XFA, optional content, embedded attachments, external streams, JavaScript/actions, multimedia, signatures without existing acknowledgement, and unknown dictionary/operator features until explicitly supported. Do not silently strip visible/interactive content or call flatten as an implicit archival repair. Correctly decrypted exports must be saved without encryption and retain the existing unlocked-copy disclosure. [ASSUMED: proposed support policy; VERIFIED: engine/export/pdf.py; server/worker.py:205–245; CITED: R7]
6. For accepted input, perform structural serialization, valid trailer ID, PDF 1.7-compatible output, controlled XMP with pdfaid:part=2 and pdfaid:conformance=B, and the ICC output intent; reject unsupported custom XMP instead of copying arbitrary claims. Commit metadata before saving, reopen the final bytes for structural checks, then return the bounded artifact. Writing a declaration or reading pdfa_status is not validation. Do not force a PDF 2.0 file to 1.7 by changing only its header. [ASSUMED: proposed support policy; VERIFIED: installed pikepdf/models/metadata/_core.py:325–335; CITED: R7,R8]

**G7a acceptance:** Maintain a manifest with explicit success/refusal expectations. Successful fixtures must include multiple engine-subset text families/styles, RGB and gray images, image-only pages, inherited/shared resources, and page geometry; validate every produced file at 2b and compare rendering/page geometry where relevant. Add known-invalid/missing-font/CMYK/active-content/unknown-feature controls that must refuse. Assert expected success count and each expected successful case, not merely “all emitted outputs pass”; an always-refuse converter must fail. Record baseline source verdicts separately from converted verdicts. No such coverage is claimed by this research refresh. [ASSUMED: proposed gate design; CITED: R3,R7; VERIFIED: existing harness architecture]

### veraPDF 1.30.3: official download, integrity, install and gate

- Official stable archive index lists 1.30.3 dated 2026-10-07, size 32,971,125 bytes. Archive: https://software.verapdf.org/rel/1.30/verapdf-greenfield-1.30.3-installer.zip ; detached signature: https://software.verapdf.org/rel/1.30/verapdf-greenfield-1.30.3-installer.zip.asc . Avoid floating /rel links and odd-minor development builds. [CITED: R1,R2]
- The official directory lists ZIP and .asc files, not a SHA-256 sidecar. The documented trust mechanism is GPG with fingerprint 13DD102B4DD69354D12DE5A83184863278B17FE7; verify that full fingerprint and the signature over the exact ZIP, then record its computed SHA-256 for repeatable tooling. A locally computed digest alone is not publisher authentication. No archive checksum value was independently computed in this refresh. [CITED: R1,R2]
- The ZIP contains an IzPack installer JAR and launcher scripts. Run the actual extracted installer JAR with a CLI-only automated-install XML into a task-specific directory under /private/tmp; official docs show CLI pack index 1, and java -jar avoids disagreement between script names in docs and README. Discover the installed launcher rather than assuming its path. This requires no Docker or system-wide install. [CITED: R2,R4; recommendation]
- The version-tagged README lists installer Java 8/11/17/21. Temurin 26.0.1 and uv are present. The parent installed CLI-only 1.30.3 at /private/tmp/pdf-tool-phase8-tools/verapdf and validated real files with JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-26.jdk/Contents/Home. Evidence records a good GPG signature matching the official fingerprint and archive SHA-256 b512bf24945503a33fc10738ecffc1f2dccaaf8593a448e94ee9ac86a9559a59. The unmodified 13-file sample completed in 4.93s: one compliant source (verapdf_type3_font_fixture.pdf), twelve noncompliant, no infrastructure errors, process exit 1. This is a baseline, not converter acceptance. [CITED: R4; VERIFIED: 08-TOOLCHAIN-BASELINE.md]
- Run an argument vector equivalent to VERAPDF_CMD --flavour 2b --format json output.pdf with bounded subprocess timeout/output and no shell expansion. Explicit 2b avoids metadata-driven flavour selection. Require exactly the expected job/result count and each compliant=true; batchSummary.failedParsingJobs, failedEncryptedJobs, outOfMemory and veraExceptions must be zero. Its validationSummary must have failedJobCount=0, nonCompliantPdfaCount=0 and compliantPdfaCount equal to the expected successes. Missing, malformed or empty output fails closed; retain failed rule identifiers as CI evidence. Audit inline-image dictionaries/filters too, or refuse them; checking only XObject streams misses the observed negative control. [CITED: R3; VERIFIED: negative-smoke.json; recommendation]
- Corrected exit observation: direct-process evidence proves the inline-LZW negative (rule 6.1.10-1) returns exit 1 and compliant=false, consistent with upstream tests. The earlier reported zero belonged to a following shell head command; no exit-zero-invalid behavior was observed. Still require structured verdicts/counts and reject process errors, malformed/empty reports and parser/OOM failures. JSON uses report.jobs[].validationResult[].compliant (boolean), details.ruleSummaries[], and report.batchSummary, not a reports array or XML's isCompliant name. [CITED: R3,R5; VERIFIED: 08-TOOLCHAIN-BASELINE.md; /private/tmp/pdf-tool-phase8-tools/negative-smoke-exit.json]
- veraPDF apps 1.30.3 is dual GPLv3+/MPLv2+; keep it a CI/dev file-in/file-out subprocess outside served requests. The Python installed-distribution gate cannot audit a downloaded JAR or ICC file; document these assets and licences separately. MPL is a file-level copyleft licence, not “permissive” as the historical summary called it. [CITED: R4; VERIFIED: tools/license_gate.py; CLAUDE.md]

### ICC asset, direct OOXML and remaining blockers

- Vendor the unmodified ICC v2 sRGB2014.icc from https://registry.color.org/rgb-registry/profiles/sRGB2014.icc ; record source, retrieval date, SHA-256 and embedded copyright tag alongside it. The ICC profile page links this exact asset and general licensing terms; those terms expressly permit copying, distributing and embedding ICC-owned profiles. Keep the actual attribution/terms, rather than assuming the Python dependency's licence covers the binary. This replaces the historical preference for an implicit Pillow-generated profile with a reproducible asset. [CITED: R9,R10; recommendation]
- Recommend stdlib zipfile + xml.etree.ElementTree for the deliberately bounded DOCX package, owned wholly by engine/export/docx.py and imported only on the DOCX branch. Include content types, root/document relationships, document, styles and image relationships/media; use safe escaped XML, unique relationship IDs, fixed ZIP paths, xml:space and explicit whitespace/break handling. No python-docx/lxml installation is required for this approach. Keep an optional capability registration boundary so absence of DOCX leaves other exports runnable. [ASSUMED: recommended OOXML design requiring package/schema and Word-client validation; VERIFIED: D-8.3/D-8.5 permit this discretion]
- Inline images remain a concrete gap: add bounded image placement metadata to the existing RunIndex/PageIndex boundary and carry supported images into DocumentBlocks; do not start another text extractor. Make warning facts and the writer consume the same document snapshot. Do not widen table detection or excluded multi-column/header/footer reconstruction. [VERIFIED: engine/blocks.py; 08-CONTEXT.md; recommendation]
- Blockers before implementation is accepted: vendor/audit ICC bytes; lock the supported/refused PDF/A envelope; execute the non-vacuous converted-output corpus gate; provide existing-model image facts and structured degradation facts needed by DOCX. Parent completed installer authentication/pinning and real known-positive/negative baseline validation; this researcher ran no dependency installation, test suite or validator. [VERIFIED: 08-TOOLCHAIN-BASELINE.md; ASSUMED: implementation acceptance sequence]

### Refresh primary references

- **R1:** https://software.verapdf.org/rel/1.30/ — versioned stable archive names, dates, sizes and signatures. [CITED]
- **R2:** https://docs.verapdf.org/install/ — macOS installer, automated XML packs and GPG fingerprint. [CITED]
- **R3:** https://docs.verapdf.org/cli/validation/ — explicit flavours, XML reports, compliance and batch counters. [CITED]
- **R4:** https://raw.githubusercontent.com/veraPDF/veraPDF-apps/v1.30.3/README.md — release-tagged licences, installer Java versions and direct JAR invocation. [CITED]
- **R5:** https://raw.githubusercontent.com/veraPDF/veraPDF-apps/v1.30.3/tests/exit-status.sh — upstream exit-code assertions. [CITED]
- **R6:** https://pikepdf.readthedocs.io/en/latest/topics/pdfa.html — added-in-10.14 boundary, optional dependencies and limits; latest docs 10.17.0, not the project pin. [CITED]
- **R7:** https://raw.githubusercontent.com/veraPDF/veraPDF-validation-profiles/integration/PDF_A/PDFA-2B.xml — authoritative rule discovery; integration is moving, so the installed 1.30.3 profiles and actual reports own the gate. [CITED]
- **R8:** https://pikepdf.readthedocs.io/en/latest/topics/metadata.html — metadata commits and misleading copied conformance declarations. [CITED]
- **R9:** https://registry.color.org/rgb-registry/srgbprofiles — official sRGB2014 binary link and profile description. [CITED]
- **R10:** https://registry.color.org/profile-library/ — ICC profile licence and attribution source. [CITED]

**Assumptions log:** Proposed PDF/A support/refusal envelope, fixture success classes, direct-OOXML packaging/validation and acceptance sequence are recommendations awaiting lock/implementation evidence; no general-converter capability is asserted. **Availability:** Java26/uv present and parent-installed veraPDF available via explicit path; Context7 MCP and ctx7 CLI unavailable, so official docs were used. **Validation:** retain enabled Nyquist coverage, target the new PDF/A/runner/DOCX/API/controller behaviours, then existing full regressions and strict engine/server mypy; this research intentionally ran no tests. [ASSUMED: recommendations; VERIFIED: .planning/config.json; environment probes; parent handoff; pyproject.toml]
