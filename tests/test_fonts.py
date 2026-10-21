"""D-06/D-07/FONT-01: the static bundled-font mapping table, exact-match only.

Proves `lookup_bundled_font` never falls back to case-insensitive or substring matching
(the table's whole reason for existing per D-06 -- a font with no entry refuses BY NAME,
never a guess), that the 12 Base-14 non-symbol names all resolve to the correct Liberation
family/variant, and reports a real corpus-measured mapped/refused coverage number
(Pitfall 10) as a pinned lower bound -- not the approximate ~660+ figure from
03-RESEARCH.md, but the actual count this repo's own corpus produces.
"""

from __future__ import annotations

import io
import re
import subprocess
from hashlib import md5
from pathlib import Path
from unittest.mock import patch

import pikepdf
import pytest
from fontTools.subset import Subsetter
from fontTools.ttLib import TTFont

from engine.encoding_table import (
    FontProgram,
    FontVerdict,
    embedded_font_bytes,
    encoding_map,
    resolve_font,
)
from engine.fonts import (
    NOTDEF_GLYPH_NAME,
    SEAM_ADVANCE_DELTA_PT,
    BundledFamily,
    BundledVariant,
    SubstitutionTrigger,
    build_cid_font_descriptor,
    SubsetFont,
    build_tounicode_cmap_bytes,
    build_w_array,
    embed_type0_font,
    has_unmapped_glyph,
    liberation_advance_1000u,
    liberation_font_path,
    lookup_bundled_font,
    reverse_encoding_map,
    run_needs_substitution,
    shape_cids,
    shape_glyph_names,
    subset_cid_widths,
    subset_font_for_family,
)

REPO_ROOT = Path(__file__).parent.parent

# The Private Use Area codepoint used by the D-05/Pattern 4 negative-case tests below,
# built via `chr()` rather than a literal escape so this source file itself carries no
# non-ASCII bytes (the acceptance criterion this task pins is about `.reason` strings and
# test assertions alike never containing the literal decoded character).
PUA_CHAR = chr(0xE000)

# U+4E2D, a CJK ideograph -- a REAL character from a real script that no bundled Liberation
# face has a glyph for (D-07 bundles Latin/Greek/Cyrillic coverage only), deliberately not
# the Private Use codepoint above, which could be dismissed as a synthetic case. Same
# `chr()` construction and same reason: this source file carries no non-ASCII bytes.
NO_GLYPH_CHAR = chr(0x4E2D)

# The full bundled set (D-07), as (family, variant) pairs.
BUNDLED_FACES: list[tuple[BundledFamily, BundledVariant]] = [
    (family, variant)
    for family in ("Sans", "Serif", "Mono")
    for variant in ("Regular", "Bold", "Italic", "BoldItalic")
]


def test_mapping_table_is_exact_match_no_fuzzy_logic() -> None:
    """D-06: no case-insensitive matching, no substring matching, Symbol/ZapfDingbats
    correctly refuse (no Liberation equivalent, per Pitfall 10 -- not a coverage gap), and
    an unmapped long-tail name refuses by name, never a generic message."""
    # Case sensitivity: the exact-cased entry maps, the lowercased spelling does not.
    exact = lookup_bundled_font("Helvetica-BoldOblique")
    assert exact.mapped is True
    assert exact.family == "Sans"
    assert exact.variant == "BoldItalic"

    lowercased = lookup_bundled_font("helvetica")
    assert lowercased.mapped is False

    # Substring matching: a name that merely contains a known entry must not match.
    substring = lookup_bundled_font("MyHelveticaClone")
    assert substring.mapped is False

    # Symbol/ZapfDingbats: deliberately absent, correctly refused, not a coverage gap.
    symbol = lookup_bundled_font("Symbol")
    assert symbol.mapped is False
    assert symbol.family is None
    assert symbol.variant is None

    zapf = lookup_bundled_font("ZapfDingbats")
    assert zapf.mapped is False

    # Long-tail unmapped name: refuses, and the reason names the BaseFont, not a generic
    # message.
    garamond = lookup_bundled_font("AGaramond-Regular")
    assert garamond.mapped is False
    assert garamond.reason is not None
    assert "AGaramond-Regular" in garamond.reason


def test_base14_non_symbol_names_all_map_to_liberation() -> None:
    """The 12 Base-14 non-symbol names (Helvetica/Times/Courier families x
    regular/bold/italic/bolditalic) all resolve to their correct Liberation
    family/variant."""
    expected: dict[str, tuple[str, str]] = {
        "Helvetica": ("Sans", "Regular"),
        "Helvetica-Bold": ("Sans", "Bold"),
        "Helvetica-Oblique": ("Sans", "Italic"),
        "Helvetica-BoldOblique": ("Sans", "BoldItalic"),
        "Times-Roman": ("Serif", "Regular"),
        "Times-Bold": ("Serif", "Bold"),
        "Times-Italic": ("Serif", "Italic"),
        "Times-BoldItalic": ("Serif", "BoldItalic"),
        "Courier": ("Mono", "Regular"),
        "Courier-Bold": ("Mono", "Bold"),
        "Courier-Oblique": ("Mono", "Italic"),
        "Courier-BoldOblique": ("Mono", "BoldItalic"),
    }
    for base_font_name, (family, variant) in expected.items():
        verdict = lookup_bundled_font(base_font_name)
        assert verdict.mapped is True, base_font_name
        assert verdict.family == family, base_font_name
        assert verdict.variant == variant, base_font_name


