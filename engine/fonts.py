"""Bundled-font mapping: /BaseFont name -> Liberation family/variant, exact-match only.

Read side only (this task): a static table answering "does this PDF font map to a
bundled substitute?" and, if so, which one. Write/subsetting (embedding the mapped
Liberation face as a new Type0/CIDFontType2 font, per FONT-02/FONT-03/FONT-05) is
Phase 3's own later work (03-05), not this file's task-1 scope; Tasks 2 and 3 append the
edit-time substitution trigger and the embedding path to this same module.

Write side (this task, 03-05 task 1): font subsetting and the "shape twice" pre-subset
glyph-name / post-subset CID resolution (D-12/D-13/D-14, FONT-02/FONT-03/FONT-04/FONT-05)
that makes the substitution pipeline's replacement text actually reference the correct
glyphs once the bundled Liberation face is subset and re-embedded per document.

D-05: a missing glyph substitutes the entire visual run, never a partial one -- FONT-06.
D-06: automatic matching for a font with no entry refuses BY NAME. The recipe API also
allows an explicit user-selected replacement family; that choice bypasses this lookup,
without claiming to identify the original. No serif/sans fallback derived
from `/FontDescriptor` flags -- that is precisely the heuristic FONT-01 forbids, the flags
lie often, and a confident-wrong pick is the failure mode this product exists to avoid.
D-07: the bundled set is the Liberation trio only (Sans/Serif/Mono, 4 weights each) --
metric-compatible with Arial/Times/Courier, so a mapped substitution needs no width
refitting. Noto/DejaVu are deliberately absent (deferred until refusal data shows a real
gap) and are never accepted as a lookup target here.

Mirrors `engine/encoding_table.py`'s own convention: `STANDARD_14`/`SIMPLE_SUBTYPES` are
flat frozensets built from an enumerated, corpus-verified list, never from a name-parsing
or regex step (see that module's "Static table, exact-match only" pattern). This table is
the same shape: `BASE_FONT_MAPPING` is a flat literal `dict`, and `lookup_bundled_font` is
a single `dict.get()` -- no lowercasing, no whitespace trimming, no substring/regex
matching, so a BaseFont spelling this table doesn't already know refuses by name rather
than guessing.

Table contents per 03-RESEARCH.md Pitfall 10 (corpus-measured, every font resource
resolved through `resolve_font` and filtered to `editable=True, substitution=True`):
- The 12 Base-14 non-symbol names (~660+ occurrences measured) -- `Symbol`/`ZapfDingbats`
  are deliberately ABSENT: they have no Liberation equivalent, and D-06 says refuse by
  name, so their absence from this table IS the correct behavior, not a coverage gap.
- The MS-core-font forward-looking entries (Arial/Times New Roman/Courier New name
  variants) -- observed frequently in the corpus but always embedded there, so this table
  covers them anyway as low-cost robustness for the broader PDF ecosystem beyond this
  corpus, per Pitfall 10's own recommendation.
- A long tail of exotic non-Base-14 names (AvantGarde, AGaramond, Palatino, ...) has no
  entry and correctly refuses -- also not a coverage gap to close (Pitfall 10).
"""

from __future__ import annotations

import functools
import io
from dataclasses import dataclass
from hashlib import md5
from pathlib import Path
from typing import Literal

import pikepdf
import uharfbuzz as hb
from fontTools import subset
from fontTools.agl import UV2AGL
from fontTools.ttLib import TTFont

from engine.encoding_table import FontProgram, FontVerdict, encoding_map, glyph_presence

BundledFamily = Literal["Sans", "Serif", "Mono"]
BundledVariant = Literal["Regular", "Bold", "Italic", "BoldItalic"]


@dataclass(frozen=True, slots=True)
class MappingVerdict:
    """The logged outcome of one BaseFont name's lookup against the bundled table.

    Mirrors `FontVerdict`'s shape (encoding_table.py) per 03-PATTERNS.md: `mapped=False`
    is a refusal and `reason` names the BaseFont, never a generic message -- deliberately
    its own type rather than reusing `FontVerdict`, since a mapping-table lookup answers a
    different question (which bundled face substitutes, if any) than a font's own
    editability verdict does.
    """

    mapped: bool
    family: BundledFamily | None
    variant: BundledVariant | None
    reason: str | None = None


FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


def liberation_font_path(family: BundledFamily, variant: BundledVariant) -> Path:
    """The bundled Liberation .ttf path for a (family, variant) pair (D-07's naming)."""
    return FONTS_DIR / f"Liberation{family}-{variant}.ttf"


@functools.lru_cache(maxsize=None)
def _liberation_ttfont(family: BundledFamily, variant: BundledVariant) -> TTFont:
    """Cached `TTFont` load for one bundled face, keyed on (family, variant) only --
    `functools.lru_cache` (stdlib, no new dependency) so each of the up-to-12 Liberation
    files loads from disk at most once per process, no matter how many glyphs are looked
    up against it."""
    return TTFont(str(liberation_font_path(family, variant)))


