# Architecture Research

**Domain:** Browser-based PDF editor with content-stream text editing, hybrid client/server processing, ephemeral no-retention server
**Researched:** 2026-08-11
**Confidence:** MEDIUM-HIGH (library capabilities verified against official docs; the composite architecture is a synthesis — no reference implementation of this exact shape was found in public sources)

---

## The One-Paragraph Answer

There is no such thing as "the text in the PDF." There is a **content stream** (byte-level operators the server can rewrite) and a **rendered text layer** (what pdf.js reconstructs for display). These are two derived views that share no identifier. Everything else in this architecture follows from refusing to let them drift: **the server owns a single content-stream interpreter that produces the text index and performs the rewrite, from the same code path.** The browser never invents an address — it only echoes back IDs the server issued. The document state is a small declarative **recipe** (a page list plus a sparse map of run-ID → replacement) held in browser memory; the server holds nothing it cannot afford to lose. Every edit is applied to the *immutable original bytes*, never to a previously edited output.

---

## Standard Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             BROWSER                                         │
│                                                                             │
│  ┌──────────────┐   ┌───────────────────┐   ┌───────────────────────────┐  │
│  │  Viewer      │   │  Edit Surface     │   │  Recipe Store             │  │
│  │  (pdf.js     │◄──┤  (hit boxes from  │◄──┤  {sources, pages[],       │  │
│  │   canvas)    │   │   server run map) │   │   overrides{}, undo[]}    │  │
│  └──────┬───────┘   └─────────┬─────────┘   └────────┬──────────────────┘  │
│         │                     │                       │                     │
│         │  ┌──────────────────▼───────────┐  ┌───────▼──────────────────┐  │
│         │  │  Optimistic Preview Overlay  │  │  Page Ops (pdf-lib)      │  │
│         │  │  (DOM text, NEVER exported)  │  │  insert/reorder/rotate/  │  │
│         │  └──────────────────────────────┘  │  merge — preview + pure- │  │
│         │                                     │  page-op download        │  │
│  ┌──────▼────────────────────────────────┐   └──────────┬───────────────┘  │
│  │  Source Bytes (ArrayBuffer, authoritative)│           │                  │
│  └──────┬────────────────────────────────┘              │                  │
└─────────┼────────────────────────────────────────────────┼──────────────────┘
          │  HTTPS  (bytes on cache-miss only) │ recipe JSON (always)
┌─────────▼────────────────────────────────────▼──────────────────────────────┐
│                          API / TRANSPORT LAYER                              │
│  ┌────────────────┐  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │ Ingest         │  │ Ephemeral Blob      │  │ Job Queue                │  │
│  │ (sniff, size   │  │ Cache               │  │ (async exports only)     │  │
│  │  cap, hash)    │  │ content-addressed,  │  │ 202 + job id + SSE       │  │
│  │                │  │ RAM/tmpfs, TTL,     │  │                          │  │
│  │                │  │ evictable ANY TIME  │  │                          │  │
│  └───────┬────────┘  └──────────┬──────────┘  └────────────┬─────────────┘  │
└──────────┼──────────────────────┼──────────────────────────┼────────────────┘
           │                      │                          │
┌──────────▼──────────────────────▼──────────────────────────▼────────────────┐
│                    ENGINE WORKERS (sandboxed, no network, hard timeouts)    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  ★ CONTENT-STREAM INTERPRETER  (the load-bearing component)           │  │
│  │    one walker · two outputs                                           │  │
│  │    ┌──────────────────────┐        ┌────────────────────────────────┐ │  │
│  │    │ OUT A: Run Index     │        │ OUT B: Rewritten Stream        │ │  │
│  │    │ id, unicode, bbox,   │        │ substituted glyphs +           │ │  │
│  │    │ font, size, fingerpr.│        │ width-fitted spacing           │ │  │
│  │    └──────────────────────┘        └────────────────────────────────┘ │  │
│  └────────────┬──────────────────────────────────────┬───────────────────┘  │
│               │                                      │                       │
│  ┌────────────▼───────────┐  ┌─────────────────┐  ┌─▼────────────────────┐  │
│  │ Font Service           │  │ Width Fitter    │  │ Document Assembler   │  │
│  │ • decode enc→Unicode   │  │ Tz / TJ deltas  │  │ page list → output   │  │
│  │ • glyph coverage query │  │ / Tc            │  │ pikepdf/qpdf write   │  │
│  │ • subset + embed       │  └─────────────────┘  └──────────────────────┘  │
│  │   (bundled OFL fonts)  │                                                 │
│  └────────────────────────┘                                                 │
│                                                                             │
│  ┌────────────────────────┐  ┌──────────────────────────────────────────┐   │
│  │ Rasterizer             │  │ Conversion Sidecars  (LICENSE BOUNDARY)  │   │
│  │ page → PNG/JPEG        │  │ ┌──────────┐ ┌──────────┐ ┌───────────┐  │   │
│  │ (preview + export)     │  │ │unoserver │ │Ghostscript│ │ veraPDF  │  │   │
│  └────────────────────────┘  │ │  DOCX    │ │  PDF/A   │ │ validate │  │   │
│                              │ └──────────┘ └──────────┘ └───────────┘  │   │
│                              │  separate processes / separate service   │   │
│                              └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Owns | Must NOT do | Typical implementation |
|-----------|------|-------------|------------------------|
| **Viewer** | Rasterizing pages for display; zoom/scroll | Own any edit address | pdf.js `getDocument` → `page.render()` to canvas |
| **Edit Surface** | Hit-testing clicks against server-issued run boxes; caret/selection UI | Use pdf.js `getTextContent()` for targeting | Absolutely-positioned divs from run bboxes via `viewport.convertToViewportRectangle` |
| **Preview Overlay** | Showing typed text instantly, before the server confirms | Ever be part of a downloaded file | Contenteditable div clipped to the run bbox |
| **Recipe Store** | The whole document state: source list, page list, override map, undo stack | Contain PDF bytes (except as opaque handles) | Plain JS object + structuredClone snapshots |
| **Page Ops (client)** | Materializing the page list for preview; producing the download when the recipe has *zero* overrides | Produce the download when any override exists | pdf-lib `copyPages`/`insertPage`/`setRotation` |
| **Ingest** | Magic-byte sniff, size cap, SHA-256 content hash, encryption check | Persist anything | Streaming upload → hash → RAM buffer |
| **Ephemeral Blob Cache** | Holding source bytes keyed by content hash, with TTL; being safely losable | Be the system of record | Redis `SET ... EX 900` with `maxmemory-policy allkeys-lru`, or in-process LRU |
| **★ Content-Stream Interpreter** | Walking text state machine; emitting run index; emitting rewritten stream | Have two implementations (one for read, one for write) | Custom walker over `pikepdf.parse_content_stream` |
| **Font Service** | Encoding→Unicode decode, glyph coverage queries, subsetting, embedding | Run on every keystroke | fontTools (`subset`, `ttLib`) + font dict construction |
| **Width Fitter** | Making replacement text occupy the original run's advance | Change line breaks or reflow | Tz / TJ kern deltas / Tc, in that preference order |
| **Document Assembler** | Turning a recipe into output bytes; page insert/delete/reorder/rotate/merge server-side | Re-parse already-edited output | pikepdf/qpdf |
| **Rasterizer** | Page → image, for both preview confirmation and PNG/JPEG export | Be the fallback for "hard" pages | pdfium or MuPDF CLI in a worker |
| **Conversion Sidecars** | DOCX, PDF/A, validation | Be linked into the main app process | Separate containers, subprocess-only interface |
| **Job Queue** | Async exports with progress | Handle edit commits | Celery/RQ/arq + Redis; SSE for progress |