def test_liberation_font_path_shape() -> None:
    """`liberation_font_path` builds the D-07 `fonts/Liberation{family}-{variant}.ttf`
    path, without touching the filesystem (bundling the actual .ttf files is a later
    task's concern, not this lookup helper's)."""
    from engine.fonts import liberation_font_path

    path = liberation_font_path("Sans", "BoldItalic")
    assert path.parts[-2:] == ("fonts", "LiberationSans-BoldItalic.ttf")


# --------------------------------------------------------------------------------------
# FONT-06 edit-time glyph-availability check (D-05, 03-RESEARCH.md Pattern 4)
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def editable_original() -> tuple[pikepdf.Object, FontVerdict, FontProgram | None]:
    """The shared editable_original fixture, built once and reused across the tests below:
    a synthetic simple TrueType font dict, `/Encoding /WinAnsiEncoding`, whose
    `/FontDescriptor`'s `/FontFile2` stream holds the REAL
    `spike/fixtures/LiberationSans-Regular.ttf` bytes. Non-symbolic, so `resolve_font`
    lands on `FontVerdict("TT-a", editable=True, substitution=False)` -- the
    editable_original shape the brief's negative case needs its contrast against."""
    pdf = pikepdf.Pdf.new()
    ttf_bytes = (REPO_ROOT / "spike" / "fixtures" / "LiberationSans-Regular.ttf").read_bytes()
    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/Flags": 32,  # non-symbolic
                "/FontFile2": pdf.make_stream(ttf_bytes),
            }
        )
    )
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
                "/FontDescriptor": descriptor,
            }
        )
    )
    verdict = resolve_font(font)
    program = embedded_font_bytes(font.get("/FontDescriptor"))
    return font, verdict, program


def _type0_editable_original() -> tuple[pikepdf.Object, FontVerdict]:
    """A synthetic Type0/CIDFontType2 font dict, reusing 03-03-PLAN.md's own established
    in-memory `pikepdf.Dictionary`/`pikepdf.Array` construction style for this same font
    shape (`/Encoding /Identity-H`, one `/DescendantFonts` entry, `/Subtype
    /CIDFontType2`, `/CIDToGIDMap /Identity`) -- the well-formed embedded-CID shape that
    resolves to branch `C-3a`, `editable=True, substitution=False`."""
    pdf = pikepdf.Pdf.new()
    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/Flags": 4,
                "/FontFile2": pdf.make_stream(b"dummy-truetype-program"),
            }
        )
    )
    descendant = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/CIDFontType2"),
                "/DW": 1000,
                "/CIDToGIDMap": pikepdf.Name("/Identity"),
                "/FontDescriptor": descriptor,
            }
        )
    )
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/Type0"),
                "/Encoding": pikepdf.Name("/Identity-H"),
                "/DescendantFonts": pikepdf.Array([descendant]),
            }
        )
    )
    return font, resolve_font(font)


def test_reverse_encoding_map_inverts_encoding_map() -> None:
    """Direct unit test of `reverse_encoding_map` against the WinAnsi fixture."""
    pdf = pikepdf.Pdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/Encoding": pikepdf.Name("/WinAnsiEncoding"),
            }
        )
    )
    reverse = reverse_encoding_map(font)
    assert reverse["A"] == 65
    assert reverse["space"] == 32


def test_editable_original_run_still_substitutes_on_missing_glyph(
    editable_original: tuple[pikepdf.Object, FontVerdict, FontProgram | None],
) -> None:
    """The negative case: U+E000 (Private Use Area) has no Adobe Glyph List name at all,
    so check 1a fires and the run substitutes -- even though `font_verdict.substitution`
    on this SAME font_verdict is False, proving this trigger is independent of Phase 2's
    existing flag, not merely consistent with it."""
    font, verdict, program = editable_original
    assert verdict.editable is True
    assert verdict.substitution is False  # editable_original, not editable_substitution

    result = run_needs_substitution(font, verdict, program, PUA_CHAR)

    assert result.substitute is True
    assert verdict.substitution is False


def test_run_needs_substitution_check_two_fires_when_program_is_none(
    editable_original: tuple[pikepdf.Object, FontVerdict, FontProgram | None],
) -> None:
    """`program=None` -- `glyph_presence` always downgrades to `(True, True)` when
    `program_bytes` is falsy, even though "A" has a valid WinAnsi code -- proves check 2's
    wiring is independent of check 1."""
    font, verdict, _program = editable_original
    result = run_needs_substitution(font, verdict, None, "A")
    assert result.substitute is True


def test_run_needs_substitution_returns_false_when_every_character_available(
    editable_original: tuple[pikepdf.Object, FontVerdict, FontProgram | None],
) -> None:
    """Plain ASCII against the real embedded LiberationSans-Regular.ttf, which covers
    basic Latin: no trigger fires."""
    font, verdict, program = editable_original
    result = run_needs_substitution(font, verdict, program, "cafe")
    assert isinstance(result, SubstitutionTrigger)
    assert result.substitute is False
    assert result.reason is None