def liberation_advance_1000u(
    family: BundledFamily, variant: BundledVariant, glyph_name: str
) -> float | None:
    """The bundled Liberation{family}-{variant}.ttf `hmtx` advance for `glyph_name`,
    scaled to 1000-units-per-em (`hmtx_value * 1000 / head.unitsPerEm`) so it is directly
    comparable to a PDF `/Widths` entry, which is always in that same 1000-unit space.

    D-08's machine-metric half: this is the read primitive `SEAM_ADVANCE_DELTA_PT` below
    is measured and pinned against. Returns `None` -- never raises `KeyError` -- when
    `glyph_name` is absent from this font's own glyph set, matching this phase's
    established "unknown glyph is a caller-visible absence, not a crash" posture
    (`glyph_presence`, encoding_table.py).
    """
    font = _liberation_ttfont(family, variant)
    hmtx = font["hmtx"]
    if glyph_name not in hmtx.metrics:
        return None
    advance_units: int = hmtx[glyph_name][0]
    units_per_em: int = font["head"].unitsPerEm
    return advance_units * 1000.0 / units_per_em


# D-08 machine-metric threshold, Open Question 2 (03-RESEARCH.md): the per-glyph advance
# delta (abs(original /Widths value - liberation_advance_1000u(...)), both in 1000u space)
# a substituted run must stay within to count as seam-quality per D-08's "near-zero"
# framing.
#
# MEASURED (this task, 2026-08-24, corpus/public -- 217-document govdocs1-based corpus,
# every font resource resolved through resolve_font, filtered to editable=True,
# substitution=True (Phase 2's state) AND lookup_bundled_font(base_font_name).mapped
# (Task 1's table) -- 618 distinct (document, font-object) usages, the same population
# test_corpus_substitution_coverage_report's mapped_count pins):
#   count=13,497 glyph comparisons, mean=4.6872pt, median~=0.15pt, max=500.0pt.
# D-07's "metric-compatible" framing holds for the OVERWHELMING majority of glyphs --
# median delta is 0.15pt, essentially float-precision noise, and only 445/13,497 (~3.3%)
# exceed 1pt. It does NOT hold uniformly: the long tail (max=500.0pt) is real, not a
# measurement artifact, and is NOT hand-waved away here -- two distinct causes, both
# confirmed by inspecting the worst offenders directly:
#   1. Several corpus documents declare a full 0..255 /Widths array but leave rarely-used
#      codes (Euro, hyphen) at a literal declared width of 0 -- a common producer
#      placeholder for "this code is never actually rendered in this document", not a
#      real advance claim. Comparing it against Liberation's real (non-zero) glyph
#      advance produces a large delta (up to 500.0pt for Euro) that would never actually
#      surface as a visible seam, since that code is never in the run being substituted.
#   2. nasa_graphics_standards_manual.pdf declares genuinely non-standard /Widths for
#      "space" (570-675, vs Liberation/standard Times' 250) and "hyphen" (713, vs
#      Liberation's 333) -- a real, single-document metric divergence unrelated to
#      Liberation's own fidelity.
# Pinned to the actual measured maximum, not a hand-guessed number and not widened to
# flatter the result (03-CONTEXT.md's Deferred Ideas explicitly reserves widening
# BASE_FONT_MAPPING for later -- this constant is independent of that and stays pinned to
# what was actually measured): every value in the distribution above is <= 500.0, so this
# is the real ceiling for the confirmed causes above, not a promise that D-07 holds
# near-zero for every declared codepoint in every corpus document.
SEAM_ADVANCE_DELTA_PT: float = 500.0


