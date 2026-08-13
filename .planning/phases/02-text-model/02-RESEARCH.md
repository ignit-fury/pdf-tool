# Phase 2: Text Model - Research

**Researched:** 2026-08-13
**Domain:** PDF content-stream interpretation, font encoding resolution, glyph clustering, page/run editability classification
**Confidence:** HIGH on everything measured against this repo's corpus (most of it). MEDIUM on cross-viewer behaviour (source-verified, not executed). LOW on nothing that matters — the LOW items are flagged inline and none sit on the critical path.

## Summary

Nearly every question this phase asks could be answered by *measuring this repository* rather than by reading. So that is what was done: the 216-document corpus was probed directly for encoding-branch distribution, `/Contents` fusion risk, classification signals, glyph provenance availability, and parse cost. Six of those measurements contradict something written down elsewhere in the planning documents, and those six are the most valuable output of this research.

The three that change the plan:

1. **The "Symbolic + `/Encoding` is unresolvable" premise is over-broad.** It is unresolvable for **TrueType** simple fonts (ISO 32000-1 §9.6.6.4). For **Type1/CFF** it is resolved by §9.6.6.2 — `/Differences` overlays the font's built-in encoding, and every major implementation agrees. In this corpus that distinction is the difference between a **23.1%** document-level refusal rate and a **1.9%** one. If D-04 is implemented as "Symbolic + `/Encoding` ⇒ refuse", it refuses 50 of 216 documents for no reason.
2. **`nasa_graphics_standards_manual.pdf` is mislabelled.** The manifest calls it `vector_outlined_text`. Its `/Producer` is `Adobe Acrobat Pro 11.0.0 Paper Capture Plug-in`, its `/Creator` is `Canon DR-7550C TWAIN`, every glyph on it is render mode 3 over 984×1200 image XObjects. It is an OCR'd scan. **There is no vector-outlined-text page anywhere in the 216-document corpus** — a scan for pages with zero glyphs, low image coverage and >200 path objects returned zero candidates. Gate G1 criterion 3 and CLAS-03 currently have no fixture.
3. **`/Contents` fusion is real here, not theoretical.** Across 114 `contents_array` documents, **78 of 2,560 part boundaries (3.0%) in 18 documents** have no whitespace on either side. `govdocs1_002_002167.pdf` naive-concatenated lexes `Q` + `BT` into the single bogus keyword `QBT` — qpdf #444, reproduced, with a named file. That file is the FAIL-proof for TEXT-07.

The shape of the interpreter is settled by a concrete API finding: **`playa` gives every semantic field of the glyph record and none of the provenance fields, but `playa.parser.ObjectParser` gives every provenance field and no semantics — and the two run over the same bytes in the same order, so they zip exactly.** Two passes per content-stream part, joined by ordinal, with `LazyInterpreter._curpos` used as a free always-on alignment assertion. No fuzzy join anywhere.

**Primary recommendation:** Build one walker that, per content-stream part, runs `playa.parser.ObjectParser` to build an operator table (byte offsets of every keyword and every operand) and `playa.interp.LazyInterpreter` to yield resolved `TextObject`s, zips them by ordinal, asserts alignment against `_curpos`, and emits glyph records. Address runs by *byte offset of the operator keyword within its content-stream part*, not by a counted ordinal. Refuse only on the genuinely ambiguous branches (TrueType symbolic + `/Encoding`, and non-embedded symbolic), not on the whole Symbolic class.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** **A run is a visual line.** Glyphs are merged across text-showing-operator boundaries
  into what reads as a line on the page, breaking on font change, size change, baseline shift, or a
  horizontal gap wider than the tuned threshold. Chosen because it matches what a user believes they
  are clicking. Accepted cost: one visual line commonly spans several `Tj`/`TJ` operators, so a
  replacement must rewrite all of them coherently — the run model and the rewrite engine are
  therefore coupled, and Phase 3 inherits this.

- **D-02:** **Sub-runs are the addressable unit when a line splits.** Where a line contains an
  unmappable glyph, each editable fragment gets its own run ID and is independently selectable; the
  locked glyph sits between them and is greyed. An ID always names something that can be acted on.
  Accepted cost: the number of IDs a visual line yields depends on its content, so the run map is
  less uniform than a strictly line-shaped one. Follows from D-01 + D-04.

- **D-03:** **The synthetic-space threshold is tuned against the corpus with a measured target, not
  guessed.** Run extraction across the 216-document public corpus, measure against known-good text,
  minimise error, then pin the number with the measurement recorded — the same discipline that
  produced Phase 1's 8% render tolerance. Research calls this threshold "the whole game" for
  extraction quality, and it is the single tunable that most directly determines whether the text
  model is any good. Requires ground-truth text for a sample of the corpus; that setup is in scope.

- **D-04:** **Ambiguous encoding refuses, and logs which branch was ambiguous.** The PDF spec does
  not cleanly resolve `Symbolic` + `/Encoding`, real files do it constantly, and viewers disagree on
  the answer. When the decision table cannot resolve a font, the affected runs are marked
  not-editable with a stated reason and the ambiguous branch is logged. Consistent with rejecting
  white-box overlay: a wrong-but-confident result is the failure mode this product exists to avoid,
  and guessing here would mean the three-engine harness is catching our own deliberate guess.
  Accepted cost: some genuinely editable text will be refused. **The refusal rate is unknown and
  must be measured against the corpus during this phase** — if it is high, that is a finding worth
  surfacing, not a number to quietly accept.

- **D-05:** **A run splits at a bad glyph rather than locking wholesale.** One Type3 glyph or one
  character with no `/ToUnicode` mapping locks only itself; surrounding clean text stays editable.
  Chosen so a single stray character cannot lock a paragraph the user reasonably expects to edit.
  Accepted cost: run boundaries now depend on glyph-level classification, so the map is more
  fragmented and carries more IDs.

- **D-06:** **Page-at-a-time, cached.** A page is parsed when first needed and the result retained.
  First page usable almost immediately; memory proportional to pages actually visited. Accepted cost:
  find-across-all-pages must force a full parse, so the first search on a long document pays the
  whole cost at once. **That needs a visible progress affordance when the UI arrives in Phase 4** —
  record it as a known consequence now rather than discovering it as a UX bug later.

### Claude's Discretion

- Whether the Phase 1 spike modules (`spike/playa_decode_probe.py`, `spike/tj_refit_prototype.py`)
  are absorbed, rewritten, or left alone. Phase 1's CONTEXT.md declared spike code throwaway, judged
  only on whether it answered its question. `playa_decode_probe.py` is nonetheless the established
  single module boundary for `playa` decode calls, and that boundary must be preserved however the
  code is reorganised — no abstraction layer, per Phase 1 D-locked guidance.
- Internal structure of the glyph record and run record, beyond the provenance fields already fixed
  by research.
- How ground-truth text for D-03's threshold tuning is obtained.

### Deferred Ideas (OUT OF SCOPE)

- **Progress affordance for the first full-document search** — a direct consequence of D-06's
  page-at-a-time indexing. Belongs to Phase 4/5 where the UI exists, but it is a known consequence
  now rather than a surprise later.
- **Background full-index after page 1** — the third indexing option, offering the best experience
  at the cost of a partially-complete index to reason about. Revisit in Phase 4 if the first-search
  cost proves painful in practice.
- **Surfacing shared Form XObjects to the user** — they are marked not-editable in v1 because editing
  one changes every page referencing it. Explaining *why* to a user, or offering a "edit all
  instances" affordance, is a Phase 4 UI question.
- **Ground-truth text corpus as a reusable asset** — if D-03's tuning produces a labelled
  ground-truth set, it may be worth keeping as a permanent extraction-quality regression suite rather
  than a one-off tuning input.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEXT-01 | Content-stream interpreter walks a document in index mode, emits a run record per text run | §8 (interpreter shape — `LazyInterpreter` + `ObjectParser` zip), §Architecture Patterns |
| TEXT-02 | Every glyph record carries full provenance (code, glyph, unicode, position, advance, font, render mode, visibility, stream id, operator index, index within TJ, byte offset) | §8 field-by-field availability table — 9 fields free from playa, 4 derived from the `ObjectParser` pass |
| TEXT-03 | Run IDs address the immutable original bytes; ordinals never drift | §Run ID Scheme — byte offset of the operator keyword within its `/Contents` part, not a counted ordinal |
| TEXT-04 | Forward encoding resolution as a documented decision table, fired branch logged per font | §1 — the full table, 14 branches, with corpus occurrence counts per branch |
| TEXT-05 | `Code→Glyph` and `Code→str` distinct types the checker refuses to interchange | §Code Examples (`NewType` pattern); Wave 0 gap — no type checker is installed or wired to CI |
| TEXT-06 | Text located outside `/Contents`; shared Form XObjects marked not-editable | §5 — measured: one XObject in `irs_1040_instructions.pdf` is referenced by 43 of 126 pages |
| TEXT-07 | `/Contents` arrays coalesced before parsing | §6 — measured 78/2560 risky boundaries; `govdocs1_002_002167.pdf` produces `QBT`; playa never concatenates, so this is already safe — the risk is *introducing* a naive concat |
| TEXT-08 | Text split across operators reconstructs into readable runs, incl. glyph-at-a-time and two-column | §3 — clustering algorithm; glyph-at-a-time confirmed present (`irs_1040_instructions.pdf` XObject emits `Futu` then `r`) |
| CLAS-01 | Four-bucket page classification from three signals | §7 — thresholds, and the image-coverage formulation bug (bbox-area sum exceeds 1.0; needs union) |
| CLAS-02 | OCR'd scan → "searchable, not editable" | §7 — `invoice_book_1842.pdf` gives 45 OCR pages + 7 no-text pages; NASA manual is a second OCR fixture |
| CLAS-03 | Vector-outlined text as its own bucket | §7 — **no fixture exists in the corpus.** Wave 0 blocker |
| CLAS-04 | Three-state per-run classification available before the user clicks | §1 + §7 — classification derives from the fired encoding branch, so it is free once §1 exists |
| CLAS-05 | Refuse the operation, never the document | §7 — needs a constructed mixed fixture; `invoice_book_1842.pdf` is all-scanned, the inverse of what CLAS-05 tests |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Directives extracted verbatim in force for this phase. The planner must not produce a task that violates one.

| Constraint | Applies how in Phase 2 |
|---|---|
| **No AGPL anywhere in the runtime dependency tree, transitively.** `tools/license_gate.py` enforces on the resolved lockfile. | Phase 2 adds **no runtime dependencies**. Any new dev dependency must still pass `license_gate.py`. AGPL permitted only in CI/dev tooling no served request can reach — `mutool` already lives there. |
| **Content-stream editing only. No white-box overlays. No reflow.** | The run model must never produce an address that only an overlay could act on. Refusal is the substitute. |
| **`pikepdf` writes, `playa` reads.** "pikepdf: ❌ No — raw objects only" for encoding decode; "playa-pdf: ✅ Yes". | Do not attempt encoding decode through pikepdf. Do not attempt content-stream *writing* through playa (it is read-only by design). |
| **`playa` decode calls stay confined to one module, with no abstraction layer around them.** | Established boundary is `spike/playa_decode_probe.py`. Whatever the Phase 2 module is called, `import playa` must appear in exactly one file. The `pdfminer.six` swap remains a one-file blast radius. |
| **`/ToUnicode` is display and search only. It never produces output bytes.** | Enforced structurally via distinct types (TEXT-05), not by convention. |
| **Byte-level round-trip equality is not a valid correctness test** — qpdf-class libraries silently repair xrefs. | Gate G1's round-trip must compare *run IDs and glyph records*, never output bytes. |
| **`tools/probe_corpus.py` must never consume the Phase 2 interpreter.** | Repeated from Phase 1 D-04. Phase 2 may read from the prober; the prober may never read from Phase 2. |
| **Still CLI-only.** No web tier before Gate G2b in Phase 3. | Phase 2 ships `pdftool index` (or equivalent CLI), not an endpoint. |
| **Checks must be able to fail.** Phase 1 produced three green checks measuring the wrong thing. | Every Phase 2 gate needs a named deliberate mutation that turns it red. See §Validation Architecture. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Content-stream tokenisation + byte offsets | Engine (Python, `playa.parser.ObjectParser`) | — | Provenance must come from the same bytes the rewrite will target. No other tier sees them. |
| Font encoding decode (code → glyph) | Engine (`playa.font`) | — | The one place in the stack that decodes encodings. pikepdf explicitly does not. |
| Graphics/text state machine + CTM composition | Engine (`playa.interp.LazyInterpreter`) | — | Already implemented and validated against real documents in Phase 1. Reimplementing it is the single largest avoidable cost in this phase. |
| Glyph → visual-line clustering (D-01) | Engine (ours) | — | No library does this to the standard the product needs. This is the code Phase 2 writes. |
| Synthetic-space threshold (D-03) | Engine (ours, tuned) | — | Same. |
| Per-run and per-page classification (CLAS-01..05) | Engine (ours) | — | Consumes the run index; must be server-side because only the server has provenance. |
| Object-layer structural facts (`/Contents` array shape, font dicts, XObject refcounts) | Engine (`pikepdf`) | — | qpdf repairs and normalises; it is the correct source for structure. Note: it is also the *only* library here that can coalesce, so it is where the TEXT-07 helper lives. |
| Content-stream **writing** (Gate G1 round-trip only) | Engine (`pikepdf`) | — | `unparse_content_stream`. Deliberately minimal in this phase — see §9. |
| Run index caching (D-06) | Engine, in-process | — | No persistence. A cache with observable loss violates PRIV-02 in Phase 4; keep it a plain in-process dict now so it stays one later. |
| Rendering / pixel comparison | CI harness (`harness/`) | pdfium / Poppler / MuPDF | Already built. Phase 2 reuses it for the round-trip rather than inventing a mechanism. |
| Anything in a browser | **None in this phase** | — | CLI-only until Gate G2b. |

---

# The Ten Research Questions

## 1. The forward encoding decision table

`[CITED: ISO 32000-1:2008 §9.6.6 (Character Encoding), §9.6.6.2 Type 1, §9.6.6.3/§9.6.6.4 TrueType, §9.6.6.5 Type 3, §9.7.4/§9.7.5 Type 0/CID]`
`[VERIFIED: measured against corpus/public — 216 documents, 24,039 simple-font page-resource occurrences + 10,515 Type0 + 336 Type3]`

The table is presented as it must be implemented: **evaluate top to bottom, first match wins, log the branch ID.**

### Simple fonts — `/Type1`, `/MMType1`, `/TrueType`, `/Type3`

Preliminary: build the **base encoding array** `base[0..255] → glyph name`, then overlay `/Differences`.

| Step | Condition | Base encoding used |
|---|---|---|
| B1 | `/Encoding` is a **name** (`/WinAnsiEncoding`, `/MacRomanEncoding`, `/MacExpertEncoding`) | that named encoding |
| B2 | `/Encoding` is a **dictionary** with `/BaseEncoding` | that named encoding |
| B3 | `/Encoding` is a **dictionary** without `/BaseEncoding`, font **non-symbolic** | `StandardEncoding` |
| B4 | `/Encoding` is a **dictionary** without `/BaseEncoding`, font **symbolic**, program embedded | the **font program's built-in encoding** |
| B5 | `/Encoding` absent, font non-symbolic | `StandardEncoding` (Type1) — the implicit default |
| B6 | `/Encoding` absent, font symbolic | the font program's built-in encoding |