def test_substitution_trigger_reason_omits_decoded_character(
    editable_original: tuple[pikepdf.Object, FontVerdict, FontProgram | None],
) -> None:
    """The `.reason` string names the codepoint in `U+XXXX` hex form only -- never the
    decoded character itself."""
    font, verdict, program = editable_original
    result = run_needs_substitution(font, verdict, program, PUA_CHAR)
    assert result.reason is not None
    assert "U+E000" in result.reason
    assert PUA_CHAR not in result.reason


def _tiny_glyph_order_ttf_bytes() -> bytes:
    """`LiberationSans-Regular.ttf` subsetted down to just `.notdef` -- fontTools'
    `Subsetter` with an empty glyph request keeps only the mandatory `.notdef`, so no
    real named glyph (in particular no `A`) survives. Used by the test below to prove
    check 2 does a genuine glyph-NAME lookup, not a bare bounds check (task-review
    AMENDED 2026-08-24 finding)."""
    ttf_path = REPO_ROOT / "spike" / "fixtures" / "LiberationSans-Regular.ttf"
    font = TTFont(str(ttf_path))
    subsetter = Subsetter()
    subsetter.populate(glyphs=[])
    subsetter.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def test_check_two_uses_glyph_name_not_encoding_code_for_lookup() -> None:
    """AMENDED 2026-08-24 (task-review finding): check 2 must look up the glyph by NAME
    (`glyph_name`), never by the raw `/Encoding` byte code (`code`). Built here: a font
    whose `/Differences` maps code 0 to glyph name `/A` (so `reverse_encoding_map(font)
    ["A"] == 0` -- the lowest code wins over WinAnsi's own code-65 `"A"` entry), paired
    with an embedded program subsetted down to glyph order `['.notdef']` (length 1, no
    real `A` glyph). Under the OLD int-code bug, `glyph_presence(verdict, 0, program)`
    would bounds-check `0 <= 0 < 1` -- trivially True -- and wrongly report the glyph
    present. The fixed string-based lookup checks `"A" in ['.notdef']`, correctly False,
    so the run correctly substitutes."""
    pdf = pikepdf.Pdf.new()
    tiny_ttf = _tiny_glyph_order_ttf_bytes()
    descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/Flags": 32,  # non-symbolic
                "/FontFile2": pdf.make_stream(tiny_ttf),
            }
        )
    )
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/Encoding": pikepdf.Dictionary(
                    {
                        "/BaseEncoding": pikepdf.Name("/WinAnsiEncoding"),
                        "/Differences": pikepdf.Array([0, pikepdf.Name("/A")]),
                    }
                ),
                "/FontDescriptor": descriptor,
            }
        )
    )
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-a"
    assert verdict.editable is True

    reverse = reverse_encoding_map(font)
    assert reverse["A"] == 0  # lowest code wins over WinAnsi's own code-65 "A" entry

    program = embedded_font_bytes(font.get("/FontDescriptor"))
    result = run_needs_substitution(font, verdict, program, "A")
    assert result.substitute is True


def test_type0_cid_font_always_substitutes_without_reverse_map_lookup() -> None:
    """AMENDED (plan-checker finding, Seam-7): a Type0/CIDFontType2 font always
    substitutes, and never calls `reverse_encoding_map` at all -- proving the early return
    actually short-circuits rather than merely happening to produce the right answer
    downstream of a still-wrong lookup. Plain ASCII ("cafe") is deliberately the input: it
    is the exact shape that would WRONGLY return `substitute=False` under the
    pre-amendment code, since ASCII collides with StandardEncoding's fallback codes."""
    font, verdict = _type0_editable_original()
    # Precondition, asserted explicitly: fails loudly if resolve_font's Type0 dispatch
    # ever changes rather than silently testing the wrong branch.
    assert verdict.branch_id in ("C-3a", "C-3b"), verdict.branch_id
    assert verdict.editable is True
    assert verdict.substitution is False

    with patch("engine.fonts.reverse_encoding_map") as mock_reverse:
        result = run_needs_substitution(font, verdict, None, "cafe")

    assert result.substitute is True
    mock_reverse.assert_not_called()