# D-06/FONT-01: flat, finite, exact-match dictionary -- never built from a name-parsing
# or regex step. Base-14 non-symbol names plus explicit MS-core-font aliases
# (Arial x4, TimesNewRoman x4, TimesNewRomanPS...MT x4, CourierNewPS...MT x4,
# CourierNew x4 -- Pitfall 10's forward-looking robustness set).
BASE_FONT_MAPPING: dict[str, tuple[BundledFamily, BundledVariant]] = {
    # Exact display-name aliases emitted by PDF producers, including escaped spaces.
    "Times New Roman": ("Serif", "Regular"),
    "Times New Roman,Bold": ("Serif", "Bold"),
    "Times New Roman,Italic": ("Serif", "Italic"),
    "Times New Roman,BoldItalic": ("Serif", "BoldItalic"),
    "Times New Roman Bold": ("Serif", "Bold"),
    "Times New Roman Italic": ("Serif", "Italic"),
    "Times New Roman Bold Italic": ("Serif", "BoldItalic"),
    "Courier New": ("Mono", "Regular"),
    "Courier New,Bold": ("Mono", "Bold"),
    "Courier New,Italic": ("Mono", "Italic"),
    "Courier New,BoldItalic": ("Mono", "BoldItalic"),
    "Courier New Bold": ("Mono", "Bold"),
    "Courier New Italic": ("Mono", "Italic"),
    "Courier New Bold Italic": ("Mono", "BoldItalic"),
    # Base-14 non-symbol names (STANDARD_14 minus Symbol/ZapfDingbats -- deliberately
    # absent, refuse by omission per D-06 and Pitfall 10).
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
    # MS-core-font forward-looking entries (exact strings only -- no space in
    # CourierNew/TimesNewRoman, matching the corpus-measured convention, not the
    # "Times New Roman" display name).
    "Arial": ("Sans", "Regular"),
    "Arial,Bold": ("Sans", "Bold"),
    "Arial,Italic": ("Sans", "Italic"),
    "Arial,BoldItalic": ("Sans", "BoldItalic"),
    "ArialMT": ("Sans", "Regular"),
    "Arial-BoldMT": ("Sans", "Bold"),
    "Arial-ItalicMT": ("Sans", "Italic"),
    "Arial-BoldItalicMT": ("Sans", "BoldItalic"),
    "TimesNewRoman": ("Serif", "Regular"),
    "TimesNewRoman,Bold": ("Serif", "Bold"),
    "TimesNewRoman,Italic": ("Serif", "Italic"),
    "TimesNewRoman,BoldItalic": ("Serif", "BoldItalic"),
    "TimesNewRomanPSMT": ("Serif", "Regular"),
    "TimesNewRomanPS-BoldMT": ("Serif", "Bold"),
    "TimesNewRomanPS-ItalicMT": ("Serif", "Italic"),
    "TimesNewRomanPS-BoldItalicMT": ("Serif", "BoldItalic"),
    "CourierNewPSMT": ("Mono", "Regular"),
    "CourierNewPS-BoldMT": ("Mono", "Bold"),
    "CourierNewPS-ItalicMT": ("Mono", "Italic"),
    "CourierNewPS-BoldItalicMT": ("Mono", "BoldItalic"),
    "CourierNew": ("Mono", "Regular"),
    "CourierNew,Bold": ("Mono", "Bold"),
    "CourierNew,Italic": ("Mono", "Italic"),
    "CourierNew,BoldItalic": ("Mono", "BoldItalic"),
}


def lookup_bundled_font(base_font_name: str) -> MappingVerdict:
    """D-06: a single exact-match dict lookup, never a heuristic.

    No lowercasing, no whitespace trimming, no substring/regex matching anywhere -- a name
    this table doesn't already know refuses BY NAME (`mapped=False`), which is the
    correct, expected outcome for Symbol/ZapfDingbats and the exotic long tail (Pitfall
    10), not a coverage gap this function should try to close by guessing.
    """
    entry = BASE_FONT_MAPPING.get(base_font_name)
    if entry is None:
        return MappingVerdict(
            False, None, None, f"no mapping table entry for BaseFont {base_font_name!r}"
        )
    family, variant = entry
    return MappingVerdict(True, family, variant, None)


@dataclass(frozen=True, slots=True)
class SubstitutionTrigger:
    """The edit-time D-05/FONT-06 verdict: given a run's own font and its proposed
    replacement text, does this run need the bundled substitute face?

    Deliberately its own type, not `MappingVerdict` reused: a mapping-table lookup
    ("which bundled face substitutes") and this edit-time availability check ("does this
    text even need one") answer different questions -- the same "deliberately its own
    type" precedent `GlyphVerdict` already established in `encoding_table.py`.
    """

    substitute: bool
    reason: str | None = None


def reverse_encoding_map(font: pikepdf.Object) -> dict[str, int]:
    """glyph-name -> code, inverted from `encoding_table.encoding_map(font)`.

    Sorted-ascending iteration over the forward map, then `dict.setdefault`, makes the
    LOWEST code win deterministically on any name collision (a hostile `/Differences`
    could in principle map two codes to the same name) -- never last-write-wins, which
    would depend on dict iteration order instead.

    Simple-font (Type1/TrueType) callers only: see `run_needs_substitution`'s Type0/CID
    short-circuit for why this must never be called for a Type0/CIDFontType2 font.
    """
    forward = encoding_map(font)
    reverse: dict[str, int] = {}
    for code, name in sorted(forward.items()):
        reverse.setdefault(name, code)
    return reverse


