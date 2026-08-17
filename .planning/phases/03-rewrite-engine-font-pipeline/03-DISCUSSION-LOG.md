# Phase 3: Rewrite Engine + Font Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-17
**Phase:** 3-Rewrite Engine + Font Pipeline
**Areas discussed:** Width-fit refusal ladder, Substitution trigger + seam bar, Edit representation / CLI shape, Font embedding at save

---

## Width-fit refusal ladder

### Q1 — Condensing mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Tz horizontal scaling | One operator, uniform, maps directly to a percentage. Cost: Tz persists in the text object until reset, so save/restore must be correct | ✓ |
| Per-glyph TJ kern squeeze | Stays inside the TJ array the spike already proved. Cost: tightening letter-spacing 5–10% is more visible than scaling, and "90–95%" stops mapping to one number | |
| No condensing rung at all | Simplest and most honest, matches the spike's own scope. Cost: contradicts roadmap criterion 5, which would need amending | |

**User's choice:** Tz horizontal scaling
**Notes:** Roadmap criterion 5's "condensed only within 90–95%" language maps onto Tz directly, which is what made it the natural fit.

### Q2 — Ladder position

| Option | Description | Selected |
|--------|-------------|----------|
| Last resort, after both kern rungs | trailing_kern → inter_word → Tz → refuse. Kerning is invisible at these magnitudes, Tz genuinely deforms glyphs | ✓ |
| Before inter-word distribution | Uniform scaling arguably beats uneven word gaps on justified text. Cost: deforms before exhausting a non-deforming option | |
| Only for growth, not shrink | Asymmetric ladder — Tz only when replacement is longer. Cost: harder to reason about and to explain in a refusal message | |

**User's choice:** Last resort, after both kern rungs

### Q3 — Overflow disclosure (EDIT-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Dry-run reports the fit plan | Compute and print rung + Δwidth + refusal reason without writing; separate flag commits. Phase 4 renders the same data | ✓ |
| Always write, print report alongside | Fewer steps. Cost: "disclosed BEFORE commit" becomes disclosed *during* | |
| Report only when past trailing-kern | Less noise on the common case. Cost: user can't distinguish a clean edit from silence | |

**User's choice:** Dry-run reports the fit plan

### Q4 — Post-run text matrix invariant (G2a)

| Option | Description | Selected |
|--------|-------------|----------|
| Assert it, refuse on violation | Re-walk after building the rewrite; refuse with a named reason on mismatch. Runtime guard, not just a test | ✓ |
| Test-only assertion | Cheaper per edit. Cost: a document shape absent from the fixture corpus violates it silently | |
| You decide | Let Claude pick once the re-walk cost is known | |

**User's choice:** Assert it, refuse on violation
**Notes:** Phase 2 measured page parse at ~9–15ms, so the per-edit re-walk is affordable.

---

## Substitution trigger + seam bar

### Q1 — Substitution trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Any missing glyph substitutes the whole run | FONT-06 implemented directly; partial-run seam becomes structurally impossible. Cost: one accented char re-renders a whole line | ✓ |
| Substitute only if the font program lacks the outline | Cost: the embedded program *is* the subset — outlines it doesn't contain can't be recovered, so this collapses into option 1 | |
| Try metric-compatible swap first, else refuse | Most conservative on fidelity. Cost: refuses a lot of genuinely editable text in non-core-font documents | |

**User's choice:** Any missing glyph substitutes the whole run

### Q2 — Unmapped font policy (FONT-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse with a named reason | Honest, matches D-04's posture and EDIT-04, keeps the table the single source of truth | ✓ |
| Fall back by serif/sans classification | Fewer refusals. Cost: exactly the heuristic FONT-01 forbids; descriptor flags lie often | |
| Refuse, but report unmapped fonts as corpus data | Same refusal plus evidence-gathering. Cost: extra plumbing Phase 3 doesn't strictly need | |

**User's choice:** Refuse with a named reason
**Notes:** Option 3's reporting idea was noted as a deferred nice-to-have rather than dropped.

### Q3 — Seam acceptance bar (Risk #4)

| Option | Description | Selected |
|--------|-------------|----------|
| Measured proxy + rendered contact sheet | Advance-delta gate in CI, plus a one-time human look at rendered before/after | ✓ |
| Pure human review, no metric gate | Honest about it being judgment. Cost: nothing catches a later regression | |
| Metric gate only | Fully automated. Cost: identical advances can still look wrong — stroke weight and x-height read as a seam | |

**User's choice:** Measured proxy + rendered contact sheet

### Q4 — Bundled font set

| Option | Description | Selected |
|--------|-------------|----------|
| Liberation trio only, widen on evidence | Metric-compatible with Arial/Times/Courier; smallest surface to validate | ✓ |
| Liberation + Noto Sans/Serif now | Broader Unicode up front. Cost: Noto is not metric-compatible, so every substitution needs the full refit path | |
| Liberation + Noto + DejaVu | Maximum coverage. Cost: widest metric matrix to validate in the phase that gates the project | |

**User's choice:** Liberation trio only, widen on evidence
**Notes:** Surfaced during discussion that no `fonts/` directory exists yet — the Phase 1 spike borrowed `spike/fixtures/LiberationSans-Regular.ttf`.

---

## Edit representation / CLI shape

