# Phase 4: Web Tier Walking Skeleton + Hardening — Plan Outline

**Phase goal:** A stranger can open the site with an untrusted PDF, see it rendered faithfully,
understand exactly what is and is not editable and where each operation runs, edit one text run, and
undo it — with nothing about the session surviving on the server. Gate G3, one indivisible claim:
*safe to hand a stranger*. Largest phase by requirement count (20).

**Governing constraint — D-4.4.** Hardening lands before the mutating UI. The ephemerality canary,
the isolated-worker limits, and the `no-store`/CSP posture are in force *before* the first byte of
user document is accepted through a mutating route. Gate criteria 1–3 occupy waves 3–7; criteria 4–5
occupy waves 8–10. This is why the middle of the phase is serial: it is the requirement, not a
planning artifact.

## Plan Table

| Plan ID | Objective | Wave | Depends On | Requirements |
|---------|-----------|------|------------|---------------|
| 04-01 | Branch merge, scaffold demolition, test-infra config: `main` → worktree, untrack `client/node_modules`, delete dead + out-of-scope `server/`, markers/`httpx`/mypy | 1 | — | PRIV-04, PRIV-07, EDIT-01 |
| 04-02 | Six fixtures that do not exist: user-password, genuinely-signed, decompression bomb, cyclic page tree, self-referencing Form XObject, canary-marker PDF | 2 | 04-01 | INGE-02, INGE-03, INGE-04, PRIV-05 |
| 04-03 | INGE-02 password threading through `RunIndex`/`classify_document`/`plan_recipe`/`apply_recipe` + `server/secrets.py` redacting wrapper | 2 | 04-01 | INGE-02, PRIV-04 |
| 04-04 | FONT-07 recipe-contract extension: optional `style` key, colour operator, weight/style variant routing, named refusal for size (A-4.2) | 3 | 04-03 | FONT-07 |
| 04-05 | `engine/boxes.py`: the run bounding box EDIT-01 needs and `RunRecord` cannot supply (height measures 0.0) | 3 | 04-03 | EDIT-01 |
| 04-06 | Isolation boundary: `server/worker.py` + `server/isolation.py` + injectable `server/errors.py`, all three hostile inputs, `CVE-VERIFICATION.md` | 3 | 04-01, 04-02, 04-03 | INGE-04, PRIV-04, PRIV-07 |
| 04-07 | `server/app.py` core rebuilt around `engine.recipe`: lifespan scratch, unified content address, worker dispatch, CORS + `no-store` + CSP middleware | 4 | 04-06 | PRIV-03, PRIV-06, PRIV-07 |
| 04-08 | Ingest routes: magic-byte sniff + size cap, password intake, signature detection and warn-before-save | 5 | 04-02, 04-03, 04-07 | INGE-01, INGE-02, INGE-03 |
| 04-09 | Ephemerality contract: `409 SOURCE_MISSING` on every document route, re-upload restores, scratch gone on both paths, no queue, no object store | 6 | 04-07, 04-08 | PRIV-02, PRIV-03 |
| 04-10 | PRIV-05 canary: five surfaces × two paths, fault injection, log AST scan, password marker, CI wiring | 7 | 04-02, 04-06, 04-08, 04-09 | PRIV-04, PRIV-05 |
| 04-11 | Server API surface: `/pages/{n}/runs` (boxes + bucket + verdicts, one response), `/edit`, `/ocr-notify`, `server/disclosure.py` | 8 | 04-04, 04-05, 04-09, 04-10 | VIEW-01, VIEW-02, CLAS-06, CLAS-07, EDIT-01, FONT-07, PRIV-01 |
| 04-12 | Client viewer: pdf.js render, `TextLayer`, page-1-first, thumbnail rail + badges, refusal screen + named OCR route, password prompt, signature warning | 9 | 04-11 | VIEW-01, VIEW-02, VIEW-03, VIEW-04, CLAS-06, CLAS-07, INGE-02, INGE-03 |
| 04-13 | Client edit surface: server-issued box overlay (never the text layer), style toolbar, recipe-as-undo-unit stack, per-operation local/server disclosure | 10 | 04-11, 04-12 | EDIT-01, EDIT-05, FONT-07, PRIV-01 |
| 04-14 | Gate G3: recorded manual journey verification (A-4.3), CDN `cf-cache-status` check (A-4.4), G3-diff regression, dated results document | 11 | 04-13 | VIEW-01, VIEW-03, VIEW-04, CLAS-07, EDIT-01, EDIT-05, PRIV-06 |

**14 plans, 11 waves.**

## Plan Details

### 04-01 — Branch merge, scaffold demolition, test-infra config