def run_needs_substitution(
    font: pikepdf.Object,
    font_verdict: FontVerdict,
    program: FontProgram | None,
    proposed_text: str,
) -> SubstitutionTrigger:
    """D-05/03-RESEARCH.md Pattern 4's edit-time glyph-availability check -- the genuinely
    NEW question Phase 2's `font_verdict.substitution` cannot answer, because Phase 2
    resolved that flag at classification time, before any replacement text existed. A run
    can be `editable_original` (font embedded, `substitution=False`) at classification time
    and still need substitution once the user's proposed text contains a character the
    embedded subset has no glyph for.

    Precondition: only called for runs already classified `editable=True` upstream (by
    `resolve_font`/`classify_run`); this function does NOT itself re-check
    `font_verdict.editable`.

    Two checks per character, first failure wins -- D-05: the entire run substitutes,
    never a partial one, so this function never inspects more than the first failing
    character:
    1. does this font's own encoding have a CODE for this Unicode character? (1a: no AGL
       name at all; 1b: the AGL name has no code in this font's own encoding)
    2. is that code's glyph actually present in the embedded program? (delegates entirely
       to `glyph_presence`, already built and tested -- no new logic needed here, only a
       new caller). Checked by GLYPH NAME, not by the `/Encoding` byte code -- see the
       AMENDED note below and the call site's comment.

    AMENDED (plan-checker finding, Seam-7): Type0/CIDFontType2 fonts (`font_verdict
    .branch_id` starting `"C-"`) always substitute, checked FIRST -- before `reverse_map`
    is ever built. A Type0 font's `/Encoding` is the Name `/Identity-H`; `encoding_map`'s
    `base_encoding` has no `/Identity-H` entry in `NAMED_BASE_ENCODINGS` and silently falls
    through to a single-byte `STANDARD_ENCODING` table for what is actually a 2-byte CID
    codespace. Reusing that reverse map for a CID-keyed font would silently produce a
    WRONG answer (a false "code exists" via StandardEncoding's incidental collisions with
    plain ASCII), not merely a missing one -- so this is checked before the reverse-map
    lookup is attempted at all, not merely before its result is trusted. 03-05 already
    builds a correct, tested Type0/CIDFontType2 embedding path for the substituted branch,
    so routing every CID-keyed original through it reuses already-proven code rather than
    inventing a new CID-native availability check.

    AMENDED 2026-08-24 (task-review finding): check 2 passes `glyph_name` (the AGL `str`),
    NOT `code` (the `/Encoding` byte value), to `glyph_presence`. `_glyph_present`'s own
    contract (encoding_table.py) treats an `int` as a real GID/CID and a `str` as a glyph
    NAME -- a raw PDF `/Encoding` byte value is neither, and passing it as `code` degrades
    check 2 to a bare bounds check (`0 <= code < len(order)`) that trivially passes for any
    full/lightly-subsetted program regardless of whether THAT glyph exists (a genuine
    false-negative: a run silently NOT flagged for substitution despite a missing glyph).
    `code` is still needed above for check 1b's own `code is None` test; it has no further
    use after that.
    """
    if font_verdict.branch_id.startswith("C-"):
        return SubstitutionTrigger(
            True,
            "Type0/CID font: character availability not checked by this simple-font-"
            "encoding path, so this run always routes through substitution",
        )

    reverse_map = reverse_encoding_map(font)
    for ch in proposed_text:
        glyph_name = UV2AGL.get(ord(ch))
        if glyph_name is None:
            return SubstitutionTrigger(True, f"no Adobe Glyph List name for U+{ord(ch):04X}")
        code = reverse_map.get(glyph_name)
        if code is None:
            return SubstitutionTrigger(True, f"font encoding has no code for U+{ord(ch):04X}")
        # AMENDED 2026-08-24: glyph_name (str), never code (int) -- code is a raw
        # /Encoding byte value, not a real GID/CID, and glyph_presence's int branch is a
        # bare bounds check that would trivially "pass" regardless of whether this
        # SPECIFIC glyph exists. Residual, disclosed limitation: a TrueType font with only
        # synthetic post-table names (format 3.0, no real glyph names) still won't match
        # glyph_name here, but that fails toward unnecessary substitution, never a silent
        # missing glyph -- safe-direction, left for a later phase's cmap-based GID
        # resolution if corpus evidence shows it matters.
        _editable, needs_sub = glyph_presence(font_verdict, glyph_name, program)
        if needs_sub:
            return SubstitutionTrigger(
                True, f"glyph for U+{ord(ch):04X} absent from embedded program"
            )
    return SubstitutionTrigger(False, None)


@dataclass(frozen=True, slots=True)
class SubsetFont:
    """One fontTools-subsetted, in-memory Liberation face, ready to embed.

    `.data` is the fully-serialized TTF bytes (never written to scratch by this module --
    embedding, Task 2/3's job, decides if/when bytes ever touch disk). `.tag` is the fresh
    6-uppercase-letter subset tag (FONT-05) for this exact glyph union; `.family`/`.variant`
    echo the bundled face this subset was built from, so a caller building the Type0
    font dictionary never has to re-derive them from the tag or re-open the file.
    """

    data: bytes
    tag: str
    family: BundledFamily
    variant: BundledVariant


def subset_tag(description: str) -> str:
    """WeasyPrint's verified fresh-subset-tag algorithm (FONT-05), exact: 6 uppercase
    letters, deterministic per `description` string -- the same description always
    produces the same tag, and any two different descriptions produce (for all practical
    purposes) different tags, so a different glyph union naturally gets a fresh tag."""
    digest = md5(description.encode(), usedforsecurity=False).digest()[:6]
    return "".join(chr(65 + b % 26) for b in digest)


