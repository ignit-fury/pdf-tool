# TJ-Refit Prototype: Measured Results

**Phase:** 01-conformance-harness-engine-spike, Plan 06
**Requirement retired:** ENG-05 (Risk #5, research/SUMMARY.md)
**Question answered:** Can replacement text be fitted into an original text run's advance width
within `|Δwidth| < 0.5pt`, using the TJ kern-absorption strategy, in both the shorter- and
longer-replacement directions?

**Answer: Yes**, for deltas within roughly one space-glyph width, using a single trailing TJ
kern number. The 0.5pt target was hit with room to spare — both hand-picked runs landed at
`Δwidth ≈ 0.0000pt` (floating-point-exact), not merely under threshold.

---

## The hand-picked run

Real document: `spike/fixtures/tj_refit_sample.pdf` — IRS Form W-9 (Rev. March 2024), U.S.
Government Work, public domain, fetched directly from `irs.gov`.

| Field | Value |
|---|---|
| Page | 0 |
| Font resource | `/T1_2` — `MCXSQA+ITCFranklinGothicStd-Demi` (Type1, subset, `/WinAnsiEncoding`) |
| Font size | 14pt (via `Tm [14 0 0 14 ...]`, `Tf` itself is `1`) |
| Original run text | `"Request for Taxpayer "` (21 chars) |
| Original advance | **137.76pt** — computed from the PDF's own `/Widths` array (the font
  *dictionary*, not the embedded font program's metrics — see Pitfall 5: the two are allowed to
  disagree and the dictionary is what viewers actually use) |

Replacement text is shaped against `spike/fixtures/LiberationSans-Regular.ttf` (SIL OFL 1.1),
the font family this project has already committed to bundling (`PROJECT.md`), simulating the
bundled-font-substitution path — Pitfall 4's *default* case, not the optimization.

## Measured Δwidth, both directions

| Direction | Replacement text | Chars | Shaped advance (unfit) | Δwidth before fit | Strategy | Δwidth after fit | Pass (< 0.5pt)? |
|---|---|---|---|---|---|---|---|
| Shorter | `"Request Payer Tax ID"` | 20 | 135.919pt | −1.841pt | `trailing_kern` (kern = −131.50) | **0.0000pt** | **PASS** |
| Longer | `"Ask for Taxpayer Data "` | 22 | 141.360pt | +3.600pt | `trailing_kern` (kern = +257.17) | **0.0000pt** | **PASS** |

Both pre-fit deltas fall inside the trailing-kern absorption range (one space-glyph width at
this font/size ≈ 3.89pt), so priority 1 of the absorption strategy (Pitfall 5's ordered list)
handles both directions with a single kern number, applied at the end of the run. Because a
single TJ kern makes the fit numerically exact (not merely "close enough"), the residual delta
in both cases is 0.0000pt to four decimal places — floating-point noise, not measurement error.

## Sign convention, proven directly

A TJ array number `K` is subtracted from the advance, in thousandths of text space, scaled by
font size: `displacement_pt = -(K / 1000) * font_size_pt`. At 14pt: `K = 50` → `−0.7pt`
(tightens); `K = −50` → `+0.7pt` (widens). `test_sign_convention_positive_kern_tightens_advance`
asserts both directions directly against the formula and against `total_advance_with_kerns`.
Getting this backwards would have doubled the error instead of cancelling it — this was checked
before trusting any other number in this document.

## Beyond the required two cases (exercised, not required by ENG-05)

The priority-2 (inter-word kern distribution) and priority-5 (honest refusal) branches of the
absorption strategy were also exercised, to confirm the algorithm degrades correctly rather than
guessing when a single trailing kern is not the natural fit:

| Case | Replacement text | Δwidth before fit | Strategy | Result |
|---|---|---|---|---|
| Larger delta, still absorbable | `"Request for Taxpayer Info "` | +26.19pt | `inter_word_kern` (4 gaps, ~+467.6 each) | Δwidth after fit = 0.0000pt |
| Delta too large to absorb honestly | `"X"` | −128.42pt | `refused` | `FitResult.refused = True`, reason string names the exceeded bound |

The refusal path matters as much as the fitting path: per phase_critical_constraint #5, a
confident wrong fit is the failure mode this prototype exists to catch, and `fit_run` returns a
clearly-flagged refusal (`refused=True`, `refusal_reason` set, `strategy == "refused"`) rather
than emitting a kern number that would produce a visually wrong result.

## What this prototype does NOT prove (explicitly out of scope)

- `Tz` (horizontal scale) absorption — priority 3 of Pitfall 5's ladder.
- The "refuse if the run must grow and content follows on the same baseline" rule.
- Type0/CID width lookup (`/W`, `/DW`) — `read_original_advance_pt` raises `NotImplementedError`
  if pointed at a Type0 font rather than silently reusing the `/Widths`-based path (Pitfall 3).
- Byte-level content-stream rewriting (writing the fitted kern back into the PDF). This
  prototype computes the fit; Phase 3 builds the rewrite engine on top of it.

These are the real Phase 3 rewrite engine's job. This spike answers exactly one question —
whether the fitting math and sign convention are correct — and stops there deliberately.

---

## Reusable for Phase 3

Per `.planning/phases/01-conformance-harness-engine-spike/01-CONTEXT.md`'s "Claude's Discretion"
note (Spike code disposition): `spike/tj_refit_prototype.py` itself is throwaway spike code,
judged only on whether it answered the question above. It is **not** what Phase 3 should import
or extend. The following three artifacts ARE carried forward as Phase 3's seed acceptance
fixtures and should be read directly rather than re-derived:

1. **`tests/test_tj_refit_prototype.py`** — the two required shorter/longer fit assertions, the
   sign-convention assertion, and the bonus inter-word-kern and refusal-path assertions. Phase 3
   should port these test *cases* (same fixture text, same expected deltas) onto the real
   rewrite engine's fitting function, not re-invent them.
2. **`spike/fixtures/tj_refit_sample.pdf`** — the real, hand-verified IRS Form W-9 document and
   the exact run (`page 0`, `/T1_2`, `"Request for Taxpayer "` @ 14pt) whose original advance
   (137.76pt) is now a known-good baseline number.
3. **This file (`TJ-REFIT-RESULTS.md`)** — the measured numbers above. Phase 3 planning should
   cite these Δwidth figures rather than re-measuring the same run from scratch.

`spike/fixtures/LiberationSans-Regular.ttf` (+ its `LiberationSans-OFL-LICENSE.txt`) is a
genuine early instance of the bundled-font asset Phase 4 will need regardless — reasonable to
keep, not required to.