@pytest.mark.corpus
def test_corpus_substitution_coverage_report(manifest: list, corpus_dir) -> None:  # type: ignore[type-arg]
    """Pitfall 10's corpus-wide coverage measurement: every font resource across every
    page, resolved through `resolve_font` (Phase 2's existing forward-encoding table) and
    filtered to `editable=True, substitution=True` (Pitfall 10's own filter -- these are
    exactly the fonts whose text would be substituted into a bundled face), tallied by
    `lookup_bundled_font` into mapped vs refused BaseFont occurrences.

    The lower bound below is NOT 03-RESEARCH.md's approximate "~660+" figure -- it is the
    literal count this repo's own corpus produced when this test was written (measured via
    a throwaway scan script, same idiom as this test). Pinning the real number, not the
    approximation, makes a future regression in either the table or `resolve_font` visible
    immediately rather than hiding under a loose bound.
    """
    mapped_count = 0
    refused_count = 0
    mapped_by_name: dict[str, int] = {}
    refused_by_name: dict[str, int] = {}
    # A font OBJECT can be referenced from every page's /Resources in a large document
    # (measured: one ZapfDingbats object in a 2026-page corpus document is referenced
    # from all 2026 pages) -- tallying per page-encounter would count that single font
    # usage thousands of times over and inflate the coverage number far past the real
    # signal. Dedupe by (document, font object identity) first, matching
    # `test_type1_fontfile_corpus_wide_parse_rate`'s own established convention for this
    # same "distinct usage, not page-repetition" question.
    seen: set[tuple[str, tuple[int, int]]] = set()

    for entry in manifest:
        path = corpus_dir / entry["filename"]
        if not path.exists():
            continue
        try:
            pdf = pikepdf.open(path)
        except Exception:  # noqa: BLE001 - encrypted/broken files are not this test's subject
            continue
        try:
            for page in pdf.pages:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                fonts = resources.get("/Font")
                if fonts is None:
                    continue
                for _key, font in fonts.items():
                    identity = (entry["filename"], font.objgen)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    try:
                        verdict = resolve_font(font)
                    except Exception:  # noqa: BLE001 - unresolvable fonts aren't this test's subject
                        continue
                    if not (verdict.editable and verdict.substitution):
                        continue
                    # `/BaseFont` read directly off the font dict -- `_base_font_name` is
                    # private to encoding_table.py and not imported here. Only the leading
                    # "/" pikepdf.Name stringification adds is stripped; these substitution-
                    # path fonts are non-embedded Base-14/long-tail names, never subset-tagged.
                    base_font_name = str(font.get("/BaseFont", "")).lstrip("/")
                    result = lookup_bundled_font(base_font_name)
                    if result.mapped:
                        mapped_count += 1
                        mapped_by_name[base_font_name] = mapped_by_name.get(base_font_name, 0) + 1
                    else:
                        refused_count += 1
                        refused_by_name[base_font_name] = (
                            refused_by_name.get(base_font_name, 0) + 1
                        )
        except Exception:  # noqa: BLE001
            pass
        finally:
            pdf.close()

    print(
        f"\nmapped: {mapped_count} distinct (document, font-object) usages "
        f"across {len(mapped_by_name)} distinct BaseFont names"
    )
    for name, count in sorted(mapped_by_name.items(), key=lambda kv: -kv[1]):
        print(f"  mapped {name!r}: {count}")
    print(
        f"refused: {refused_count} distinct (document, font-object) usages "
        f"across {len(refused_by_name)} distinct BaseFont names"
    )
    for name, count in sorted(refused_by_name.items(), key=lambda kv: -kv[1]):
        print(f"  refused {name!r}: {count}")

    # Pinned lower bound: the literal count measured on this repo's corpus (2026-08-24)
    # after (document, font-object) dedup -- within 7% of Pitfall 10's ~660+ estimate,
    # confirming this is the real signal (the prior, since-fixed pin at 2273 counted raw
    # per-page occurrences and was inflated ~3.7x by large documents whose single shared
    # font object is referenced from every page).
    assert mapped_count >= 618, f"expected at least 618 mapped usages, got {mapped_count}"


# --------------------------------------------------------------------------------------
# D-08 seam-quality machine metric / RESEARCH.md Open Question 2 / D-07 verification
# --------------------------------------------------------------------------------------


def test_liberation_advance_1000u_scales_by_units_per_em() -> None:
    """Direct unit test, independent of the corpus: LiberationSans-Regular.ttf's own
    `hmtx` advance for glyph `A`, scaled to 1000-units-per-em, matches the exact value
    computed by hand from the font's own `hmtx`/`head` tables. Also proves the `None`
    contract for a glyph name absent from the font's glyph set, never a `KeyError`."""
    font = TTFont(str(REPO_ROOT / "fonts" / "LiberationSans-Regular.ttf"))
    expected = font["hmtx"]["A"][0] * 1000.0 / font["head"].unitsPerEm

    result = liberation_advance_1000u("Sans", "Regular", "A")

    assert isinstance(result, float)
    assert result == pytest.approx(expected)

    assert liberation_advance_1000u("Sans", "Regular", "nonexistent_glyph_name") is None


class _MalformedWidthsArrayError(ValueError):
    """Raised by `_read_widths_1000u` for a `/Widths` array shorter than its own declared
    `/FirstChar`..`/LastChar` range -- a named exception, never an uncaught `IndexError`,
    matching `engine.fit.read_original_advance_pt`'s established bounds-checking posture
    for this exact same untrusted-array shape."""


def _read_widths_1000u(font: pikepdf.Object) -> dict[int, float]:
    """code -> `/Widths` value (already in 1000u space) for every code in this simple
    font's own `/FirstChar`..`/LastChar` range, bounds-checked against `/Widths`'s actual
    length before indexing -- reuses `engine.fit.read_original_advance_pt`'s defensive
    shape rather than a fresh ad-hoc one."""
    first_char = int(font["/FirstChar"])
    last_char = int(font["/LastChar"])
    widths = font["/Widths"]
    out: dict[int, float] = {}
    for code in range(first_char, last_char + 1):
        index = code - first_char
        if index >= len(widths):
            raise _MalformedWidthsArrayError(
                f"code {code} is within FirstChar..LastChar ({first_char}..{last_char}) "
                f"but /Widths has only {len(widths)} entries -- refusing to index past "
                "the end of a malformed array"
            )
        out[code] = float(widths[index])
    return out