@functools.lru_cache(maxsize=12)
def _bundled_shaping_metadata(
    family: BundledFamily, variant: BundledVariant
) -> tuple[hb.Face, tuple[str, ...]]:
    """Only immutable installed-face metadata; never document text or PDF fonts.

    Fonts and buffers remain per-call, so scale/font-function changes cannot
    pollute another shaping operation. There are exactly twelve bundled faces.
    """
    path = liberation_font_path(family, variant)
    face = hb.Face(hb.Blob.from_file_path(str(path)))
    with TTFont(str(path)) as font:
        names = tuple(font.getGlyphOrder())
    return face, names


def shape_glyph_names(
    family: BundledFamily, variant: BundledVariant, text: str
) -> tuple[str, ...]:
    """Pattern 2 step A / Pitfall 5: shape `text` against the FULL bundled font to learn
    which glyphs it needs, resolved immediately to stable glyph NAMES -- never returning
    the raw pre-subset `info.codepoint` (a pre-subset GID), since fontTools' default
    subsetting renumbers glyph IDs and a pre-subset GID is not a valid post-subset GID
    (Pitfall 5). Glyph names survive subsetting unchanged, which is exactly why this
    function's return type is `str`, not `int`.
    """
    try:
        face, glyph_names = _bundled_shaping_metadata(family, variant)
        hb_font = hb.Font(face)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(hb_font, buf)

        return tuple(glyph_names[info.codepoint] for info in buf.glyph_infos)
    except Exception as exc:
        raise RuntimeError(
            f"cannot shape text for {family}/{variant}: {len(text)} chars"
        ) from exc


# GID 0's glyph name in every one of the 12 bundled Liberation faces (pinned by
# `test_notdef_is_glyph_zero_in_every_bundled_face`), and therefore the name
# `shape_glyph_names` resolves for any character the target face has no glyph for --
# harfbuzz maps an uncovered character to GID 0.
NOTDEF_GLYPH_NAME = ".notdef"


def has_unmapped_glyph(family: BundledFamily, variant: BundledVariant, text: str) -> bool:
    """Does any character of `text` shape to `.notdef` in the bundled `family`/`variant`?

    D-06's discipline at the CHARACTER level, one rung below the mapping table's own:
    exactly as a `/BaseFont` this table does not know refuses rather than guessing a face,
    a character the chosen face has no glyph for must refuse rather than rendering a box.
    Liberation covers Latin/Greek/Cyrillic and common punctuation, and nothing else -- an
    emoji, a CJK ideograph, a Private Use codepoint, and every script outside that set all
    land here.

    The one guard between the shaping boundary and everything downstream of it. It is
    load-bearing for `subset_cid_widths`/`build_w_array`, whose `/W` array covers exactly
    the subset's non-`.notdef` glyphs: a `.notdef` reaching `shape_cids` would be emitted
    into the content stream as CID 0 with NO `/W` entry, falling through to `/DW`, which is
    precisely FONT-04's "never silently falls back to a `/MissingWidth` of 0" in its Type0
    form. `engine.recipe._resolve_op` is the caller that enforces it, at plan time, so the
    refusal is disclosed before any commit (D-03) rather than discovered at save.
    """
    return NOTDEF_GLYPH_NAME in shape_glyph_names(family, variant, text)


def substitution_unicode_reason(
    family: BundledFamily, variant: BundledVariant, texts: tuple[str, ...]
) -> str | None:
    """Refuse Unicode that cannot survive the shared CID-to-Unicode mapping.

    The current writer supports one source codepoint per glyph. A composed
    cluster would otherwise lose characters, and two source characters sharing
    one glyph would overwrite each other's ToUnicode entry across operations.
    Check all replacement texts sharing a bundled face together, before subsetting.
    """
    font = hb.Font(hb.Face(hb.Blob.from_file_path(str(liberation_font_path(family, variant)))))
    unicode_by_gid: dict[int, str] = {}
    for text in texts:
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        infos = tuple(buf.glyph_infos or ())
        if tuple(info.cluster for info in infos) != tuple(range(len(text))):
            return "multi_character_shaping_unsupported"
        for info, character in zip(infos, text):
            previous = unicode_by_gid.setdefault(info.codepoint, character)
            if previous != character:
                return "ambiguous_glyph_unicode_mapping"
    return None