Then: if `/Encoding` is a dictionary, overlay `/Differences`. **`/Differences` is `[code name name … code name …]` — a mixed array of integers and names where each integer resets the running code counter. A pairwise parse is wrong and produces an off-by-one that looks like "all letters shifted by one."**

Now resolve **name → glyph**, by subtype:

| # | Subtype | Condition | Resolution | Corpus occurrences |
|---|---|---|---|---|
| **T1-a** | Type1/CFF | embedded (`/FontFile` Type1, `/FontFile3` `/Type1C`) | glyph **name** → CFF `charset` / Type1 `/CharStrings` lookup. Names are the currency. | 3,439 (`enc=dict+Diff`) + 3,157 (`enc=name`) + 113 (`enc=none`), all `sym=False`, embedded |
| **T1-b** | Type1/CFF | embedded, **symbolic**, `/Encoding` present | **Same as T1-a.** §9.6.6.2 gives `/Differences` precedence over the built-in encoding unconditionally; `Symbolic` only selects which *base* the differences overlay (B4). **Not ambiguous.** | 987 + 25 = **1,012 occurrences across 50 of 216 docs (23.1%)** |
| **T1-c** | Type1 | **not embedded**, one of the Standard 14 | Name → the AFM metrics + the viewer's substitute face. Widths from `/Widths` if present, else the built-in AFM. `playa.fontmetrics` ships the Standard-14 metrics. | 2,406 (`enc=none`) + 2,111 (`enc=name`) + 1,051 (`enc=dict+Diff`) |
| **T1-d** | Type1 | not embedded, **not** Standard 14 | No font program to consult. Glyph identity is whatever the viewer substitutes. **Editable-with-substitution at best; never editable-in-original-font.** | included in T1-c counts; 21 docs have a symbolic non-embedded simple font |
| **TT-a** | TrueType | **non-symbolic**, `/Encoding` present | name → Unicode (Adobe Glyph List) → `cmap (3,1)`. Fallback `cmap (1,0)` via the code's MacRoman meaning. Final fallback `post` table `nameToGID`. | 5,579 non-embedded + 2,031 embedded + 187 (`dict+Diff`) |
| **TT-b** | TrueType | **symbolic**, `/Encoding` **absent** | `/Encoding` is ignored. Look the raw code up in `cmap (3,0)`, trying high-byte prefixes `0x00, 0xF0, 0xF1, 0xF2` in that order. Fallback `cmap (1,0)` with the raw code. | 1,710 embedded + 254 non-embedded, **37 of 216 docs (17.1%)** |
| **TT-c** | TrueType | **symbolic**, `/Encoding` **present** | ⚠️ **THE AMBIGUOUS BRANCH.** §9.6.6.4 says the `Symbolic` flag means `/Encoding` "shall be ignored," but real producers set both and viewers disagree. **REFUSE (D-04).** | 27 embedded + 3 non-embedded = 30 occurrences, **4 of 216 docs (1.9%)** |
| **TT-d** | TrueType | symbolic, only a `(3,1)` cmap and no `(3,0)`/`(1,0)` | ISO 32000-1 requires `(3,0)` or `(1,0)`; ISO 19005-2 §6.2.11.6 explicitly permits a sole non-standard cmap. Implementations split (veraPDF miscomputes widths, Callas reports missing glyphs, 3-Heights accepts). **REFUSE.** | not separately counted — detect at font-load time |
| **TT-e** | TrueType | **no `cmap` table at all** (common in subset fonts) | PDFium falls back to `glyph_index[charcode] = charcode`; PDFBox falls to `post`. **Identity fallback is a guess.** REFUSE for editing; still decode for display. | not separately counted |
| **T3-a** | Type3 | always | `/Encoding /Differences` gives a glyph **name**; the name indexes `/CharProcs`, whose value is a *content stream*. Width comes from `/Widths` **in glyph space**, scaled by `/FontMatrix` — **not** divided by 1000. | 336 occurrences, **12 of 216 docs (5.6%)** |

`[VERIFIED: measured]` playa handles T3-a's `/FontMatrix` correctly. `verapdf_type3_font_fixture.pdf` has `/FontMatrix [0.001 0 0 0.001 0 0]` and reports `displacement = 12.0`; `govdocs1_000_000135.pdf` has `/FontMatrix [1 0 0 1 0 0]` and reports `1.92`. The "0.1×0.1 em box breaks the divide-by-1000 assumption" trap from PITFALLS is present in this corpus and playa already survives it.

### Type0 / CID fonts

| # | Step | Resolution |
|---|---|---|
| **C-1** | bytes → **code** | Via the CMap's **codespace ranges**. 1–4 bytes, and *mixed widths within one string are legal*. `Identity-H`/`Identity-V` are uniformly 2-byte. **Never hardcode 2.** |
| **C-2** | code → **CID** | Via the CMap. `Identity-*` ⇒ CID == code. A named CMap (`UniJIS-UCS2-H` etc.) ⇒ table lookup. `/Encoding` may also be an embedded CMap *stream*. |
| **C-3a** | CID → **GID**, `CIDFontType2` (TrueType) | `/CIDToGIDMap` is `/Identity` **or a binary stream of big-endian 2-byte GIDs indexed by CID**. Handling only the `/Identity` case is correct on most files and garbage on the rest. |
| **C-3b** | CID → **GID**, `CIDFontType0` (CFF, `/FontFile3 /CIDFontType0C`) | Through the **CFF charset**, not `/CIDToGIDMap`. |
| **C-4** | widths | `/W` (nested run-length: `[c [w w w] cFirst cLast w …]`) with `/DW` default **1000**. Never `/Widths`, never `/MissingWidth`. |
| **C-5** | word spacing | `Tw` applies **only to single-byte code 32**. It is a no-op on `Identity-H`. |
| **C-6** | mixed codespace | If the CMap declares codespace ranges of differing byte lengths, flag the font. Writing into it is out of scope — **refuse** (already an accepted PITFALLS position). |

`[VERIFIED: PLAYA-DECISION.md]` playa resolves C-1..C-3b on real documents including CID-keyed CFF with live CJK (`irs_publication_17.pdf` → `中文한국어`, `wikipedia_zh_monthly_magazine.pdf` → `维基人 2013年04月13日 第5期`).

### Which producers emit what

`[VERIFIED: corpus/sources.md producer distribution + measured branch counts]`

- **Acrobat Distiller (Windows/Mac, 56 docs, 26% of corpus)** — dominates T1-a and T1-b. Type1 with `/Differences` over `StandardEncoding` is its house style, and it sets `Symbolic` liberally on embedded subsets. This is why T1-b is 23% of documents: it is one producer's habit, not a spec-edge population.
- **Acrobat PDFWriter (31 docs)** — TrueType non-symbolic with a named `/Encoding` (TT-a), mostly non-embedded.
- **Corel PDF Engine, Adobe PDF Library, Antenna House, iText** — mixed; the Type0/`Identity-H` population (10,515 occurrences, 33 docs) is concentrated here and in modern IRS output.
- **Paper Capture / TWAIN scanners** — Standard-14 non-embedded Type1 in render mode 3 (T1-c). This is the OCR population, and it is why T1-c matters for classification even though it is never editable.
- **`mutopia_vocalise_abt.pdf` (LilyPond sheet music)** — one of the four TT-c documents. Music notation fonts are the canonical symbolic-with-Encoding case.

### The refusal surface, precisely

| Reason | Docs affected | % of corpus |
|---|---|---|
| TT-c: TrueType symbolic + `/Encoding` | 4 | **1.9%** |
| TT-d/TT-e: symbolic TrueType with an unusable cmap set | detect at load | unmeasured — see Open Questions |
| Symbolic + not embedded (no program to consult) | 21 | 9.7% |
| Type3 glyph with no `/ToUnicode` mapping (per-glyph, D-05) | 12 docs contain Type3 | 5.6% |
| **If T1-b were wrongly refused** | **+50** | **+23.1%** |

**This is the finding that most changes the plan.** D-04's stated cost ("some genuinely editable text will be refused") is small — roughly 2% of documents at the font level — *provided the table distinguishes Type1 from TrueType*. Collapsing them costs 23%.

---

## 2. Where the spec is genuinely ambiguous, and what viewers do

`[CITED: mozilla/pdf.js src/core/fonts.js readCmapTable; PR #6425; PDFBox PDTrueTypeFont.codeToGID; PDFium CPDF_TrueTypeFont::LoadGlyphMap; veraPDF-library issue #818]`

### The Symbolic + `/Encoding` case (TT-c)

| Implementation | Behaviour | Source |
|---|---|---|
| **pdf.js** | cmap preference: non-symbolic → `(3,1)` then `(1,0)`; symbolic → `(3,0)` then `(1,0)`. But `(3,1)` is selectable when `hasEncoding` is true *even for a symbolic font* — the condition is `platformId===3 && encodingId===1 && (hasEncoding \|\| !potentialTable)`. So **pdf.js lets a present `/Encoding` pull a symbolic font onto the `(3,1)` path**, which is the opposite of what §9.6.6.4 says. | `src/core/fonts.js` `readCmapTable`; PR #6425 "Only choose a (3,1) cmap table for TrueType fonts that have an encoding specified (issue 6410)" |
| **PDFBox** | For symbolic fonts: **if `/Encoding` is `WinAnsiEncoding` or `MacRomanEncoding`, treat the font as non-symbolic.** Otherwise try `(3,1)` with the raw code, then `(3,0)` with `0xF000/0xF100/0xF200` bias, then `(1,0)`. | `PDTrueTypeFont.codeToGID` |
| **PDFium** | If non-symbolic **or** encoding is WinAnsi/MacRoman with empty `char_names_`, take the glyph-name path. Symbolic + MS Symbol charmap → `GetGlyphIndexForMSSymbol` with `kPrefix = {0x00, 0xF0, 0xF1, 0xF2}`. Final fallback `glyph_index_[charcode] = charcode`. | `core/fpdfapi/font/cpdf_truetypefont.cpp` |
| **Poppler** | Not read in this session. Historically prefers `(3,0)` for symbolic and falls back through `(1,0)`/`(3,1)`. `[ASSUMED]` |
| **Acrobat** | Not readable. pdf.js issue #14117 is titled "`/Encoding` prevents characters in a specific font from rendering but they do in ghostscript, chrome, and acrobat" — i.e. Acrobat *honours* the `/Encoding` where pdf.js did not. `[CITED: mozilla/pdf.js#14117]` |

Three implementations, three different tie-break rules, and pdf.js's own history is a sequence of reversals on exactly this condition. **This is the refusal surface and it is correctly refused.**

### Other genuinely ambiguous cases — the full refusal list

| # | Ambiguity | Why unresolvable | Disposition |
|---|---|---|---|
| A-1 | **TrueType symbolic + `/Encoding` present** | §9.6.6.4 vs. producer practice; three viewers disagree | REFUSE, log `TT-c` |
| A-2 | **Symbolic TrueType with only a `(3,1)` cmap** | ISO 32000-1 forbids, ISO 19005-2 §6.2.11.6 permits; veraPDF, Callas and 3-Heights each behave differently | REFUSE, log `TT-d` `[CITED: veraPDF-library#818]` |
| A-3 | **TrueType with no `cmap` at all** | PDFium falls back to identity, PDFBox to `post`. Both are guesses. | REFUSE for edit, log `TT-e` |
| A-4 | **Font with conflicting cmaps** (format-0 Apple Roman + format-4 Unicode disagreeing on the same code) | Selection order is per-implementation | REFUSE, log `TT-f` |
| A-5 | **Symbolic simple font, not embedded** | There is no font program. Whatever the viewer substitutes decides the pixels. | REFUSE (21 docs). Distinct from A-1: not a spec ambiguity, an *information* ambiguity. Log `NOEMB` |
| A-6 | **`/Encoding` names a base encoding the font program contradicts** (e.g. `/WinAnsiEncoding` on a symbol font) | Non-symbolic path says use the name; the program has no such glyphs | Resolvable — the glyph-presence check catches it. Downgrade to `editable-with-substitution`, do not refuse |
| A-7 | **`/ActualText` covering a span** | The span's user-visible text is not the concatenation of its glyphs' Unicode, and individual glyphs inside it may not be addressable | Use `/ActualText` for display; **never as an edit target**. Mark the span not-editable, log `ACTUALTEXT` |
| A-8 | **Glyph with no `/ToUnicode` and a non-AGL glyph name** (e.g. `g47`, `uni` -less subset names) | The glyph renders; the character it represents is unknown | Per-glyph refusal (D-05). Log `NOUNI`. This is exactly what `govdocs1_000_000135.pdf` produces — Type3 glyphs with `cid=0, text=''` |

**A-6 is the important negative result:** it looks ambiguous and is not. Resolve it with a glyph-presence query against the parsed font program (never against the PDF dictionaries), and downgrade rather than refuse.

---

## 3. Run clustering — glyphs into visual lines (D-01)

### What existing implementations do, and what each gets wrong