@pytest.mark.corpus
def test_corpus_advance_delta_measurement_pins_seam_threshold(
    manifest: list,  # type: ignore[type-arg]
    corpus_dir: Path,
) -> None:
    """RESEARCH.md Open Question 2 / D-08's machine-metric half: for every corpus font
    resource that this project would ACTUALLY substitute -- `editable=True,
    substitution=True` (Phase 2's state) AND `lookup_bundled_font(base_font_name).mapped`
    (Task 1's table) -- compare every glyph's own `/Widths` advance against Liberation's
    `hmtx` advance for the SAME glyph name, both in 1000u space. This is the corpus-wide,
    per-glyph measurement D-07's "metric-compatible with Arial/Times/Courier" claim has
    never actually been checked against until now; SEAM_ADVANCE_DELTA_PT is pinned to
    the real result, not assumed to be near-zero.

    Same (document, font-object) dedup idiom as `test_corpus_substitution_coverage_report`
    above (a shared font object referenced from every page must not be measured once per
    page-reference).
    """
    deltas: list[float] = []
    seen: set[tuple[str, tuple[int, int]]] = set()

    for entry in manifest:
        path = corpus_dir / entry["filename"]
        if not path.exists():
            continue
        try:
            pdf = pikepdf.open(path)
        except Exception:  # noqa: BLE001 - encrypted/broken files are not this test's subject
            continue
        try:
            for page in pdf.pages:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                fonts = resources.get("/Font")
                if fonts is None:
                    continue
                for _key, font in fonts.items():
                    identity = (entry["filename"], font.objgen)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    try:
                        verdict = resolve_font(font)
                    except Exception:  # noqa: BLE001 - unresolvable fonts aren't this test's subject
                        continue
                    if not (verdict.editable and verdict.substitution):
                        continue
                    base_font_name = str(font.get("/BaseFont", "")).lstrip("/")
                    mapped = lookup_bundled_font(base_font_name)
                    if not mapped.mapped:
                        continue
                    assert mapped.family is not None
                    assert mapped.variant is not None
                    try:
                        widths_1000u = _read_widths_1000u(font)
                    except Exception:  # noqa: BLE001 - malformed /Widths isn't this test's subject
                        continue
                    glyph_names = encoding_map(font)
                    for code, original_width_1000u in widths_1000u.items():
                        glyph_name = glyph_names.get(code)
                        if glyph_name is None:
                            continue
                        liberation_width = liberation_advance_1000u(
                            mapped.family, mapped.variant, glyph_name
                        )
                        if liberation_width is None:
                            continue
                        deltas.append(abs(original_width_1000u - liberation_width))
        except Exception:  # noqa: BLE001
            pass
        finally:
            pdf.close()

    assert deltas, "expected at least one comparable glyph across the corpus"
    count = len(deltas)
    max_delta = max(deltas)
    mean_delta = sum(deltas) / count
    print(
        f"\nadvance-delta (1000u space): count={count} max={max_delta:.4f} "
        f"mean={mean_delta:.4f}"
    )
    assert max_delta <= SEAM_ADVANCE_DELTA_PT, (
        f"measured max delta {max_delta:.4f} exceeds pinned SEAM_ADVANCE_DELTA_PT "
        f"={SEAM_ADVANCE_DELTA_PT}"
    )


# --------------------------------------------------------------------------------------
# Task 1: shape-twice primitives + fontTools subsetting + fresh subset tag
# (FONT-02/FONT-05, Pattern 2, Pitfall 5, Pitfall 8)
# --------------------------------------------------------------------------------------