Merges `main` (commit `0acd3eb`) **into** the Phase 3 worktree branch rather than porting ~3,000
lines of gate-proven engine plus `fonts/` onto `main` — the branch is 45 commits ahead and carries
the project gate, so direction is the whole risk decision (§1.1). Resolves the `uv.lock` conflict by
re-running `uv lock`, and **drops `python-docx`**, a Phase 8 (EXPO-07) dependency pulled in only by
the out-of-scope DOCX endpoint. Runs `git rm -r --cached client/node_modules` (**5,041 tracked
files**, including built Vite dep bundles), adds it to `.gitignore`, and confirms
`client/package-lock.json` survives. Executes A-4.1's demolition: delete `server/engine_replace.py`
(a pre-G2b rewrite fork that violates D-11 by saving after collecting refusals at `:331` and never
checks `source_hash`), `server/ephemeral.py` (288 lines of dead code raising `NameError` on import,
whose `:157` writes a raw user filename to the log — PRIV-04), `server/diag{,2,3}.py`,
`server/font_subsetter.py` (superseded by `engine/fonts.py`'s D-13 union subsetting),
`server/smoke_test.py`, and the ~700 of 1,105 `app.py` lines implementing Phase 6/7/8 endpoints —
including `_pdf_to_docx` (`:912`), a **second text-extraction path** with its own `y_tolerance = 3.0`
clustering heuristic that bypasses `engine.clusterer`. **Deleting is not ignoring:** the removed
endpoint shapes are prior art for Phases 6–8 and the client expects several of them, so the plan
records what was removed and why in a committed deletion note. Adds pytest markers `linux_only` /
`e2e` / `cdn`, extends mypy `files` to `["engine", "server"]`, and adds `httpx` as a dev dependency —
`fastapi.testclient.TestClient` requires it and it is **installed on neither branch**. `httpx` is
tagged `[ASSUMED]` in RESEARCH's Package Legitimacy Audit, so a `checkpoint:human-verify` against
`pypi.org/project/httpx` gates the install (plan is not autonomous). Reimplementing any deleted
endpoint is explicitly out of scope.

### 04-02 — The six fixtures that do not exist

Every one of these was **measured absent** from the 217-document corpus, and four of the five
`Wave 0` test files below cannot be written without them. Copies `tools/build_mixed_fixture.py`'s
one-off-builder shape (pikepdf construction, `if __name__ == "__main__"`, output committed under
`tests/fixtures/`) for: a **user-password** PDF (`pikepdf.Encryption(user=…, owner=…, R=6)` — the
corpus's `irs_form_w9_encrypted.pdf` opens with an *empty* password and is a permissions fixture, not
an INGE-02 fixture; sweeping all 217 files for `PasswordError` returned empty); a **genuinely-signed**
PDF carrying a `/FT /Sig` field with a `/V` signature dictionary (`/ByteRange` + `/Contents`) —
hand-built in pikepdf rather than adding a signing dependency, because INGE-03's detector reads the
object graph and never verifies cryptographically, so `endesive`/`pyhanko` would be a new package for
a structural assertion; a **canary-marker** PDF carrying **two** distinct high-entropy markers, one in
a real text run and one in the filename, so a leak tells you *which* rule broke (never the content
hash — RETENTION-MAP explicitly permits hashes in logs). Builds the three INGE-04 hostile inputs: a
**decompression bomb** as a *generator run at test time*, never a checked-in multi-GB artifact; a
**cyclic page tree** (`/Pages /Kids` referencing an ancestor) via raw byte assembly since pikepdf will
likely refuse to write it; and a **self-referencing Form XObject** — which per 04-PATTERNS' key
finding is near-total reuse of the already-working
`tests/test_outside_contents.py:301-338`, because `engine/walker.py` and `engine/shared_xobjects.py`
already carry a per-branch visited-set cycle guard that terminates cleanly with a logged "cycle guard"
message and zero leaked glyph text. **This resolves 04-CONTEXT's second open question**: INGE-04's
third case is a worker-limit-and-verify task, not an engine-fix task — materially smaller than the
other two, and the plan must say so rather than budget for a fix that is not needed. Owns
`tests/conftest.py` fixture-path helpers for this wave.

### 04-03 — INGE-02 password threading + the redacting wrapper

`RunIndex.__init__` calls `pikepdf.open(path)` and `open_document(path)` (`index.py:113-114`) with no
password; `classify_document` (`classify_run.py:305`) and `plan_recipe`/`apply_recipe`
(`recipe.py:443`, `:646`) likewise. Threads an optional password through all five call sites.
`engine/playa_boundary.py` needs no wrapper code — `open_document` is a straight re-export of playa's
`open()` and its password kwarg passes through. **The hard half is not the signature change.** The
password is document content by any reasonable reading of PRIV-04, so it must never be logged, never
enter an error message, never be stored in the job record, and never appear in an error-reporter frame
local. `server/secrets.py` provides a redacting wrapper with a `__repr__`/`__str__` that cannot leak;
the plan checks `pydantic.SecretStr` first (already a transitive FastAPI dependency — rung 5 of the
ladder) before hand-rolling one. Also promotes `engine.recipe._active_font_name_and_size`
(`recipe.py:189-209`, with its spec-correct `_TF_NAME_SIZE_RE`) to public API, naming 04-05's
`engine/boxes.py` as its second consumer — this file is `engine/recipe.py`'s only same-wave writer, so
the promotion lands here rather than forcing a file conflict later. Tests extend the existing engine
test files; `tests/test_ingest.py` is created wholly by 04-08.

### 04-04 — FONT-07 recipe-contract extension

RESEARCH names this **the single largest under-estimation risk in the phase**: FONT-07 reads like one
UI toolbar and is a four-way engine change. `grep -rn "FONT-07" engine/ tools/ tests/` returns **zero
matches**; `RecipeOp` is a frozen two-field dataclass and `parse_recipe` rejects any op carrying a
third key (`recipe.py:117-120`). Adds an **optional** `style` object to `RecipeOp` and relaxes the
exact-key check — an *optional* key is a backward-compatible extension (old two-key recipes still
parse), and the plan states this explicitly so it does not read as a D-09 wire-format violation.
Per **A-4.2**: **colour and weight/style ship; a size change gets a named refusal** added to EDIT-04's
refusal vocabulary, because the D-01 fit ladder fits replacement text into the *original run's measured
width* and a size change makes that target a design decision rather than a measurement — refusing it
visibly is consistent with EDIT-04, CLAS-04 and FIND-05. Colour clones `engine/rewrite.py:900-957`'s
`Tf` save/restore bracket mechanically for `rg`/`g`/`k` (already a run-breaking attribute at
`rewrite.py:624`), and the D-04 matrix guard test at `tests/test_rewrite.py:693-733` is the template
for proving following text is undisturbed. Weight/style is near-zero new code — `BundledVariant`
already models `Regular|Bold|Italic|BoldItalic` (`fonts.py:62`) — but **must confront D-13 rather than
discover it at execution**: a bold variant is a second face in the same family, and D-13 is one subset
per family per document. `engine/fit.py` likely needs no change; `fit_run` already takes
`font_size_pt` as a parameter.

### 04-05 — `engine/boxes.py`: the run bounding box

EDIT-01 hit-tests against **server-issued boxes**, and no such box exists or can be derived from
`RunRecord` alone. Measured on `irs_form_w4.pdf` p0 run `'W-4'`: width comes out correctly at 40.0pt
from `GlyphRecord.x`/`advance`, but **height measures 0.0** — `advance` is `(dx, dy)` and purely
horizontal for horizontal writing mode, and none of `GlyphRecord`'s 13 fields carries font size,
ascent or descent. `ClusterAttrs.effective_em` holds the size the clusterer used but is dropped during
clustering and never retained on `RunRecord`. Takes the size from 04-03's promoted
`active_font_name_and_size` re-scan (option 1 — reuse, do not re-implement) and a fixed padding
multiple of the font size for ascent/descent (option 3), tagged `# ponytail:` with the upgrade path to
the font descriptor's `/Ascent`/`/Descent` via `engine.encoding_table.resolve_font` — there is
precedent, `tests/test_gate_g2b.py` already uses exactly this simplification and it is recorded in
`G2B-GATE-RESULTS.md:65`. A hit box needs to be unambiguous between adjacent lines, not typographically
precise, and the corpus test asserts exactly that property. **The derivation lives in one engine-side
module** so the box the server issues and the box `apply_recipe` reasons about cannot drift. Emits PDF
user space, origin bottom-left; the pdf.js top-left transform is the client's job via
`PageViewport.convertToViewportPoint` (verified present in the pinned 6.2.108).

### 04-06 — Isolation boundary, hostile inputs, CVE verification

Builds `server/isolation.py` (parent-side spawn) and `server/worker.py` (child entry point,
JSON-over-stdio) — **no analog exists in this repo**; no forked or subprocess Python worker exists
anywhere. The mechanism decision is settled by measurement: on the dev machine (macOS 15.7.7, arm64)
`setrlimit(RLIMIT_AS, …)` **cannot be set at all**, in a child, with both limits reported
`RLIM_INFINITY` beforehand, and `docker info` is `command not found`. So `RLIMIT_AS` and `RLIMIT_CPU`
are set in the child guarded by `try/except ValueError` (macOS degrades rather than crashes), the
`RLIMIT_AS` assertions carry `skipif(sys.platform == "darwin")` with an explicit reason string, and
the **wall-clock parent-side kill is the non-skippable control** — `RLIMIT_CPU` caps CPU time, not
wall time, and a worker blocked on I/O never trips it. CI is `ubuntu-latest` on all four workflows, so
the memory-cap clause is provable there and **must be asserted there or it silently never runs**.
Ships `server/errors.py` — an injectable error-reporter interface with a test double — **before any
reporter is initialized at module scope**; §8.3 names this as the single most likely thing to be
retrofitted badly, and 04-10's canary cannot capture events without it. Worker log records travel
structured back to the parent rather than to the child's own stderr, because `caplog` cannot see a
subprocess. Asserts INGE-04 on **host survival plus a named error**, never on a specific kill
mechanism — worker killed by rlimit/timeout, engine cycle-guard refusal, and an existing cap
(`MAX_DOCUMENT_GLYPHS = 10_000_000`) all satisfy "fails on its own limits", and pinning one mechanism
breaks the test whenever a cheaper guard fires first. PRIV-07 gets a **static** proof — importing
`server.app` leaves no `engine.*` module in `sys.modules` — which is the assertion that fails the
moment someone adds a convenience `from engine.index import RunIndex` at the top of `app.py`, which is
exactly how this regresses. Commits `CVE-VERIFICATION.md` from RESEARCH §12 (`G2B-GATE-RESULTS.md`
precedent), clearing STATE.md's aggregator-sourced-CVE blocker: 6 of 9 in-scope claims hold, three
mechanisms are uncorroborated by NVD, one version is wrong, and **CVE-2026-48155 is misattributed** —
the genuine self-referencing/re-used XForm match is GHSA-763m-79hh-57f2, which has no CVE. The
mitigation is unchanged; the attribution must be corrected rather than propagated.

### 04-07 — `server/app.py` core + HTTP posture

Rebuilds `server/app.py` around `engine.recipe`, keeping the four things the audit measured as
correct: content-addressing (`app.py:79-80`, already the same `sha256` digest `RunIndex` computes for
`source_hash` at `index.py:118` — Pitfall 9 forbids letting these drift into two identities), opaque
job IDs (`sha256(os.urandom(16))[:16]`), the `_scratch_dir` `try/finally` + `rmtree` shape, and the
per-page `{page, bucket, runs, editable, substitution, not_editable}` status payload shape. Fixes
defect #7 first: `SCRATCH_ROOT: Path` is a **bare annotation binding no value**, so `_ensure_scratch()`
raises `NameError` outside the ASGI startup event and no unit test, worker, or CLI entry point can
touch scratch — the canary test cannot be written at all until this is fixed. Moves to a `lifespan=`
context manager (`@app.on_event` is deprecated since FastAPI 0.93 and will warn on 0.141.1) and writes
uploads into the **per-job** dir, not the scratch root. Adds the project's **first HTTP middleware**
(zero `add_middleware` calls exist today — defect #4): CORS, `Cache-Control: no-store, private` on
document routes, and a CSP with **no `'unsafe-eval'`**. Pins the exact header string in a test —
`no-cache` and `max-age=0` are traps that produce `MISS` then `REVALIDATED`/`EXPIRED` at Cloudflare
rather than `BYPASS`, so a developer "hardening" the header would silently start caching at the edge.
Belt-and-braces per RETENTION-MAP: no `.pdf` extension in URL paths, which forces `DYNAMIC` and removes
the dependency on the header alone. The route-coverage test **enumerates `app.routes` dynamically**, so
every route added by 04-08/04-09/04-11 is automatically held to the header contract instead of
escaping a hand-maintained list. `isEvalSupported: false` is a **no-op** on the pinned pdfjs-dist
6.2.108 — the option appears in zero files and all three browser bundles contain zero `eval(` and zero
`new Function(` — so it is not the evidence; a unit tripwire re-greps the pinned bundles so a pdf.js
upgrade that reintroduces dynamic evaluation fails loudly. `tests/test_cdn.py` lands here behind the
`cdn` marker, **parameterized on a deployment URL per A-4.4** (Cloudflare is the assumed instance, not
a locked dependency), asserting `cf-cache-status ∈ {BYPASS, DYNAMIC}` and never
`HIT`/`MISS`/`EXPIRED`/`REVALIDATED`/`STALE`; the live run is 04-14's.

### 04-08 — Ingest: magic bytes, password, signature

INGE-01 is violated by design in the scaffold: `app.py:169-170` validates by **file extension** and no
`%PDF` check exists anywhere in `server/`. Replaces it with the strict sniff `data[:5] == b"%PDF-"` —
**measured safe against 217/217 corpus files** including all 17 malformed fixtures, with zero at a
later offset. The permissive `head[:1024].find(b"%PDF-")` form is deliberately rejected: at a trust
boundary tolerance is attack surface, the corpus does not need it, and a refusal here is a clean named
error rather than a wrong result. Size cap enforced **before the parser sees the bytes**. INGE-02
wires 04-03's threading to a password intake that is never persisted in the job record. INGE-03's
detector is the pitfall: five IRS corpus forms carry `/AcroForm /SigFlags 2`, which is bit 2
(`AppendOnly`) — bit 1 (`SignaturesExist`) is **not** set and no `/FT /Sig` field carries a `/V`, so a
detector written as `"/SigFlags" in acroform` reports five signed IRS forms that are not signed and
INGE-03's warning becomes noise users learn to dismiss. Checks `SigFlags & 1` or a `/FT /Sig` field
with a `/V`, and uses **those five files as the negative-case fixtures**. The warn-before-saving flag
is set here; the UI gate is 04-12's. Note for the UI: owner-password-only encryption is trivially
strippable and must never be presented as protection.

### 04-09 — Ephemerality: the `409` contract

PRIV-02's testable claim — killing the cache mid-session leaves the session working. Implements
`409 {"missing": ["sha256:…"]}` and the re-POST path, and this path **must be exercised by evicting
the cache, not by faking it**; an in-process LRU is acceptable for v1 and makes the eviction trivial.
**Every document-touching route needs the 409 branch, not just status** — if `/pages/{n}/runs` 200s
from a cached index while `/edit` 409s, the cache is not honestly evictable — so the test enumerates
routes dynamically for the same reason 04-07's header test does. Resolves a flagged conflict:
ARCHITECTURE.md:199's separate `fp` fingerprint yielding `409 STALE_RUN` is **superseded by D-10**,
where `source_hash` is embedded in the `run_id` itself and mismatch is a hard refusal with no override
flag. Building both means two staleness mechanisms disagreeing — `409 SOURCE_MISSING` is about cache
residency, `source_hash_mismatch` is about document identity, and they stay different responses.
PRIV-03: per-job scratch dir gone after the job returns on **both** the success and exception paths;
scratch is tmpfs asserted via `/proc/mounts`/`os.statvfs` on Linux/CI and skipped with a reason on
macOS, where RETENTION-MAP and the scaffold both already concede tmpfs is unavailable. **No queue is
built.** CLAUDE.md:89 calls a queue durable state and an anti-feature for a no-retention product;
Phase 4 has no LibreOffice, no conversion, and no operation exceeding a request timeout, so PRIV-03's
queue clause and PRIV-05's object-store surface are satisfied **structurally, by proving absence** —
via the `importlib.metadata.distributions()` scan `tools/license_gate.py:20-33` already uses. Pitfall 5
is explicit: adding Redis or an S3 client so the canary has something to inspect introduces the exact
durable state the requirement forbids.

### 04-10 — PRIV-05: the canary

The hardest item in the phase, and the reason D-4.4 puts hardening first — it pins design decisions
rather than merely testing them. Five surfaces × two paths, with RETENTION-MAP quoted as the
specification rather than assertions invented fresh. Positive proofs (walk the filesystem, grep
captured output, inspect the captured event dict) for **scratch**, **logs** and **error reporter**;
negative proofs by absence for **queue** and **object store**. The crash path is where retention
actually happens — a `finally` that does not run, a traceback carrying frame locals, a dead-letter
record — so it gets a **deliberate test-only fault-injection hook** rather than a hunt for a real input
that crashes, and the reporter assertion inspects **frame locals**, not just the message. Includes
PRIV-04's AST scan asserting no `logger.*` call in `server/` or `engine/` interpolates a variable
holding text or bytes, and a **password marker** in the canary set specifically (Pitfall 11: INGE-02
threads a password through five call sites and any `repr()`, log line or reporter frame local carrying
it violates PRIV-04 invisibly). Wires the whole suite explicitly into
`.github/workflows/tests.yml` — a canary that exists in the repo but not in CI is not a tripwire.
The test docstring states the honest limitation: this proves the canary did not leak on the paths
exercised, not that no document content leaks anywhere. That matches
`G2B-GATE-RESULTS.md`'s "What was NOT tested" discipline and is worth more than an overclaimed
assertion. Any leak this finds is fixed here, which is why it owns a wave of its own rather than
racing another `server/` writer.

### 04-11 — Server API surface

**One endpoint returns both boxes and verdicts per page**, so the CLAS-06 badge data and the EDIT-01
hit-test data cannot disagree: `GET /jobs/{id}/pages/{n}/runs` → `{page, bucket, runs:[{run_id, text,
box, state, reason}]}`, boxes from 04-05 in PDF user space. VIEW-02's bottleneck is measured and it is
the **server run index, not the raster**: on the 126-page `irs_1040_instructions.pdf`, first page ready
at 67ms versus 96.5s whole-document — a **1:1441 ratio** — and the scaffold actively destroys it by
looping `for p in range(page_count): idx.page(p)` before returning anything (`app.py:206-217`).
`RunIndex` is already lazy per-page with LRU eviction, so the engine half is done; the durable
assertion patches `RunIndex._parse_page` (explicitly built as "its own patchable method",
`index.py:139-143`) and asserts it was called **once, not 126 times**. All six `Bucket` literals map to
a defined badge state — the plan documents a collapse to three visual states with the exact bucket and
reason preserved for the refusal screen, never lost. The `/edit` route feeds request bytes **straight
into `parse_recipe`** rather than building `RecipeOp`s from a Pydantic model: `parse_recipe` is already
the hardened untrusted-input boundary (stdlib `json.loads` never `eval`, unknown-key rejection, both
DoS ceilings checked before any per-op object is constructed) and a parallel model duplicates the
validation and drifts from it. Adds the **separate request-body size limit on the recipe route applied
before `json.loads`** that §3.4 requires — `MAX_RECIPE_OPS = 50_000` × `MAX_NEW_TEXT_CHARS = 10_000` is
a 500 MB worst case reasoned for a human CLI operator, not an anonymous public endpoint. Dry-run and
commit expose the **same response schema** (D-11: `apply_recipe` returns `plan_recipe`'s report
unchanged, and on failure returns without reaching `save()` so no output exists at all), rendered
field-by-field from `RecipeReport`/`ResolvedOp` exactly as `tools/pdftool.py:94-111` does — never a
server-side recomputation of `delta_pt`, `strategy` or any reason string, and **never a rewritten or
prettified reason in transit**. `/ocr-notify` is a bare counter with **no payload** — no email, no
document reference, no IP retention — which satisfies both PRIV-04 and the no-accounts position while
still answering OCR-03's "how many people wanted this"; a local state toggle produces zero measurement
and silently defeats the requirement. `server/disclosure.py` is the PRIV-01 predicate: one function
over the pending operation set returning `"local" | "server"`, used **both** to route and to render the
badge, because two predicates make the badge a lie. Phase 4 ships no page ops so the local branch has
no operations to route yet — it must still exist and be tested, or Phase 6's PAGE-09 inherits a
retrofit.

### 04-12 — Client viewer

Rewrites `client/src/App.jsx` (692 lines, no decomposition today; component boundaries and state
management are Claude's Discretion). The canvas render path at `:56-66` already works and stays;
`getDocument`/`getPage(1)` render page 1 while later pages are unfetched, and **no pdf.js streaming
configuration is needed for the primary flow** because the client already holds the full `ArrayBuffer`
from the file input — page-1-first is achieved by fetching `/pages/{n}/runs` on demand. Adds
`TextLayer` (present at `pdf.mjs:14819`; `grep -i textlayer client/src/` currently returns nothing) as
absolutely-positioned transparent spans over the canvas, which is what makes **browser find and copy
work natively** because the text is real DOM — requires the pdf.js text-layer CSS or selection is
visible and misaligned. Thumbnail rail renders progressively as pages are fetched, with an honest
"not yet classified" state rather than blocking the rail on a whole-document pass. The refusal screen
renders `RunVerdict.reason` / `Bucket` **verbatim through a reason→copy mapping table with an explicit
unknown-reason fallback** — never invented prose (EDIT-04). Adds the password prompt (collected, never
persisted) and the signature warning gate before saving. **Carries a `checkpoint:decision`**: CLAS-07's
"specific external OCR route" must be a **named tool the user can go use today**, and it is a product
decision with no technical answer — a `TODO` there silently defeats the requirement and OCR-03's
measurement depends on it. Plan is not autonomous.

### 04-13 — Client edit surface

**Two overlays, and the plan says so explicitly** (Pitfall 6): 04-12's text layer is for selection,
copy and find only; the edit hit-test uses a **separate overlay of server-issued boxes** transformed
through `convertToViewportPoint`. Reusing the pdf.js text items is convenient, right there, and
violates D-4.2 and EDIT-01's explicit wording — and the run boundaries would not match the clusterer's,
which breaks runs on gap, font, size, colour, visibility and per-glyph verdict. A static source scan
asserts no client file ever constructs a `run_id`; the client echoes them byte-for-byte and never
parses the 8-optional-segment grammar. EDIT-05's undo store follows from the engine and needs **no
batching mechanism**: a recipe is already `tuple[RecipeOp, ...]` and `apply_recipe` is all-or-nothing
over the whole list, so **one recipe is one undo step** and Phase 5's replace-all is a recipe of length
N — the forward constraint falls out for free. The stack lives in the browser; a server-side undo log
is durable per-session state, exactly PRIV-02's prohibition. Undo re-applies the whole prefix from the
original bytes — one full `apply_recipe` per undo, not an incremental patch — and **nobody may optimize
this into an incremental model**: it looks like a performance win and it breaks the D-10 addressing
invariant the whole project rests on, because incremental undo would address the *output* bytes.
Editing the same run twice **replaces the stack entry rather than appending** (Pitfall 10:
`plan_recipe` refuses any recipe with a duplicate `run_id`, marking *every* op
`"duplicate_run_id_in_recipe"` — a naive append-only stack surfaces this as a baffling whole-recipe
refusal after the second edit). FONT-07 style ops live in the **same** recipe entries or undo reverts
text and style independently. The style toolbar surfaces A-4.2's size refusal like any other refusal.
`tests/test_undo.py` pins the **engine-side invariants** in Python — D-11 atomicity over a length-N
recipe, the duplicate-`run_id` refusal the replace rule must not collide with, and proof-by-absence
that no undo state is stored server-side; the browser stack's own behaviour is a recorded manual check
per A-4.3 rather than a reason to add a JS test runner for three assertions.

### 04-14 — Gate G3

The phase's terminal plan. Per **A-4.3**, the ~10 `e2e (browser)` rows of the test map are **recorded
manual checks, not dropped rows**, following the `G2B-GATE-RESULTS.md` precedent: a dated results
document with a `## Decision` header, per-check evidence, and an explicit "what was NOT tested"
section. A `checkpoint:human-verify` walks the G3-4 journey (open including a password-protected and a
signed document, faithful render, page 1 interactive before the last page parses, select/copy/browser-
find, badges in the rail, refusal naming its reason plus the named OCR route and the notify signal) and
the G3-5 journey (select a run, replace it, restyle it, see per-operation local/server disclosure,
revert with one Ctrl+Z), plus PRIV-06's behavioural CSP proof — render a document and populate its text
layer **under** a CSP lacking `'unsafe-eval'`, which is what actually proves the property; asserting
the header alone does not. Runs the CDN check against a deployment URL (A-4.4) and records the result;
if no deployment exists at gate time, that is recorded as NOT TESTED with the reason rather than
quietly passed. Re-runs G3-diff — `tests/test_gate_g2b.py::test_g2b_full_pipeline`, the one row that
already exists — to prove the Phase 4 transport did not regress the confined diff Phase 3 proved. Plan
is not autonomous.

## Sequencing Rationale

**Waves 1–3 front-load everything parallelizable; waves 4–11 are largely serial, and the serialization
is the requirement rather than a planning choice.**

- **Wave 1** (04-01): alone, because it is a whole-tree git merge plus a mass deletion. A parallel plan
  writing files during a merge is a conflict hazard even with disjoint `files_modified`.
- **Wave 2** (04-02, 04-03): disjoint file sets — fixture builders under `tools/`/`tests/fixtures/`
  versus `engine/recipe.py`/`index.py`/`classify_run.py` + `server/secrets.py`. Both depend only on the
  merged tree. Fixtures go early because four Wave-0 test files cannot be written without them.
- **Wave 3** (04-04, 04-05, 04-06): three disjoint file sets — `engine/recipe.py`+`rewrite.py`+`fonts.py`,
  `engine/boxes.py`, and `server/worker.py`+`isolation.py`+`errors.py`. All three are prerequisites the
  UI cannot be built without, and none of them is UI work. 04-04 and 04-05 both wait on 04-03 for file
  ownership of `engine/recipe.py` and for the promoted `active_font_name_and_size`.
- **Waves 4–7** (04-07 → 04-08 → 04-09 → 04-10): **this is D-4.4 executing.** Headers and CSP are in
  force before the ingest route exists; the ingest route exists before the ephemerality contract is
  proven; the canary runs against a settled surface before any mutating route is written. All four also
  own `server/app.py` or fix what it exposes, so same-wave parallelism is impossible regardless. The
  route-coverage tests in 04-07 and 04-09 enumerate `app.routes` **dynamically**, so routes added later
  in 04-11 are held to the header and `409` contracts automatically instead of escaping a
  hand-maintained list.
- **Wave 8** (04-11): the first mutating route. Every gate criterion 1–3 control is in force before it
  exists, which is the literal wording of D-4.4.
- **Waves 9–10** (04-12, 04-13): both rewrite `client/src/App.jsx` and share it as a composition root
  regardless of how components are decomposed, so they are sequential by file ownership. Viewer before
  edit surface also matches criteria 4 before 5.
- **Wave 11** (04-14): the gate, after everything, because its manual journeys exercise the whole
  assembled product.

**Where the hard constraints landed:**

| # | Constraint | Plan |
|---|------------|------|
| 1 | Merge direction (`main` → worktree, not the reverse) | 04-01 |
| 2 | `client/node_modules` untracked (5,041 files); `python-docx` dropped | 04-01 |
| 3 | A-4.1 demolition; ~700 out-of-scope lines deleted, none reimplemented | 04-01 |
| 4 | `httpx` `[ASSUMED]` → blocking legitimacy checkpoint before install | 04-01 |
| 5 | Markers `linux_only`/`e2e`/`cdn`; mypy `files=["engine","server"]` | 04-01 |
| 6 | Six absent fixtures built | 04-02 |
| 7 | Self-ref Form XObject already terminates → verify, not fix (open question closed) | 04-02, 04-06 |
| 8 | INGE-02 password threading + never in a `repr`/log/frame local | 04-03, 04-10 |
| 9 | FONT-07 = engine contract change, own plan; A-4.2 size refusal | 04-04 |
| 10 | `engine/boxes.py` — one module so server and `apply_recipe` cannot drift | 04-05 |
| 11 | `RLIMIT_AS` unavailable on macOS → skip guard + CI assertion; wall clock never skipped | 04-06 |
| 12 | Injectable error reporter **before** any module-scope reporter | 04-06 |
| 13 | `CVE-VERIFICATION.md` (doc artifact; CVE-2026-48155 misattribution corrected) | 04-06 |
| 14 | `SCRATCH_ROOT` `NameError` fixed before the canary can be written | 04-07 |
| 15 | Exact header string pinned; `no-cache`/`max-age=0` named as traps | 04-07 |
| 16 | `isEvalSupported` is a no-op; CSP is the real control + pdf.js grep tripwire | 04-07, 04-14 |
| 17 | Strict `%PDF-` sniff (217/217 measured), not the tolerant form | 04-08 |
| 18 | Signature detector: `SigFlags & 1` / `/FT /Sig` + `/V`; 5 IRS forms as negatives | 04-08 |
| 19 | `409 SOURCE_MISSING` on **every** document route, cache evicted not faked | 04-09 |
| 20 | D-10 supersedes `fp`/`409 STALE_RUN`; do not build both | 04-09 |
| 21 | No queue, no object store — proof by absence, not new infrastructure | 04-09 |
| 22 | Canary: 5 surfaces × 2 paths, fault injection, frame locals, CI-wired | 04-10 |
| 23 | One response carries bucket + boxes + verdicts (cannot disagree) | 04-11 |
| 24 | VIEW-02: `_parse_page` called once, not N times (1:1441 measured) | 04-11 |
| 25 | Request bytes → `parse_recipe` directly; body cap before `json.loads` | 04-11 |
| 26 | PRIV-01: one predicate for both dispatch and badge | 04-11, 04-13 |
| 27 | CLAS-07 OCR route named before ship (`checkpoint:decision`) | 04-12 |
| 28 | Two overlays; hit-test never against pdf.js text items | 04-13 |
| 29 | One recipe = one undo step; replace-not-append on repeat `run_id` | 04-13 |
| 30 | A-4.3 journey rows = recorded manual checks; A-4.4 CDN parameterized | 04-14 |

## Coverage Check

**Requirements.** All 20 phase IDs appear in at least one plan's Requirements column: INGE-01 (04-08),
INGE-02 (04-02, 04-03, 04-08, 04-12), INGE-03 (04-02, 04-08, 04-12), INGE-04 (04-02, 04-06),
PRIV-01 (04-11, 04-13), PRIV-02 (04-09), PRIV-03 (04-07, 04-09), PRIV-04 (04-01, 04-03, 04-06, 04-10),
PRIV-05 (04-02, 04-10), PRIV-06 (04-07, 04-14), PRIV-07 (04-01, 04-06, 04-07), VIEW-01 (04-11, 04-12,
04-14), VIEW-02 (04-11, 04-12), VIEW-03 (04-12, 04-14), VIEW-04 (04-12, 04-14), CLAS-06 (04-11, 04-12),
CLAS-07 (04-11, 04-12, 04-14), EDIT-01 (04-01, 04-05, 04-11, 04-13, 04-14), EDIT-05 (04-13, 04-14),
FONT-07 (04-04, 04-11, 04-13).

**Validation rows.** All 84 rows of `04-VALIDATION.md` have an owning plan. Data rows are automated in
the plan that implements their behaviour. The ~10 `e2e (browser)` rows become recorded manual checks
owned by 04-14 per A-4.3 — none is dropped. Both document artifacts have owning tasks:
`CVE-VERIFICATION.md` (04-06) and the CDN/journey results document (04-14). `G3-diff` is the one row
that already exists and is re-run in 04-14.

**Wave 0.** Every item in `04-RESEARCH.md`'s `## Wave 0 Gaps` list is owned: merge/`uv.lock`/
`python-docx`, `node_modules` untracking, scaffold deletion, `httpx`, markers, mypy `files`, and the
e2e-harness decision (settled by A-4.3, not built) in 04-01; the six fixtures in 04-02; password
threading in 04-03; the recipe schema extension in 04-04; `engine/boxes.py` in 04-05; the injectable
error reporter and `conftest.py`'s fault-injection hook in 04-06; the scratch-root-without-ASGI-startup
fixture in 04-07; the `TestClient` fixture in 04-07's header tests; the ten new test files across
04-05 through 04-11; and the `tests.yml` canary/hostile-input wiring in 04-10.

**Open items closed by this outline.** 04-CONTEXT's second still-open question (whether a
self-referencing Form XObject already terminates) is answered by `04-PATTERNS.md`'s key finding —
`engine/walker.py` and `engine/shared_xobjects.py` already carry a visited-set cycle guard proven by
`tests/test_outside_contents.py:301-338` — so it is scoped as reuse-and-verify in 04-02/04-06, not an
engine fix. The first still-open question (CLAS-07's named external OCR route) cannot be answered by a
planner and carries a `checkpoint:decision` in 04-12, before the refusal screen ships.

**Exclusions.** No plan implements a Deferred Idea (OCR, redaction, accounts, multi-page find/replace
UI) or an Out of Scope item (a bulk find-replace endpoint, white-box overlays, a second rewrite path,
a job queue, an object store). No deleted Phase 6/7/8 endpoint is reimplemented.

## OUTLINE COMPLETE

Plan count: 14