| Implementation | Line grouping | Failure mode |
|---|---|---|
| **pdfminer.six** (`LAParams`) | `char_margin=2.0` (× char width) groups chars into a line; `line_margin=0.5` (× line height) groups lines into a paragraph; `word_margin=0.1` (× char width) inserts spaces; `boxes_flow=0.5` orders boxes. `[CITED: pdfminer/layout.py docstring]` | Everything is relative to *character width*, so a run of narrow glyphs (`illi`) gets a smaller space threshold than a run of wide ones. Two-column detection is `boxes_flow`, a single scalar — it does not detect columns, it weights a sort. |
| **pdf.js `TextLayer`/`getTextContent`** | Thresholds as fractions of **font size**: `notASpace = 0.03×fs`, `trackingSpaceMin = 0.102×fs`, `spaceInFlowMin = 0.102×fs`, `spaceInFlowMax = 0.6×fs`, `negativeSpaceMax = −0.2×fs`. Line break when vertical movement exceeds 50% of line height. `[CITED: mozilla/pdf.js src/core/evaluator.js]` | Items are *rendering* groupings. Overlapping strings merge (#7445); font transitions vanish from `fontName` (#7297). Not usable as addresses — already settled. |
| **PDFBox `PDFTextStripper`** | `expectedStartOfNextWordX = endOfLastTextX + min(spaceWidth × spacingTolerance, avgCharWidth × averageCharTolerance)` with `spacingTolerance=0.5`, `averageCharTolerance=0.3`. When the font's space width is 0 or NaN, `deltaSpace = Float.MAX_VALUE` so the char-width term wins. Lines group by baseline **overlap** (`maxYForLine`, ~0.1 unit tolerance), not by equality. `[CITED: PDFBox PDFTextStripper]` | Best of the three. The `min()` of two independent estimators, with an explicit degenerate-case fallback, is the design to copy. Still gets multi-column wrong without `setSortByPosition`. |
| **playa** | `extract_text_untagged` inserts a space when `origin − prev_end > 0.5` — an **absolute** 0.5 units, with the source comment `# 0.5 here is a heuristic!!!`. Line break via `_next_line`: the y-component of the origin decreased. `[VERIFIED: read playa/page.py:550-620]` | Absolute threshold means it is wrong at every font size except one. This is precisely the number D-03 replaces. Do not consume `extract_text*` for anything load-bearing. |

### Recommended clustering algorithm

Operate on the glyph stream in **stream order**, in device space (post-CTM), per page (plus per XObject/annotation invocation — see §5).

**Step 1 — sort into baseline bands.** Do **not** group by exact `y`. Group by baseline within a tolerance, using PDFBox's overlap test rather than equality:

```
same_line(g_prev, g) ⟺
    |baseline(g) − baseline(g_prev)| < 0.2 × effective_font_size
    AND  the writing direction is unchanged
```

Compute `baseline` as the y of the glyph origin projected onto the text-line direction implied by the **text rendering matrix**, not the raw device y. This is what makes rotated text work.

**Step 2 — break the band into runs.** Emit a break when any of:

| Break cause | Test |
|---|---|
| Font change | `gstate.font is not previous font` (identity, not `/BaseFont` name) |
| Size change | `effective_font_size` differs by > 1% |
| Baseline shift | fails `same_line` above, or `Ts` (rise) changes — **this is what separates a superscript from a new line** |
| Render-mode / visibility change | `gstate.render_mode` changes, or clip/OCG visibility changes |
| Colour change | `gstate.ncolor` changes (D-01 does not name colour, but a colour change is a visible seam a user perceives as a boundary; recommend including it and recording the decision) |
| Gap | `gap > threshold` (§4) |
| Direction reversal | horizontal advance goes backwards by more than `0.2 × fs` — the pdf.js `negativeSpaceMax` rule |
| Bad glyph (D-05) | glyph classification is `not-editable` — the run splits, the glyph gets its own single-glyph locked record |

**Step 3 — insert synthetic spaces.** Within a run, where `space_threshold < gap ≤ break_threshold`, insert a synthetic space *into the run's display text only*. It has no glyph record and no byte offset. Keep the two thresholds distinct — one word gap does not end a run.

### Superscript vs. line break

A superscript is a baseline shift with **no horizontal reset**: `Δy ≠ 0` and `Δx > 0` and `|Δy| < 0.5 × fs`. A line break has `Δx < 0` (carriage return) or `|Δy| ≥ 0.5 × fs`. Additionally, a superscript is usually implemented as `Ts` (text rise), which is *state*, not geometry — check `gstate.rise` first, and only fall back to geometry when `Ts == 0` and the producer moved the matrix instead. `[ASSUMED — the Ts-first heuristic is sound but not corpus-validated; the geometry fallback is what pdf.js does]`

### RTL and vertical writing

`[VERIFIED: read playa/font.py]` playa exposes `font.vertical` (from `cmap.is_vertical()`), per-glyph vertical displacement `vdisp`, and the position vector — including the `/DW2` default `[880, −1000]`. So vertical mode is *decodable*; the clustering must switch its band axis from y to x and its advance axis from x to y. `playa.page._next_line` already models this.

RTL is different and worse: PDF has **no** RTL text state. Arabic and Hebrew are emitted in visual order by the producer, so glyph stream order is already visual, and the run reads correctly left-to-right in *stream* order but is semantically reversed. There is one marked-content signal, `/ReversedChars`, which playa honours in `extract_text_tagged`. **Recommendation: detect RTL by Unicode bidi class of the run's decoded text, mark the run `editable: false, reason: "right-to-left text"` in v1, and record it as a deferred capability.** Editing an RTL run correctly requires re-shaping and re-ordering, which is the reflow problem in miniature. No corpus fixture exists (the corpus has CJK but no RTL), so it would be untestable anyway.

### Rotated text (non-identity `Tm`)

`[VERIFIED: playa exposes `TextObject.matrix`, `scaling_matrix`, `text_matrix` and per-glyph `matrix`]` Clustering must never read raw device x/y. Derive the line direction from the text rendering matrix `TRM = Tm × CTM`, project each glyph origin onto it, and cluster in that 1-D projected space. A page with text at 0°, 90° and 45° yields three independent band sets keyed by rotation angle (quantise to ~1°).

### Two-column layout — the Gate G1 case

Do **not** attempt column detection. D-01 defines a run as a visual line, and a two-column page has two independent lines at the same baseline. The correct handling falls out of Step 2's gap rule: the inter-column gutter is far wider than any word gap, so the band splits into two runs naturally. **Column detection would only be needed for reading *order*, which Phase 2 does not owe anybody** — reading order is a Phase 7 export concern.

The real two-column hazard is the *opposite*: producers commonly emit both columns interleaved, so glyphs at the same baseline in different columns arrive non-adjacently in stream order. Therefore **Step 1 must sort each baseline band by projected position before Step 2 walks it**, and Step 2's gap must be computed on the sorted order, not stream order. Missing that sort is the specific bug that makes two-column pages produce interleaved gibberish.

### Glyph-at-a-time — the other Gate G1 case

`[VERIFIED: measured]` Present in this corpus. `irs_1040_instructions.pdf`'s Form XObject `I1` emits `Futu` then `r` as consecutive `Tj` operators at byte offsets 673 and 679. The clustering handles it for free — it is just a run whose glyphs come from many operators, which is exactly what D-01 specifies. The thing that breaks on it is any code that assumes one operator == one run. **`TextObject`-count-per-page is 371 on `irs_1040_instructions.pdf` for 4,725 glyphs — 12.7 glyphs per operator on average, with a long tail at 1.**

---

## 4. The synthetic-space threshold and how to measure it (D-03)

### Standard formulations

| Family | Formula | Used by | Behaviour |
|---|---|---|---|
| Fraction of **space glyph width** | `gap > k × width(space)` , `k ≈ 0.5` | PDFBox (`spacingTolerance`) | Correct in principle. Fails hard when the font has no space glyph — extremely common in subset fonts, where a face used only for a heading may never encode code 32. |
| Fraction of **average char width** | `gap > k × avgCharWidth`, `k ≈ 0.3` | PDFBox (`averageCharTolerance`), pdfminer (`word_margin=0.1` × char width) | Robust, but drifts with content: a line of digits and a line of `illi` get different thresholds. |
| Fraction of **font size** (em) | `gap > k × fontSize`, `k ≈ 0.102` | pdf.js (`TRACKING_SPACE_FACTOR`) | Stable across content, needs no font metrics at all, and font size is always available. |
| **Absolute** text-space units | `gap > 0.5` | playa | Wrong at every size but one. |

**Recommendation: use the em formulation as primary (`gap / effective_font_size`), with PDFBox's `min()` guard.** Concretely:

```
threshold = min(K_EM × effective_font_size,
                K_SPACE × space_advance)          # omit this term if the font has no space glyph
break     = BREAK_EM × effective_font_size        # separate, larger constant for run breaks
```

where `effective_font_size` is the em height in device space derived from the full text rendering matrix (`Tf` size × `Tm` scale × `Tz`/100 × CTM scale), **not** `gstate.fontsize`, which on real files is frequently `1.0` with the real size living in `Tm`. `[VERIFIED: measured — `irs_form_w9.pdf` reports `gstate.fontsize == 1.0` with `line_matrix == (7.0, 0, 0, 7.0, 36.0, 738.832)`]` Getting this wrong makes the threshold 7× too small on that document and is the single easiest way to produce a green-but-wrong tuning run.

### How to obtain ground truth — the recommended method

Four options were evaluated:

| Option | Coverage | Circularity | Verdict |
|---|---|---|---|
| Tagged PDFs (`/StructTreeRoot`, `/ActualText`) | **32 of 216 docs = 15%** `[VERIFIED: measured]` | None | Viable, small, and biased toward modern Acrobat/Word output — the population where extraction is already easy. Use as a *secondary* check only. |
| `pdftotext` (Poppler) as reference | 100% | Not circular w.r.t. D-04, but it embeds **Poppler's own threshold**. Minimising disagreement tunes toward Poppler, not toward truth. | Reject as the primary metric. Useful as a third-opinion tiebreak. |
| Hand-labelled samples | Whatever you label | None | Expensive, unrepeatable, and does not scale to a regression suite. Reject. |
| **★ Held-out real space glyphs (self-supervised)** | **88% of documents; 11.1% of all glyphs are real spaces** `[VERIFIED: measured on a 60-doc random sample]` | None — the labels come from the producer's own glyph stream | **Recommended.** |

**The method:** a document that draws a literal space glyph has already told you where its word boundaries are. Remove the space glyphs from the geometry, run the synthetic-space inference over the remaining glyphs, and measure how many of the known boundaries it recovers and how many it invents. No labelling, no external tool, no circularity, and it produces a proper ROC.

**Metric to minimise: `1 − F1` on the binary per-gap classification (space / no-space), computed over all held-out gaps in the tuning set, weighted equally per gap.** Report precision and recall separately, because their costs differ: a false positive (`Invo ice`) breaks find-and-replace on a real word; a false negative (`InvoiceTotal`) merges two runs into one address. Both matter; F1 is the honest single number.

### Prototype run — the method works, with numbers

`[VERIFIED: executed 2026-08-13, 25-document random sample, first 2 pages each, 11,527 positive gaps / 90,498 negative gaps]`

| threshold (em) | recall | FPR | F1 |
|---|---|---|---|
| 0.10 | 0.9866 | 0.0162 | **0.9337** |
| 0.15 | 0.9847 | 0.0161 | 0.9329 |
| 0.20 | 0.9547 | 0.0158 | 0.9184 |
| 0.25 | 0.8088 | 0.0148 | 0.8405 |
| 0.30 | 0.3505 | 0.0124 | 0.4840 |
| 0.40 | 0.0761 | 0.0056 | 0.1359 |

Distributions: true word gaps cluster tightly, p10 = 0.229 em, p50 = 0.274 em, p90 = 0.355 em. Intra-word gaps are 0 for 95% of pairs, p99 = 0.330 em, p999 = 0.616 em.

Three things to take from this:

- **The optimum sits at 0.10–0.15 em**, independently converging on pdf.js's `TRACKING_SPACE_FACTOR = 0.102`. That convergence is corroboration, not coincidence.
- **The false-positive rate floors at ~1.6% and does not improve with a higher threshold.** Those are the kerning-split runs — genuinely large intra-word gaps. They are irreducible by thresholding and are the documented top edge-case source (`pypdf_strreplace`). Expect ~1.6% of word boundaries to be wrong no matter what number is pinned.
- **This prototype normalised by `fontsize × line_matrix[0]`, which is an approximation.** The real tuning run must use the full TRM-derived em (including `Tz` and CTM). Expect the optimum to shift; the *method* is what is validated here, not the number.

Additional guidance: pin **two** constants (`K_EM` for space insertion, `BREAK_EM` for run breaks) and tune them independently. `BREAK_EM` should land near the gutter width of a two-column page — the corpus p999 of 0.616 em is a sensible starting bracket, and the tuning target for it is different (maximise agreement between run count and visual line count on a hand-checked subset, or simply: no run may span a column gutter).

### Honest limitation

Documents that draw **no** space glyphs (12% of the sample — 7 of 58) are exactly the population where synthetic-space inference is load-bearing, and they are excluded from the training set by construction. The threshold is fit on the easy population and applied to the hard one. **Mitigation:** validate the pinned value on the no-space subset using a lexicon metric (fraction of length-≥2 alphabetic tokens present in an English word list, plus fraction of length-1 tokens), reported as a secondary number, and require it not to regress. State this limitation in whatever artifact records the pinned threshold — the same way Phase 1's 8% render tolerance records its derivation.

---

## 5. Text outside `/Contents`

### The four locations, and how each is reached

| Location | How reached | playa support | ID path segment |
|---|---|---|---|
| **Form XObject** | `/Resources /XObject /Xn` where `/Subtype /Form`, invoked by `Do`. CTM composed as `CTM' = /Matrix × CTM`, clipped to `/BBox`. | `Page.xobjects` yields `XObjectObject{xobjid, stream, resources, group, ctm, gstate}`; `XObjectObject.interp()` returns a fresh `LazyInterpreter`. `Page.flatten()` recurses with a **per-branch visited set** (`parents | {stream_id}`) — self-reference is already handled. **No depth cap.** `[VERIFIED: read playa/page.py:474-520]` | `x{xobjStreamObjid}` |
| **Annotation appearance stream** | `/Annots[i] /AP /N` — which may be a stream, **or a dictionary keyed by appearance state selected by the annotation's `/AS`**. Positioning is ISO 32000-1 §12.5.5: transform `/BBox` by `/Matrix`, compute its bounding box, then compute the matrix `A` that maps that box onto `/Rect`. | `Page.annotations` yields `Annotation{type, rect, props}` — **`props` is the raw dict and that is all.** playa does **not** interpret `/AP`. `[VERIFIED: read playa/page.py:692-780]` | `a{annotIndex}:{apStateName}` |
| **Tiling pattern** | `/Resources /Pattern /Pn` with `/PatternType 1`; the pattern object *is* a content stream, invoked implicitly by `scn`/`SCN` with a pattern colour space. | **None.** playa has no `PatternObject` and `do_scn` only sets colour. `[VERIFIED: grep interp.py]` | `t{patternStreamObjid}` |
| **Type3 `/CharProcs`** | Each glyph is a content stream in `/CharProcs`, indexed by glyph name. Can itself contain text-showing operators. | `Type3Interpreter` exists (`playa/interp.py:1118`) and `Type3Font.charprocs` is exposed. | `y{charProcName}` |

**Consequence for the interpreter:** the walker must own the recursion, not delegate to `Page.flatten()`. `flatten()` gives you objects but not the inner interpreter, so you lose `_curpos`/`streamid` for anything below the top level. Drive `LazyInterpreter` yourself at every level. Add a **depth cap** (playa has a visited set but no depth limit — a 500-deep XObject chain is a Python recursion blow-up), and reuse the same visited-set-per-branch semantics.

### Shared Form XObjects — detection and measured cost

Detection: build a map `formXObjectStreamObjid → set(pages referencing it)` by walking every page's `/Resources /XObject` (plus nested XObject resources). Any objid with `|pages| > 1` is shared. pikepdf exposes `obj.objgen` for identity; do **not** compare by resource name — `/Fm0` on page 3 and `/Fm0` on page 9 are frequently different objects, and the same object frequently has different names on different pages.

`[VERIFIED: measured across the 19 `form_xobjects` corpus documents]`

| Document | Pages | Form XObjects | Shared (>1 page) | Max page-references |
|---|---|---|---|---|
| `irs_1040_instructions.pdf` | 126 | 25 | 8 | **43** |
| `irs_publication_17.pdf` | 142 | 14 | 8 | **47** |
| `govdocs1_004_004119.pdf` | 26 | 5 | 4 | 22 |
| `irs_1040_tax_tables.pdf` | 28 | 4 | 1 | 2 |
| `invoice_1905_james_green.pdf` | 3 | 1 | 1 | 3 |
| `govdocs1_003_003074.pdf` | 8 | 2 | 0 | 1 |
| `govdocs1_004_004126.pdf` | 7 | 6 | 0 | 1 |
| `govdocs1_004_004132.pdf` | 38 | 2 | 0 | 1 |

Shared XObjects are common and they are running headers and footers — the text most visible on a page. **Confirmed: mark shared-Form-XObject runs `editable: false, reason: "shared across N pages"` in v1.** The measured cost is small (typically one header line per page on 5 of 19 documents) and the alternative — copy-on-write per page — changes the object graph, which is Phase 3's territory and a `/Resources`-mutation hazard in its own right.

**Non-shared Form XObject text stays fully editable.** That is the majority of it: 11 of 19 documents have no shared form XObject at all.

### Run ID scheme, extended

Keeping the settled shape from `research/SUMMARY.md` and extending the stream-part segment into a **path**:

```
{sourceHash}:p{page}:c{part}[/x{xobjObjid}]*[/a{annotIdx}:{apState}][/t{patternObjid}][/y{charProcName}]:o{byteOffset}[:g{start}-{end}]
```

**Define `o` as the byte offset of the operator keyword token within its own decoded content-stream part — not a counted ordinal.**

Rationale (this is a recommendation, not a relitigation of the settled scheme):
- It is free — `LazyInterpreter._curpos` and the `ObjectParser` pass both hand it to you.
- It is directly verifiable against the immutable original bytes: given the source hash and the ID, you can seek to the offset and confirm the keyword is there. An ordinal can only be verified by re-running the count.
- A counted ordinal requires the counting rule to be *identical* in index mode and rewrite mode. That is precisely the drift the one-walker rule exists to prevent, and a byte offset has no counting rule to drift.
- It is stable under sub-run splitting (D-02): all sub-runs of one operator share the `o` and differ only in `:g{start}-{end}`.

**Note the interaction with §6:** the offset is *within the part*, so it is only meaningful alongside the part index, and it is **invalid in coalesced space**. Do not coalesce before indexing.

---

## 6. `/Contents` array coalescing

### The failure mode, confirmed and reproduced

`[VERIFIED: measured — 114 `contents_array` documents, 2,560 part boundaries]`

| Measurement | Value |
|---|---|
| `/Contents` part boundaries examined | 2,560 |
| Boundaries with whitespace on at least one side (safe under naive concat) | 2,482 (97.0%) |
| **Boundaries with no whitespace on either side (fusion risk)** | **78 (3.0%), across 18 of 114 documents** |

The reproduction, exact:

```
govdocs1_002_002167.pdf, page 0, 11 parts
  naive b"".join(parts)  → 890 tokens, token[798] = KWD(b'QBT')
  b"\n".join(parts)      → 891 tokens, token[798] = KWD(b'Q'), token[799] = KWD(b'BT')
```

That is qpdf #444, in this repository, with a named file and a named token index. Other observed risky boundaries: `...q` ‖ `/GS1 gs...`, and dozens of `...)]` ‖ `TJ...` (benign — `]` is a delimiter — but indistinguishable from the dangerous kind without lexing).

### The correct rule, and who does it

| Library | Behaviour | Correct? |
|---|---|---|
| **`playa`** | `ContentParser` parses **each part separately**, calling `_parser.newstream(buffer, streamid=...)` at exhaustion. It **never concatenates**. `[VERIFIED: read playa/parser.py:898-950]` | **Yes** — fusion is structurally impossible. Trade-off: a token genuinely split *mid-token* across parts (which §7.2 forbids but non-conforming writers produce) is lost rather than fused. Losing a token is a visible failure; fusing one is a silent corruption. Correct trade. |
| **`pikepdf`** | `Page.contents_coalesce()` joins parts **with a newline inserted between each**. Measured on `govdocs1_000_000010.pdf`: 8 parts, naive concat = 11,088 bytes, coalesced = 11,095 bytes, exactly 7 bytes inserted at the 7 boundaries. `[VERIFIED: executed]` | **Yes.** Note it **mutates the PDF object** — it replaces the `/Contents` array with a single stream. |
| **Anything hand-rolled with `b"".join(...)`** | Fuses. | **No.** This is the thing to never write. |

### Recommendation

**Do not coalesce for indexing.** playa's per-part parsing is already correct, and per-part byte offsets are what the run ID scheme wants (§5). Coalescing would destroy the addressing.

TEXT-07 is therefore satisfied not by *adding* coalescing but by **proving that no naive concatenation exists anywhere in the codebase and that the per-part path produces the right tokens**. The check that satisfies TEXT-07:

```
assert token_stream(per_part_parse(parts)) == token_stream(ObjectParser(b"\n".join(parts)))
```
across all 114 `contents_array` documents. It goes red the moment anyone writes `b"".join`.

If Phase 3 needs a coalesced stream for rewriting, use `pikepdf.Page.contents_coalesce()` on a *copy*, and translate addresses from part space to coalesced space explicitly (offset = sum of prior part lengths + 1 per inserted newline + part-local offset). That translation is arithmetic and testable; a fuzzy re-match is not.

---

## 7. Four-bucket page classification (CLAS-01..CLAS-03, CLAS-05)

### The three signals, defined operationally

**Signal 1 — visible glyph count.** A glyph is *visible* iff **all** of:
- `gstate.render_mode ∉ {3, 7}` — 3 is invisible, 7 is add-to-clip-only.
- Not clipped entirely away. Practical approximation: the glyph bbox intersects the current clipping path's bbox. playa tracks `GraphicState.clipping_path` but it is typed `None` in 1.1.0, i.e. **not populated** `[VERIFIED: read playa/content.py GraphicState]`. Recommendation: approximate with the page CropBox intersection, and **log that clipping is not evaluated** rather than pretending it is.
- Not inside an optional-content group that is OFF in the default configuration. Reachable via `mcstack` — a `BDC` with tag `/OC` and a property referencing an OCG — cross-checked against `/Root /OCProperties /D /OFF`. `[VERIFIED: measured — only **3 of 216** corpus documents have `/OCProperties` at all.]` Low-frequency; implement the check, do not over-invest.
- `gstate.ncolor` is not identical to the fill beneath it. **Out of scope** — white-on-white text is a real hiding technique but detecting it requires compositing. Note as a known gap.

`[VERIFIED: measured on a 40-document / 76-page random sample]` render-mode distribution: **Tr=0 91.41%, Tr=3 8.59%**, no other mode observed. The Tr=3 population is concentrated in the two OCR documents. So the signal is cleanly bimodal in practice.

**Signal 2 — image coverage.** ⚠️ **The naive formulation is wrong.** Summing image-XObject bbox areas and dividing by the page area yields values **above 1.0** on real files — measured 2.0 on `invoice_book_1842.pdf` and 2.749 on `nasa_graphics_standards_manual.pdf`, because a scanner emits several overlapping or tiled image XObjects per page. Recommendation: compute the **union area** of image bboxes clipped to the CropBox (a simple rectangle-union or a coarse raster occupancy grid — an 80×80 boolean grid over the CropBox is sufficient and O(images)). Then `coverage = union_area / cropbox_area`, bounded to [0, 1].

**Signal 3 — invisible:visible glyph ratio.** `invisible / max(visible, 1)`.

### Proposed thresholds

Starting values, to be validated (see below) and pinned with their measurement recorded:

| Bucket | Rule |
|---|---|
| **Scan, no text layer** | `coverage ≥ 0.5` AND `visible + invisible == 0` |
| **OCR'd scan** | `coverage ≥ 0.5` AND `visible == 0` AND `invisible > 0` |
| **Vector-outlined text** | `coverage < 0.5` AND `visible + invisible == 0` AND `path_object_count ≥ P` |
| **Empty page** | `coverage < 0.5` AND `visible + invisible == 0` AND `path_object_count < P` |
| **Editable** | `visible > 0` (subject to per-run classification) |
| **Mixed / degraded** | `visible > 0` AND `coverage ≥ 0.5` AND `invisible/visible ≥ 3` — a scan with a small caption. Classify as OCR'd scan but keep the visible runs editable (CLAS-05). |

`P` needs a fixture to pick and **no fixture exists** — see below. `[ASSUMED: P ≈ 200]` on the reasoning that a page of outlined body text produces one path object per glyph, so a text-shaped page has hundreds; a decorative page has tens.

### How classification is validated — and the corpus problems that block it

`[VERIFIED: measured on the actual corpus files]`

| Document | Manifest label | What it actually is |
|---|---|---|
| `invoice_book_1842.pdf` | `ocr_scan` | **Correct, and better than labelled.** 52 pages: 7 with zero glyphs and full image coverage (bucket 1), 45 with invisible-only glyphs (bucket 2). One document supplies both scan buckets. |
| `nasa_graphics_standards_manual.pdf` | `vector_outlined_text` | ❌ **WRONG. It is an OCR'd scan.** `/Producer = Adobe Acrobat Pro 11.0.0 Paper Capture Plug-in`, `/Creator = Canon DR-7550C TWAIN`, Standard-14 non-embedded Type1 fonts, **every glyph render mode 3**, over 984×1200 image XObjects. `extract_text()` returns a clean OCR'd index page. |
| **any document** | — | ❌ **No vector-outlined-text page exists in the corpus.** A scan for pages with zero glyphs, image coverage < 0.2 and > 200 path objects returned **0 candidates across all 216 documents.** |
| **any document** | — | ❌ **No mixed mostly-editable-with-a-few-scans document exists.** CLAS-05's stated case ("40-page contract with 3 scanned pages → 37 editable, 40 page-op-able") has no fixture. `invoice_book_1842.pdf` is the inverse. |

Two of Gate G1 criterion 3's three named claims currently have no valid fixture. **This is a Wave 0 blocker and it is the same failure class Phase 1 hit three times** — a check that goes green because it is measuring a document that does not contain what the label says.

**Required Wave 0 remediation:**
1. Correct `corpus/manifest.json`: move `nasa_graphics_standards_manual.pdf` from `vector_outlined_text` to `ocr_scan`. This makes the `vector_outlined_text` category zero-count, which `tools/probe_corpus.py --enforce_full_coverage` **will fail on** (`CANONICAL_CATEGORIES - declared_categories_seen`). That failure is correct and desirable — it is the existing corpus gate doing its job, and it must not be silenced.
2. Harvest or construct a genuine vector-outlined-text document (Illustrator/Inkscape "convert text to outlines" export is the canonical producer; check redistribution licence per `corpus/sources.md` policy) and disclose it in the "Disclosed substitutions" section if constructed.
3. Construct the CLAS-05 mixed fixture by merging N editable pages with 3 scanned pages from `invoice_book_1842.pdf` via pikepdf. This is a *test fixture*, not a corpus category — keep it under `tests/fixtures/`, not `corpus/public/`, so it never enters the harness's producer-diversity accounting.

### Distinguishing vector-outlined text from a scan

They differ on **signal 2**, not signal 1. Both have zero glyphs. A scan has one-or-few large image XObjects covering the page; outlined text has zero images and hundreds-to-thousands of small filled path objects with glyph-like bounding boxes (height 6–20 units, aspect < 2, clustered on horizontal baselines). The path-count threshold `P` is the primary discriminator; a secondary, more robust one is **baseline clustering of path bboxes** — outlined text's path bboxes form rows, a logo's do not. Recommend implementing count-only for v1 and recording baseline clustering as the upgrade path if `P` proves unstable once a fixture exists.

---

## 8. What playa gives vs. what must be built

**This determines the fundamental shape of the interpreter. Answered concretely.**

### Field-by-field availability

`[VERIFIED: read playa 1.1.0 source + executed against corpus files]`

| Required field (TEXT-02) | playa source | Availability |
|---|---|---|
| `code` / `cid` | `GlyphObject.cid` | ✅ direct |
| `glyph` | `gstate.font` + the font's own decode; `playa.font.Font` subclasses expose `charprocs`, `cmap`, `vertical` | ✅ direct (the font object *is* the resolved encoding) |
| `unicode` | `GlyphObject.text` — **`/ToUnicode`-derived; display and search only** | ✅ direct |
| `x`, `y` | `GlyphObject.matrix[4:6]`, `GlyphObject.origin`, `GlyphObject.bbox` — device space, CTM composed | ✅ direct |
| `advance` | `GlyphObject.displacement` → `(dx, dy)` tuple (note: **a tuple, not a scalar** — vertical mode uses `dy`) | ✅ direct |
| `font` | `gstate.font` (object identity is the correct key — never `/BaseFont`) | ✅ direct |
| `render_mode` | `gstate.render_mode` | ✅ direct |
| `visible` | derived from `render_mode` + `mcstack` (OCG) + clip | ⚠️ derived; `gstate.clipping_path` is **not populated** in 1.1.0 |
| **`stream_id`** | `LazyInterpreter.parser.streamid` — a documented property with an upstream `TODO: Ideally this would be returned in __next__` | ⚠️ **available but not on the object** — must be read off the interpreter at yield time |
| **`operator_index`** | ❌ not exposed on any object. `LazyInterpreter._curpos` holds the byte offset of the operator keyword; **private attribute** | ❌ **must be tracked by us** |
| **`item_index_within_TJ`** | `TextObject.args` gives the raw `List[bytes \| float]`, so the index is countable, but the mapping from glyph → arg index is not exposed | ❌ **must be tracked by us** |
| **`byte_offset_within_string`** | ❌ not exposed | ❌ **must be tracked by us** |

**Conclusion: playa gives every semantic field and no provenance field.** But the missing four are all obtainable from the *same library*, through its public parser.

### The recommended interpreter shape

`playa.parser.ObjectParser` is `Iterator[Tuple[int, PDFObject]]` — **it yields the byte offset of every token, operands included.** `LazyInterpreter` consumes exactly that parser, in exactly that order. So:

**Per content-stream part, run two passes over the same buffer and zip them by operator ordinal.**

- **Pass A — provenance.** `ObjectParser(part_buffer, doc)`. Accumulate operands on a stack; on a `PSKeyword`, emit `(keyword, keyword_byte_offset, [(operand, operand_byte_offset), ...])`. For a `TJ`, the operand is an array — its element offsets require descending one level, which `ObjectParser` also does (it yields array elements before the array is popped; `ObjectParser.pop_to` returns `(pos, items)`). This pass gives `stream_id`, `operator_index` (as byte offset), `item_index_within_TJ`, and `byte_offset_within_string`.
- **Pass B — semantics.** `LazyInterpreter(page, [part], filter_classes=[TextObject])`. Yields resolved `TextObject`s with `args`, `line_matrix`, `gstate`, and iterable `GlyphObject`s.
- **Join:** the *k*-th text-showing operator in Pass A corresponds to the *k*-th `TextObject` in Pass B. Exact, deterministic, same parser, same order. **Not a fuzzy join.**
- **Free always-on assertion:** after each Pass B yield, `LazyInterpreter._curpos` must equal the keyword byte offset from Pass A. Assert it. This costs nothing, catches any desynchronisation immediately, and is the tripwire that fires if a `playa` upgrade changes iteration semantics.

Empirically confirmed on `corpus/public/irs_form_w9.pdf` page 0:

```
curpos=204 → buffer[174:210] = b'7 0 0 7 36 738.832 Tm\n(Form  )Tj\n/T1'
             (byte 204 is the 'T' of 'Tj')  ✔ points at the operator keyword
curpos=250 → b' 0 0 24 56.23 738.832 Tm\n(W-9)Tj\nEMC'
curpos=435 → b'9.409 Tm\n(\\(Rev. March 2024\\))Tj\nEMC'   ← note escaped parens; hex output on rewrite avoids this
```

And on a `/Contents` array (`irs_form_1040.pdf`, 8 parts of ~9.4 KB each), `parser.streamid` steps 2405→2412 while `_curpos` resets per part — exactly the `(part, offset)` addressing the run ID needs.

### What must be built (the actual Phase 2 code)

1. The two-pass walker above, with XObject / annotation `/AP` / tiling-pattern / Type3 `/CharProcs` recursion driven by us (§5), with a depth cap and a visited set.
2. The forward encoding decision table (§1) as an explicit dispatch with a logged branch ID — playa resolves encodings internally but does **not** tell you which branch it took, and D-04/TEXT-04 require exactly that. This is a *parallel* structural determination from the font dictionary, not a re-implementation of the decode.
3. Run clustering + synthetic spaces (§3, §4).
4. Per-glyph and per-run editability classification (§1's refusal list, §7).
5. Per-page classification (§7).
6. `Code→Glyph` / `Code→str` newtypes and the checker that enforces them (§Code Examples).
7. The `(part, byte-offset)` run ID codec.

**Not built:** the graphics/text state machine, CTM composition, encoding decode, CMap resolution, `/W` and `/Widths` lookup, Type3 `/FontMatrix` scaling, `/CIDToGIDMap` streams, inline-image tokenisation. All of that is `playa` and it is already validated on this corpus.

### The one-module boundary

`import playa` must stay in one file. Note that the recommendation above imports **three** playa symbols — `playa.open`, `playa.parser.ObjectParser`, `playa.interp.LazyInterpreter` — plus reads one private attribute (`_curpos`). All of that belongs in the same single module. `playa-pdf==1.1.0` is already pinned exactly in `pyproject.toml`; the `_curpos` dependence makes that pin load-bearing rather than merely tidy, and the alignment assertion above is what makes an accidental upgrade fail loudly instead of silently.

---

## 9. Provenance round-trip — the minimum write capability (Gate G1 criterion 1)

Gate G1 criterion 1 names *rewrite*, which Phase 3 owns. The line to draw:

**Phase 2 builds an identity-rewrite: parse → unparse with zero semantic change, then re-index.** Nothing more.

Concretely, per page:
1. Index the page → run map `M₁` (run IDs + glyph records).
2. `ops = pikepdf.parse_content_stream(page)`; `new_bytes = pikepdf.unparse_content_stream(ops)`; write it back and `pdf.save()`.
3. Re-index the output → run map `M₂`.
4. Assert: the **ordered sequence of run IDs is identical**, and each glyph record matches on `(code, unicode, font identity, render_mode, x, y, advance)` within epsilon.

**Why this is the right line:**

- It exercises the entire address round-trip — parse, offset computation, ID encode, re-parse, ID decode, re-match — which is what the criterion is actually about.
- It requires **zero** width fitting, zero font subsetting, zero glyph substitution, zero TJ arithmetic. Those are Phase 3, and none of them are needed to prove IDs survive.
- It fails loudly on exactly the bugs Phase 2 can introduce: a byte offset computed in the wrong coordinate space, an ID that encodes a counted ordinal that shifts, an inline image mis-tokenised, a `/Contents` part boundary handled inconsistently between index and re-index.
- It is *harder* than it sounds, and that is the point: `unparse_content_stream` re-serialises literal strings, numbers and whitespace differently from the input, so **byte offsets will change**. That is the correct behaviour and the correct test: run IDs address the **immutable original** (TEXT-03), so `M₂` must be indexed against the *original* addresses, not re-derived from the output. The assertion is therefore: re-indexing the output produces the same *sequence and count* of runs with the same content, and every original run ID still resolves against the original bytes.

**Explicitly out of scope for Phase 2:** any operator whose operands change; anything touching `/Font` resources; `TJ` number adjustment; anything that changes a glyph. If a task is tempted to "just change one word to prove it," that is Gate G2a and it belongs in Phase 3.

**One optional extension worth considering** (and this is the only place the line could reasonably move): a **null-edit** that rewrites a `Tj` literal string as an equivalent **hex string** `<48656C6C6F>` with identical bytes. It changes the serialisation without changing a single glyph, so the masked pixel diff must be exactly zero in all three engines, and it proves the index→address→rewrite→re-index loop end to end rather than just parse→unparse. It requires no width logic. Recommend including it; recommend refusing anything beyond it.

**Verification vehicle:** `harness/run_corpus_harness.py`, not a new mechanism. Phase 1 measured the cross-engine tolerance (8%) and built `masked_diff.masked_pixel_diff()` as the exact zero-tolerance primitive for same-engine before/after. An identity rewrite is the ideal same-engine test: the diff must be **exactly zero**, no tolerance. `[VERIFIED: read harness/run_corpus_harness.py module docstring]`

---

## 10. Performance under D-06

`[VERIFIED: measured 2026-08-13 on this machine (macOS arm64, Python 3.13, playa-pdf 1.1.0)]`

### Parse cost

| Document | Pages | `playa.open()` | Page 1 glyphs | Page 1 parse | 10 pages |
|---|---|---|---|---|---|
| `irs_1040_instructions.pdf` | 126 | 5.9 ms | 984 | 9.5 ms | 64.5 ms (32,328 glyphs) |
| `irs_publication_17.pdf` | 142 | 5.9 ms | 719 | 15.0 ms | 122.9 ms (52,410 glyphs) |
| `far_federal_acquisition_regulation.pdf` | **2,026** | 5.5 ms | 178 | 2.0 ms | 16.8 ms (3,599 glyphs) |

**Document open is ~6 ms regardless of size** (2,026 pages opens as fast as 126). D-06's "first page usable almost immediately" is comfortably met: open + first page is **12–21 ms**.

### Full-document parse — the first-search cost

| Document | Pages parsed | Wall time | Glyphs | ms/page |
|---|---|---|---|---|
| `irs_1040_instructions.pdf` | 126 | **21.0 s** | 595,373 | 167 |
| `far_federal_acquisition_regulation.pdf` | 126 | 9.3 s | 324,594 | 74 |

Extrapolated to a **400-page document at IRS density: ~67 seconds.** That is the price of the first find-across-all-pages, and it lands on the user in one lump. The deferred "progress affordance" is not a nicety — at 67 seconds it is the difference between a feature and a hang. Worth recording the measured number in whatever artifact Phase 4 inherits.

Note: the bulk of that cost is playa's per-glyph materialisation. Iterating `TextObject`s only (no glyph expansion) on the same 126 pages costs **12.65 s** — 60% of the full cost — so lazy glyph expansion inside a cached run record recovers ~40% for search-only workloads. Worth doing.

### Memory profile of a cached run map

| Representation | 126 pages, 595k glyphs | Bytes/glyph | Extrapolated to 400 IRS-density pages |
|---|---|---|---|
| `@dataclass(slots=True)` per glyph, 12 fields | **165.7 MB** | 278 | **~526 MB** |
| **Columnar** (`array.array` per field + one interned text list) | **56.1 MB** | 94 | **~178 MB** |
| `TextObject`-level only (no glyph records) | 28.6 MB | — | ~91 MB |

**Recommendation: columnar per-page storage.** One `array.array` per numeric field per page, plus a single joined text string with offsets. It is 3× smaller, it is stdlib-only (no numpy dependency added), and per-page arrays keep D-06's eviction story simple — evict a page, free its arrays.

`[ASSUMED]` A per-glyph Python object graph would also stress the GC on large documents; columnar arrays are opaque to it. Not measured.

**Explicit cache-size consequence to record:** at 178 MB for one 400-page document, a naive unbounded per-session cache is not viable once Phase 4 has concurrent users. Phase 2 should cap the cache by **glyph count, not page count** (page density varies 26× across this corpus — 178 to 4,725 glyphs/page) and evict LRU. Keeping the run *records* (~50/page, negligible) while evicting the *glyph arrays* is the natural two-tier split, and it costs a re-parse of one page (~167 ms) on a miss.

---

# Standard Stack

## Core — all already pinned, nothing new

| Library | Version | Purpose | Why standard |
|---|---|---|---|
| `playa-pdf` | **1.1.0** (exact pin) | Encoding decode, glyph geometry, text/graphics state machine, `ObjectParser` byte offsets | Phase 1 GO verdict with per-file evidence. The pin is now load-bearing (`_curpos`). |
| `pikepdf` | **10.11.0** (bundles qpdf **12.3.2**) | Object layer, font dictionaries, `/Contents` array shape, XObject refcounts, identity rewrite | The only correct source for structure. Note: the CLAUDE.md stack table says qpdf 12.4.0; the wheel actually bundles **12.3.2**, while the system CLI is 12.4.0. Harmless, worth knowing when comparing `qpdf --check` output to library behaviour. `[VERIFIED: `pikepdf.__libqpdf_version__`]` |
| Python | 3.13 | — | `requires-python = ">=3.13"` |

**No new runtime dependency is required for Phase 2.** `fonttools`, `uharfbuzz`, `pypdfium2` and `pillow` are already present and are Phase 3 / Phase 7 concerns; the glyph-presence check in §1 (A-6) will use `fontTools` and it is already pinned.

## Supporting — dev only

| Library | Version | Purpose | Why needed |
|---|---|---|---|
| `mypy` | **2.3.0** | **TEXT-05.** "`Code→Glyph` and `Code→str` are distinct types **the type checker refuses to interchange**" is unverifiable without a type checker, and none is installed. | Mature, standard, MIT. `pyright` is the alternative and would require Node in CI — reject on that basis alone. |
| `pytest` | 9.1.1 (already in dev group) | Test runner | Already present. **Not wired to CI** — see Wave 0 gaps. |

### Alternatives considered

| Instead of | Could use | Tradeoff |
|---|---|---|
| Two-pass `ObjectParser` + `LazyInterpreter` zip | Read `LazyInterpreter._curpos` alone | Simpler (one pass), but `_curpos` gives only the *operator keyword* offset — not `item_index_within_TJ` or `byte_offset_within_string`, both required by TEXT-02. The second pass is not optional. |
| `playa` | `pdfminer.six` | Settled in Phase 1 (PLAYA-DECISION.md: GO). Note `pdfminer.six` was never installed, so the fallback is untested — if a Phase 2 blocker emerges, the swap is a real (if bounded) piece of work, not a flag flip. |
| `mypy` | `pyright` | Requires Node in CI; the repo's CI is Python + a Docker image with PDF CLIs. Adding a JS toolchain for one check is not worth it. |
| Columnar `array.array` | `numpy` | numpy is a new runtime dependency (BSD, licence-clean) for a 3× memory win that `array.array` already delivers. Reject on the no-new-dependency principle. |
| Custom rectangle union for image coverage | `shapely` | New GEOS dependency for a job an 80×80 boolean occupancy grid does in 20 lines. Reject. |

**Installation:**
```bash
uv add --dev mypy==2.3.0
```

**Version verification:** `mypy 2.3.0` resolved and installed cleanly from PyPI on 2026-08-13. `playa-pdf 1.1.0` and `pikepdf 10.11.0` confirmed installed at the pinned versions.

## Package Legitimacy Audit

Phase 2 adds **one** package, dev-only.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---|---|---|---|---|---|---|
| `mypy` | PyPI | 13+ yrs | ~30M/wk | github.com/python/mypy | `[OK]` — `slopcheck install mypy` completed with no SLOP/SUS verdict | Approved |
| `pytest` | PyPI | 15+ yrs | ~60M/wk | github.com/pytest-dev/pytest | `[OK]` | Approved (already present) |
| `playa-pdf` | PyPI | — | — | github.com/dhdaines/playa | not re-run — pinned since Phase 1 and validated by PLAYA-DECISION.md | Approved |
| `pikepdf` | PyPI | — | — | github.com/pikepdf/pikepdf | not re-run — pinned since Phase 1 | Approved |

**Packages removed due to slopcheck `[SLOP]` verdict:** none
**Packages flagged as suspicious `[SUS]`:** none

`slopcheck` was available and executed (`slopcheck install mypy`, `slopcheck install pytest`), both clean. Transitive additions from mypy: `pathspec`, `mypy_extensions`, `librt`, `ast-serialize` — all resolved by pip from PyPI as part of mypy's declared dependencies; **`tools/license_gate.py` must be re-run after adding mypy**, since it enforces on the resolved lockfile and these are new lockfile entries.

---

# Architecture Patterns

## System Architecture Diagram

```
                        ┌──────────────────────────────────────────┐
   original PDF bytes ──▶│  pikepdf.open()   [object layer]         │
   (immutable, hashed)   │  • page tree, /Resources inheritance     │
                         │  • font dicts (encoding branch decision) │
                         │  • /Contents array shape (part list)     │
                         │  • Form XObject reference counting       │
                         └───────┬───────────────────────┬──────────┘
                                 │ structural facts      │ shared-XObject set
                                 ▼                       │
   ┌─────────────────────────────────────────────┐       │
   │  FORWARD ENCODING DECISION TABLE  (§1)      │       │
   │  in: font dict + font program               │       │
   │  out: branch_id  +  editability verdict     │       │
   │       (resolve / substitute / REFUSE+reason)│       │
   └───────────────┬─────────────────────────────┘       │
                   │ per-font verdict + branch_id        │
                   ▼                                     │
   ╔═══════════════════════════════════════════════════╗ │
   ║   THE WALKER   (one function, two modes)          ║ │
   ║                                                    ║ │
   ║   for each content-stream part:                    ║ │
   ║     PASS A  playa.parser.ObjectParser              ║ │
   ║        → (keyword, byte_off, [(operand,byte_off)]) ║ │
   ║     PASS B  playa.interp.LazyInterpreter           ║ │
   ║        → TextObject{args,line_matrix,gstate}       ║ │
   ║           → GlyphObject{cid,text,matrix,displ}     ║ │
   ║     ZIP by operator ordinal                        ║ │
   ║     ASSERT interp._curpos == passA.keyword_off  ◀──╫─┼── free drift tripwire
   ║                                                    ║ │
   ║   recurse (own visited set + depth cap) into:      ║ │
   ║     Do → Form XObject     ─┐                       ║ │
   ║     /Annots → /AP /N      ─┤ each = new part,      ║ │
   ║     /Pattern (tiling)     ─┤ own byte-offset space ║ │
   ║     Type3 /CharProcs      ─┘                       ║ │
   ╚═══════════════╤═══════════════════════════╤═══════╝ │
                   │ glyph records             │ mode=rewrite (Phase 3)
                   ▼                           └──────────▶ pikepdf.unparse_content_stream
   ┌───────────────────────────────────┐
   │  GLYPH CLASSIFIER  (D-05)         │  per glyph:
   │  branch verdict + /ToUnicode      │  ok | locked(reason)
   │  + glyph-presence in program      │
   └───────────────┬───────────────────┘
                   ▼
   ┌───────────────────────────────────────────────────┐
   │  RUN CLUSTERER  (D-01, D-02, D-03)                │
   │  1. project origins onto TRM line direction       │
   │  2. band by baseline (±0.2 em overlap)            │
   │  3. SORT band by projected position  ◀── two-column│
   │  4. break on font/size/rise/Tr/colour/gap/locked  │
   │  5. insert synthetic spaces (tuned K_EM)          │
   └───────┬──────────────────────────────┬────────────┘
           │ run records                  │ per-glyph signals
           ▼                              ▼
   ┌──────────────────────┐   ┌────────────────────────────────┐
   │ RUN ID CODEC (TEXT-03)│   │ PAGE CLASSIFIER (CLAS-01..03)  │
   │ {hash}:p{n}:c{part}   │   │ visible count · image-coverage │
   │   [/x…][/a…]:o{byte}  │   │   UNION (not sum) · inv:vis    │
   │   [:g{s}-{e}]         │   │ → 4 buckets + editable         │
   └──────────┬────────────┘   └───────────────┬────────────────┘
              │                                │
              ▼                                ▼
   ┌──────────────────────────────────────────────────────────┐
   │  PAGE RUN MAP  (columnar arrays, D-06 LRU by glyph count)│
   │  consumed by: Phase 3 rewrite · Phase 5 find · Phase 7 exports │
   └──────────────────────────────────────────────────────────┘
```

## Component responsibilities

| Component | File (suggested) | Owns | Must NOT |
|---|---|---|---|
| playa boundary | one module (successor to `spike/playa_decode_probe.py`) | the only `import playa` in the repo; both passes; `_curpos` assertion | expose a Protocol/ABC/adapter around playa |
| Encoding table | separate module | branch dispatch, branch_id logging, refusal verdicts | call into the walker (it runs *before* the walk, per font) |
| Walker | separate module | traversal, recursion, provenance assembly | decide editability, cluster runs |
| Clusterer | separate module | D-01/D-02/D-03 | know about byte offsets (it consumes glyph records) |
| Classifier | separate module | CLAS-01..05 | be consumed by `tools/probe_corpus.py` — **ever** |
| Run ID codec | separate module | encode/decode/verify against original bytes | be reimplemented anywhere else |

## Pattern 1: The two-pass zip with a free alignment assertion

**What:** run the token parser and the interpreter over the same buffer, join by ordinal, assert the join.
**When to use:** every content-stream part, always.

```python
# Source: verified against playa 1.1.0 (playa/parser.py:898, playa/interp.py:308)
from playa.interp import LazyInterpreter
from playa.content import TextObject
from playa.parser import ObjectParser, PSKeyword

TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}

def operator_table(buffer: bytes, doc) -> list[tuple[int, bytes, list[tuple[int, object]]]]:
    """Pass A: (keyword_byte_offset, keyword, [(operand_byte_offset, operand)])."""
    stack: list[tuple[int, object]] = []
    out = []
    for pos, obj in ObjectParser(buffer, doc):
        if isinstance(obj, PSKeyword):
            if obj.name in TEXT_OPS:
                out.append((pos, obj.name, list(stack)))
            stack.clear()
        else:
            stack.append((pos, obj))
    return out

def walk_part(page, part_stream, doc):
    table = operator_table(part_stream.buffer, doc)
    interp = LazyInterpreter(page, [part_stream], filter_classes=[TextObject])
    for k, text_obj in enumerate(interp):
        kw_off, kw, operands = table[k]
        # Free, always-on drift tripwire. Costs one integer compare.
        assert interp._curpos == kw_off, (
            f"playa iteration desync at op {k}: _curpos={interp._curpos} != {kw_off}. "
            f"playa-pdf version changed iteration semantics — do not proceed."
        )
        yield kw_off, interp.parser.streamid, operands, text_obj
```

## Pattern 2: `/Contents` parts are addressed, never concatenated

```python
# Source: verified — playa/parser.py ContentParser docstring; pikepdf Page.contents_coalesce
# CORRECT — playa keeps parts separate; each part has its own byte-offset space
for part_index, stream in enumerate(page.streams):
    yield from walk_part(page, stream, doc)

# CORRECT if a single buffer is unavoidable (Phase 3): newline-joined, never bare
merged = b"\n".join(bytes(s.buffer) for s in page.streams)

# WRONG — measured to produce KWD(b'QBT') on govdocs1_002_002167.pdf
merged = b"".join(bytes(s.buffer) for s in page.streams)   # ← never
```

## Pattern 3: Distinct types for the two maps (TEXT-05)

```python
# Source: PITFALLS.md Pitfall 1 + PEP 484 NewType
from typing import NewType

CharCode  = NewType("CharCode",  int)   # a code as it appears in the content stream
GlyphId   = NewType("GlyphId",   int)   # a GID / CID in the font program
Unicode   = NewType("Unicode",   str)   # /ToUnicode output — DISPLAY AND SEARCH ONLY

CodeToGlyph   = dict[CharCode, GlyphId]   # the FORWARD map. Decides pixels.
CodeToUnicode = dict[CharCode, Unicode]   # /ToUnicode. Decides nothing.

def encode_for_output(text: str, fwd: CodeToGlyph) -> bytes: ...
def display_text(codes: list[CharCode], tou: CodeToUnicode) -> str: ...

# mypy rejects: encode_for_output("x", tou)          → arg-type
# mypy rejects: {v: k for k, v in tou.items()}       → dict[Unicode, CharCode], unusable as CodeToGlyph
```

The mypy setting that makes this bite: `strict = true` (or at minimum `disallow_any_generics`, `warn_return_any`, `no_implicit_reexport`) scoped to the engine package. `NewType` on `int` is enforced by mypy but **erased at runtime** — so the check exists only if mypy runs in CI. That is why the CI job is not optional.

## Anti-patterns to avoid

- **Consuming `playa.Page.extract_text()` / `extract_text_untagged()` for anything load-bearing.** It uses an absolute `0.5`-unit space heuristic with a `# heuristic!!!` comment in the source. Fine for the Phase 1 sanity probe; wrong for D-03.
- **Using `Page.flatten()` / `Page.glyphs` for indexing.** They discard `_curpos` and `streamid` for everything below the top level, so all Form XObject text loses its provenance.
- **Keying anything on `/BaseFont`.** Two different subsets share the name. Key on the resolved font object's identity, and on the embedded program's content hash when persistence is needed.
- **`page['/Resources']` without an inheritance walk.** Inheritable per §7.7.3.4, alongside `/MediaBox`, `/CropBox`, `/Rotate`.
- **Summing image bbox areas for coverage.** Measured to exceed 1.0 on real files. Union, then clip to CropBox.
- **A counted operator ordinal in the run ID.** Requires the counting rule to be identical in both walker modes; a byte offset has no rule to drift.
- **Wiring `tools/probe_corpus.py` to the interpreter.** Restated from Phase 1 D-04. The prober's whole value is independence.
- **A regex over decompressed content-stream bytes.** Named in PITFALLS as "the project's single worst shortcut."

---

# Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Content-stream tokenisation with byte offsets | A lexer | `playa.parser.ObjectParser` | Inline images (`BI…ID…EI`) contain arbitrary binary that legitimately includes `EI`; string escapes have balanced-paren rules; `#`-escaped names. Multiple CVEs live here. |
| `/Contents` array handling | `b"".join` or a custom joiner | `playa.parser.ContentParser` (per-part) or `pikepdf.Page.contents_coalesce()` | Measured 78 fusion-risk boundaries in this corpus. |
| Graphics + text state machine | A `Tf/Tm/Td/TD/T*/TL/Tc/Tw/Tz/Ts/Tr` tracker | `playa.interp.LazyInterpreter` | The `q`/`Q` stack interaction with text state, the `'`/`"` compound operators, and XObject gstate inheritance are each independently easy to get subtly wrong. |
| Encoding decode (name→glyph, code→CID→GID) | Encoding tables | `playa.font` + `playa.encodingdb` + `playa.cmap` | Ships the Standard-14 AFM metrics, the AGL, and ~160 predefined CMaps. Rebuilding is weeks. |
| Type3 `/FontMatrix` width scaling | `w/1000` | `playa` `GlyphObject.displacement` | Verified correct on both the 0.001 and 1.0 `/FontMatrix` cases present in this corpus. |
| `/CIDToGIDMap` stream decoding | An `/Identity` equality check | `playa.font` | The binary-stream case exists and produces garbage when skipped. |
| Font program parsing / glyph presence | Reading `glyf`/`CFF` | `fontTools` (already pinned) | The load-bearing dependency; nothing in any language is close. |
| Object layer, xref repair, filter chains | Anything | `pikepdf` | "Do not hand-serialize PDF structure." |
| Image rectangle union | A polygon library | 20 lines over an 80×80 occupancy grid | A new GEOS dependency for a coarse coverage fraction is not worth it. |

**Key insight:** everything in this table is *read-side plumbing that already exists and has been validated on this exact corpus*. The code Phase 2 actually writes is the clustering, the threshold, the decision-table dispatch, the classification, and the addressing — roughly 800–1,200 lines. Any plan whose task list contains "implement the text state machine" or "write the encoding tables" has mis-scoped the phase by an order of magnitude.

---

# Common Pitfalls

### Pitfall 1: Using `gstate.fontsize` as the em size

**What goes wrong:** every gap threshold, baseline tolerance and size-change break is scaled wrongly, usually by a large integer factor. Tuning converges on a number that is meaningless.
**Why:** producers routinely emit `/F1 1 Tf` and put the real size in `Tm`. `[VERIFIED: `irs_form_w9.pdf` page 0 — `gstate.fontsize == 1.0`, `line_matrix == (7.0, 0, 0, 7.0, 36.0, 738.832)`]`
**Avoid:** derive the effective em from the full text rendering matrix: `Tfs × |Tm scale| × (Tz/100) × |CTM scale|`. `TextObject.scaling_matrix` and `TextObject.text_matrix` exist for this.
**Warning sign:** a tuned threshold that works on one producer and not another; measured font sizes clustering at exactly 1.0.

### Pitfall 2: Refusing all Symbolic + `/Encoding` fonts

**What goes wrong:** 23% of the corpus becomes uneditable for no reason, and the refusal-rate finding D-04 asks for reports a number that reflects a bug rather than the spec.
**Why:** §9.6.6.4's "ignore `/Encoding`" language is TrueType-specific; §9.6.6.2 gives Type1 a clear rule.
**Avoid:** branch on `/Subtype` **before** branching on `Symbolic`.
**Warning sign:** the measured refusal rate lands near 23%.

### Pitfall 3: Sorting a baseline band by stream order

**What goes wrong:** two-column pages produce interleaved gibberish, and the gap threshold sees enormous negative gaps that it interprets as run breaks in the wrong places. This is Gate G1 criterion 2's named failure.
**Why:** producers emit by font/colour/layer, so two columns at the same baseline arrive non-adjacently.
**Avoid:** sort each band by projected position before computing gaps.
**Warning sign:** run text alternating between two columns; gaps in the sweep distribution with large negative values.

### Pitfall 4: Losing provenance below the top level

**What goes wrong:** all Form XObject and annotation text gets an address that points into the page's content stream rather than the XObject's. Rewriting it in Phase 3 corrupts the page.
**Why:** `Page.flatten()` recurses for you and yields objects, but the inner `LazyInterpreter` — and therefore `_curpos` and `streamid` — is not reachable.
**Avoid:** own the recursion; construct the inner `LazyInterpreter` yourself.
**Warning sign:** two runs from different streams sharing an ID; the `_curpos` assertion never firing on a document known to have XObject text.

### Pitfall 5: Summing image bounding boxes for coverage

**What goes wrong:** coverage exceeds 1.0 (measured 2.749), so a `coverage >= 0.5` rule fires on pages with two small overlapping images and the classifier is silently wrong in the permissive direction.
**Avoid:** union, clipped to the CropBox.
**Warning sign:** any coverage value above 1.0 in a debug dump. Make that an assertion.

### Pitfall 6: A green classification check on a mislabelled fixture

**What goes wrong:** exactly Phase 1's failure, three times over. `nasa_graphics_standards_manual.pdf` is labelled `vector_outlined_text` and is an OCR'd scan; a CLAS-03 check asserting "this document classifies as vector-outlined" would either fail correctly (good) or be written to match the observed behaviour (catastrophic — it would encode "OCR scan == vector outlined" as the spec).
**Avoid:** fix the manifest first, then write the check. Never write a classification assertion by observing what the current code does.
**Warning sign:** a check whose expected value was derived from a run rather than from the document's actual content.

### Pitfall 7: Treating `_curpos` as public API without a tripwire

**What goes wrong:** a `playa` patch release changes iteration order or when `_curpos` is set; the two-pass zip silently misaligns; every run ID in the system points at the wrong operator. It would look like data corruption, not a version bump.
**Avoid:** the assertion in Pattern 1, always on (not behind a debug flag), plus the exact version pin already in `pyproject.toml`.
**Warning sign:** none — that is the point. The assertion *is* the warning sign.

### Pitfall 8: Building the full-document run map eagerly

**What goes wrong:** 21 s and 166 MB on a 126-page document; ~67 s and ~526 MB extrapolated to 400 pages.
**Avoid:** D-06's page-at-a-time with columnar storage, cache capped by glyph count not page count.
**Warning sign:** a test that indexes a whole corpus document and takes longer than a second.

---

# Code Examples

### Deriving the effective em size

```python
# Source: PDF 32000-1 §9.4.4 displacement; playa TextObject.scaling_matrix / text_matrix
import math

def effective_em(text_obj) -> float:
    """Em height in device space. NOT gstate.fontsize — see Pitfall 1."""
    a, b, c, d, _, _ = text_obj.matrix      # TRM = params x Tm x CTM, playa composes it
    # length of the transformed unit-y vector = device-space height of 1 text-space unit
    return math.hypot(c, d) * text_obj.gstate.fontsize if text_obj.gstate.fontsize else math.hypot(c, d)
```
`[ASSUMED]` — the exact composition playa applies to `TextObject.matrix` was not verified field-by-field against §9.4.4. Confirm empirically during implementation by checking that a known 12 pt run reports ~12.0.

### Detecting shared Form XObjects

```python
# Source: verified against corpus — irs_1040_instructions.pdf has an XObject on 43 of 126 pages
import collections, pikepdf

def shared_form_xobjects(pdf: pikepdf.Pdf) -> dict[int, int]:
    """objid -> number of pages referencing it. >1 means editing it changes every one."""
    refs = collections.Counter()
    for page in pdf.pages:
        seen = set()
        for _, xo in ((page.get("/Resources") or {}).get("/XObject") or {}).items():
            if str(xo.get("/Subtype")) == "/Form":
                oid = xo.objgen[0]
                if oid and oid not in seen:
                    refs[oid] += 1
                    seen.add(oid)
    return {oid: n for oid, n in refs.items() if n > 1}
```

### Self-supervised space-threshold tuning (D-03)

```python
# Source: executed 2026-08-13 against corpus/public — see §4 for the resulting curve
def held_out_space_gaps(text_obj, em: float):
    """Yield (gap_in_em, is_word_boundary) by deleting real space glyphs from the geometry."""
    glyphs = list(text_obj)
    prev_end = None
    for i, g in enumerate(glyphs):
        x, adv = g.origin[0], g.displacement[0]
        if g.text == " ":                              # POSITIVE: known word boundary
            if prev_end is not None and i + 1 < len(glyphs):
                yield (glyphs[i + 1].origin[0] - prev_end) / em, True
        else:                                          # NEGATIVE: known intra-word gap
            if prev_end is not None and glyphs[i - 1].text != " ":
                yield (x - prev_end) / em, False
        prev_end = x + adv
```
Sweep the threshold over the collected pairs, maximise F1, pin the argmax, record the curve.

### Reproducing the `/Contents` fusion (the TEXT-07 FAIL-proof)

```python
# Source: executed — govdocs1_002_002167.pdf, page 0, 11 parts
from playa.parser import ObjectParser
parts  = [bytes(s.read_bytes()) for s in page.obj["/Contents"]]
naive  = [t for _, t in ObjectParser(b"".join(parts),  doc)]   # 890 tokens, [798] == KWD(b'QBT')
proper = [t for _, t in ObjectParser(b"\n".join(parts), doc)]  # 891 tokens, [798] == KWD(b'Q')
assert len(proper) == len(naive) + 1
```

---

# State of the Art

| Old approach | Current approach | When changed | Impact |
|---|---|---|---|
| `pdfminer.six` `LAParams` char-width-relative thresholds | pdf.js font-size-relative factors (`TRACKING_SPACE_FACTOR = 0.102`) | pdf.js text-layer rewrite, ~2021 onward | Font-size relative is content-independent and needs no font metrics. Our measurement independently lands at 0.10–0.15 em. |
| Single-estimator space threshold | PDFBox's `min(spaceWidth × 0.5, avgCharWidth × 0.3)` with an explicit degenerate fallback | PDFBox 2.x | Handles the very common subset font with no space glyph. |
| `pdf.js` "always prefer (3,1) for TrueType" | "(3,1) only when an `/Encoding` is specified" (PR #6425), then further conditioned | 2015 and continuing | The condition has been reversed more than once. It is not settled upstream, which is why refusal is correct. |
| ISO 32000-1: symbolic TrueType **must** have (3,0) or (1,0) | ISO 19005-2 §6.2.11.6 permits a sole non-standard cmap | PDF/A-2, 2011 | Two standards disagree; three validators behave differently (veraPDF#818). Refusal surface, not a resolvable branch. |
| `pikepdf` `Page.contents_coalesce()` as an opt-in | still opt-in, still mutating | — | Not a default. Anyone reaching for coalescing must know it rewrites `/Contents`. |

**Deprecated / outdated in the planning documents:**
- CLAUDE.md's stack table lists **qpdf 12.4.0** inside pikepdf 10.11.0. The wheel bundles **12.3.2**. `[VERIFIED: `pikepdf.__libqpdf_version__`]`
- `research/SUMMARY.md` §Gaps: "Simple-font encoding resolution when `Symbolic` and `/Encoding` are both present — the spec does not cleanly resolve it." **Over-broad** — true for TrueType, false for Type1. Corrected in §1.
- `corpus/manifest.json`'s `vector_outlined_text` label on `nasa_graphics_standards_manual.pdf`. **Wrong** — corrected in §7.

---

# Runtime State Inventory

Not applicable — Phase 2 is greenfield engine code with no rename, refactor or migration component. No stored data, live service config, OS-registered state, secrets, or build artifacts carry a string this phase changes.

One adjacent item that is *not* runtime state but is checked-in state requiring a change: **`corpus/manifest.json`'s category labels** (see §7). That is a data edit inside the repo, covered by a normal task.

---

# Environment Availability

`[VERIFIED: probed 2026-08-13 on the development machine]`

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| Python | everything | ✓ | 3.13 (venv) | — |
| `playa-pdf` | read side | ✓ | 1.1.0 (exact pin) | `pdfminer.six` — **not installed**, swap untested |
| `pikepdf` | object layer, identity rewrite | ✓ | 10.11.0 / qpdf 12.3.2 | — |
| `fontTools` | glyph-presence check (A-6) | ✓ | 4.63.0 | — |
| `pytest` | test runner | ✓ | 9.1.1 | — |
| **`mypy`** | **TEXT-05 enforcement** | ✗ | — | **none — TEXT-05 is unverifiable without it** |
| `qpdf` CLI | structural validation | ✓ | 12.4.0 | — |
| `pdftotext` (Poppler) | tertiary space-threshold reference | ✓ | present (rejects `--version`) | optional |
| `mutool` (MuPDF) | third harness engine, CI-only | ✓ | 1.28.2 | — |
| `pdfcpu` | structural validation | ✓ | present | — |
| `pypdfium2` | first harness engine | ✓ | 5.12.1 | — |
| `docker` | pinned CI image | assumed present in CI (`Dockerfile.ci`) | — | — |
| English word list | secondary D-03 lexicon metric on the no-space subset | ✗ | — | macOS `/usr/share/dict/words`; or vendor a small list; or drop the secondary metric |

**Missing dependencies with no fallback:**
- `mypy` — TEXT-05 cannot be verified without a type checker. Wave 0.

**Missing dependencies with fallback:**
- English word list — the lexicon metric is a *secondary* validation of the D-03 threshold on the 12% of documents with no space glyphs. If unavailable, report that population's threshold behaviour qualitatively and record the gap.

---

# Validation Architecture

## Test Framework

| Property | Value |
|---|---|
| Framework | `pytest` 9.1.1 (dev group) |
| Config file | **none** — no `pytest.ini`, no `[tool.pytest.ini_options]`, no `conftest.py`. Wave 0. |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -q && uv run mypy engine/ && uv run python tools/probe_corpus.py corpus/manifest.json corpus/public` |
| Existing tests | 37 collected, all green |
| **CI status** | ❌ **No workflow runs pytest.** `.github/workflows/{corpus,harness,license-gate}.yml` run `probe_corpus.py`, the harness, and `license_gate.py` — never the test suite. Wave 0. |

## Phase Requirements → Test Map

| Req | Behaviour | Type | Automated command | Exists? |
|---|---|---|---|---|
| TEXT-01 | Walker emits a run record per text run on every corpus document without exception | integration | `pytest tests/test_walker.py::test_walks_full_corpus_without_exception -x` | ❌ Wave 0 |
| TEXT-02 | Every glyph record has all 13 provenance fields populated (none `None`, none sentinel) | unit | `pytest tests/test_glyph_record.py::test_all_provenance_fields_populated -x` | ❌ Wave 0 |
| TEXT-02 | Two-pass zip stays aligned: `_curpos == passA_keyword_offset` on every operator | integration | `pytest tests/test_walker.py::test_curpos_alignment_holds_across_corpus -x` | ❌ Wave 0 |
| TEXT-03 | Run ID resolves against the original bytes: seek to `o`, find the operator keyword | unit | `pytest tests/test_run_id.py::test_id_offset_points_at_operator_keyword -x` | ❌ Wave 0 |
| TEXT-03 | Identity rewrite → re-index yields identical ordered run IDs (Gate G1 crit. 1) | integration | `pytest tests/test_roundtrip.py::test_identity_rewrite_preserves_run_ids -x` | ❌ Wave 0 |
| TEXT-04 | Every font in the corpus resolves to exactly one branch ID; no font hits the default | integration | `pytest tests/test_encoding_table.py::test_every_corpus_font_fires_exactly_one_branch -x` | ❌ Wave 0 |
| TEXT-04 | Type1 symbolic + `/Encoding` resolves (does NOT refuse); TrueType symbolic + `/Encoding` refuses | unit | `pytest tests/test_encoding_table.py::test_type1_symbolic_encoding_resolves_truetype_refuses -x` | ❌ Wave 0 |
| TEXT-05 | `Code→Glyph` and `Code→str` are not interchangeable | static | `uv run mypy engine/ --strict` + `pytest tests/test_types.py::test_mypy_rejects_inverted_tounicode -x` (runs mypy on a fixture snippet, asserts non-zero exit) | ❌ Wave 0 |
| TEXT-06 | Text found in Form XObjects, annotation `/AP /N`, tiling patterns, Type3 `/CharProcs` | integration | `pytest tests/test_outside_contents.py -x` | ❌ Wave 0 |
| TEXT-06 | Shared Form XObject runs are `editable=False` with reason naming the page count | unit | `pytest tests/test_outside_contents.py::test_shared_form_xobject_marked_not_editable -x` | ❌ Wave 0 |
| TEXT-07 | Per-part parse ≡ newline-joined parse, across all 114 `contents_array` docs | integration | `pytest tests/test_contents_parts.py::test_no_token_fusion_across_corpus -x` | ❌ Wave 0 |
| TEXT-08 | Glyph-at-a-time and two-column pages reconstruct into readable runs | integration | `pytest tests/test_clustering.py -x` | ❌ Wave 0 |
| CLAS-01 | Four buckets assigned; image coverage never exceeds 1.0 | unit | `pytest tests/test_classify.py::test_buckets_and_coverage_bounded -x` | ❌ Wave 0 |
| CLAS-02 | `invoice_book_1842.pdf` → 45 OCR pages, 7 no-text pages | integration | `pytest tests/test_classify.py::test_ocr_scan_fixture -x` | ❌ Wave 0 |
| CLAS-03 | Vector-outlined page → own bucket | integration | `pytest tests/test_classify.py::test_vector_outlined_fixture -x` | ❌ **Blocked — no fixture exists** |
| CLAS-04 | Every run carries one of three states before any edit; refusal reasons enumerable | unit | `pytest tests/test_classify.py::test_every_run_has_three_state_verdict -x` | ❌ Wave 0 |
| CLAS-05 | Mixed fixture: N−3 editable pages, N page-op-able | integration | `pytest tests/test_classify.py::test_mixed_document_refuses_operation_not_document -x` | ❌ Wave 0 (fixture must be constructed) |
| D-03 | Pinned threshold reproduces its recorded F1 within tolerance | integration | `pytest tests/test_space_threshold.py::test_pinned_threshold_reproduces_measured_f1 -x` | ❌ Wave 0 |
| D-04 | Measured refusal rate is recorded and does not regress | integration | `pytest tests/test_encoding_table.py::test_refusal_rate_within_recorded_bound -x` | ❌ Wave 0 |
| D-06 | First page indexed in < 100 ms on a 100+ page document | integration | `pytest tests/test_perf.py::test_first_page_latency -x` | ❌ Wave 0 |

## Sampling rate

- **Per task commit:** `uv run pytest tests/ -x -q` (37 existing + new; currently 0.14 s to collect, sub-second to run)
- **Per wave merge:** full suite — `pytest` + `mypy engine/ --strict` + `probe_corpus.py` + `license_gate.py`
- **Phase gate:** full suite green, plus one full harness pass (`harness/run_corpus_harness.py`) on the identity-rewrite outputs, before `/gsd:verify-work`

## Every check, and the deliberate mutation that turns it red

This is not boilerplate. Phase 1 shipped three green checks that measured the wrong thing. Each Phase 2 check below names the mutation that must be *demonstrated* going red before the check is trusted.

| Check | Deliberate mutation that must produce RED |
|---|---|
| **TEXT-07 fusion check** | Change the joiner in the test's reference from `b"\n".join` to `b"".join`. `govdocs1_002_002167.pdf` produces `KWD(b'QBT')` and the token counts differ by 1. **This mutation is already verified to work** (§6). If the check stays green with `b"".join`, it is measuring nothing. |
| **`_curpos` alignment assertion** | Advance the `LazyInterpreter` one extra step before zipping (`next(interp)` once before the loop). Every offset shifts by one operator and the assert fires on operator 0. |
| **TEXT-04 branch coverage** | Delete the TT-c branch from the dispatch table. `mutopia_vocalise_abt.pdf`, `govdocs1_010_010123.pdf`, `govdocs1_011_011078.pdf`, `govdocs1_011_011080.pdf` fall through to the default and the "exactly one branch" assertion fires. ⚠️ **Phase 1's decision-coverage gate passed 0/0 on a file with four decisions** — so this check must additionally assert `branches_fired_count > 0` and `distinct_branches_fired >= 8`, or it will pass vacuously on an empty font set. |
| **TEXT-04 Type1-vs-TrueType** | Change the branch condition from `subtype == "/TrueType" and symbolic and has_encoding` to `symbolic and has_encoding`. The refusal rate jumps from 4 docs to 54 and the recorded-bound assertion fires. |
| **TEXT-05 type separation** | Add `unicode_to_code = {v: k for k, v in tou.items()}` and pass it to `encode_for_output`. `mypy --strict` must exit non-zero. If mypy is not in CI, this check does not exist — that is the Wave 0 gap. |
| **TEXT-02 provenance completeness** | Set `byte_offset_within_string = None` for `TJ` operands (the field most likely to be quietly skipped). The "none `None`" assertion fires. Must assert on **field values**, not on the presence of dataclass attributes — `slots=True` guarantees the attribute exists regardless. |
| **TEXT-03 ID resolves** | Add 1 to the encoded byte offset. Seeking to `o` no longer finds the operator keyword. |
| **TEXT-03 round-trip** | Change the run ID from a byte offset to a counted ordinal, then delete one non-text operator from the stream before re-indexing. Ordinals shift; byte offsets do not. |
| **TEXT-06 shared XObject** | Change `shared` detection from `objgen[0]` to the resource *name*. `irs_1040_instructions.pdf` — where the same object appears under different names on different pages — mis-detects, and the "43 pages" assertion fires. ⚠️ **Phase 1's producer cap keyed on a string that split one product into two buckets.** Same failure shape; this is the check that catches it. |
| **CLAS-01 coverage bound** | Revert the union to a sum of bbox areas. `nasa_graphics_standards_manual.pdf` reports 2.749 and the `coverage <= 1.0` assertion fires. **Verified to reproduce** (§7). |
| **CLAS-02 OCR fixture** | Change the visible test from `render_mode not in (3, 7)` to `render_mode != 3`. Does **not** go red on this corpus (no Tr=7 observed) — **so this check cannot detect a Tr=7 bug and must not claim to.** Add a synthetic single-page fixture with one Tr=7 glyph to `tests/fixtures/` and assert on it, or state the limitation explicitly. |
| **CLAS-03 vector-outlined** | ⚠️ **No mutation can make this check meaningful until a fixture exists.** Currently it would either fail (correct, blocked) or be written against `nasa_graphics_standards_manual.pdf`, which is an OCR scan — encoding the mislabel into the test suite. **This is the exact Phase 1 failure mode ("a corpus label asserting a font class the document did not contain") and it must be resolved in Wave 0, not worked around.** |
| **CLAS-05 mixed document** | Change the classifier from per-page to per-document (`any(page is scanned) → document uneditable`). The "N−3 editable" assertion fires. |
| **D-03 threshold** | Change `effective_em` to return `gstate.fontsize`. On `irs_form_w9.pdf` the em becomes 1.0 instead of 7.0 and F1 collapses below the recorded bound. **This mutation matters most** — it is the silent one. |
| **D-04 refusal rate** | See the Type1-vs-TrueType mutation above. The bound must be a *two-sided* range (e.g. `1% ≤ rate ≤ 5%`), not an upper bound — an upper bound stays green if the table stops refusing anything at all. |
| **D-06 first-page latency** | Replace lazy per-page indexing with an eager full-document index. `irs_1040_instructions.pdf` takes 21 s instead of ~15 ms. |
| **Corpus manifest integrity** | Already covered by `tools/probe_corpus.py`'s zero-count-category check — and after the `vector_outlined_text` relabel it will **legitimately go red** until a real fixture is added. Do not silence it. |

## Wave 0 gaps

- [ ] `.github/workflows/tests.yml` — **no CI workflow runs pytest.** 37 tests exist and nothing executes them. Everything above is theatre until this lands.
- [ ] `pyproject.toml` `[tool.pytest.ini_options]` — testpaths, and a `corpus` marker so corpus-wide integration tests can be excluded from the quick run.
- [ ] `tests/conftest.py` — shared fixtures: corpus manifest loader, per-category document selector, a `doc()` helper that opens from `corpus/public`.
- [ ] `uv add --dev mypy==2.3.0` + `[tool.mypy] strict = true` scoped to the engine package + a CI step. **TEXT-05 is unverifiable without this.**
- [ ] **Corpus fix:** relabel `nasa_graphics_standards_manual.pdf` `vector_outlined_text` → `ocr_scan` in `corpus/manifest.json`.
- [ ] **Corpus gap:** obtain a genuine vector-outlined-text document. **Blocks CLAS-03 and Gate G1 criterion 3.**
- [ ] `tests/fixtures/mixed_scanned.pdf` — constructed via pikepdf, N editable pages + 3 pages lifted from `invoice_book_1842.pdf`. Blocks CLAS-05.
- [ ] `tests/fixtures/render_mode_7.pdf` — one-page synthetic with a `Tr 7` glyph. Without it, the visible-glyph rule's `7` case is untested (no corpus document exercises it).
- [ ] Optional: an English word list for the D-03 secondary lexicon metric on the no-space-glyph subset.

---

# Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json`, so this section is required. Phase 2 is CLI-only over locally-trusted corpus files — the untrusted-input boundary is Phase 4 — but three controls belong here because retrofitting them costs more than adding them now.

### Applicable ASVS categories

| ASVS category | Applies | Standard control |
|---|---|---|
| V2 Authentication | no | No accounts, no web tier in this phase |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | CLI, local files |
| V5 Input Validation | **yes** | Recursion depth cap + visited set on every graph traversal (XObject `Do`, annotation `/AP`, pattern, Type3 `/CharProcs`, `/Pages /Kids`). Wall-clock cap per document. Bounds-checked `/Widths` indexing. |
| V6 Cryptography | no | Nothing cryptographic. Source hashing for run IDs is integrity-of-address, not a security control — use SHA-256 anyway rather than a fast non-crypto hash, since Phase 4's content-addressed cache will key on it. |
| V7 Error Handling & Logging | **yes** | **PRIV-04 starts here.** No decoded text, no `content_stream_bytes`, no filenames in log or exception messages — only run IDs, byte offsets, branch IDs and counts. A `logger.debug(f"...{run.text}...")` written in Phase 2 becomes a privacy leak in Phase 4. |
| V12 Files & Resources | **yes** | Only reads from an explicit corpus path. No writes outside the identity-rewrite output path. No network. |
| V14 Configuration | **yes** | `tools/license_gate.py` on the resolved lockfile after adding mypy. |

### Known threat patterns for this stack

| Pattern | STRIDE | Standard mitigation |
|---|---|---|
| Self-referencing Form XObject → unbounded recursion (CVE-2026-48155 shape) | DoS | Visited set **per branch** + explicit depth cap. playa's `flatten()` has the visited set but **no depth cap**; since we own the recursion (§5), we own both. |
| Cyclic page tree | DoS | pikepdf/qpdf handles page-tree traversal; do not write a manual `/Kids` walk. |
| Unterminated inline image (`BI…ID` with no `EI`) → CPU exhaustion (CVE-2026-59935/6 shape) | DoS | `playa.parser` handles inline images inside the parser (§8.9.7). Do not write a tokenizer. Add a per-document wall-clock cap regardless. |
| Predictor / decompression bomb | DoS | Per-document wall-clock cap and a glyph-count cap on the index. A 400-page document produces ~1.9 M glyphs; anything above ~10 M is pathological — abort with a named reason. |
| Decoded document text in logs or exception messages | Information disclosure | Log run IDs and counts only. Enforce with a grep-based test over the engine package for f-strings containing `.text`, `chars`, `buffer` — cheap, and it is exactly the sort of check that only exists if written before the code. |
| `/ToUnicode` inversion producing output bytes | Tampering (wrong glyphs shipped) | Distinct types + mypy (TEXT-05). This is a *correctness* control that happens to be enforced by a type system. |

---

# Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | Poppler prefers `(3,0)` for symbolic TrueType and falls back through `(1,0)`/`(3,1)` | §2 | Low — Poppler's exact rule does not change the refusal decision (three implementations already disagree, which is sufficient). Verify if a refusal is ever contested. |
| A2 | Superscript detection should check `gstate.rise` before geometry | §3 | Medium — if producers commonly move `Tm` instead of setting `Ts`, the `Ts`-first rule silently never fires and geometry carries the whole load. Measurable during implementation. |
| A3 | Path-count threshold `P ≈ 200` distinguishes vector-outlined text from decorative vector art | §7 | High — unvalidated because **no fixture exists**. Must be re-derived once one does. Do not pin `P` before then. |
| A4 | Columnar arrays reduce GC pressure relative to a per-glyph object graph | §10 | Low — the 3× memory win is measured; the GC claim is inference. |
| A5 | `TextObject.matrix` composes `Tfs × Tm × CTM` such that `hypot(c,d) × fontsize` gives the device em | §Code Examples | Medium — a wrong composition makes every threshold wrong by a constant factor. Trivially checkable against a known 12 pt run; do it in the first tuning task. |
| A6 | RTL runs should be refused in v1 | §3 | Low — no corpus fixture exists, so the alternative (attempt and get it wrong) is untestable either way. Recording the refusal is strictly safer. |
| A7 | White-on-white text detection is out of scope for the visibility signal | §7 | Low for v1; it is a deliberate, recorded gap rather than an oversight. |
| A8 | 8 distinct encoding branches is a reasonable floor for the "branch coverage is non-vacuous" assertion | §Validation | Low — the corpus measurement shows at least 10 distinct `(subtype, symbolic, encoding-kind, embedded)` combinations with ≥25 occurrences each, so 8 is conservative. |

---

# Open Questions (ALL RESOLVED)

> Resolved 2026-08-13 during planning. Each question below is closed by a named plan task or a
> CONTEXT.md decision; the original reasoning is preserved for the record.
>
> | # | Question | Resolved by |
> |---|---|---|
> | 1 | TT-d / TT-e refusal counts | **02-02 Task 3** — `tools/measure_truetype_cmap_gaps.py` enumerates each embedded TrueType's cmap subtables and sizes D-04's bound |
> | 2 | Should colour break a run | **02-CONTEXT.md D-01**, extended 2026-08-13 — fill colour breaks; stroke mode and text render mode explicitly rejected |
> | 3 | Vector-outlined fixture source | **02-02 Task 1** — targeted govdocs1 search, then construct-and-disclose if that fails |
> | 4 | Run IDs on malformed documents | **02-10 Task 2** — identity-rewrite round trip over the 17 `malformed` documents |
> | 5 | Cache eviction budget | **02-09 Task 1** — RunIndex cache sizing against the measured 166MB/126-page profile |


1. **How many corpus fonts hit TT-d (symbolic TrueType with an unusable cmap set) and TT-e (no cmap)?**
   - Known: these branches exist and both are refusals. `TrueType symbolic, no /Encoding` covers 37 documents, but how many of those have a *usable* `(3,0)` or `(1,0)` is unmeasured.
   - Unclear: whether the total refusal rate is nearer 2% or nearer 10%.
   - Recommendation: measure it as the first task of the encoding-table work, by loading each embedded TrueType program with `fontTools` and enumerating its cmap subtables. It is a ~30-line probe and it sizes D-04's headline number, which CONTEXT.md explicitly asks for.

2. **Should a colour change break a run (D-01)?**
   - Known: D-01 names font, size, baseline and gap. It does not name colour.
   - Unclear: whether the user perceives a colour change mid-line as a boundary. A hyperlink in blue inside a black sentence is the common case.
   - Recommendation: break on colour, and record it as a Phase 2 implementation decision extending D-01 rather than contradicting it. Breaking is the conservative direction — it produces more, smaller addressable units, which D-02 has already accepted as a cost.

3. **Where does the vector-outlined-text fixture come from?**
   - Known: none exists in 216 documents; the labelled one is an OCR scan.
   - Unclear: whether one is findable in `govdocs1` (design exports are rare in a government-web-server scrape) or must be constructed.
   - Recommendation: try a targeted `govdocs1` search first (files whose page has zero fonts in `/Resources` and >200 path operators); if that fails, construct one and disclose it in `corpus/sources.md`'s substitutions section, as veraPDF fixtures already are.

4. **Does the identity rewrite (§9) actually round-trip on the 17 `malformed` documents?**
   - Known: qpdf repairs on open, so the output is structurally different by design; byte comparison is invalid.
   - Unclear: whether the *run IDs* survive — a repaired xref may renumber objects, which changes `streamid`.
   - Recommendation: this is why the run ID uses the **part index**, not the stream objid. Confirm empirically on the 17 malformed documents as an explicit task; if part indices also shift, the ID scheme needs a third option and it is much cheaper to discover now.

5. **What is the right cache eviction budget for D-06?**
   - Known: ~178 MB for a 400-page IRS-density document with columnar storage; density varies 26× across the corpus.
   - Unclear: the concurrency model, which is Phase 4's.
   - Recommendation: cap by glyph count with a conservative default, make it a single named constant, and record the measured bytes-per-glyph next to it so Phase 4 can size it against a real worker budget.

---

# Sources

### Primary (HIGH confidence)

- **Direct measurement of `corpus/public` (216 documents), executed 2026-08-13** — encoding branch distribution, `/Contents` boundary analysis, `QBT` fusion reproduction, classification signals, shared-XObject reference counts, render-mode distribution, real-space-glyph frequency, space-threshold ROC, parse timings, memory profiles. Every number tagged `[VERIFIED: measured]` in this document comes from here.
- **`playa-pdf` 1.1.0 source** (`.venv/.../playa/{parser,interp,content,page,font}.py`) — `ContentParser` per-part semantics, `LazyInterpreter._curpos`/`parser.streamid`, `GlyphObject`/`TextObject`/`GraphicState` fields, `flatten()` visited set, `extract_text_untagged`'s 0.5 heuristic, vertical-writing support.
- **`pikepdf` 10.11.0** — `Page.contents_coalesce()` newline insertion (measured: 7 bytes for 7 boundaries), `parse_content_stream`/`unparse_content_stream`, `__libqpdf_version__ == 12.3.2`.
- [ISO 32000-1:2008 §9.6.6 / PDF errata clause 09](https://pdf-issues.pdfa.org/32000-2-2020/clause09.html) — encoding chain, `/Differences` array form, `/MissingWidth` default 0, `/DW` default 1000, `Tw` single-byte-32 restriction.
- [mozilla/pdf.js `src/core/fonts.js`](https://github.com/mozilla/pdf.js/blob/master/src/core/fonts.js) — `readCmapTable` preference order and the `hasEncoding` condition.
- [mozilla/pdf.js `src/core/evaluator.js`](https://github.com/mozilla/pdf.js/blob/master/src/core/evaluator.js) — `TRACKING_SPACE_FACTOR 0.102`, `NOT_A_SPACE_FACTOR 0.03`, `NEGATIVE_SPACE_FACTOR −0.2`, `SPACE_IN_FLOW_MIN/MAX 0.102/0.6`.
- [mozilla/pdf.js PR #6425](https://github.com/mozilla/pdf.js/pull/6425) — "(3,1) cmap only for TrueType fonts that have an encoding specified".
- [Apache PDFBox `PDTrueTypeFont`](https://github.com/apache/pdfbox/blob/trunk/pdfbox/src/main/java/org/apache/pdfbox/pdmodel/font/PDTrueTypeFont.java) — `codeToGID` symbolic/non-symbolic branches, `0xF000/0xF100/0xF200` bias.
- [Apache PDFBox `PDFTextStripper`](https://github.com/apache/pdfbox/blob/trunk/pdfbox/src/main/java/org/apache/pdfbox/text/PDFTextStripper.java) — `spacingTolerance 0.5`, `averageCharTolerance 0.3`, the `min()` rule and the `Float.MAX_VALUE` degenerate fallback, `maxYForLine` overlap grouping.
- [PDFium `cpdf_truetypefont.cpp`](https://github.com/chromium/pdfium/blob/main/core/fpdfapi/font/cpdf_truetypefont.cpp) — `LoadGlyphMap` stages, `kPrefix = {0x00, 0xF0, 0xF1, 0xF2}`, identity fallback.
- [pdfminer.six `layout.py`](https://github.com/pdfminer/pdfminer.six/blob/master/pdfminer/layout.py) — `LAParams` defaults and docstring semantics.
- [qpdf issue #444](https://github.com/qpdf/qpdf/issues/444) — concatenated content streams producing merged tokens.
- Repository artifacts: `.planning/research/{SUMMARY,ARCHITECTURE,PITFALLS}.md`, `PLAYA-DECISION.md`, `corpus/sources.md`, `tools/probe_corpus.py`, `harness/run_corpus_harness.py`, `.github/workflows/*.yml`, `pyproject.toml`.

### Secondary (MEDIUM confidence)

- [veraPDF-library issue #818](https://github.com/veraPDF/veraPDF-library/issues/818) — symbolic TrueType with a sole `(3,1)` cmap; ISO 32000-1 vs ISO 19005-2 §6.2.11.6; veraPDF / Callas / 3-Heights disagreement.
- [mozilla/pdf.js issue #14117](https://github.com/mozilla/pdf.js/issues/14117) — `/Encoding` blocking rendering in pdf.js but not in Ghostscript, Chrome or Acrobat. Used as the evidence for Acrobat's behaviour, which is not directly observable.
- [mozilla/pdf.js issue #12237](https://github.com/mozilla/pdf.js/issues/12237) — `/ActualText` not honoured.
- `slopcheck install mypy` / `slopcheck install pytest`, executed 2026-08-13 — both clean.

### Tertiary (LOW confidence — flagged inline)

- Poppler's symbolic-TrueType cmap preference (A1) — not read this session.
- `TextObject.matrix` composition semantics (A5) — inferred from field names and one spot check, not traced through the source.
- `P ≈ 200` path-count threshold (A3) — no fixture to validate against.

---

# Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|---|---|---|
| Encoding decision table structure | **HIGH** | Spec clause + three implementations read at source level + branch distribution measured across 24,039 corpus font occurrences |
| The Type1-vs-TrueType ambiguity correction | **HIGH** | Spec-grounded and measured: 4 docs vs 50 docs, reproducible by re-running the probe |
| `/Contents` fusion | **HIGH** | Reproduced with a named file, a named token index, and an exact token-count delta |
| Interpreter shape (two-pass zip) | **HIGH** | Executed against real corpus files; byte offsets confirmed to land on operator keywords |
| Space-threshold method | **HIGH** | Prototype executed, produced a proper ROC, and converges independently on pdf.js's constant |
| Space-threshold *number* | **MEDIUM** | The em normaliser used in the prototype is an approximation; the optimum will move |
| Corpus fixture defects (NASA mislabel, missing vector-outlined) | **HIGH** | Producer/Creator metadata read directly; zero-candidate scan across all 216 documents |
| Classification thresholds | **MEDIUM** | Signals verified and formulation bug found; the specific cut points are proposals, and `P` has no fixture |
| Performance and memory | **HIGH** | Measured on this machine; extrapolations are linear and labelled as such |
| Cross-viewer behaviour | **MEDIUM** | Source-read for pdf.js, PDFBox, PDFium; inferred for Acrobat; not read for Poppler |
| Run clustering algorithm | **MEDIUM** | Assembled from three implementations' verified behaviour plus reasoning. Only the gap rule has been prototyped; the banding, sorting and break rules have not. |

**Research date:** 2026-08-13
**Valid until:** ~2026-09-13 (30 days). The measured corpus facts do not expire — they are properties of checked-in bytes and are re-derivable by re-running the probes. The viewer-behaviour findings and the `mypy` version are the parts with a shelf life.