### Q1 — What an edit is

| Option | Description | Selected |
|--------|-------------|----------|
| JSON recipe file, list of ops | `{run_id, new_text}` entries replayed by `pdftool edit`. Matches run_id.py's own "(original bytes, recipe) → output" model; becomes Phase 4's wire format unchanged | ✓ |
| Single edit via flags | Simplest CLI. Cost: Phase 5 needs batch anyway, and FONT-02's save-time subsetting needs all edits at once | |
| Both: flags as sugar over the recipe | Cost: two entry points and two paths to test, in the phase that gates the project | |

**User's choice:** JSON recipe file, list of ops

### Q2 — Source-hash mismatch

| Option | Description | Selected |
|--------|-------------|----------|
| Hard refuse, whole recipe | A byte offset against different bytes is meaningless. Makes TEXT-03 enforceable rather than aspirational | ✓ |
| Warn and attempt anyway | More forgiving. Cost: `resolve_run_id_offset` returning True isn't proof the offset means the same thing | |
| Refuse, with an explicit override flag | Cost: an escape hatch on the one invariant the addressing model rests on — and Phase 4 inherits it as an API parameter | |

**User's choice:** Hard refuse, whole recipe

### Q3 — Partial failure within a recipe

| Option | Description | Selected |
|--------|-------------|----------|
| All-or-nothing: refuse the whole recipe | Deterministic replay; gives FONT-02's subsetting the final edit set | ✓ |
| Apply what works, report what didn't | Useful for bulk find-and-replace. Cost: output becomes engine-version-dependent, so replay stops being deterministic | |
| All-or-nothing by default, `--partial` opt-in | Cost: pre-commits a design decision Phase 5 should make with its own evidence | |

**User's choice:** All-or-nothing: refuse the whole recipe
**Notes:** `--partial` explicitly captured as a deferred idea for Phase 5 rather than rejected outright.

---

## Font embedding at save

### Q1 — Fate of the original embedded font

| Option | Description | Selected |
|--------|-------------|----------|
| Leave original untouched, add a new font | Criterion 3 satisfied structurally — you can't break what you never touched | ✓ |
| Re-subset the original over the glyph union | Cost: can't supply the new character anyway, so it's re-subsetting for its own sake while incurring the exact risk criterion 3 warns about | |
| Merge: extend original where possible | Cost: mixing outlines from two font programs is how you get glyphs that don't match each other | |

**User's choice:** Leave original untouched, add a new font

### Q2 — Subset granularity (FONT-02)

| Option | Description | Selected |
|--------|-------------|----------|
| One subset per family, glyph union, at save | FONT-02's wording exactly; smallest output; direct beneficiary of all-or-nothing recipe application | ✓ |
| One subset per edited run | Simpler bookkeeping. Cost: near-identical font programs duplicated, and FONT-05 now has many tags per family | |
| One subset per page | Cost: neither smallest nor simplest, and nothing requires page-level font independence | |

**User's choice:** One subset per family, glyph union, at save

### Q3 — Where FONT-04's width assertion binds

| Option | Description | Selected |
|--------|-------------|----------|
| Assert on `/W`, treat `/Widths` as the untouched-original case | New fonts are Type0 with `/W`; originals keep `/Widths` untouched so the `/MissingWidth`-0 failure can't arise there | ✓ |
| Assert on both, regenerate `/Widths` too | Cost: contradicts "leave original untouched" — regenerating widths *is* touching it | |
| You decide | Let Claude resolve once the embedding code exists | |

**User's choice:** Assert on `/W`, treat `/Widths` as the untouched-original case

### Q4 — How G2b is gated

| Option | Description | Selected |
|--------|-------------|----------|
| Automate OTS + qpdf + pixels; record viewer checks as evidence | CI gates what machines can decide; the three viewer opens recorded once, following the PLAYA-DECISION.md / TJ-REFIT-RESULTS.md precedent | ✓ |
| Automate everything possible, skip viewer checks | Cost: drops the check closest to real user experience; three open-source engines agreeing doesn't prove Acrobat is happy | |
| Block the gate on manual viewer verification | Most faithful to the wording. Cost: the project gate can no longer run in CI | |

**User's choice:** Automate OTS + qpdf + pixels; record viewer checks as evidence

---

## Claude's Discretion

- Disposition of the Phase 1 spike modules (`spike/tj_refit_prototype.py`, `spike/playa_decode_probe.py`) — absorb, rewrite, or leave alone
- Where the rewrite engine's module boundary sits within `engine/`, and how it composes with `engine/identity_rewrite.py`
- The exact `Tz` floor within the 90–95% band, and whether `Tz` may stack with inter-word distribution
- Bold/italic variant selection within a mapped family, and what the mapping table keys on
- ToUnicode CMap generation specifics for emitted Type0 fonts

## Deferred Ideas

- `--partial` recipe application — Phase 5 (find-and-replace) has the evidence to decide
- Noto Sans/Serif and DejaVu bundling — until refusal data proves a coverage gap
- Widening the font mapping table from collected unmapped-font evidence
- Recipe format versioning field — matters once Phase 4 sends recipes over a wire
- Fixing the per-part `/Tf` scoping limit in `engine/classify_run.py` — inherited from Phase 2's verification, not in Phase 3's requirement list