---

## 1. Component Boundaries — What Talks to What

Four hard boundaries. Cross them only in the direction shown.

**Boundary 1: Browser ↔ Server = recipe JSON + content hash, not documents.**
The browser sends `{sourceHashes[], pages[], overrides{}}`. Bytes only travel on a cache miss, and the server tells the browser when it needs them (`409 SOURCE_MISSING` → browser re-uploads → retries). This makes the server restartable and losable, which is the same property that makes the no-retention promise credible.

**Boundary 2: Viewer ↔ Edit Surface = the run map, one-way.**
pdf.js paints pixels. The server's run map paints hit boxes on top. The viewer's own text layer is used only for select/copy/browser-find UX and is *never* consulted for edit targeting. See §2 for why.

**Boundary 3: Interpreter ↔ everything else = the run index is the only public shape.**
The Font Service, Width Fitter, and Assembler all consume run records. Nobody outside the interpreter touches raw operators. This is what keeps find/replace, single-run edit, and scanned-page detection from becoming three different parsers.

**Boundary 4: App ↔ Conversion Sidecars = subprocess with a file in and a file out.**
Ghostscript and PyMuPDF are AGPL; Ghostscript's own FAQ is explicit that AGPL code "made available over a network must itself be released under the AGPL," which for a hosted SaaS means the whole app ([ghostscript.com/faq](https://ghostscript.com/faq/)). Whether subprocess isolation is sufficient is a legal question, not an engineering one — but architecturally, keeping these behind a swappable process boundary means the answer can change (buy a commercial license, swap the tool, drop the feature) without touching the engine. Do not `import fitz` into the edit path.

---

## 2. ★ How Is an Edit Represented? (the make-or-break decision)

### The problem, stated precisely

