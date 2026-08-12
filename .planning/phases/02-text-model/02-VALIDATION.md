---
phase: 2
slug: text-model
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> **Full detail lives in `02-RESEARCH.md` under `# Validation Architecture`** (§Test Framework,
> §Phase Requirements → Test Map, §Sampling rate, §Every check and the deliberate mutation that
> turns it red, §Wave 0 gaps). This file is the contract; that section is the reference. Do not
> duplicate the tables — read them there.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 9.1.1 (dev group) |
| **Config file** | **none** — no `pytest.ini`, no `[tool.pytest.ini_options]`, no `conftest.py`. **Wave 0 installs.** |
| **Quick run command** | `uv run --frozen pytest tests/ -x -q` |
| **Full suite command** | `uv run --frozen pytest tests/ -q && uv run --frozen mypy engine/ && uv run --frozen python tools/probe_corpus.py corpus/manifest.json corpus/public` |
| **Estimated runtime** | ~20 s unit; full corpus integration measured at ~21 s for a 126-page parse |
| **Type checker** | `mypy` **not installed**. TEXT-05 is unverifiable without it. **Wave 0.** |
| **CI status** | `.github/workflows/tests.yml` added 2026-08-13 and now runs the suite. Previously **no workflow ran pytest** — 37 tests existed and never executed in CI. |

---

## Sampling Rate

- **After every task commit:** `uv run --frozen pytest tests/ -x -q`
- **After every plan wave:** full suite command above
- **Before `/gsd:verify-work`:** full suite green, and every mutation in §"Every check…" demonstrated
- **Max feedback latency:** ~20 s for the unit path

---

## The rule this phase is built around

**A check is not trusted until it has been demonstrated failing.**

This is not process decoration. Phase 1 shipped **five** checks that reported green while measuring
the wrong thing:

1. A decision-coverage gate that passed `0/0` on a CONTEXT.md containing four decisions
2. A producer cap keyed on a string that split one product into two buckets, reporting ~14% each
   while the real producer sat at 28.8%
3. A corpus label asserting a font class (`subset_fonts`) the document did not contain
4. A second wrong label on the *same* document (`vector_outlined_text` on an OCR'd scan), which the
   prober could not catch because that category sits in `UNVERIFIED_CATEGORIES`
5. `validate_manifest` reporting "all 15 categories represented" while one category had no genuine
   fixture at all

Every check in this phase therefore names the deliberate mutation that must produce RED. See
`02-RESEARCH.md` §"Every check, and the deliberate mutation that turns it red" for the full table.

**Three of those mutations carry specific warnings and must not be softened:**

- **TEXT-04 branch coverage** must additionally assert `branches_fired_count > 0` and
  `distinct_branches_fired >= 8`. Without those it passes vacuously on an empty font set — failure
  mode 1 above, exactly.
- **D-04 refusal rate** must be bounded **two-sided** (e.g. `1% ≤ rate ≤ 5%`). An upper bound alone
  stays green if the decision table stops refusing anything at all.
- **CLAS-02 `Tr 7`** — the render-mode mutation does **not** go red on this corpus, because no
  `Tr 7` glyph exists in it. The check therefore cannot detect a `Tr 7` bug and **must not claim
  to**. Either add a synthetic fixture or state the limitation in the test.

---

## Blocking: CLAS-03 has no fixture

`vector_outlined_text` has **zero** documents. The only file that claimed it —
`nasa_graphics_standards_manual.pdf` — is an OCR'd scan (`/Producer` = Acrobat Paper Capture
Plug-in, `/Creator` = Canon DR-7550C TWAIN, every glyph render mode 3 over page images, no visible
text) and was relabelled `ocr_scan` on 2026-08-13.

Consequences, all current:

- `tools/probe_corpus.py` exits 1 (zero-count category)
- `corpus/validate_manifest.py` exits 1
- Two tests fail; CI is **legitimately red**
- **CLAS-03 and Gate G1 criterion 3 are untestable**

**Do not silence this.** Writing the CLAS-03 test against the NASA file would encode the mislabel
into the test suite — failure mode 3 above, repeated deliberately. Sourcing a genuine
vector-outlined fixture is a **Wave 0 blocker**.

---

## Wave 0 gaps (must be scheduled before interpreter work)

| Gap | Why it blocks |
|---|---|
| No `conftest.py` / pytest config | No shared fixtures; corpus paths re-derived per test file |
| `mypy` not installed | TEXT-05 (`Code→Glyph` vs `Code→str` distinct types) is unverifiable without a type checker |
| No vector-outlined fixture | CLAS-03 and Gate G1 criterion 3 untestable; CI red until resolved |
| No `Tr 7` fixture | CLAS-02's visibility check cannot detect a `Tr 7` bug |
| No constructed CLAS-05 mixed fixture | The "40-page document, 3 scanned pages → 37 editable / 40 page-op-able" criterion has nothing to assert against |
| TT-d / TT-e refusal counts unmeasured | D-04's headline refusal number is unsized; ~30-line `fontTools` cmap probe closes it |

---

## Per-Task Verification Map

Populated by the planner from `02-RESEARCH.md` §"Phase Requirements → Test Map", which already maps
every one of TEXT-01..TEXT-08 and CLAS-01..CLAS-05 to a named test file, test function, and
automated command, with an `Exists?` column marking Wave 0 items.

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Exists | Status |
|---------|------|------|-------------|-----------|-------------------|--------|--------|
| *(planner fills from RESEARCH.md §Phase Requirements → Test Map)* | | | | | | | |

---

*Derived from `02-RESEARCH.md` §Validation Architecture, 2026-08-13.*