def _assert_passes_ots(data: bytes, tmp_path: Path) -> None:
    """Shared helper (also needed by Task 3, per the plan): write subset bytes to a real
    file and run `ots-sanitize` (subprocess) against it, per Pitfall 8's "run OTS as a
    development-time check immediately after every subset call, not only at the final
    gate" guidance."""
    path = tmp_path / "subset.ttf"
    path.write_bytes(data)
    result = subprocess.run(["ots-sanitize", str(path)], capture_output=True)
    assert result.returncode == 0, (
        f"ots-sanitize rejected subsetted font: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_subset_covers_union_across_recipe(tmp_path: Path) -> None:
    """A subset built over a known `glyph_names` frozenset contains every requested glyph
    name (via the SUBSET font's own `getGlyphOrder()`) and is strictly smaller than the
    source TTF -- D-13's "subset once, over the exact glyph union" contract."""
    glyph_names = frozenset({"H", "e", "l", "o"})
    source_size = (
        Path(__file__).parent.parent / "fonts" / "LiberationSans-Regular.ttf"
    ).stat().st_size

    result = subset_font_for_family("Sans", "Regular", glyph_names)

    assert result.family == "Sans"
    assert result.variant == "Regular"
    assert len(result.tag) == 6
    assert result.tag.isupper()
    assert result.data
    assert len(result.data) < source_size

    subset_ttfont = TTFont(io.BytesIO(result.data))
    subset_glyph_order = set(subset_ttfont.getGlyphOrder())
    for name in glyph_names:
        assert name in subset_glyph_order


def test_fresh_subset_tag_per_family() -> None:
    """VALIDATION.md's pinned name for FONT-05's requirement: "Two subsets of the same
    family in one document get distinct tags." Exercised through the REAL
    `subset_font_for_family` call, not just `subset_tag()` in isolation -- the SAME
    family+variant subsetted over two DIFFERENT glyph_names frozensets gets two different
    `.tag` values, and each tag is a deterministic 6-uppercase-letter string (folding in
    the pure-hash sanity check `subset_tag` itself provides)."""
    subset_a = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o"}))
    subset_b = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o", "W"}))

    assert subset_a.tag != subset_b.tag
    for tag in (subset_a.tag, subset_b.tag):
        assert len(tag) == 6
        assert tag.isalpha()
        assert tag.isupper()

    # Deterministic: re-subsetting the SAME glyph union produces the SAME tag.
    subset_a_again = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o"}))
    assert subset_a_again.tag == subset_a.tag


def test_emitted_font_passes_ots(tmp_path: Path) -> None:
    """G2b's own literal acceptance criterion (Pitfall 8): every `SubsetFont.data`
    produced by `subset_font_for_family` passes `ots-sanitize` cleanly."""
    subset = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o"}))
    _assert_passes_ots(subset.data, tmp_path)


def test_shape_glyph_names_resolves_against_bundled_font_own_glyph_order() -> None:
    """`shape_glyph_names` returns glyph NAMES (never raw codepoints), resolved against
    the bundled font's own glyph order."""
    names = shape_glyph_names("Sans", "Regular", "Hello")

    assert isinstance(names, tuple)
    assert all(isinstance(n, str) for n in names)
    assert "H" in names
    assert "e" in names
    assert "l" in names
    assert "o" in names


def test_shape_twice_post_subset_cids_match_subset_glyph_ids(tmp_path: Path) -> None:
    """The single most load-bearing correctness property in this task (Pattern 2/Pitfall
    5): `shape_cids`'s returned CIDs must equal exactly what the SUBSET font's own
    `getGlyphID(name)` returns for each shaped glyph -- proving the two-pass shape-twice
    order (shape full font for names -> subset to those names -> shape subset for CIDs)
    produces CIDs with zero manual GID translation, and that pre-subset GIDs were never
    smuggled through.
    """
    text = "Hello"
    glyph_names = shape_glyph_names("Sans", "Regular", text)
    subset = subset_font_for_family("Sans", "Regular", frozenset(glyph_names))
    _assert_passes_ots(subset.data, tmp_path)

    result = shape_cids(subset, text)

    subset_ttfont = TTFont(io.BytesIO(subset.data))
    assert result
    assert len(result) == len(glyph_names)
    for (cid, source_char), name in zip(result, glyph_names):
        assert isinstance(cid, int)
        assert isinstance(source_char, str)
        # The Pattern 2/Pitfall 5 load-bearing property: shape_cids' CID for each glyph
        # is exactly the SUBSET font's own getGlyphID for the glyph name the FIRST
        # (pre-subset) shaping pass resolved -- not a pre-subset GID, not a manually-
        # translated value, zero translation between the two shaping passes.
        assert cid == subset_ttfont.getGlyphID(name)


def test_subset_cid_widths_covers_every_non_notdef_glyph() -> None:
    """FONT-04/D-14: `subset_cid_widths` returns exactly N entries for an N-non-.notdef-
    glyph subset, keys covering every GID from 1 through N inclusive (GID 0/.notdef
    excluded) -- complete for every glyph in the subset's own glyph order, which the
    function iterates in full.

    CORRECTED alongside `subset_cid_widths`'s own docstring (2026-08-31): that is NOT
    automatically "the exact same set `shape_cids` can ever emit", as this docstring used
    to claim. `shape_cids` emits CID 0 for any character the face has no glyph for --
    see `test_shape_cids_emits_uncovered_cid_zero_that_subset_cid_widths_cannot_cover`
    below for the reproduction, and `has_unmapped_glyph` for the guard that keeps such
    text away from the subsetting path in the first place."""
    glyph_names = frozenset({"H", "e", "l", "o"})
    subset = subset_font_for_family("Sans", "Regular", glyph_names)
    subset_ttfont = TTFont(io.BytesIO(subset.data))
    glyph_order = subset_ttfont.getGlyphOrder()
    n = len(glyph_order) - 1  # exclude GID 0 (.notdef)

    widths = subset_cid_widths(subset)

    assert len(widths) == n
    assert set(widths) == set(range(1, len(glyph_order)))
    units_per_em = subset_ttfont["head"].unitsPerEm
    hmtx = subset_ttfont["hmtx"]
    for gid in range(1, len(glyph_order)):
        expected = hmtx[glyph_order[gid]][0] * 1000.0 / units_per_em
        assert widths[gid] == pytest.approx(expected)


def test_build_w_array_groups_contiguous_cids_and_breaks_on_gaps() -> None:
    """FONT-04: the verified WeasyPrint run-grouped `/W` algorithm -- CIDs 1 and 2 are
    contiguous and group into one run, CID 3 is a gap so CID 4 starts a fresh run.
    `{1: 500.0, 2: 278.0, 4: 600.0}` -> `[1 [500 278] 4 [600]]`."""
    result = build_w_array({1: 500.0, 2: 278.0, 4: 600.0})

    assert isinstance(result, pikepdf.Array)
    assert list(result) == [1, [500, 278], 4, [600]]


def test_font04_missing_width_never_falls_through_silently() -> None:
    """VALIDATION.md's pinned name. Negative case: `subset_cid_widths`'s key set exactly
    equals every non-.notdef GID in the subset's own glyph order -- no gap can exist for
    a real glyph, so no glyph in use can ever silently fall through to an uncovered `/DW`.
    Separately: 03-06's Type0 assembly (Task 3) never emits a `/DW` key at all, so no
    caller of `build_cid_font_descriptor` ever needs one as a cover for a missing `/W`
    entry."""
    subset = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o"}))
    widths = subset_cid_widths(subset)
    glyph_order = TTFont(io.BytesIO(subset.data)).getGlyphOrder()

    assert set(widths) == set(range(1, len(glyph_order)))

    # build_cid_font_descriptor never emits /DW -- its caller never needs one.
    pdf = pikepdf.Pdf.new()
    descriptor = build_cid_font_descriptor(pdf, subset)
    assert "/DW" not in descriptor


def test_build_cid_font_descriptor_never_mutates_preexisting_font_object() -> None:
    """D-12 proof, scoped to this task's own function: `build_cid_font_descriptor` only
    ever creates NEW indirect objects in `pdf` -- it never accepts, and therefore cannot
    disturb, a pre-existing font/FontDescriptor object already in the same `pdf`."""
    pdf = pikepdf.Pdf.new()
    preexisting_bytes = b"unrelated-preexisting-fontfile2-bytes"
    preexisting_descriptor = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/FontDescriptor"),
                "/FontFile2": pdf.make_stream(preexisting_bytes),
            }
        )
    )
    before_hash = md5(bytes(preexisting_descriptor["/FontFile2"].read_bytes())).hexdigest()

    subset = subset_font_for_family("Sans", "Regular", frozenset({"H", "e", "l", "o"}))
    new_descriptor = build_cid_font_descriptor(pdf, subset)

    after_hash = md5(bytes(preexisting_descriptor["/FontFile2"].read_bytes())).hexdigest()
    assert after_hash == before_hash
    assert new_descriptor.get("/FontFile2") is not None
    assert bytes(new_descriptor["/FontFile2"].read_bytes()) == subset.data
    assert new_descriptor is not preexisting_descriptor