def subset_font_for_family(
    family: BundledFamily, variant: BundledVariant, glyph_names: frozenset[str]
) -> SubsetFont:
    """D-13: subset the bundled `family`/`variant` face down to exactly `glyph_names`,
    once, in memory -- the exact fontTools call verified in 03-RESEARCH.md's Code
    Examples section, with `retain_gids` left at its default (False, per Pattern
    2/Pitfall 5: this project's one-subset-per-document-per-family design has no
    cross-save GID-stability need, so the renumbered/compact glyph order is strictly
    better). Population is by glyph NAME (`glyphs=`), not `text=` -- the names already
    came from `shape_glyph_names`, and re-deriving them via a fresh cmap lookup here could
    diverge on ligature-produced glyphs that have no single originating character.
    """
    try:
        font = TTFont(str(liberation_font_path(family, variant)))
        options = subset.Options()
        options.set(notdef_outline=True, recommended_glyphs=False, desubroutinize=False)
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(glyphs=sorted(glyph_names))
        subsetter.subset(font)

        buf = io.BytesIO()
        font.save(buf)
        data = buf.getvalue()

        description = f"{family}-{variant}-{','.join(sorted(glyph_names))}"
        tag = subset_tag(description)
        return SubsetFont(data, tag, family, variant)
    except Exception as exc:
        raise RuntimeError(
            f"cannot subset {family}/{variant} for {len(glyph_names)} glyph names"
        ) from exc


def shape_cids(subset: SubsetFont, text: str) -> tuple[tuple[int, str], ...]:
    """Pattern 2 step B / Pitfall 5: shape `text` again, now against the SUBSET's own
    bytes (never `from_file_path` -- the subset exists only in memory, per
    `subset_font_for_family`'s own contract), and return each shaped glyph's final CID
    exactly as harfbuzz's `info.codepoint` reports it against this subset -- zero manual
    GID translation, because that IS the subset font's own `getGlyphID(name)` value (the
    load-bearing Pattern 2/Pitfall 5 property this task exists to prove). Each CID is
    paired with its SOURCE character only after checking a one-codepoint-per-glyph
    mapping. Multi-character clusters refuse rather than silently truncating Unicode;
    the recipe caller preflights the full face with `substitution_unicode_reason`.
    """
    try:
        font = hb.Font(hb.Face(hb.Blob(subset.data)))
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        infos = tuple(buf.glyph_infos or ())
    except Exception as exc:
        raise RuntimeError(f"cannot shape text against subset: {len(text)} chars") from exc
    if tuple(info.cluster for info in infos) != tuple(range(len(text))):
        raise ValueError("multi_character_shaping_unsupported")
    unicode_by_cid: dict[int, str] = {}
    for info, character in zip(infos, text):
        if unicode_by_cid.setdefault(info.codepoint, character) != character:
            raise ValueError("ambiguous_glyph_unicode_mapping")
    return tuple((info.codepoint, character) for info, character in zip(infos, text))


def subset_cid_widths(subset: SubsetFont) -> dict[int, float]:
    """FONT-04/D-14: every non-.notdef glyph's `hmtx` advance in the subset, keyed by GID
    -- and since `/CIDToGIDMap /Identity` + `/Encoding /Identity-H` make the content-
    stream code, the CID, and the GID the same number (see `encoding_table
    ._cid_to_gid_map_ok` and this module's own `shape_cids`, which returns exactly these
    GIDs as CIDs), this dict is keyed directly usable as `/W` CIDs with no translation.

    Starts at GID 1, never 0, so `.notdef` is excluded -- and this iterates the subset's
    ENTIRE non-`.notdef` glyph order, so within that set `/W` completeness is structural:
    no such glyph is missing from this dict, and this function itself never raises
    KeyError and never silently substitutes a 0-width entry.

    CORRECTED 2026-08-31 (Phase 8 research, PDF/A-2b 6.2.11.8-1). This paragraph used to
    claim `.notdef` "is never a value `shape_cids` can emit" and was therefore excluded
    "BY CONSTRUCTION". **That was false as written.** `shape_cids` emits CID 0 for any
    character the subset has no glyph for, which is any character the BUNDLED FACE has no
    glyph for -- an emoji, a CJK ideograph, any script Liberation does not cover.
    Reproduced: `shape_cids(subset, "A\N{GRINNING FACE}B")` returned `((1, 'A'), (0, ...),
    (2, 'B'))` against a subset whose `/W` covered only CIDs 1 and 2, so CID 0 was
    referenced by the content stream with no width entry and fell through to `/DW`.

    What enforces the exclusion NOW is a caller-side precondition, not a property of
    harfbuzz: `has_unmapped_glyph` above answers exactly that question, and
    `engine.recipe._resolve_op` refuses any op whose replacement text shapes to `.notdef`
    in its bundled face (`"character_has_no_glyph_in_bundled_font"`) BEFORE
    `subset_font_for_family`/`shape_cids` are ever reached -- `apply_recipe` runs only on
    a `plan_recipe` report where every op resolved (D-11). So every text reaching this
    subset shapes entirely within it, and `shape_cids` emits only GIDs this dict covers.
    Call this function only for a subset built that way; it cannot itself detect the
    difference.
    """
    font = TTFont(io.BytesIO(subset.data))
    glyph_order = font.getGlyphOrder()
    hmtx = font["hmtx"]
    units_per_em: int = font["head"].unitsPerEm
    return {
        gid: hmtx[glyph_order[gid]][0] * 1000.0 / units_per_em
        for gid in range(1, len(glyph_order))
    }