pdf.js `getTextContent()` returns items shaped exactly like this ([pdf.js api.js](https://github.com/mozilla/pdf.js/blob/master/src/display/api.js)):

```javascript
/**
 * @typedef {Object} TextItem
 * @property {string} str            // reconstructed text
 * @property {string} dir
 * @property {Array<any>} transform  // TRM; [4] and [5] are x,y in PDF user space
 * @property {number} width
 * @property {number} height
 * @property {string} fontName       // pdf.js-internal name, e.g. "g_d0_f1"
 * @property {boolean} hasEOL
 */
```

There is **no operator index, no byte offset, no object number**. And the reconstruction is lossy in documented ways: overlapping strings get merged into one item ([#7445](https://github.com/mozilla/pdf.js/issues/7445)), font transitions between normal and bold can vanish from `fontName` ([#7297](https://github.com/mozilla/pdf.js/issues/7297)), and the reported `fontRef` can disagree with what was actually used to render ([#14755](https://github.com/mozilla/pdf.js/issues/14755)).

From the other side, pikepdf's own documentation says the inverse thing: *"We strongly recommend against trying to scrape text from the content stream... in general, you cannot rely on there being a transparent mapping"* between glyph codes and Unicode, and *"content streams should be thought of as an output format"* ([pikepdf content streams](https://pikepdf.readthedocs.io/en/latest/topics/content_streams.html)).

So: the client has Unicode without addresses, and the server has addresses without Unicode. Any design that tries to *reconcile* these two after the fact — string-matching pdf.js output against content-stream output, or geometry-matching bboxes — is building a fuzzy join on the critical path of the product's core value. It will work on 90% of PDFs and silently corrupt the other 10%.

### Options evaluated

| Option | Verdict |
|---|---|
| **Send whole file + patch instruction** | Correct but not sufficient on its own — it answers *transport*, not *addressing*. Still needs a run ID. Combined with the recommendation below. |
| **Server-side session with parsed document** | Rejected as the *system of record*. A parsed pikepdf object per user is tens of MB, pins a worker, requires sticky routing, and turns "we keep nothing" into "we keep everything for 15 minutes." Kept only as an *optional cache*. |
| **Structured edit-op log applied server-side** | Right shape, wrong data structure. See below. |
| **Client-side WASM engine (single representation)** | Rejected by locked constraint (multi-MB WASM, font subsetting capped). |
| **★ Server-issued run index + declarative override map** | **Recommended.** |

### The recommendation

**One interpreter, two outputs, addresses issued by the server, edits expressed as a declarative sparse map.**

Build a single content-stream walker that maintains PDF text state (`Tf Tm Td TD T* TL Tc Tw Tz Ts`, per PDF 32000 §9.4.4 — pdf.js's own `getCurrentTextTransform()` in `src/core/evaluator.js` is a working reference for the TRM math). It runs in two modes over the same traversal:

- **Index mode** → emits a run record per text-showing operator.
- **Rewrite mode** → emits new operators, consulting the override map by the same IDs it issued in index mode.

Because it is literally the same traversal function, the index and the rewrite cannot disagree. This is the single most important structural decision in the system. Two separate implementations will drift, and the drift will look like data corruption.

**Run record (the wire contract):**

```jsonc
{
  "id": "s0:p3:c0:o147",      // source · page · contentStreamPart · operator ordinal
  "text": "Total Due",         // decoded Unicode
  "bbox": [72.0, 690.1, 141.6, 702.3],   // PDF user space, unrotated
  "font": { "ref": "F3", "size": 11.0, "embedded": true, "subset": true },
  "advance": 69.6,             // the width the replacement must fill
  "fp": "a3f91c",              // fingerprint: hash(raw glyph bytes + Tm + font ref)
  "editable": true,            // false ⇒ Type3, no ToUnicode, inline-image-heavy, etc.
  "reason": null               // why not editable, for honest UI
}
```

**What crosses the wire on a commit:**

```jsonc
POST /v1/render
{
  "sources":   { "s0": "sha256:9f2a…" },
  "pages":     [ {"src":"s0","page":0,"rotate":0}, … ],
  "overrides": {
    "s0:p3:c0:o147": { "text": "Amount Due", "fp": "a3f91c",
                        "style": {"font":"NotoSans-Regular","size":11,"color":[0,0,0]} }
  },
  "want": "page-image:3"       // or "pdf" at save time
}
```

**Why declarative sparse map, not an ordered op log.** Reflow is out of scope by locked constraint — a replacement occupies the original run's space. That means **edits to different runs are independent and commutative**, and edits to the same run simply supersede each other. There is no sequence to replay. An op log would encode ordering that carries no information, and would force replay semantics on undo. A map is smaller, order-free, idempotent, and trivially diffable.

**The `fp` fingerprint is not optional.** It is the guard that turns a stale reference into a clean `409 STALE_RUN` instead of a corrupted document. Verify it before applying; refuse on mismatch.

**Preview vs. output.** The optimistic DOM overlay that appears while the user types *is* an overlay — and that is fine, because it is never exported. The "no overlay" constraint governs the artifact, not the preview. The server round-trip on commit (~200–500ms for a single page returning a rendered PNG) replaces the optimistic overlay with ground truth. This is how you get a responsive editor without shipping the engine to the browser.

---

## 3. Document Identity and State Under No-Retention

### The three options, priced

Assume a typical target document of 0.5–5 MB (contracts, invoices, letters) and a 10 Mbps upstream.

| Option | Memory (server) | Latency per commit | Privacy story | Verdict |
|---|---|---|---|---|
| **A. Re-upload per operation** | ~0 steady state | +1.6s upload for 2MB, every commit | Strongest: "we hold your file only during the request" | Too slow for interactive editing; correct as a *fallback* |
| **B. Server session with TTL** | 2MB × concurrent editors, plus a parsed doc (10–50MB) if held hot. 1000 concurrent ≈ 2 GB raw / 20+ GB parsed | ~0 upload | Weakest: a session is a retention window; needs sticky routing; a crash-dump or swap file is a disclosure | Rejected as system of record |
| **C. ★ Client-authoritative bytes + content-addressed evictable server cache** | Same as B, but the cache is *optional* — cap it and evict freely | ~0 on hit; degrades to A on miss | "The server can lose everything at any moment and nothing breaks" — a structurally verifiable claim | **Recommended** |

### Recommended: Option C in detail

- Browser holds the original `ArrayBuffer` for every source document. That is the system of record.
- On ingest, the server computes `sha256(bytes)` and returns it as the source handle.
- Server keeps `sha256 → bytes` in a RAM cache (Redis `EX 900`, `maxmemory` + `allkeys-lru`, or in-process LRU). Backing store is tmpfs if it must spill — never a persistent volume. Container runs read-only rootfs with an explicit tmpfs mount for scratch; Stirling-PDF uses exactly this pattern for its stateless mode ([Stirling-PDF discussion #5021](https://github.com/Stirling-Tools/Stirling-PDF/discussions/5021)).
- Every request carries the recipe. If a hash is missing from cache, respond `409 {missing: ["sha256:…"]}` and let the client re-POST the bytes. **This path must be exercised in tests, not just written** — it is the thing that keeps the cache honest.
- The parsed-document object (expensive) is cached separately and even more aggressively evicted, keyed by the same hash. Purely a speed optimization.

**Why this is the right reconciliation of ephemeral + interactive.** It converts the privacy promise from a *policy* ("we delete files") into a *structural property* ("the server has no state whose loss is observable"). That claim is testable: kill the cache mid-session in a test and the session must survive. Policies are unverifiable by users; structural properties can at least be described honestly.

Also: never key the cache on a client-supplied ID. Content hash means two users uploading the same file share a cache entry — which is fine and saves memory — but it also means an ID cannot be guessed to fish for someone else's document unless you already have the document. Do not add a user-visible "document ID" that is anything other than the content hash.

---

## 4. Text Run Addressing Across Edits

**The scheme that survives:** address against the **immutable original source bytes**, never against output.

```
{sourceHash}:p{pageIndexInSource}:c{contentStreamPart}:o{operatorOrdinal}[:g{start}-{end}]
```

This works because of one rule, which is the whole trick:

> **Edits are always applied to the original document. The output of an edit is never the input to the next edit.**

Object numbers churn and content streams get rewritten — but only in the *output*, which is a throwaway artifact regenerated from `(original bytes, recipe)` every time. The original never changes, so ordinals never drift. Undo, redo, and reordering all fall out for free.

Supporting details:

- **`c{contentStreamPart}`** exists because `/Contents` may be an array of streams, and the concatenation is what's rendered. Index the parts, don't assume one stream.
- **`g{start}-{end}`** is a glyph range within the run, for sub-run edits (change one word inside a `Tj` of a whole line). Optional in v1 — whole-run replacement is simpler and matches how users will select.
- **`fp` fingerprint** guards against the client having a run map from a different parse (version skew, cache confusion). Cheap, and converts a corruption class into an error class.
- **Page ops never touch run IDs**, because the ID contains the *source* page index, not the assembled output position. Reorder 40 pages and every override still resolves. This is why the page list must store `{src, page}` references rather than mutating a page array in place.
- **Form XObjects** are the sharp edge: text drawn via `/Do` lives in a different stream, potentially shared across pages. Either extend the ID with an XObject path (`x{name}`) or mark such runs `editable: false` in v1 and say so. Editing a shared XObject changes every page that references it — a genuine correctness trap.
- **MCIDs** (marked-content IDs) are a real per-page stable identifier and pdf.js can surface them via `getTextContent({includeMarkedContent: true})` — but they only exist in tagged PDFs, which most real-world documents are not. Useful as an accessibility-aware enhancement, not as the primary scheme.

---

## 5. Find and Replace Across All Pages

**It is a distinct bulk operation, not a loop over per-page edits** — but only at the *search* layer. At the *apply* layer it degenerates into ordinary overrides, which is exactly what you want.

```
1. INDEX     Client requests the full-document run index (all pages) once.
             Server streams it (NDJSON) so page 1 is interactive before page 400 parses.
             Index is cached by source hash — subsequent searches are free.

2. SEARCH    Runs entirely CLIENT-SIDE over the cached index.
             Zero round trips per keystroke in the search box.
             Cross-run matches ("To" + "tal" in adjacent Tj ops) are joined here
             using the same normalization the interpreter used.

3. PREVIEW   Client produces a match list: run ID, page, ±40 chars of context,
             projected fitted width, and a per-match warning flag:
               • "replacement is 40% wider — will be condensed"
               • "'ß' not in embedded font — will switch to Noto Sans"
               • "run is inside a shared Form XObject — affects 12 pages"
             Match count and page thumbnails render immediately. No server call.

4. CONFIRM   User deselects any matches. Client writes N entries into overrides{}
             as ONE undo step.

5. APPLY     A normal /v1/render. Server sees N overrides instead of one.
             The interpreter walks each affected page once.

6. VERIFY    Server returns rendered images for the first K affected pages.
             User sees the actual result, not a promise.
```

The important consequence: **there is no `POST /find-replace` endpoint.** Find/replace is a client-side query that produces a batch of the same overrides a manual edit produces. One apply path, one set of correctness tests. If you build a separate bulk endpoint you will have two rewrite implementations within six months.

The one genuinely bulk concern is *cost*: indexing 400 pages is seconds, not milliseconds. Index lazily (viewport pages first) for viewing; index fully and once, in the background, when the user opens the find panel.

---

## 6. Font Pipeline — Where and When

**Subsetting runs once, at export. Coverage queries run per edit. Never subset on a keystroke.**

Three distinct operations, commonly conflated:

| Operation | When | Cost |
|---|---|---|
| **Encoding decode** (glyph code → Unicode, via `/ToUnicode` CMap + `/Encoding` + `/Differences`) | Once per source doc, during indexing | Cached with the run index |
| **Coverage query** ("does the embedded subset contain 'é'?") | Per edit commit, cheap | Read the font's `cmap`/CIDToGIDMap once, cache the coverage set |
| **Subset + embed** | Once, at export/save | Hundreds of ms per font; the expensive one |

### Decision flow on an edit

```
replacement text
      │
      ├─► all glyphs present in the run's existing embedded font?
      │        YES ──► reuse the original font ref. Nothing to embed.
      │                ★ THE IDEAL PATH — output is byte-identical except
      │                  the operators you touched.
      │
      └─► NO ──► pick bundled family by best metric match to the original
                 (family name heuristic → then avg advance width + x-height)
                 ──► change /Tf for this run to the new font ref
                 ──► record it in a pending-embed set
                 ──► AT EXPORT: union all characters used across all runs
                     assigned to that bundled face → ONE subset → ONE font dict
```

That union step is why subsetting must be deferred: if you subset per edit you produce N font programs for N edits of the same face, bloating the file and creating N sets of `/BaseFont` names to keep straight. Subsetting once over the union produces one `ABCDEF+NotoSans-Regular`.

Embedding target: `Type0` / `CIDFontType2` with `Identity-H` encoding, an `Identity` `CIDToGIDMap`, a `/W` widths array, and a generated `/ToUnicode` CMap. Identity-H is the standard and simplest choice for embedded composite fonts, and generating `/ToUnicode` is non-negotiable — its absence is precisely what makes text extract as garbage in Acrobat and search break silently.

### Two merged documents with different subsets of the same family

This is the case that decides whether the merge feature is correct or a source of bug reports. Three sub-cases:

1. **Neither document's text is edited.** Do nothing. Keep both fonts as separate resources under distinct names in each page's `/Resources`. They are different font objects that happen to share a `/BaseFont` root; PDF handles this fine and merging tools do it all day. **Do not try to be clever and unify them** — different subsets have different glyph-ID assignments, so unifying without remapping every glyph code is exactly how you produce a file that shows the right words in Chrome and mojibake in Acrobat.
2. **Text is edited in one of them, all glyphs available in that document's own subset.** Also do nothing beyond the rewrite. The other document's font is untouched.
3. **Text is edited and needs a glyph absent from the local subset.** Switch that run to the bundled face. Do not attempt to merge glyphs from the other document's subset even though the family matches — the two subsets may be from different foundry versions with different outlines, and you cannot verify that at runtime.

Rule of thumb: **the font pipeline only ever adds a bundled face; it never modifies or merges an existing embedded font.** That constraint is what makes the fidelity claim defensible.

The known-hard part (flagged for deeper phase research): choosing a bundled substitute whose metrics are close enough that a whole replaced run doesn't look pasted-in. Liberation Sans/Serif/Mono are metric-compatible with Arial/Times/Courier by design, which covers a large fraction of real business documents; Noto Sans/Serif covers script breadth; DejaVu covers symbol breadth. Ship a static mapping table, not a heuristic.

---

## 7. Export and Conversion Pipeline

**Two protocols, split by *user intent*, not by measured latency.**

- **Edit commit** = synchronous request/response. Always. It is interactive; a job ID is user-hostile here.
- **Every export** = uniform async job (`202` + job id + SSE progress). Even the fast ones.

Making all exports async is the lazy-correct call: it is one client code path, one cancel path, one error path, and it means a slow PDF never times out an HTTP request. The cost is one extra round-trip on fast exports, which is invisible next to a browser download dialog. The alternative — a latency-threshold rule where some endpoints return `200 <bytes>` and some return `202 <job>` — needs both code paths anyway, so you gain nothing and own two.

| Export | Approx cost | Notes |
|---|---|---|
| Split / extract pages | ms | Could be client-side (pdf-lib) entirely |
| Plain text / Markdown | ms — the run index already has it | Free byproduct of indexing |
| HTML | 100s of ms | Positioned-div output from the run index |
| PNG / JPEG at DPI | ~50–200 ms/page (MuPDF/pdfium) | Linear in pages × DPI²; a 300-page doc at 300 DPI is minutes and needs real progress |
| Flatten | sub-second typical | |
| Compress | 1–20 s | Image recompression dominates; highly variable |
| **PDF/A** | seconds → tens of seconds | Ghostscript reprocesses the whole document. **AGPL boundary.** Then validate with veraPDF, the industry-supported PDF/A validator ([verapdf.org](https://verapdf.org/)) |
| **DOCX** | 2–30 s | unoserver/LibreOffice listener mode is 2–4× the throughput of spawning `soffice` per file ([unoserver](https://github.com/unoconv/unoserver)). Best-effort by locked constraint |

Sidecar shape: DOCX and PDF/A run in their own containers with their own worker pools and their own concurrency caps, because a LibreOffice process that wedges must not starve the edit path. `X-Concurrency` on the queue, not on the web tier.

---

## 8. Undo / Redo

**Snapshot the recipe. Not the document.**

The recipe is JSON in the kilobytes: a source list, a page list of `{src, page, rotate}` entries, and an override map. Undo is a stack of `structuredClone(recipe)` snapshots, entirely in browser memory. No server involvement, no server state, instant, and unaffected by the server restarting or the cache evicting.

```javascript
// The entire undo system.
function commit(mutator) {
  undoStack.push(structuredClone(recipe));
  redoStack.length = 0;
  mutator(recipe);
  scheduleRender();          // debounced /v1/render for the affected page
}
const undo = () => { redoStack.push(structuredClone(recipe));
                     recipe = undoStack.pop(); scheduleRender(); };
```

Cap the stack at ~100 entries; at ~2 KB each that is 200 KB.

This works *only because* of the §4 rule that edits apply to originals. If the authoritative document were a mutating server-side object, undo would require either snapshots of multi-MB documents or replay of an op log — and replay gets slower with every edit, which is a terrible property for undo specifically.

**Alternatives considered and rejected:**

- **Op-log replay.** Undo cost grows linearly with edit count. Needs memoized intermediate snapshots to be usable, which reintroduces server state. And the log's ordering carries no information (see §2).
- **PDF incremental updates as the undo stack** (append a revision per edit; undo = truncate to the previous `%%EOF`). Genuinely elegant — PDF revisions *are* a stack — and it would give byte-perfect preservation of untouched content. Rejected because qpdf, the most likely engine substrate, does not write incremental updates: running it over an incrementally-updated file drops the previous versions ([qpdf #22](https://github.com/qpdf/qpdf/issues/22)), and writing incremental updates is listed as a future item in [qpdf's TODO](https://github.com/qpdf/qpdf/blob/main/TODO.md). Implementing xref-stream-aware incremental writing by hand is a project unto itself. Revisit only if fidelity testing shows full-rewrite is losing data.

---

## 9. Build Order

### Dependency graph

```
                    ┌──────────────────────────┐
                    │ Font/Encoding Decoder    │   ← no dependencies
                    │ ToUnicode, Differences,  │      START HERE
                    │ cmap, hmtx, coverage     │
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐   ┌────────────────────────┐
                    │ ★ Content-Stream         │   │ VALIDATION HARNESS     │
                    │   Interpreter            │◄──┤ built IN PARALLEL,     │
                    │   (index + rewrite)      │   │ not after. §10          │
                    └────┬───────────────┬─────┘   └────────────────────────┘
                         │               │
              ┌──────────▼───┐    ┌──────▼──────────┐
              │ Width Fitter │    │ Run Index API   │
              └──────┬───────┘    └──┬──────────┬───┘
                     │               │          │
        ┌────────────▼───────────────▼──┐  ┌───▼────────────────┐
        │ Single-run rewrite (E2E slice)│  │ Scanned detection  │
        └────────────┬──────────────────┘  │ (0 runs + img area)│
                     │                     └────────────────────┘
        ┌────────────▼──────────────┐
        │ Font Subset + Embed       │  ← unlocks "type any character"
        └────────────┬──────────────┘
                     │
        ┌────────────▼──────────────┐     ┌──────────────────────┐
        │ Recipe model + page list  │────►│ Client page ops      │
        │ + undo                    │     │ (pdf-lib preview)    │
        └────────────┬──────────────┘     └──────────────────────┘
                     │
        ┌────────────▼──────────────┐
        │ Find & replace (all pages)│
        └────────────┬──────────────┘
                     │
        ┌────────────▼──────────────┐     ┌──────────────────────┐
        │ Sync-ish exports          │     │ Job queue            │
        │ (text/md/html/png)        │────►│  └► PDF/A, DOCX      │
        └───────────────────────────┘     └──────────────────────┘
```

### The thinnest end-to-end slice

**"Change one word in a real invoice and have it open correctly in Acrobat, Preview, and Chrome."**

Deliberately *not* a UI milestone. Do it as a CLI first, then wire the browser to it.

**Slice 0 — headless, no web tier at all.**

```bash
pdftool index invoice.pdf --page 0        # → run index JSON
pdftool edit invoice.pdf --run s0:p0:c0:o41 --text "Amount Due" -o out.pdf
```

Success criteria, all of which must hold:
1. `out.pdf` differs from `invoice.pdf` in exactly the operators of run `o41` and its containing stream — verified by diffing `qpdf --qdf --object-streams=disable` normalizations of both files.
2. The replaced text occupies the original advance (`|Δwidth| < 0.5pt`), with no visible shift of anything after it.
3. `qpdf --check out.pdf` is clean.
4. Rendered at 150 DPI by **three independent engines** (pdfium, MuPDF, Poppler), the non-edited region of the page is pixel-identical to the original in all three, and the edited region is identical *across the three engines*.
5. Opens without a repair prompt in Acrobat Reader, macOS Preview, and Chrome's built-in viewer — a human check, once, per candidate approach.

**Slice 0b — the font path.** Same, but the replacement contains a character absent from the embedded subset (`"Amount Due №1"` or an accented character). This forces bundled-font selection, subsetting, `/ToUnicode` generation, and CIDFontType2 embedding. Additional criterion: copy-paste out of Acrobat yields the correct Unicode string.

Slice 0b is the one that actually proves the architecture. Slice 0a can pass with a naive implementation that got lucky about glyph coverage. **Do not proceed to the web tier until 0b passes**, because the font layer is the load-bearing part and discovering it doesn't work after building a viewer is the expensive failure mode.

**Slice 1 — walking skeleton.** Upload → index page 1 → pdf.js canvas + server-issued hit boxes → click → type → `POST /v1/render` → page image back → download. Explicitly excluded from Slice 1: page ops, find/replace, all exports, undo, multi-page indexing.

### Ordering rationale

Everything upstream of the interpreter is a prerequisite for everything downstream, so the risk is entirely front-loaded — which is correct, because if the interpreter cannot round-trip real-world PDFs faithfully, the product does not exist and you want to know in week two. The viewer, page ops, and exports are all comparatively conventional work with well-trodden libraries; sequencing them early would produce an impressive demo built on an unproven core.

Scanned-page detection is cheap and hangs directly off the index (zero editable runs + high image-area coverage on the page), so it can ship with the index rather than as its own phase.

---

## 10. Testing Strategy for Correctness

The hazard is precisely stated in the question: **output can look fine in one viewer and be broken in another.** Testing must therefore be *differential across engines*, not *assertive against one*.

### Layer 1 — Structural validity (fast, every commit)

| Tool | Catches | Command |
|---|---|---|
| `qpdf --check` | Broken xref, bad stream lengths, damaged object structure | `qpdf --check out.pdf` |
| `pdfcpu validate` | Spec conformance; notably the only validator with PDF 2.0 coverage | `pdfcpu validate -mode strict out.pdf` |
| `mutool clean -s` | Sanitization warnings, content-stream syntax errors | `mutool clean -s -d out.pdf /dev/null` |
| `veraPDF` | PDF/A conformance, on the PDF/A export path only ([verapdf.org](https://verapdf.org/)) | `verapdf --flavour 2b out.pdf` |

Use two or three of these, not one. They disagree, and the disagreements are informative.

### Layer 2 — Cross-engine render agreement (the one that matters)

```
out.pdf ──┬─► pdfium   ─► page_N.png ─┐
          ├─► MuPDF    ─► page_N.png ─┼─► pairwise pixel diff
          └─► Poppler  ─► page_N.png ─┘    (must agree within ~0.1% of pixels)
```

If the three engines disagree on your output but agreed on the input, you produced something ambiguous — even if every one of them "opens" it. This catches the exact class of bug the question names, and it catches it without a human. Poppler, MuPDF, and pdfium are known to differ in fidelity and speed characteristics, which is what makes their *agreement* meaningful.

Pin the renderer versions in CI. Unpinned rasterizers make baselines rot.

### Layer 3 — Preservation diff (the fidelity guarantee)

For every edit test: render original and output, and assert the **unedited region is pixel-identical**, not merely similar. Mask the edited run's bbox plus a small margin; everything outside must diff to zero. This is a much stronger and much more useful assertion than a whole-page perceptual threshold, and it directly tests the product's core promise that the result "looks like nothing happened."

### Layer 4 — Semantic round-trip

Re-index the output and assert the run at the edited ID now decodes to the new string, and every other run decodes to exactly what it did before. This catches encoding and `/ToUnicode` bugs that render fine but destroy copy-paste and search — which is a real, common, and invisible-until-a-user-complains failure.

### Layer 5 — Corpus

The unit tests will not find the interesting bugs. A corpus will.

- The [veraPDF test corpus](https://github.com/veraPDF/veraPDF-corpus) — atomic per-clause files covering PDF/A 1–4, PDF/UA, and ISO 32000-1/2 edge cases.
- pdf.js's own `test/pdfs` regression corpus — hundreds of real files curated specifically because they broke something.
- A hand-built set of 30–50 real-world business documents: Word exports, LaTeX output, InDesign, scanner output, Google Docs exports, government forms, CJK, RTL, tagged and untagged. These are the actual distribution the product will meet.

Run the full corpus through **index → edit first editable run → validate → cross-render** nightly. Track a "faithfully round-trips" percentage as the primary engineering metric. That number, not feature count, is the honest measure of whether this product works.

### Layer 6 — Human check, rarely

Acrobat and macOS Preview cannot be automated cheaply, and Acrobat in particular is the viewer users will judge you by. Reserve manual verification for the slice gates and for release candidates. Do not make it routine — it will be skipped.

---

## Recommended Project Structure

```
engine/                        # pure, headless, no HTTP, no framework
├── cstream/
│   ├── walker.*               # ★ the one text-state machine (index + rewrite)
│   ├── runs.*                 # run record types, ID encode/decode, fingerprint
│   └── fit.*                  # width fitting: Tz / TJ deltas / Tc
├── fonts/
│   ├── decode.*               # ToUnicode, Encoding/Differences, cmap → Unicode
│   ├── coverage.*             # "does this face have this glyph?"
│   ├── subset.*               # fontTools wrapper
│   ├── embed.*                # Type0/CIDFontType2 dict construction, /W, /ToUnicode
│   └── bundled/               # OFL fonts + static substitution table
├── assemble.*                 # recipe → output bytes (pages, rotate, merge)
├── raster.*                   # page → image
└── cli.*                      # ★ engine is usable and testable with zero web tier

service/
├── api/                       # ingest, /v1/index, /v1/render, /v1/export
├── cache/                     # content-addressed, TTL, evictable
├── jobs/                      # queue + SSE progress
└── sandbox/                   # worker limits, timeouts, seccomp profile

sidecars/                      # LICENSE BOUNDARY — separate containers
├── docx/                      # unoserver / LibreOffice
├── pdfa/                      # Ghostscript (AGPL)
└── validate/                  # veraPDF

web/
├── viewer/                    # pdf.js canvas
├── edit/                      # hit boxes from run map, preview overlay
├── recipe/                    # state + undo stack
├── pageops/                   # pdf-lib, preview + pure-page-op download
└── search/                    # client-side find over the cached index

test/
├── corpus/                    # real-world PDFs, veraPDF corpus, pdf.js corpus
├── differential/              # 3-engine render agreement
├── preservation/              # masked pixel-identical assertions
└── baselines/                 # pinned renderer versions
```

**Rationale.** `engine/` has a CLI and no web dependency so the hard part is testable in isolation from day one and the nightly corpus run doesn't need a server. `sidecars/` is a directory boundary that mirrors a license boundary — that adjacency is deliberate and should be commented as such. `web/pageops/` is separate from `web/edit/` because they have different authority: page ops can produce a real download, edits cannot.

---

## Anti-Patterns

### 1. Deriving edit addresses from the pdf.js text layer

**What people do:** Use `getTextContent()` items as the edit targets, then string-match or geometry-match them to content-stream operators server-side.
**Why it's wrong:** They are two lossy reconstructions of different things. pdf.js merges overlapping strings, drops font transitions, and can report a `fontRef` that isn't what rendered. Any join between them is fuzzy, and it fails on exactly the complex documents your users care about most.
**Instead:** The server issues the addresses. The client only echoes them back.

### 2. Feeding edited output back in as the next edit's input

**What people do:** Keep a "current document" and apply each edit to it.
**Why it's wrong:** Every rewrite invalidates the run index, forcing a re-index per edit; ordinals drift; and full-rewrite generational loss accumulates. Undo becomes snapshots of megabytes.
**Instead:** Always `(original bytes, recipe) → output`. The output is a throwaway.

### 3. Letting the client-produced PDF be the download when overrides exist

**What people do:** pdf-lib assembles in the browser for speed, so ship that.
**Why it's wrong:** Two engines producing the delivered artifact means two fidelity behaviors and double the correctness surface.
**Instead:** One clean rule — **if `overrides` is empty and no font/format op is present, the client materializes and downloads with zero upload; otherwise the server produces it.** This preserves "page operations never leave your browser" as a literal, true statement, with a single well-defined crossover.

### 4. Subsetting fonts on every edit

**Why it's wrong:** N font programs for N edits of the same face; file bloat; `/BaseFont` name management.
**Instead:** Coverage query per edit (cheap, cached); union-then-subset once at export.

### 5. Server-authoritative session state

**Why it's wrong:** Sticky routing, memory proportional to concurrency, restarts lose user work, and a session window is a retention window that undercuts the product's central promise.
**Instead:** Client-authoritative bytes; server cache is evictable at any moment and the client transparently re-uploads.

### 6. Trusting an operator ordinal without a fingerprint

**Why it's wrong:** A stale client run map silently rewrites the wrong text. This is data corruption presented as success.
**Instead:** Carry `fp` on every override; verify before applying; `409` on mismatch.

### 7. Rasterizing a page as a fallback for "hard" pages

**Why it's wrong:** It destroys text, search, accessibility, and file size — the exact low-quality result this project exists to avoid. It also hides engine bugs behind a plausible-looking image.
**Instead:** Mark the run `editable: false` with a `reason` and say so in the UI. Refusing honestly is a feature; silently degrading is not.

### 8. Treating "it opens in Chrome" as validation

**Why it's wrong:** pdfium is forgiving. Acrobat is not, and Acrobat is the viewer that determines whether users trust the output.
**Instead:** Structural validators + three-engine render agreement, automated. See §10.

### 9. A separate code path for bulk find/replace

**Why it's wrong:** Two rewrite implementations that must stay in sync forever.
**Instead:** Find/replace is a client-side query producing N ordinary overrides through the ordinary apply path.

---

## Data Flow Summary

**Open:**
```
File → sniff/size-cap/hash → cache[sha256] → engine.index(page 0..k)
     → run map (NDJSON stream) → browser: canvas + hit boxes
```

**Edit one run:**
```
click → run id → type (optimistic DOM overlay)
     → blur/commit → recipe.overrides[id] = {text, fp, style}
     → POST /v1/render {sources, pages, overrides, want:"page-image:N"}
     → [cache hit? else 409 → re-upload bytes → retry]
     → engine: walk original page N, apply override, fit width, raster
     → PNG back → replace overlay with truth
```

**Save:**
```
POST /v1/render {..., want:"pdf"}
     → for each source: walk, apply all overrides for that source
     → union all bundled-font characters → subset once → embed
     → assemble pages per page list → write → stream to client
     → free buffers; nothing persisted
```

**Export (async):**
```
POST /v1/export {recipe, format} → 202 {jobId}
     → SSE /v1/jobs/{id}/events → progress
     → worker: render base PDF → sidecar (unoserver | ghostscript)
     → [PDF/A: veraPDF validate before returning]
     → GET /v1/jobs/{id}/result → bytes → delete
```

---

## Scaling Considerations

| Scale | Adjustment |
|---|---|
| 0–1k users | Single box. In-process LRU cache. Threads for engine work. Sidecars as sibling containers. Do not build a queue for the edit path. |
| 1k–100k | Redis for the blob cache (shared across web replicas, `allkeys-lru`). Engine workers become a separate autoscaled pool. Sidecars get independent pools and concurrency caps. Index cache becomes the highest-value cache. |
| 100k+ | Blob cache is the memory wall — consider a client-side re-upload-always mode for large documents. Rasterization moves to a GPU-less but CPU-dense pool. Regional deployment for upload latency, which is the dominant user-perceived cost. |

**First bottleneck:** blob cache memory. `concurrent_editors × avg_file_size`. Mitigation is architecturally free — shrink the TTL and let clients re-upload on miss, because that path already exists and is tested.

**Second bottleneck:** full-document indexing for large PDFs, which is CPU-bound and single-threaded per document. Mitigation: index the viewport pages first, background the rest, cache the result by content hash so it's paid once per document ever.

**Third bottleneck:** LibreOffice/Ghostscript worker saturation. Mitigation: independent pools with their own caps — never let an export queue starve the interactive edit path.

---

## Integration Points

| Service | Pattern | Gotchas |
|---|---|---|
| pdf.js | npm, worker thread | Text layer is display-only here. Version-pin: text extraction behavior has changed across releases. |
| pdf-lib | npm, main thread | Cannot render; cannot edit text. Encrypted PDFs won't load. Structural ops only. |
| pikepdf / qpdf | in-process | `parse_content_stream` / `unparse_content_stream` give token-level access; **no text decoding** — the docs explicitly point at pdfminer.six for that. Does not write incremental updates. |
| fontTools | in-process | The standard subsetter. Embedding into a PDF font dict is your code, not theirs. |
| pdfium / MuPDF | subprocess or bindings | Rasterization + differential testing. pdfium's `FPDFPage_GenerateContent` has a documented history of not marking modified objects dirty ([pdfium issue 1051](https://groups.google.com/g/pdfium-bugs/c/RBwhmdbejRk)) — do not rely on it as the edit primitive without verifying current behavior. MuPDF is AGPL. |
| unoserver / LibreOffice | subprocess, listener mode | 2–4× throughput vs per-file spawn. Processes wedge; supervise and cap. |
| Ghostscript | subprocess, separate container | **AGPL.** Network use triggers copyleft for a hosted service. Isolate or license. |
| veraPDF | subprocess, CI + PDF/A path | Ships with an atomic per-clause test corpus — use it as a corpus, not just a validator. |

**Security posture (non-negotiable, per the "never lazy about" list):** PDF parsers are a well-documented attack surface for untrusted input. Engine workers run non-root, read-only rootfs with a tmpfs scratch mount, no network egress, hard wall-clock and memory limits, and a restrictive seccomp profile. Validate magic bytes and cap size at ingest before the parser sees anything. A malicious PDF that hangs a worker must not hang the service.

---

## Sources

**Verified against official documentation (HIGH confidence):**
- [pdf.js `TextItem` typedef, `src/display/api.js`](https://github.com/mozilla/pdf.js/blob/master/src/display/api.js) — no content-stream back-reference
- [pdf.js `getCurrentTextTransform()`, `src/core/evaluator.js`](https://github.com/mozilla/pdf.js/blob/master/src/core/evaluator.js) — TRM computation reference
- [pikepdf: Working with content streams](https://pikepdf.readthedocs.io/en/latest/topics/content_streams.html) — parse/unparse; explicit warning against scraping text; "content streams should be thought of as an output format"
- [fontTools subset documentation](https://fonttools.readthedocs.io/en/stable/subset/)
- [qpdf issue #22 — `--qdf` scraps incremental updates](https://github.com/qpdf/qpdf/issues/22) and [qpdf TODO.md](https://github.com/qpdf/qpdf/blob/main/TODO.md)
- [veraPDF](https://verapdf.org/) and [veraPDF test corpus](https://github.com/veraPDF/veraPDF-corpus)
- [Ghostscript FAQ — AGPL vs commercial licensing](https://ghostscript.com/faq/)
- [pdfium `public/fpdf_edit.h`](https://github.com/klokantech/pdfium/blob/master/public/fpdf_edit.h) — `FPDFText_SetText`, `FPDFPage_GenerateContent`

**Verified across multiple credible sources (MEDIUM confidence):**
- [pdfium bug 1051 — `GenerateContent` dirty-flag gap](https://groups.google.com/g/pdfium-bugs/c/RBwhmdbejRk)
- [pdf.js #7445](https://github.com/mozilla/pdf.js/issues/7445), [#7297](https://github.com/mozilla/pdf.js/issues/7297), [#14755](https://github.com/mozilla/pdf.js/issues/14755) — text-layer reconstruction fidelity limits
- [Stirling-PDF stateless / temp-file discussion #5021](https://github.com/Stirling-Tools/Stirling-PDF/discussions/5021) — ephemeral processing as a shipped pattern
- [unoserver](https://github.com/unoconv/unoserver) — LibreOffice listener-mode throughput
- [PDF rendering engine comparisons](https://theproductguy.in/blogs/pdf-rendering-engines/) — Poppler / MuPDF / pdfium fidelity and speed differences
- [PDF text operators and TJ kerning](https://www.syncfusion.com/succinctly-free-ebooks/pdf/text-operators)
- [MCIDs and tagged PDF structure](https://www.overleaf.com/learn/latex/An_introduction_to_tagged_PDF_files%3A_internals_and_the_challenges_of_accessibility)

**LOW confidence — flagged for phase-level validation:**
- Latency figures for engine operations are order-of-magnitude estimates from general reports, not measurements on this workload. Measure in Slice 0.
- Bundled-font metric substitution quality (Liberation ↔ Arial/Times/Courier metric compatibility is documented by design; whether it is *visually* good enough mid-paragraph is unverified). Needs an empirical phase.
- No public reference implementation of the server-issued-run-index + declarative-recipe architecture was found. The individual pieces are each well-supported; the composition is a synthesis and should be de-risked by Slice 0b before committing the roadmap to it.

---
*Architecture research for: browser-based content-stream PDF editor, hybrid processing, ephemeral server*
*Researched: 2026-08-11*