# --------------------------------------------------------------------------------------
# Task 3: ToUnicode CMap + full Type0/CIDFontType2 assembly (FONT-03, D-12 completion)
# --------------------------------------------------------------------------------------

_BFCHAR_BLOCK_RE = re.compile(rb"beginbfchar(.*?)endbfchar", re.DOTALL)
_BFCHAR_LINE_RE = re.compile(r"<([0-9A-Fa-f]{4})>\s+<([0-9A-Fa-f]+)>")


def _parse_tounicode_cmap(cmap_bytes: bytes) -> dict[int, str]:
    """Test-only round-trip helper: regex over `<XXXX> <YYYY>` lines WITHIN each
    `beginbfchar`/`endbfchar` block only (never the fixed `<0000> <ffff>`
    `begincodespacerange` line), decoding the second group as UTF-16BE -- the exact
    inverse of `build_tounicode_cmap_bytes`, used only to prove the writer's own output
    round-trips (VALIDATION.md's pinned test)."""
    result: dict[int, str] = {}
    for block in _BFCHAR_BLOCK_RE.findall(cmap_bytes):
        for cid_hex, utf16be_hex in _BFCHAR_LINE_RE.findall(block.decode("ascii")):
            result[int(cid_hex, 16)] = bytes.fromhex(utf16be_hex).decode("utf-16-be")
    return result


def test_tounicode_cmap_roundtrips_ascii_and_accented() -> None:
    """VALIDATION.md's pinned test name: build a small CMap covering plain ASCII ("A")
    and an accented character ("e" with U+00E9, e-acute), then parse the CMap's own
    output back via a regex round-trip helper and assert it recovers the original dict
    exactly."""
    cid_to_unicode = {7: "A", 12: "é", 15: "l", 17: "o"}

    cmap_bytes = build_tounicode_cmap_bytes(cid_to_unicode)

    assert b"/CIDInit /ProcSet findresource begin" in cmap_bytes
    assert b"begincmap" in cmap_bytes
    assert b"/CIDSystemInfo" in cmap_bytes
    assert b"Adobe-Identity-UCS" in cmap_bytes

    recovered = _parse_tounicode_cmap(cmap_bytes)
    assert recovered == cid_to_unicode


def test_tounicode_cmap_fixed_header_and_single_block_shape() -> None:
    """`build_tounicode_cmap_bytes({7: "H", 12: "e", 15: "l", 17: "o"})` emits the fixed
    header/trailer verbatim and exactly one `beginbfchar`/`endbfchar` block with 4 entries
    formatted `<0007> <0048>` (UTF-16BE hex) per line."""
    cmap_bytes = build_tounicode_cmap_bytes({7: "H", 12: "e", 15: "l", 17: "o"})
    lines = cmap_bytes.split(b"\n")

    assert lines[0] == b"/CIDInit /ProcSet findresource begin"
    assert lines[-1] == b"end"
    assert lines[-2] == b"end"
    assert lines[-3] == b"CMapName currentdict /CMap defineresource pop"
    assert lines[-4] == b"endcmap"

    assert cmap_bytes.count(b"beginbfchar") == 1
    assert cmap_bytes.count(b"endbfchar") == 1
    assert b"4 beginbfchar" in cmap_bytes
    assert b"<0007> <0048>" in cmap_bytes  # "H" == U+0048