def build_w_array(cid_widths: dict[int, float]) -> pikepdf.Array:
    """The verified WeasyPrint `/W` run-grouping algorithm (FONT-04), exact: iterate CIDs
    in ascending order, starting a new `[c [w1 w2 ...]]` run whenever the previous CID is
    NOT in `cid_widths` (a gap). Each width is rounded to the nearest int at this
    boundary only -- `subset_cid_widths` itself stays float-precise; every real-world PDF
    writer emits `/W` widths as integers, so the rounding happens here, once, at the
    point of PDF serialization.
    """
    pdf_widths: list[int | list[int]] = []
    current_widths: list[int] = []
    for i in sorted(cid_widths):
        if i - 1 not in cid_widths:
            pdf_widths.append(i)
            current_widths = []
            pdf_widths.append(current_widths)
        current_widths.append(round(cid_widths[i]))
    # pikepdf.Array converts each nested Python list into its own nested pikepdf.Array,
    # so the plain-list structure built above only needs wrapping once, at the end.
    return pikepdf.Array(pdf_widths)


# Flags bits (PDF 32000-1 Table 123) this module ever sets on a synthesized
# /FontDescriptor -- named here rather than as bare integer literals at the call site.
_FLAG_FIXED_PITCH = 1
_FLAG_SERIF = 2
_FLAG_NONSYMBOLIC = 32
_FLAG_ITALIC = 64


def _tagged_base_font_name(subset: SubsetFont) -> str:
    """The shared `{tag}+Liberation{family}` BaseFont construction (FONT-05's subset-tag
    prefix convention) -- extracted so `build_cid_font_descriptor` and `embed_type0_font`
    both call one helper instead of duplicating the f-string, per this task's own brief."""
    return f"{subset.tag}+Liberation{subset.family}"


def build_cid_font_descriptor(pdf: pikepdf.Pdf, subset: SubsetFont) -> pikepdf.Object:
    """FONT-03: a NEW `/FontDescriptor` for a Type0/CIDFontType2 embedding of `subset`,
    added to `pdf` as a fresh indirect object.

    D-12 is enforced by this SIGNATURE, not by a runtime check: this function only ever
    takes `pdf` (to create new objects in) and `subset` (already-independent, in-memory
    data) -- it never accepts an existing font/FontDescriptor object, so it has no way to
    reach into, and therefore cannot disturb, any pre-existing font object already in
    `pdf`.
    """
    font = TTFont(io.BytesIO(subset.data))
    units_per_em: int = font["head"].unitsPerEm
    scale = 1000.0 / units_per_em

    font_name = _tagged_base_font_name(subset)

    flags = _FLAG_NONSYMBOLIC
    if subset.family == "Mono":
        flags |= _FLAG_FIXED_PITCH
    if subset.family == "Serif":
        flags |= _FLAG_SERIF
    if subset.variant in ("Italic", "BoldItalic"):
        flags |= _FLAG_ITALIC

    head = font["head"]
    bbox = pikepdf.Array(
        [head.xMin * scale, head.yMin * scale, head.xMax * scale, head.yMax * scale]
    )

    hhea = font["hhea"]
    ascent = hhea.ascent * scale
    descent = hhea.descent * scale

    if "OS/2" in font:
        cap_height = font["OS/2"].sCapHeight * scale
    else:
        cap_height = ascent

    italic_angle = font["post"].italicAngle

    # StemV has no exact measured field in TrueType hmtx/post/OS2 -- this is a fixed,
    # commented ESTIMATE (not a measured value), following the common convention of a
    # heavier estimate for bold weights.
    stem_v = 120 if subset.variant in ("Bold", "BoldItalic") else 80

    descriptor = pikepdf.Dictionary(
        {
            "/Type": pikepdf.Name("/FontDescriptor"),
            "/FontName": pikepdf.Name(f"/{font_name}"),
            "/Flags": flags,
            "/FontBBox": bbox,
            "/ItalicAngle": italic_angle,
            "/Ascent": ascent,
            "/Descent": descent,
            "/CapHeight": cap_height,
            "/StemV": stem_v,
            "/FontFile2": pikepdf.Stream(pdf, subset.data),
        }
    )
    return pdf.make_indirect(descriptor)


# WeasyPrint's verified fixed ToUnicode CMap HEADER/TRAILER byte shape (FONT-03), quoted
# key-for-key from 03-RESEARCH.md's own Code Examples section -- never a hand-rolled
# variant. Adobe-Identity-UCS is the standard CMap name for this purpose; NOT the same
# CIDSystemInfo as the font's own descendant dict, which uses Ordering=Identity, not
# Ordering=UCS.
_TOUNICODE_HEADER: tuple[bytes, ...] = (
    b"/CIDInit /ProcSet findresource begin",
    b"12 dict begin",
    b"begincmap",
    b"/CIDSystemInfo",
    b"<< /Registry (Adobe)",
    b"/Ordering (UCS)",
    b"/Supplement 0",
    b">> def",
    b"/CMapName /Adobe-Identity-UCS def",
    b"/CMapType 2 def",
    b"1 begincodespacerange",
    b"<0000> <ffff>",
    b"endcodespacerange",
)
_TOUNICODE_TRAILER: tuple[bytes, ...] = (
    b"endcmap",
    b"CMapName currentdict /CMap defineresource pop",
    b"end",
    b"end",
)
# Adobe's documented cap on codespacerange/bfchar block size -- matches
# `engine.encoding_table._parse_codespace_widths`'s own docstring for the read side.
_BFCHAR_BLOCK_SIZE = 100


