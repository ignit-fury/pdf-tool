# Phase 4: Web Tier Walking Skeleton + Hardening - Pattern Map

**Mapped:** 2026-08-30
**Files analyzed:** 47 (create/modify, across server/, engine/, tests/, tools/, harness/, client/, config)
**Analogs found:** 38 / 47 (8 have no real in-repo analog and are flagged explicitly; 1 — the
self-referencing Form XObject fixture — already has a working implementation to reuse almost
verbatim, not merely an analog)

**Scaffold framing (per 04-CONTEXT.md Amendment A-4.1 — read before using this document):** the
`server/app.py` / `client/src/App.jsx` entries below marked **"prior art, not a pattern"** are
being deleted or rewritten wholesale, not extended. Where they appear as an "analog" it is
because their *shape* (a route name, a payload field, a try/finally block) is worth keeping —
never because their code should be copied as a starting point. Four specific things ARE worth
copying verbatim (content-addressing, opaque job IDs, the scratch try/finally shape, the
status-payload shape) and are called out as such below.

---

## File Classification

### Server / API layer (new territory over an engine that already does the hard part)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `server/app.py` | controller (FastAPI routes) | request-response + file-I/O | `server/app.py` (main, prior art — 4 shapes kept, ~700 lines deleted) + `tools/pdftool.py` (report rendering) + `engine.recipe` (validation boundary) | role-match (rebuild, not extend) |
| `server/app.py::upload` route (INGE-01) | controller | file-I/O, request-response | `server/app.py:167-178` (main, prior art — wrong check) + `corpus` measurement in RESEARCH.md §5.1 | prior art shows the wrong pattern; no right-pattern analog in repo |
| `server/app.py::/jobs/{id}/pages/{n}/runs` route (EDIT-01, CLAS-06, VIEW-02) | controller | request-response (lazy, per-page) | `engine.index.RunIndex.page(n)` (`engine/index.py:162-174`) + `tools/pdftool.py::_print_page_runs` (`tools/pdftool.py:76-82`) | role-match (engine side is exact; only the HTTP wrapper is new) |
| `server/app.py::/jobs/{id}/edit` route (D-4.3, D-11) | controller | request-response | `tools/pdftool.py::_cmd_edit` / `_print_report` (`tools/pdftool.py:94-135`) | exact (same `RecipeReport` object, HTTP instead of stdout) |
| `server/app.py::/jobs/{id}/ocr-notify` route (CLAS-07/OCR-03) | controller | request-response (counter, no payload) | none in repo (first pure-counter endpoint) | no analog |
| CORS + `Cache-Control`/CSP middleware (PRIV-06) | middleware | request-response | none in repo (`server/app.py` on `main` has zero `add_middleware` calls — defect #4) | no analog — first HTTP middleware in this codebase |
| `server/isolation.py` (parent-side spawn, `RLIMIT_AS`/`RLIMIT_CPU` + wall-clock kill) | service (process isolation) | subprocess / event-driven | `harness/run_corpus_harness.py::_run_structural_check` (`harness/run_corpus_harness.py:170-186`) — **partial**, external-tool subprocess+timeout only | weak/partial — nearest shape in repo, not the same mechanism |
| `server/worker.py` (isolated child process entry point, JSON-over-stdio) | worker / service | event-driven (stdio IPC) | none | **no analog — new territory, see below** |
| `server/secrets.py` (redacting password wrapper, INGE-02) | utility | transform | none (no `SecretStr`-style type exists anywhere in this codebase) | no analog |
| `server/disclosure.py` (PRIV-01 local/server predicate) | utility / service | transform (pure predicate) | conceptually `engine.classify_run.classify_run` (`engine/classify_run.py:187-232`) — a pure function returning one of a fixed set of named states | weak/conceptual only — business rule is new |
| `server/errors.py` (injectable error-reporter interface + test double) | service | event-driven | none | **no analog — new territory, see below** |

### Engine extensions (modify existing strict-typed modules)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `engine/boxes.py` (NEW — run bbox derivation, EDIT-01) | model / utility (pure transform) | transform | `engine.recipe._active_font_name_and_size` (`engine/recipe.py:189-209`) + `engine.rewrite`'s `Tf` bracket (`engine/rewrite.py:900-957`) + `engine.records.RunRecord`/`ClusterAttrs` (`engine/records.py:36-70`) | exact — reuse, don't reinvent |
| `engine/recipe.py` (MODIFY — optional `style` key on `RecipeOp` for FONT-07; password threading into `plan_recipe`/`apply_recipe`) | model + service (contract surface) | transform + CRUD-like resolve | itself — `RecipeOp` (`engine/recipe.py:81-86`), `parse_recipe`'s exact-key check (`engine/recipe.py:117`) | exact (self-analog; extend the existing shape) |
| `engine/index.py` (MODIFY — optional `password` param on `RunIndex.__init__`) | service (cache/index) | CRUD (lazy read, cached) | itself — `RunIndex.__init__` (`engine/index.py:112-123`, `pikepdf.open` at :113, `open_document` at :114) | exact |
| `engine/classify_run.py` (MODIFY — optional `password` param on `classify_document`) | service | batch/transform | itself — `classify_document` (`engine/classify_run.py:305-337`, opens at :316 and :327) | exact |
| `engine/rewrite.py` (MODIFY — colour operator bracket for FONT-07) | service (content-stream surgery) | transform | itself — the `Tf` save/restore bracket (`engine/rewrite.py:900-957`), same mechanical template for `rg`/`g`/`k` | exact — same bracket-and-restore shape, new operator |
| `engine/fonts.py` (POSSIBLY MODIFY, small — weight/style variant selection for FONT-07) | model / service | transform | itself — `BundledVariant` already models `Regular\|Bold\|Italic\|BoldItalic` (`engine/fonts.py:62`); `lookup_bundled_font` (`engine/fonts.py:205`, referenced) | exact — likely near-zero new code, see note below |
| `engine/fit.py` (LIKELY NO CHANGE — size-change re-fit for FONT-07) | service | transform | itself — `fit_run(original_advance_pt, replacement_text, font, font_size_pt)` (`engine/fit.py:304-376`) already takes `font_size_pt` as a parameter | exact — reuse as-is, new caller only |
| `engine/playa_boundary.py` (LIKELY NO CHANGE — password passthrough) | boundary/adapter | transform | itself — `open_document` is `from playa import open as open_document` (`engine/playa_boundary.py:121`), a straight re-export | exact — playa's own `open()` password kwarg passes through with no wrapper code to write |

### Fixtures that must be built (Wave 0, RESEARCH.md §5)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| Password-protected PDF fixture builder (INGE-02) | test fixture / utility | file-I/O (one-off, committed output) | `tools/build_mixed_fixture.py` (`tools/build_mixed_fixture.py:93-122`) — one-off builder script, pikepdf construction, `if __name__ == "__main__"` runner, output committed under `tests/fixtures/` | exact |
| Genuinely-signed PDF fixture builder (INGE-03) | test fixture / utility | file-I/O | `tools/build_mixed_fixture.py` (same shape) | exact shape; signing itself needs a library this repo does not have yet (flag as a dependency question, not a pattern gap) |
| Decompression-bomb fixture generator (INGE-04) | test fixture / utility | file-I/O (generate-at-test-time, not committed) | `tools/build_mixed_fixture.py::build_render_mode_7` (`tools/build_mixed_fixture.py:110-122`) — hand-built single-page PDF via raw content-stream bytes | role-match (generator-at-test-time rather than committed artifact — RESEARCH.md §5.4 is explicit this must NOT be a checked-in multi-GB file) |
| Cyclic page tree fixture builder (INGE-04) | test fixture / utility | file-I/O | `tests/test_outside_contents.py:321-329`'s self-reference-after-construction technique (`form.Resources.XObject = pikepdf.Dictionary(Fself=form)`) | exact technique, different object graph (`/Pages /Kids` instead of `/XObject`) |
| Self-referencing Form XObject fixture (INGE-04) | test fixture / utility | file-I/O | **`tests/test_outside_contents.py::test_self_referencing_form_xobject_walks_to_completion`, lines 301-338 — an almost-exact, already-working implementation, not merely an analog. See finding below.** | exact — near-total reuse |
| Canary-marker PDF builder (PRIV-05/PRIV-04) | test fixture / utility | file-I/O | `tools/build_mixed_fixture.py::build_render_mode_7` (`tools/build_mixed_fixture.py:110-122`) — hand-built minimal PDF, real text run, Standard-14 font, no embedding | exact |

### Tests — new (Wave 0)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_ingest.py` (INGE-01/02/03) | test | request-response / transform | `tests/test_recipe.py`'s untrusted-input boundary tests (`tests/test_recipe.py:50-118`) + `tools/probe_corpus.py::probe_file` (`tools/probe_corpus.py:125-178`, category detection via pikepdf object inspection — the signature-detector shape) | strong |
| `tests/test_hostile_input.py` (INGE-04) | test | integration / subprocess | `tests/test_outside_contents.py:301-338` (fixture + cycle-guard assertion, self-ref case) + `harness/run_corpus_harness.py::_run_structural_check` (`harness/run_corpus_harness.py:170-186`, subprocess + timeout) | strong for self-ref case; partial for bomb/cyclic-tree |
| `tests/test_isolation.py` (PRIV-07) | test | static analysis / subprocess | `tests/test_recipe.py::test_no_eval_or_exec_in_recipe_module` (`tests/test_recipe.py:115-118`) — source-text static-assertion pattern, for "no `engine.*` in `sys.modules`" | partial — static-check style transfers, the pid-diff dynamic check does not |
| `tests/test_ephemerality.py` (PRIV-02/03) | test | integration | `server/app.py:70-77` (main, prior art)'s `_scratch_dir` try/finally shape (the thing being tested against) + `tools/license_gate.py::_offending_distributions` (`tools/license_gate.py:20-33`, `importlib.metadata.distributions()` scan) for the "no queue importable" proof-by-absence | strong for scratch; strong for proof-by-absence |
| `tests/test_privacy_canary.py` (PRIV-04/05) | test | integration (log/event capture) | **`tests/test_outside_contents.py:331-338`** — `caplog.at_level(...)` + `assert not any("X" in m for m in caplog.messages)` is the exact existing shape for a content-canary-in-logs assertion | strong |
| `tests/test_headers.py` (PRIV-06) | test | request-response (HTTP headers) | none — first HTTP-header test in the repo; weak structural echo of `harness/run_corpus_harness.py`'s per-route iterate-and-report loop (`harness/run_corpus_harness.py:189-242`) | no strong analog |
| `tests/test_disclosure.py` (PRIV-01) | test | unit (pure predicate) | generic unit-test shape only (`tests/test_recipe.py`'s frozen/slots tests, `tests/test_recipe.py:106-113`) | weak — business logic is new |
| `tests/test_boxes.py` (EDIT-01) | test | unit / corpus measurement | `tests/test_recipe.py`'s fixture-measurement helpers (e.g. `_liberation_widths`, `tests/test_recipe.py:127-130`) + RESEARCH.md §3.1's own measured derivation (w=40.0, h=0.0 on `irs_form_w4.pdf`) | strong |
| `tests/test_undo.py` (EDIT-05) | test | unit | `tests/test_recipe.py::test_plan_recipe_refuses_a_recipe_carrying_a_duplicate_run_id` (`tests/test_recipe.py:1157`) — the exact duplicate-`run_id` refusal this undo-stack-replace rule must not collide with | strong |
| `tests/test_viewer_api.py` (VIEW-01/02, CLAS-06/07) | test | integration | `engine.index.RunIndex._parse_page`'s own docstring (`engine/index.py:139-143`) — explicitly built as "its own patchable method" so a test can `monkeypatch.setattr` and assert call count | exact |
| `tests/test_cdn.py` (PRIV-06, `cdn` marker) | test | manual / live-deployment | none | no analog |
| `tests/test_edit_e2e.py`, `tests/test_viewer_e2e.py` (e2e or recorded manual, A-4.3) | test | browser e2e | none | **no analog — see below** |

### Tests — extended (existing files, small additions)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_recipe.py` (+ `test_optional_style_key_is_backward_compatible`) | test | unit | itself — `test_parse_recipe_rejects_op_with_extra_key` (`tests/test_recipe.py:76-79`) is the exact contrasting case | exact (self-analog) |
| `tests/test_fonts.py` (+ style→variant routing test) | test | unit | itself + `engine.fonts.BundledVariant`/`lookup_bundled_font` (`engine/fonts.py:62`, `:205`) | exact |
| `tests/test_fit.py` (+ size-change refit/refuse test) | test | unit | itself + `fit_run`'s refusal branch (`engine/fit.py:364-376`) | exact |
| `tests/test_rewrite.py` (+ colour-change preserves matrix test) | test | unit | itself — `test_edit02_matrix_invariant_holds_after_fit` / `test_matrix_guard_fires_on_synthetic_shift` (`tests/test_rewrite.py:693-733`) is the D-04 guard test template to clone | exact |
| `tests/conftest.py` (+ `TestClient` fixture, scratch-root fixture, error-reporter double, fault-injection hook) | test config | fixture provisioning | itself — existing `manifest`/`corpus_dir` session fixtures and `open_doc`/`docs_with_category` helpers (`tests/conftest.py:22-63`) | exact (self-analog for style; content is new) |

### Config / CI

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pyproject.toml` (+ `linux_only`/`e2e`/`cdn` markers, `httpx` dev dep, mypy `files=["engine","server"]`) | config | — | itself — existing `markers` list (`pyproject.toml:25-27`) and `[[tool.mypy.overrides]]` blocks (`pyproject.toml:36-45`) | exact (self-analog) |
| `.github/workflows/tests.yml` (+ explicit canary/hostile-input job step) | CI config | — | itself (`​.github/workflows/tests.yml`, full file, 36 lines) | exact (self-analog) |
| `.gitignore` (+ `client/node_modules/`) | config | — | trivial, no analog needed | n/a |

### Client (`client/src/`)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `client/src/App.jsx` (heavy rewrite: per-page fetch, `TextLayer`, box overlay, thumbnail rail + badges, refusal screen, undo stack, disclosure UI, style toolbar) | component (React) | request-response + client state | `client/src/App.jsx` (main, **prior art, not a pattern** — `apiFetch` helper at lines 15-23 is worth keeping; the canvas-only render loop and the `doFindReplace` stub at lines 126-153 are being replaced, not extended) | prior art only |
| New client modules (component decomposition — Claude's Discretion) | component / hook / store | client state | none beyond the single-file `App.jsx`'s own `apiFetch` (lines 15-23) and canvas-render-loop patterns | **no analog — new territory, see below** |
| `client/vite.config.js` (proxy additions if routes change) | config | — | itself, full file already read | exact (self-analog) |

### Docs / results artifacts

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `CVE-VERIFICATION.md` | doc artifact | — | `G2B-GATE-RESULTS.md` / `PLAYA-DECISION.md` precedent (dated results doc, `## Decision` header, per-check evidence) — named directly in RESEARCH.md §12 | exact (precedent named by research itself) |
| Phase-gate manual-verification doc (G3-4/G3-5 journeys, CDN check) | doc artifact | — | same precedent, `G2B-GATE-RESULTS.md` | exact |

---

## Pattern Assignments

### `engine/boxes.py` (NEW module, EDIT-01's run bounding box)

**Analog:** `engine/recipe.py`'s existing `Tf`-scan helper, plus `engine/rewrite.py`'s bracket
pattern, plus the shape of every other verdict/record type in `engine/`.

This is the single most important new engine module in the phase (RESEARCH.md §3.1: "a run's
width comes out of `GlyphRecord.x`/`advance` correctly... but its height measures 0.0"). Do not
reinvent the `Tf` scan — reuse it:

**Reuse this exact helper for font size** (`engine/recipe.py:189-209`):
```python
_TF_NAME_SIZE_RE = re.compile(rb"/([^\s/\[\](){}<>%]+)\s+([+-]?[0-9.]+)\s+Tf\b")


def _active_font_name_and_size(
    stream_bytes: bytes, byte_offset: int
) -> tuple[bytes, float] | None:
    """The `(resource name, size)` operands of the LAST `Tf` at or before `byte_offset`."""
    try:
        found: re.Match[bytes] | None = None
        for match in _TF_NAME_SIZE_RE.finditer(stream_bytes):
            if match.start() > byte_offset:
                break
            found = match
        if found is None:
            return None
        return found.group(1), float(found.group(2))
    except Exception:  # noqa: BLE001 - classify-never-crash
        return None
```
`engine/rewrite.py:643-662` carries the character-for-character-identical regex with the same
"must select the SAME `Tf` occurrence `classify_run` did" rationale — this is a project
convention (each module re-implements this tiny scan rather than importing a private helper
across a module boundary), not an oversight. `engine/boxes.py` should follow the same convention:
its own copy, or promote the existing one to public — either is consistent with precedent, but a
new fourth private copy with a *different* regex is exactly Pitfall from `engine/rewrite.py:643-661`'s
own comment (two regexes that "merely usually agree" caused a real, corpus-confirmed divergence).

**The two remaining inputs (width is already solved):**
- Width: `GlyphRecord.x` + `advance` (`engine/records.py:19-33`) — already correct per RESEARCH.md
  §3.1's own measurement (40.0pt on a real run).
- Height: RESEARCH.md's own recommendation is option 1 (re-scan `Tf` for size, exactly as above)
  for the scale, and option 3 (a fixed padding multiple of the font size, `# ponytail:`-tagged)
  for ascent/descent — **there is direct precedent for this exact simplification already in the
  test suite**: `tests/test_gate_g2b.py:88-92`:
  ```python
  # Generous fixed padding standing in for real font ascent/descent. ponytail: fixed padding,
  # upgrade to real font-program ascent/descent if a corpus run ever produces a false pass (a
  # mask so large it hides a genuine regression). Same value and same tagged simplification as
  # tests/test_gate_g2a.py's own constant.
  MASK_VERTICAL_PAD_PT = 14.0
  ```
  `engine/boxes.py` should carry the same style of comment, not silently pick a number.

**Dataclass shape convention** (`engine/records.py:36-62`, `engine/fit.py:60-66`,
`engine/classify_run.py:70-78`): every verdict/record type in `engine/` is
`@dataclass(frozen=True, slots=True)` so a construction call missing a field raises `TypeError`
rather than silently defaulting. A new `RunBox` (or similar) type in `engine/boxes.py` should
follow this without exception — it is the one universal convention across every engine module
read for this phase.

**Where it must live:** RESEARCH.md is explicit — "the derivation must live in ONE engine-side
module... so the box the server issues and the box `apply_recipe` reasons about cannot drift."
`engine/boxes.py` is a pure transform over already-parsed `RunRecord`/stream bytes, same role as
`engine/fit.py` — no pikepdf/playa opening of its own, called with data the caller already has.

---

### `engine/recipe.py` (MODIFY — FONT-07's optional `style` key, INGE-02's password threading)

**Analog:** itself. This is the untrusted-input boundary already built to the bar this phase
needs; extend its existing shape rather than building beside it.

**Current `RecipeOp` and the check that must relax** (`engine/recipe.py:81-86`, `:117`):
```python
@dataclass(frozen=True, slots=True)
class RecipeOp:
    """One `{run_id, new_text}` edit op (D-09)."""

    run_id: str
    new_text: str
```
```python
        if not isinstance(item, dict) or set(item) != {"run_id", "new_text"}:
            raise ValueError(
                f"recipe op {i} must be an object with exactly run_id and new_text keys"
            )
```
FONT-07 needs an *optional* third key (a `style` object: colour, weight/style — **size is
refused by name per Amendment A-4.2**, not represented as a settable field at all). The exact-key
check at line 117 must become "these two keys required, this one optional" — `set(item) - {"run_id", "new_text"}` reduced to at most `{"style"}`, checked and validated the same
defensive way the existing two fields are (explicit `isinstance` checks, never trust the shape).
This is a backward-compatible wire extension (old two-key recipes still parse) — RESEARCH.md
§3.3 flags this explicitly as something "the plan should say... rather than let it look like a
violation" of 03-CONTEXT.md's "Phase 4's wire format, unchanged" framing.

**The five-reason refusal vocabulary this module owns** (`engine/recipe.py:137-143`, values
minted at lines 449, 453, 458, 340, 350, 423, 546, 558) is closed and self-testing — see
`tests/test_recipe.py::test_module_own_reasons_matches_the_source` below. A font-size change's
refusal (Amendment A-4.2) should mint a new named reason in this same closed set, following the
identical convention — never invented prose, and the new reason string must be added to both the
module's own docstring list and the test's `MODULE_OWN_REASONS` set (see Testing pattern below).

**Password threading (INGE-02):** `plan_recipe` (`engine/recipe.py:369-468`) and `apply_recipe`
(`engine/recipe.py:562-718`) both call `classify_document` and open their own `pikepdf.Pdf`
handle (`pikepdf.open(path)` at line 443). Both call sites need a `password: str | None`
parameter threaded straight through to `pikepdf.open(path, password=...)` and down into
`classify_document`'s own opens. RESEARCH.md's own constraint: the password must never enter a
`repr()`, log line, or error-reporter frame local — pair this with `server/secrets.py`'s
redacting wrapper type (no analog; new territory, see below) rather than passing a bare `str`
through five call sites.

---

### `engine/index.py` / `engine/classify_run.py` (MODIFY — INGE-02 password threading)

**Analog:** itself, both files. Two open call sites need one new keyword argument each; no
structural change.

`engine/index.py:112-123`:
```python
    def __init__(self, path: str | Path) -> None:
        self._pdf = pikepdf.open(path)
        self._doc: Document = open_document(path)
        # D-10: the same digest `classify_document` embeds...
        self._source_hash = hashlib.sha256(Path(path).read_bytes()).hexdigest()
```
`engine/classify_run.py:316` (`pdf = pikepdf.open(path)`) and `:327`
(`with open_document(path) as doc:`) are the mirror pair inside `classify_document`.

**`open_document` needs no wrapper code written** — `engine/playa_boundary.py:121`:
```python
from playa import open as open_document
```
is a straight re-export (documented at `engine/playa_boundary.py:145-150`: "`open_document` is
`playa.open` under the same rule"). Passing `password=` through to it is calling playa's own
`open()` with an extra kwarg, not writing new adapter logic — confirm playa's signature accepts
`password` (RESEARCH.md treats this as the expected shape but did not quote playa's own
signature) before assuming zero new code here.

---

### `engine/rewrite.py` (MODIFY — FONT-07 colour operator)

**Analog:** itself — the existing `Tf` save/restore bracket is the exact mechanical template.

**The bracket to clone** (`engine/rewrite.py:900-957`, condensed):
```python
    """
    `Tf` is bracketed and restored the identical way `_bracket_for_fit` already brackets
    `Tz`, for the identical reason: `Tf` is a text-state parameter that persists past `BT`
    (D-02), so leaving the substituted run's font in force would silently re-render every
    later run in the text object...
    """
    ...
    tf_new = pikepdf.ContentStreamInstruction(
        [pikepdf.Name(resource_key), font_size], pikepdf.Operator("Tf")
    )
    tf_restore = pikepdf.ContentStreamInstruction(
        [pikepdf.Name("/" + original_name.decode("latin-1")), font_size],
        pikepdf.Operator("Tf"),
    )
    return replacement, [tf_new, tf_restore]
```
A colour change is the same shape: read the currently-active colour operand (via a `rg`/`g`/`k`
backward scan analogous to the `Tf` scan), emit the new colour before the replacement's
text-showing operator, and restore the original after — because colour, like `Tf`, is a graphics-
state parameter that persists past the run. **Caution flagged by RESEARCH.md §3.3**:
`engine/rewrite.py:624` (inside `_operator_shared_with_another_run`'s docstring) notes
`engine/clusterer.py` already "breaks runs on gap, font, size, colour, visibility and per-glyph
verdict" — i.e. colour is already a run-boundary signal to the classifier. Confirm during
planning whether a colour-only edit can reuse the existing `_show_instruction`/bracket dispatch
unchanged, or whether it needs its own bracket function alongside `_bracket_for_fit` (the `Tz`
case, `engine/rewrite.py:602-611`) and the `Tf` case above — this is a three-bracket family
(`Tz`, `Tf`, and now colour), not a one-off.

---

### Isolated worker / `RLIMIT_AS` subprocess boundary (PRIV-07, INGE-04) — NO ANALOG

**Nothing in this repo forks a Python worker process with resource limits and an IPC protocol.**
The closest thing that exists is external-tool subprocess invocation with a wall-clock timeout,
which is a real but partial precedent — worth reading for the `subprocess.run(..., timeout=...)`
+ `except subprocess.TimeoutExpired` idiom, not for the isolation mechanism itself:

`harness/run_corpus_harness.py:170-186`:
```python
def _run_structural_check(args: list[str], pdf_path: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=STRUCTURAL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT after {STRUCTURAL_TIMEOUT_SECONDS}s: {' '.join(args)}"
    except (OSError, FileNotFoundError) as exc:
        return False, f"could not run {args[0]}: {exc}"

    ok = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    detail = output.splitlines()[-1] if output else f"exit {result.returncode}"
    return ok, detail
```
What this does NOT give you: `preexec_fn`/`RLIMIT_AS` setup inside the child, a JSON-over-stdio
request/response protocol, or the macOS-vs-Linux `try/except ValueError` degrade RESEARCH.md §6.1
measured as necessary (`RLIMIT_AS`/`RLIMIT_DATA` unsettable on macOS 15.7.7 arm64; `RLIMIT_CPU`
settable). **This is genuinely new territory — build it, do not search further for an in-repo
precedent.** `tools/license_gate.py`'s plain `main()`/`sys.exit(...)` CLI shape
(`tools/license_gate.py:45-56`) is a reasonable shape for `server/worker.py`'s own
`if __name__ == "__main__":` entry point, but that is the only piece of it with precedent.

---

### Fixture builders (INGE-02/03/04, PRIV-05 canary) — strong analog, exact shape to copy

**Analog:** `tools/build_mixed_fixture.py` (one-off, committed-output builder) for the
password/signed/canary fixtures; `tests/test_outside_contents.py`'s self-reference-after-
construction technique for the cyclic-graph fixtures.

**The one-off builder script shape** (`tools/build_mixed_fixture.py:1-8`, `:110-122`):
```python
"""One-off builder for two synthetic test fixtures the corpus cannot supply.

Run once; its output is committed under tests/fixtures/. Re-running regenerates
byte-identical-in-structure fixtures from the same source pages, so this script
is the audit trail for how they were built.

    uv run --frozen python tools/build_mixed_fixture.py
"""
...
def build_render_mode_7():
    pdf = pikepdf.Pdf.new()
    try:
        page = pdf.add_blank_page(page_size=(612, 792))
        font = pdf.make_indirect(
            Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
        )
        page.Resources = Dictionary(Font=Dictionary(F1=font))
        content = b"BT /F1 24 Tf 100 700 Td 7 Tr (Invisible add-to-clip text) Tj ET"
        page.Contents = pdf.make_stream(content)
        pdf.save(FIXTURES_DIR / "render_mode_7.pdf")
    finally:
        pdf.close()
```
This is the exact shape for the canary-marker PDF (a real text run carrying the canary string,
committed to `tests/fixtures/`) and a reasonable starting point for the password fixture
(RESEARCH.md §5.2 already gives the exact call: `pikepdf.save(..., encryption=pikepdf.Encryption(user="…", owner="…", R=6))`).
**The decompression bomb is the one exception to "committed fixture"** — RESEARCH.md §5.4 is
explicit it must be a *generator* invoked at test time, not a checked-in artifact; keep the
builder-function shape but call it from the test rather than from `tools/`.

**The self-reference-after-construction technique** (`tests/test_outside_contents.py:321-329`):
```python
    pdf = pikepdf.Pdf.new()
    resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    form = _form(pdf, _show(b"X") + b"/Fself Do\n", resources)
    # The self-reference, added after construction because it needs the object to exist.
    form.Resources.XObject = pikepdf.Dictionary(Fself=form)
```
This is the technique to mirror for the cyclic page tree fixture (`/Pages /Kids` pointing at an
ancestor): build the tree normally through pikepdf's high-level API, then patch in the cycle
afterward by direct dictionary assignment, because the high-level API will not let you construct
a cycle in one shot.

---

### Self-referencing Form XObject fixture (INGE-04) — a working implementation to reuse, not just an analog

**This resolves RESEARCH.md's Open Question 1.** The question was whether
`engine/walker.py`/`engine/shared_xobjects.py` already carry a visited set for `Do` recursion, or
whether a self-referencing Form XObject is an engine fix rather than a worker-limit task.
**Measured directly this session: both modules already have it.**

`engine/shared_xobjects.py:58-76` (a per-page cycle guard, keyed on full `objgen`):
```python
# A page's own /Resources -> nested Form /Resources -> nested Form /Resources chain has
# never been observed past depth 2 on the corpus... 64 is a generous bound well under
# Python's default recursion limit, guarding against a pathological or adversarial upload
# without touching any real document.
_MAX_XOBJECT_DEPTH = 64


def _walk(
    resources: pikepdf.Object | None,
    seen: set[int],
    visited: set[tuple[int, int]],
    depth: int,
) -> None:
    """`visited` is a per-page cycle guard keyed on the full `objgen` (id, gen) -- a
    self-referencing Form must not recurse into itself again. `depth` bounds recursion
    independent of cycles, for a chain that is deep but not cyclic.
    """
```
`engine/walker.py:27-45` states the same posture for the content-stream walker itself ("a
visited set built per branch... never a global set").

**And there is already a passing test that exercises exactly this shape**,
`tests/test_outside_contents.py::test_self_referencing_form_xobject_walks_to_completion`
(lines 301-338), which even names the CVE RESEARCH.md's own §12 found mis-attributed
(CVE-2026-48155):
```python
def test_self_referencing_form_xobject_walks_to_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T-02-02 (CVE-2026-48155 shape). A Form XObject that `Do`-invokes itself, on a
    2-page document so the per-BRANCH visited set is exercised rather than a global one.
    ...
    """
    pdf = pikepdf.Pdf.new()
    resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    form = _form(pdf, _show(b"X") + b"/Fself Do\n", resources)
    form.Resources.XObject = pikepdf.Dictionary(Fself=form)
    for _ in range(2):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pdf.make_stream(b"/Fx Do\n")
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fx=form))

    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))

    assert len(records) == 2, "one glyph per page: the cycle is cut, the text is not"
    assert {p.page for p, _r in records} == {0, 1}
    assert all(len(p.xobj_path) == 1 for p, _r in records)
    assert any("cycle guard" in m for m in caplog.messages), "the abort must be logged"
    assert not any("X" in m for m in caplog.messages), "T-02-04: no glyph text in logs"
```
**Planner implication:** `tests/test_hostile_input.py::test_self_referencing_form_xobject_fails_on_own_limits`
does not need an engine fix — it needs to (a) reuse this exact fixture-construction pattern
(possibly via a small shared helper), and (b) verify the *same* safe termination holds through the
full public-facing pipeline (`RunIndex`/`classify_document`/the isolated worker), not just
`walk_document` in isolation. This is one of RESEARCH.md's three acceptable outcomes for
INGE-04 ("(b) the engine detects the cycle... and returns a named refusal without ever hitting the
limit") — already true today. Scope this task much smaller than the other two hostile fixtures.

---

### Testing patterns (canary/log assertion, proof-by-absence, patchable-method, D-04 guard)

**Content-in-logs canary assertion** (directly reusable shape for `tests/test_privacy_canary.py`)
— same file as above, `tests/test_outside_contents.py:331, 337-338`:
```python
    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))
    ...
    assert not any("X" in m for m in caplog.messages), "T-02-04: no glyph text in logs"
```
This is the exact `caplog`-based pattern for PRIV-04/PRIV-05's "no canary substring in logs"
assertion — swap the single-character probe for the high-entropy canary token, and apply on both
the success and crash paths per RESEARCH.md §8.1.

**Proof-by-absence over the installed dependency closure** — `tools/license_gate.py:20-33`:
```python
def _offending_distributions() -> list[tuple[str, str, str]]:
    """Internal: (name, version, matched_field) for every offending distribution."""
    offenders: list[tuple[str, str, str]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        version = dist.metadata.get("Version", "unknown")
        fields_to_check = [dist.metadata.get("License", "") or ""]
        fields_to_check.extend(dist.metadata.get_all("Classifier") or [])
        for field in fields_to_check:
            lowered = field.lower()
            if any(sub in lowered for sub in MATCH_SUBSTRINGS):
                offenders.append((name, version, field))
                break
    return offenders
```
This `importlib.metadata.distributions()` scan is the exact mechanism for PRIV-03/PRIV-05's
"no ARQ/Redis/S3/R2/GCS client is importable or configured" proof-by-absence tests — iterate
installed distribution names (or attempt the specific imports directly) rather than inventing a
new detection mechanism.

**Patchable-method call-count proof** (VIEW-02) — `engine/index.py:139-143`:
```python
    def _parse_page(self, page_index: int) -> PageIndex:
        """The single per-page parse step, factored out as its own patchable method
        (brief ruling 5) so a test can `monkeypatch.setattr` it and assert it runs
        exactly once across two `.page(n)` calls -- the non-vacuous proof that `.page()`
        actually caches rather than re-parsing."""
```
This is already written to be tested exactly the way `tests/test_viewer_api.py::test_page_request_does_not_index_whole_document`
needs — `monkeypatch.setattr(RunIndex, "_parse_page", spy)` and assert call count, no new
engine-side hook required.

**D-04 matrix-guard test template** (for FONT-07's colour-change test) —
`tests/test_rewrite.py:693-733`:
```python
def test_edit02_matrix_invariant_holds_after_fit(monkeypatch: pytest.MonkeyPatch) -> None:
    """EDIT-02/D-04, the positive case: an edit the fit ladder guarantees costs no width
    ... leaves the first glyph after the edited run where it was, and `rewrite_run` reports ok."""
    ...
    outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", _fit_no_width_change())
    assert outcome.ok is True, outcome.reason
    assert outcome.reason is None


def test_matrix_guard_fires_on_synthetic_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    """D-04's negative case -- the one that proves the guard is load-bearing..."""
    ...
    outcome = rewrite_run(pdf, 0, target, _verdict(), runs, "x", _fit_no_width_change())
    assert outcome.ok is False
    assert outcome.reason == "text_matrix_shifted_after_edit"
```
`tests/test_rewrite.py::test_colour_change_preserves_following_text_matrix` should clone this
positive/negative pair exactly, substituting a colour bracket for the width-change trigger.

**Recipe's own self-testing reason vocabulary** — `tests/test_recipe.py:1200-1216`:
```python
def test_module_own_reasons_matches_the_source() -> None:
    """`MODULE_OWN_REASONS` is the fixed set the EDIT-04 test measures against, so it must
    not drift from the module... a newly invented reason would be waved through as
    "already in the allowed set" otherwise."""
    source = Path(recipe_module.__file__).read_text()
    for reason in MODULE_OWN_REASONS:
        assert f'"{reason}"' in source, f"{reason!r} is no longer in engine/recipe.py"

    assigned = set(re.findall(r'reason=\s*"([a-z_]+)"', source))
    assigned |= set(re.findall(r'or\s+"([a-z_]+)"', source))
    assigned |= set(re.findall(r'return\s+"([a-z_]+)"', source))
    assert assigned <= MODULE_OWN_REASONS, (...)
```
Any new refusal reason FONT-07's size-change refusal (Amendment A-4.2) mints in `engine/recipe.py`
must be added to this same `MODULE_OWN_REASONS` set, or this existing test starts failing —
plan for the edit to `tests/test_recipe.py` alongside the edit to `engine/recipe.py`, not after.

---

### `server/app.py` rebuild — what to keep verbatim vs. what is prior art only

Per Amendment A-4.1, four things in the `main`-branch scaffold are correct in shape and should be
kept; everything else in this file is prior art to delete, not a pattern to extend.

**Keep verbatim (shape, not necessarily the literal code):**

Content-addressing, `server/app.py:79-80` (main):
```python
def _content_address(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
```
— already the same digest `RunIndex`/`classify_document` compute for `source_hash`
(`engine/index.py:118`, `hashlib.sha256(Path(path).read_bytes()).hexdigest()`). Pitfall 9 in
RESEARCH.md is explicit: do not let these drift into two identities.

Opaque job IDs, `server/app.py:103-104` (main):
```python
def _new_job_id() -> str:
    return hashlib.sha256(os.urandom(16)).hexdigest()[:16]
```

Scratch try/finally shape, `server/app.py:69-77` (main):
```python
@contextmanager
def _scratch_dir(prefix: str = "job-"):
    d = _ensure_scratch() / f"{prefix}-{os.getpid()}-{hashlib.sha256(os.urandom(8)).hexdigest()[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)
```
— note `SCRATCH_ROOT: Path` at line 50 is a bare annotation with no value (defect #7,
`NameError` outside the ASGI startup event) — keep the try/finally shape, not the module-global
initialization pattern around it.

Status payload shape, `server/app.py:210-230` (main):
```python
            with RunIndex(job["pdf_path"]) as idx:
                page_count = idx.page_count
                classification = []
                for p in range(page_count):
                    page = idx.page(p)
                    ...
                    classification.append({
                        "page": p,
                        "bucket": page.bucket,
                        "runs": len(page.runs),
                        "editable": editable,
                        "substitution": substitution,
                        "not_editable": not_editable,
                    })
```
— the per-page `{page, bucket, runs, editable, substitution, not_editable}` shape is close to
what CLAS-06 needs. **Its defect is eagerness** (`for p in range(page_count): idx.page(p)` before
returning anything, RESEARCH.md §10.2's measured 1441x ratio) — keep the field shape, delete the
eager loop, make it per-page-on-demand.

**Prior art only — do not extend:**
- `server/app.py:167-170` (main) validates by file extension (`filename.lower().endswith(".pdf")`)
  — this is the wrong pattern for INGE-01; the corpus measurement (217/217 files) says the right
  one is `data[:5] == b"%PDF-"`, with no analog in this repo (first magic-byte sniff).
- `server/app.py:201-227` (main) calls `RunIndex(...)` directly inside a sync route handler —
  this is PRIV-07's violation, not a pattern.
- `client/src/App.jsx:126-153` (main) `doFindReplace` — an empty loop over a comment plus a
  fabricated UI message ("the `/jobs/{id}/runs` endpoint needs to be added to the server").
  Nothing here is reusable; it exists only to confirm no client code currently produces a
  `run_id` at all.

**Reference for response rendering** — `tools/pdftool.py:94-111`:
```python
def _print_report(report: "RecipeReport") -> None:
    """D-03's report, printed. Structured data FIRST: one line per op, built entirely
    from that op's OWN `ResolvedOp` fields -- a direct rendering, no recomputation."""
    for resolved in report.resolved:
        line = f"{resolved.op.run_id}  ok={resolved.ok}"
        if resolved.reason is not None:
            line += f"  reason={resolved.reason}"
        ...
```
The `/jobs/{id}/edit` route's JSON response should be this same direct field-by-field rendering
of `RecipeReport`/`ResolvedOp` (FastAPI's `response_model` over the dataclass fields, or a plain
`dict` built the same way) — never a server-side recomputation of `delta_pt`/`strategy`/reasons,
per D-03 and the "Don't Hand-Roll" table in RESEARCH.md.

---

## Shared Patterns

### Refusal vocabulary (EDIT-04) — applies to every controller and test file touching recipe/classification output

**Source:** `engine/recipe.py:137-143` (ResolvedOp docstring, the five owned reasons),
`engine/classify_run.py:70-78` (RunVerdict), `engine/fit.py:364-376` (fit_run's own reason
string), `engine/fonts.py:65-79` (MappingVerdict).
**Apply to:** `server/app.py`'s routes (never rewrite or prettify a reason string in transit —
RESEARCH.md §1.2 is explicit), `client/src/App.jsx`'s refusal rendering (a reason→copy mapping
table with an explicit unknown-reason fallback, never invented prose), every new test asserting a
refusal.
```python
# engine/recipe.py:137-143
"""
`reason` is either one of this module's five small fixed strings
(`"malformed_run_id"`, `"source_hash_mismatch"`, `"run_id_not_found"`,
`"resolution_failed"`, and `"fit_refused"`...) or an UNMODIFIED pass-through
of another module's own named verdict... Never invented prose.
"""
```

### Classify-never-crash

**Source:** `engine/recipe.py:339` (`except Exception:  # noqa: BLE001 - classify-never-crash`),
`engine/recipe.py:199-209` (`_active_font_name_and_size`'s try/except returning `None`).
**Apply to:** `engine/boxes.py` (a box derivation that cannot determine a size should return
`None`/a named refusal, never raise), the isolated worker's per-hostile-input handling (INGE-04),
the signature/password detectors (INGE-02/03) — a detector that raises on a malformed
`/AcroForm` is itself a new crash surface.

### Measure-then-pin, never guess

**Source:** every numeric constant read this session carries a measured provenance comment:
`engine/index.py:73` (`CACHE_GLYPH_BUDGET = 1_900_000`, "02-RESEARCH.md Section 10... 178MB"),
`engine/fonts.py:126-153` (`SEAM_ADVANCE_DELTA_PT = 500.0`, "MEASURED (this task,
2026-08-24...)"), `harness/g2b_fixture.py:73-79` (`PINNED_G2B_DOCUMENTS`, each with a measured
timing comment).
**Apply to:** any new threshold this phase introduces (a request-body size cap on the recipe
route per RESEARCH.md §3.4, a VIEW-02 first-page-ready budget, the `RLIMIT_AS` byte ceiling) —
cite the measurement or mark it `Claude's Discretion, not corpus-measured` explicitly, following
`engine/fit.py:56` (`TZ_FLOOR_PERCENT = 90.0`)'s own honest disclosure of an unmeasured constant.

### Named cap -> named exception (never a bare `Exception`)

**Source:** `engine/index.py:78-84`:
```python
MAX_DOCUMENT_GLYPHS = 10_000_000

class DocumentTooLargeError(Exception):
    """T-02-01: raised once a `RunIndex`'s cumulative walked glyph count exceeds
    `MAX_DOCUMENT_GLYPHS`. Never document content in the message -- counts only."""
```
**Apply to:** the isolated worker's own limits (`server/worker.py`) and any new engine-side cap —
a message carrying counts only, never document content, matching `engine/recipe.py:89-92`'s
identical `RecipeTooLargeError` docstring convention.

### CI workflow shape

**Source:** `.github/workflows/tests.yml` (full file, 36 lines) — `uv sync --locked`, then
`uv run --frozen pytest -q`, then `uv run --frozen mypy engine/`.
**Apply to:** the same file's extension to add an explicit canary/hostile-input step and the
`mypy engine/ server/` target (VALIDATION.md's own per-commit check), and any new workflow the
`linux_only` marker's actual execution needs — this file is the only CI precedent in the repo and
should be extended, not replaced.

---

## No Analog Found

Files/capabilities with no close match in this codebase — build these from RESEARCH.md's own
guidance rather than forcing a bad-fit analog:

| File / Capability | Role | Data Flow | Reason |
|---|---|---|---|
| `server/worker.py` (isolated subprocess entry point, JSON-over-stdio) | worker | event-driven/IPC | No forked/subprocess Python worker exists anywhere in this repo. `harness/run_corpus_harness.py`'s external-tool `subprocess.run(timeout=...)` is the nearest shape (worth reusing for the wall-clock-kill idiom) but is not the same mechanism — no `preexec_fn`/`RLIMIT_AS` setup, no IPC protocol exists to copy. |
| `server/isolation.py` (parent-side spawn + `RLIMIT_AS`/`RLIMIT_CPU` + wall-clock kill, with macOS `try/except ValueError` degrade) | service | subprocess | Same reason; RESEARCH.md §6.1's measured macOS platform difference has no precedent to follow either. |
| `server/errors.py` (injectable error-reporter interface + test double, required before any reporter is initialized at module scope) | service | event-driven | No error-reporter abstraction of any kind exists in this repo today (no Sentry, no `before_send` hook, nothing to extend). |
| `server/secrets.py` (redacting wrapper type for the INGE-02 password) | utility | transform | No `SecretStr`-equivalent type exists anywhere in this codebase. Pydantic (already a transitive dependency via FastAPI) ships `pydantic.SecretStr` — check whether reusing that (rung 5 of the ladder: an already-installed dependency) is preferable to a hand-rolled wrapper before writing new code here. |
| `server/disclosure.py` (PRIV-01's local/server predicate) | utility | transform | This is new product logic (the empty-override-set rule from ARCHITECTURE.md:588), not a pattern this repo has needed before. `engine.classify_run.classify_run`'s "pure function, one of a fixed set of named outcomes" shape is the closest structural echo, not a real analog. |
| CORS + `Cache-Control`/CSP middleware | middleware | request-response | Zero `add_middleware` calls exist in `server/app.py` on `main` (confirmed defect #4) — this is the first HTTP middleware in the project's history, not an extension of anything. |
| `tests/test_headers.py` (HTTP response-header assertions) | test | request-response | First HTTP-response test in the repo. Every existing test exercises `engine/`, `tools/`, or `harness/` functions directly — none drive a FastAPI app through `TestClient` today (confirmed: `httpx` itself is not yet installed on either branch). |
| `tests/test_cdn.py` (live-deployment `cf-cache-status` check) | test | manual/live-deployment | No deployment target is selected anywhere in the planning docs (Open Question 2); this is necessarily a first-of-its-kind manual/recorded check. |
| `tests/test_edit_e2e.py`, `tests/test_viewer_e2e.py` (browser e2e) | test | browser e2e | No e2e browser harness (`@playwright/test`, `pytest-playwright`) exists in either checkout. Per Amendment A-4.3, the controller's ruling is that these become **recorded manual checks** (the `G2B-GATE-RESULTS.md` precedent) rather than automated e2e — treat "no analog" here as confirming that ruling, not as a gap to fill with new test infrastructure. |
| New client component/hook/store files (component decomposition beyond the scaffold) | component/hook/store | client state | `client/src/App.jsx` is a single 692-line file with no decomposition today (one `apiFetch` helper, one canvas render loop, everything else inline in the `App` component). Frontend state management and component boundaries are explicitly Claude's Discretion per 04-CONTEXT.md — there is no existing multi-file React structure in this repo to mirror. |
| Signing library for the INGE-03 genuinely-signed fixture | dependency | file-I/O | `pikepdf` alone does not produce a real `/FT /Sig` `/V` signature dictionary with `/ByteRange`+`/Contents`. No signing library (e.g. `endesive`, `pyhanko`) is present in either `pyproject.toml`. This is a dependency decision for the planner/researcher, not a pattern gap — flagging rather than silently picking one. |

---

## Metadata

**Analog search scope:** `engine/` (all 18 modules), `tools/` (all 8 scripts), `harness/` (all 5
modules), `tests/` (conftest.py + 6 representative test files spanning recipe/rewrite/gate/
outside-contents), `pyproject.toml`, `.github/workflows/tests.yml`; `server/` and `client/src/`
read on the `main` checkout only (read-only, per task boundary — nothing written there).
**Files scanned (read in full or via targeted non-overlapping ranges):** `engine/recipe.py`,
`engine/records.py`, `engine/index.py`, `engine/classify_run.py`, `engine/classify_page.py`,
`engine/fit.py`, `engine/fonts.py`, `engine/rewrite.py` (targeted), `engine/run_id.py`,
`engine/shared_xobjects.py`, `engine/playa_boundary.py` (targeted), `engine/walker.py` (targeted),
`tools/pdftool.py`, `tools/build_mixed_fixture.py`, `tools/probe_corpus.py`,
`tools/license_gate.py`, `harness/g2b_fixture.py`, `harness/run_corpus_harness.py`,
`harness/masked_diff.py`, `tests/conftest.py`, `tests/test_recipe.py` (targeted),
`tests/test_gate_g2b.py` (targeted), `tests/test_rewrite.py` (targeted),
`tests/test_outside_contents.py` (targeted), `pyproject.toml`, `.github/workflows/tests.yml`,
`server/app.py` (main, targeted), `client/src/App.jsx` (main, targeted),
`client/vite.config.js` (main, full).
**Pattern extraction date:** 2026-08-30

**Key finding worth flagging to the planner directly:** the self-referencing Form XObject case
of INGE-04 is very likely already handled correctly at the engine level (`engine/walker.py` and
`engine/shared_xobjects.py` both already carry a per-branch visited-set cycle guard, and
`tests/test_outside_contents.py:301-338` already proves it terminates cleanly with a logged
"cycle guard" message and zero leaked glyph text). This resolves RESEARCH.md's Open Question 1
and means that fixture/task should be scoped as "reuse + verify through the full pipeline," not
"engine fix" — a materially smaller task than the other two INGE-04 fixtures.

## PATTERN MAPPING COMPLETE