def test_tounicode_batches_at_100_entries_per_block() -> None:
    """150 entries emit TWO `beginbfchar`/`endbfchar` blocks (100 then 50), matching the
    Adobe 100-per-block cap `encoding_table.py`'s `_parse_codespace_widths` docstring
    already names for the read side."""
    cid_to_unicode = {cid: chr(65 + (cid % 26)) for cid in range(1, 151)}

    cmap_bytes = build_tounicode_cmap_bytes(cid_to_unicode)

    assert cmap_bytes.count(b"beginbfchar") == 2
    assert cmap_bytes.count(b"endbfchar") == 2
    assert b"100 beginbfchar" in cmap_bytes
    assert b"50 beginbfchar" in cmap_bytes

    recovered = _parse_tounicode_cmap(cmap_bytes)
    assert recovered == cid_to_unicode


def _small_subset_and_cid_data() -> tuple[SubsetFont, dict[int, float], dict[int, str]]:
    """Shared build for the `embed_type0_font` tests below: a real tiny Liberation Sans
    subset over "Hello", its FONT-04 `/W`-ready widths (`subset_cid_widths`, precondition
    the brief's docstring states), and a small CID->Unicode map covering the same glyphs
    via `shape_cids`."""
    text = "Hello"
    glyph_names = shape_glyph_names("Sans", "Regular", text)
    subset = subset_font_for_family("Sans", "Regular", frozenset(glyph_names))
    cid_widths = subset_cid_widths(subset)
    cid_to_unicode = {cid: ch for cid, ch in shape_cids(subset, text)}
    return subset, cid_widths, cid_to_unicode


def test_embed_type0_font_produces_encoding_table_compatible_shape(tmp_path: Path) -> None:
    """The exact three checks `encoding_table.py`'s `_resolve_type0`/`_cid_to_gid_map_ok`
    branch on: `/Encoding == /Identity-H`, descendant `/CIDToGIDMap == /Identity`,
    descendant `/Subtype == /CIDFontType2` -- proving zero reader changes are needed.
    Also asserts the /W array, /FontDescriptor, and /ToUnicode shape, and re-runs OTS
    against the embedded subset (Pitfall 8's final-assembly recheck)."""
    subset, cid_widths, cid_to_unicode = _small_subset_and_cid_data()
    _assert_passes_ots(subset.data, tmp_path)

    pdf = pikepdf.Pdf.new()
    type0 = embed_type0_font(pdf, subset, cid_widths, cid_to_unicode)

    assert type0.get("/Subtype") == pikepdf.Name("/Type0")
    assert type0.get("/Encoding") == pikepdf.Name("/Identity-H")

    descendants = type0["/DescendantFonts"]
    assert len(descendants) == 1
    cid_font = descendants[0]
    assert cid_font.get("/Subtype") == pikepdf.Name("/CIDFontType2")
    assert cid_font.get("/CIDToGIDMap") == pikepdf.Name("/Identity")
    assert cid_font.get("/DW") is None

    expected_w = build_w_array(cid_widths)
    assert list(cid_font["/W"]) == list(expected_w)

    assert cid_font.get("/FontDescriptor") is not None
    assert bytes(cid_font["/FontDescriptor"]["/FontFile2"].read_bytes()) == subset.data

    to_unicode = type0.get("/ToUnicode")
    assert to_unicode is not None
    assert bytes(to_unicode.read_bytes()) == build_tounicode_cmap_bytes(cid_to_unicode)


def test_embed_type0_font_never_mutates_preexisting_font_object() -> None:
    """D-12, end-to-end composed-function version of
    `test_build_cid_font_descriptor_never_mutates_preexisting_font_object`:
    `embed_type0_font` takes no existing font object as a parameter anywhere in its
    signature, so a pre-existing, unrelated font object's `/FontFile2`, `/Widths`, and
    every other key are byte-identical before and after."""
    pdf = pikepdf.Pdf.new()
    preexisting_bytes = b"unrelated-preexisting-fontfile2-bytes"
    preexisting_font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/TrueType"),
                "/BaseFont": pikepdf.Name("/Unrelated"),
                "/FirstChar": 32,
                "/LastChar": 33,
                "/Widths": pikepdf.Array([600, 600]),
                "/FontDescriptor": pdf.make_indirect(
                    pikepdf.Dictionary(
                        {
                            "/Type": pikepdf.Name("/FontDescriptor"),
                            "/FontFile2": pdf.make_stream(preexisting_bytes),
                        }
                    )
                ),
            }
        )
    )
    before = dict(preexisting_font)
    before_fontfile_hash = md5(
        bytes(preexisting_font["/FontDescriptor"]["/FontFile2"].read_bytes())
    ).hexdigest()

    subset, cid_widths, cid_to_unicode = _small_subset_and_cid_data()
    embed_type0_font(pdf, subset, cid_widths, cid_to_unicode)

    after_fontfile_hash = md5(
        bytes(preexisting_font["/FontDescriptor"]["/FontFile2"].read_bytes())
    ).hexdigest()
    assert after_fontfile_hash == before_fontfile_hash
    assert preexisting_font.get("/Widths") is not None
    assert list(preexisting_font["/Widths"]) == [600, 600]
    for key in ("/Type", "/Subtype", "/BaseFont", "/FirstChar", "/LastChar"):
        assert preexisting_font.get(key) == before[key]