def build_tounicode_cmap_bytes(cid_to_unicode: dict[int, str]) -> bytes:
    """FONT-03: a `/ToUnicode` CMap stream's bytes, mapping each CID to its source
    Unicode character(s) so copy-paste out of a viewer recovers real text.

    Fixed HEADER/TRAILER lines verbatim from 03-RESEARCH.md's WeasyPrint-sourced code
    example; between them, `sorted(cid_to_unicode)` chunked into groups of
    `_BFCHAR_BLOCK_SIZE` (Adobe's 100-per-block cap), each chunk its own
    `N beginbfchar` ... `<cid> <utf16be>` lines ... `endbfchar` block. Every line is
    joined with `b"\\n"`.
    """
    cids = sorted(cid_to_unicode)
    lines: list[bytes] = list(_TOUNICODE_HEADER)
    for start in range(0, len(cids), _BFCHAR_BLOCK_SIZE):
        chunk = cids[start : start + _BFCHAR_BLOCK_SIZE]
        lines.append(f"{len(chunk)} beginbfchar".encode())
        for cid in chunk:
            utf16be_hex = cid_to_unicode[cid].encode("utf-16-be").hex()
            lines.append(f"<{cid:04X}> <{utf16be_hex}>".encode())
        lines.append(b"endbfchar")
    lines.extend(_TOUNICODE_TRAILER)
    return b"\n".join(lines)


def embed_type0_font(
    pdf: pikepdf.Pdf,
    subset: SubsetFont,
    cid_widths: dict[int, float],
    cid_to_unicode: dict[int, str],
) -> pikepdf.Object:
    """FONT-03: assemble a full Type0/CIDFontType2 font object for `subset` and add it to
    `pdf` as a fresh indirect object -- the composed write-side entry point Tasks 1-2's
    pieces (`build_cid_font_descriptor`, `build_w_array`, `subset_cid_widths`) and this
    task's own `build_tounicode_cmap_bytes` all feed into.

    Precondition: `cid_widths` must come from `subset_cid_widths(subset)` (or a superset
    covering the same GIDs) -- this function does not itself re-derive widths from
    `subset`, it only serializes whatever `cid_widths` it is given (D-14).

    D-12/D-13 are enforced by this SIGNATURE, exactly as `build_cid_font_descriptor`
    already establishes: this function takes no existing font/FontDescriptor object as a
    parameter anywhere in its signature, so it has no way to reach into, and therefore
    cannot disturb, any pre-existing font object already in `pdf`.
    """
    font_descriptor = build_cid_font_descriptor(pdf, subset)
    base_font_name = _tagged_base_font_name(subset)

    cid_font = pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.CIDFontType2,
        BaseFont=pikepdf.Name(f"/{base_font_name}"),
        CIDSystemInfo=pikepdf.Dictionary(
            Registry=pikepdf.String("Adobe"),
            Ordering=pikepdf.String("Identity"),
            Supplement=0,
        ),
        CIDToGIDMap=pikepdf.Name.Identity,
        W=build_w_array(cid_widths),
        FontDescriptor=font_descriptor,
    )

    to_unicode_stream = pikepdf.Stream(pdf, build_tounicode_cmap_bytes(cid_to_unicode))

    type0 = pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type0,
        BaseFont=pikepdf.Name(f"/{base_font_name}"),
        Encoding=pikepdf.Name("/Identity-H"),
        DescendantFonts=pikepdf.Array([cid_font]),
        ToUnicode=to_unicode_stream,
    )
    return pdf.make_indirect(type0)


__all__ = [
    "BASE_FONT_MAPPING",
    "SEAM_ADVANCE_DELTA_PT",
    "BundledFamily",
    "BundledVariant",
    "FONTS_DIR",
    "NOTDEF_GLYPH_NAME",
    "MappingVerdict",
    "SubsetFont",
    "SubstitutionTrigger",
    "build_cid_font_descriptor",
    "build_tounicode_cmap_bytes",
    "build_w_array",
    "embed_type0_font",
    "has_unmapped_glyph",
    "liberation_advance_1000u",
    "liberation_font_path",
    "lookup_bundled_font",
    "reverse_encoding_map",
    "run_needs_substitution",
    "shape_cids",
    "shape_glyph_names",
    "subset_cid_widths",
    "subset_font_for_family",
    "subset_tag",
    "substitution_unicode_reason",
]
