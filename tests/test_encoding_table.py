"""TEXT-04 / D-04: the forward encoding decision table resolves every named branch.

TT-d and TT-e have ZERO instances in the 217-document corpus (measured by
tools/measure_truetype_cmap_gaps.py: 80 TT-b fonts, TT-d 0, TT-e 0). Asserting them
against real documents is therefore impossible, and asserting them against a counter that
is always 0 is the vacuous-check failure this phase keeps finding. They get synthetic
font programs instead, built here by packing a minimal sfnt.
"""

import hashlib
import io
import json
import struct
from collections.abc import Iterator
from pathlib import Path

import pikepdf
import playa
import pytest

from engine.encoding_table import (
    STANDARD_ENCODING,
    WIN_ANSI_ENCODING,
    FontProgram,
    FontVerdict,
    base_encoding,
    cid_width,
    embedded_font_bytes,
    encoding_map,
    glyph_presence,
    glyph_verdict,
    is_symbolic,
    parse_differences,
    resolve_font,
    type3_char_proc,
    type3_width,
)
from engine.records import GlyphRecord
from engine.types import CharCode, Unicode
from engine.walker import glyph_records

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"


def _sfnt_with_cmap(subtable_ids: set[tuple[int, int]] | None) -> bytes:
    """A minimal sfnt carrying only a cmap table with the given subtable ids.

    `None` means no cmap table at all (TT-e). Subtable bodies are format-6 stubs and are
    never read: cmap_subtable_ids parses only the directory, which is the whole point of
    that function.
    """
    tables: dict[bytes, bytes] = {}
    if subtable_ids is not None:
        ids = sorted(subtable_ids)
        body = struct.pack(">HH", 0, len(ids))
        offset = 4 + 8 * len(ids)
        for platform_id, plat_enc_id in ids:
            body += struct.pack(">HHI", platform_id, plat_enc_id, offset)
        for _ in ids:
            body += struct.pack(">HHHHH", 6, 10, 0, 0, 0)
        tables[b"cmap"] = body

    header = struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0)
    directory = b""
    data = b""
    offset = 12 + 16 * len(tables)
    for tag, body in tables.items():
        directory += struct.pack(">4sIII", tag, 0, offset + len(data), len(body))
        data += body + b"\x00" * ((4 - len(body) % 4) % 4)
    return header + directory + data


def _font(
    pdf: pikepdf.Pdf,
    subtype: str,
    *,
    symbolic: bool = False,
    encoding: object = None,
    base_font: str | None = None,
    program: bytes | None = None,
    program_key: str = "/FontFile2",
) -> pikepdf.Object:
    """Build a synthetic font dictionary. Descriptor is present only when it carries
    something -- a font with no /FontDescriptor is the non-embedded, non-symbolic case."""
    font: dict[str, object] = {"/Type": pikepdf.Name("/Font"), "/Subtype": pikepdf.Name(subtype)}
    if base_font is not None:
        font["/BaseFont"] = pikepdf.Name("/" + base_font)
    if encoding is not None:
        font["/Encoding"] = encoding

    if symbolic or program is not None:
        desc: dict[str, object] = {"/Type": pikepdf.Name("/FontDescriptor")}
        desc["/Flags"] = 4 if symbolic else 32
        if program is not None:
            desc[program_key] = pdf.make_stream(program)
        font["/FontDescriptor"] = pdf.make_indirect(pikepdf.Dictionary(desc))
    return pdf.make_indirect(pikepdf.Dictionary(font))


def _cmap_stream(pdf: pikepdf.Pdf, ranges: list[tuple[bytes, bytes]]) -> pikepdf.Object:
    """A minimal embedded CMap stream carrying only a begincodespacerange block --
    everything `_codespace_widths` needs and nothing else. Not a full CMap program."""
    body = f"{len(ranges)} begincodespacerange\n".encode()
    for lo, hi in ranges:
        body += b"<" + lo.hex().encode() + b"> <" + hi.hex().encode() + b">\n"
    body += b"endcodespacerange\n"
    return pdf.make_stream(body)


def _type0_font(
    pdf: pikepdf.Pdf,
    *,
    encoding: object = pikepdf.Name("/Identity-H"),
    cid_subtype: str = "/CIDFontType2",
    cid_to_gid: object = pikepdf.Name("/Identity"),
    program: bytes | None = b"dummy-truetype-program",
    program_key: str = "/FontFile2",
) -> pikepdf.Object:
    """A synthetic Type0 font dictionary with one descendant CIDFont."""
    desc: dict[str, object] = {"/Type": pikepdf.Name("/FontDescriptor"), "/Flags": 4}
    if program is not None:
        desc[program_key] = pdf.make_stream(program)
    descendant: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name(cid_subtype),
        "/DW": 1000,
        "/FontDescriptor": pdf.make_indirect(pikepdf.Dictionary(desc)),
    }
    if cid_subtype == "/CIDFontType2":
        descendant["/CIDToGIDMap"] = cid_to_gid
    font: dict[str, object] = {
        "/Type": pikepdf.Name("/Font"),
        "/Subtype": pikepdf.Name("/Type0"),
        "/Encoding": encoding,
        "/DescendantFonts": pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(descendant))]),
    }
    return pdf.make_indirect(pikepdf.Dictionary(font))


def _first_type3_font(pdf: pikepdf.Pdf) -> pikepdf.Object:
    for page in pdf.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get("/Font")
        if fonts is None:
            continue
        for _key, font in fonts.items():
            if str(font.get("/Subtype")) == "/Type3":
                return font
    raise AssertionError("no Type3 font found")


def _first_font_with_program(
    pdf: pikepdf.Pdf, subtypes: tuple[str, ...], program_key: str
) -> pikepdf.Object:
    for page in pdf.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get("/Font")
        if fonts is None:
            continue
        for _key, font in fonts.items():
            if str(font.get("/Subtype")) not in subtypes:
                continue
            descriptor = font.get("/FontDescriptor")
            if descriptor is None or descriptor.get(program_key) is None:
                continue
            return font
    raise AssertionError(f"no {subtypes} font with {program_key!r} found")


def _first_type0_descendant(pdf: pikepdf.Pdf, descendant_subtype: str) -> pikepdf.Object:
    for page in pdf.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get("/Font")
        if fonts is None:
            continue
        for _key, font in fonts.items():
            if str(font.get("/Subtype")) != "/Type0":
                continue
            descendants = font.get("/DescendantFonts")
            if not descendants:
                continue
            if str(descendants[0].get("/Subtype")) == descendant_subtype:
                return font
    raise AssertionError(f"no Type0 font with descendant {descendant_subtype!r} found")


@pytest.fixture
def pdf() -> pikepdf.Pdf:
    return pikepdf.Pdf.new()


# --------------------------------------------------------------------------------------
# Base encoding and /Differences
# --------------------------------------------------------------------------------------


def test_win_ansi_annex_d_overrides() -> None:
    """The only two WinAnsi codes that are not plain cp1252. Goes red if the derivation
    in _build_win_ansi loses its two explicit fixups -- both derive to None without them."""
    assert WIN_ANSI_ENCODING[0xA0] == "space"
    assert WIN_ANSI_ENCODING[0xAD] == "hyphen"
    # Spot-check the derived body, including the slots most often got wrong.
    assert WIN_ANSI_ENCODING[0x41] == "A"
    assert WIN_ANSI_ENCODING[0x80] == "Euro"
    assert WIN_ANSI_ENCODING[0x92] == "quoteright"
    assert WIN_ANSI_ENCODING[0x27] == "quotesingle"


def test_differences_integer_resets_the_counter() -> None:
    """/Differences is [code name name ... code name ...], NOT pairs.

    Goes red if parsed as a pairwise zip: that reading gives {1:'a', 3:'c'} here and drops
    'b' and 'd' entirely, the off-by-one that presents as "all letters shifted by one".
    """
    diffs = pikepdf.Array(
        [1, pikepdf.Name("/a"), pikepdf.Name("/b"), 10, pikepdf.Name("/c"), pikepdf.Name("/d")]
    )
    assert parse_differences(diffs) == {1: "a", 2: "b", 10: "c", 11: "d"}


def test_base_encoding_steps(pdf: pikepdf.Pdf) -> None:
    """B1-B6 select the documented base. B4/B6 return None: the font PROGRAM's built-in
    encoding is not in the object graph, and None means "ask the program", not "unknown"."""
    named = _font(pdf, "/Type1", encoding=pikepdf.Name("/WinAnsiEncoding"))
    assert base_encoding(named) == ("B1", WIN_ANSI_ENCODING)

    with_base = _font(
        pdf,
        "/Type1",
        encoding=pikepdf.Dictionary({"/BaseEncoding": pikepdf.Name("/MacRomanEncoding")}),
    )
    assert base_encoding(with_base)[0] == "B2"

    dict_nonsym = _font(pdf, "/Type1", encoding=pikepdf.Dictionary({}))
    assert base_encoding(dict_nonsym) == ("B3", STANDARD_ENCODING)

    dict_sym = _font(pdf, "/Type1", symbolic=True, encoding=pikepdf.Dictionary({}))
    assert base_encoding(dict_sym) == ("B4", None)

    absent_nonsym = _font(pdf, "/Type1")
    assert absent_nonsym.get("/Encoding") is None
    assert base_encoding(absent_nonsym) == ("B5", STANDARD_ENCODING)

    absent_sym = _font(pdf, "/Type1", symbolic=True)
    assert base_encoding(absent_sym) == ("B6", None)


def test_encoding_map_overlays_differences_on_base(pdf: pikepdf.Pdf) -> None:
    font = _font(
        pdf,
        "/Type1",
        encoding=pikepdf.Dictionary(
            {
                "/BaseEncoding": pikepdf.Name("/WinAnsiEncoding"),
                "/Differences": pikepdf.Array([0x41, pikepdf.Name("/alpha")]),
            }
        ),
    )
    mapping = encoding_map(font)
    assert mapping[0x41] == "alpha"  # overlaid
    assert mapping[0x42] == "B"  # base survives


# --------------------------------------------------------------------------------------
# One assertion per named branch
# --------------------------------------------------------------------------------------


def test_branch_t1_a_embedded_nonsymbolic(pdf: pikepdf.Pdf) -> None:
    font = _font(pdf, "/Type1", program=b"dummy-type1", program_key="/FontFile")
    verdict = resolve_font(font)
    assert verdict.branch_id == "T1-a"
    assert verdict.editable and not verdict.substitution


def test_branch_t1_b_symbolic_with_encoding_is_editable(pdf: pikepdf.Pdf) -> None:
    """THE corrected finding (TEXT-04). 9.6.6.2 gives /Differences precedence over the
    built-in encoding unconditionally; Symbolic only selects which base it overlays.
    Refusing this branch costs 23% of the corpus -- see the Pitfall-2 test below."""
    font = _font(
        pdf,
        "/Type1",
        symbolic=True,
        encoding=pikepdf.Dictionary({"/Differences": pikepdf.Array([1, pikepdf.Name("/a")])}),
        program=b"dummy-type1",
        program_key="/FontFile",
    )
    verdict = resolve_font(font)
    assert verdict.branch_id == "T1-b"
    assert verdict.editable is True


def test_branch_t1_c_standard14_not_embedded(pdf: pikepdf.Pdf) -> None:
    font = _font(pdf, "/Type1", base_font="Helvetica")
    verdict = resolve_font(font)
    assert verdict.branch_id == "T1-c"
    assert verdict.editable and verdict.substitution


def test_branch_t1_d_not_embedded_not_standard14(pdf: pikepdf.Pdf) -> None:
    font = _font(pdf, "/Type1", base_font="SomeVendorFont-Regular")
    verdict = resolve_font(font)
    assert verdict.branch_id == "T1-d"
    assert verdict.editable and verdict.substitution


def test_branch_t1_c_strips_subset_tag(pdf: pikepdf.Pdf) -> None:
    """A subset tag must not push a Standard-14 face onto T1-d. Goes red if the six-letter
    +tag strip is dropped."""
    font = _font(pdf, "/Type1", base_font="ABCDEF+Helvetica")
    assert resolve_font(font).branch_id == "T1-c"


def test_branch_tt_a_nonsymbolic(pdf: pikepdf.Pdf) -> None:
    font = _font(
        pdf, "/TrueType", encoding=pikepdf.Name("/WinAnsiEncoding"), program=_sfnt_with_cmap({(3, 1)})
    )
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-a"
    assert verdict.editable


def test_branch_tt_b_symbolic_no_encoding(pdf: pikepdf.Pdf) -> None:
    font = _font(pdf, "/TrueType", symbolic=True, program=_sfnt_with_cmap({(3, 0), (1, 0)}))
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-b"
    assert verdict.editable


def test_branch_tt_c_symbolic_with_encoding_refuses(pdf: pikepdf.Pdf) -> None:
    """A-1. The genuinely ambiguous branch: pdf.js, PDFBox and PDFium each tie-break
    differently, so it is correctly refused rather than guessed."""
    font = _font(
        pdf,
        "/TrueType",
        symbolic=True,
        encoding=pikepdf.Name("/WinAnsiEncoding"),
        program=_sfnt_with_cmap({(3, 0)}),
    )
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-c"
    assert not verdict.editable and verdict.reason is not None


def test_branch_tt_d_only_3_1_cmap_refuses(pdf: pikepdf.Pdf) -> None:
    """A-2, on a synthetic program -- the corpus contains zero of these, so a
    corpus-derived assertion here would be vacuously green."""
    font = _font(pdf, "/TrueType", symbolic=True, program=_sfnt_with_cmap({(3, 1)}))
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-d"
    assert not verdict.editable


def test_branch_tt_e_no_cmap_refuses(pdf: pikepdf.Pdf) -> None:
    """A-3, synthetic for the same reason as TT-d."""
    font = _font(pdf, "/TrueType", symbolic=True, program=_sfnt_with_cmap(None))
    verdict = resolve_font(font)
    assert verdict.branch_id == "TT-e"
    assert not verdict.editable


def test_branch_noemb_symbolic_not_embedded(pdf: pikepdf.Pdf) -> None:
    """A-5, and it must outrank TT-c: with no program there is nothing to consult, which
    is an information gap rather than a spec ambiguity."""
    font = _font(pdf, "/TrueType", symbolic=True, encoding=pikepdf.Name("/WinAnsiEncoding"))
    verdict = resolve_font(font)
    assert verdict.branch_id == "NOEMB"
    assert not verdict.editable


def test_type0_with_no_descendant_fonts_fails_closed(pdf: pikepdf.Pdf) -> None:
    """Was test_type0_and_type3_defer_and_fail_closed pre-02-06-Task-2: Type0/Type3 no
    longer defer -- they resolve through C-1..C-6 and T3-a below. What remains genuinely
    unresolvable is a Type0 font missing /DescendantFonts entirely, which must still fail
    closed rather than crash.

    IMPORTANT 6: this is not any of C-1..C-6 (none of those steps can even begin without
    a descendant font), so it gets its own id ("NODESC") rather than borrowing "C-1" --
    a borrowed id would corrupt the D-04 census, which counts branch_id occurrences."""
    verdict = resolve_font(_font(pdf, "/Type0"))
    assert verdict.branch_id == "NODESC"
    assert not verdict.editable


def test_type3_with_no_charprocs_fails_closed(pdf: pikepdf.Pdf) -> None:
    """T3-a "always" resolves -- except a Type3 font with no /CharProcs at all has
    nothing for ANY code to resolve against, which must still fail closed."""
    verdict = resolve_font(_font(pdf, "/Type3"))
    assert not verdict.editable


# --------------------------------------------------------------------------------------
# Type0 / CID branches (C-1..C-6)
# --------------------------------------------------------------------------------------


def test_branch_c3b_cid_keyed_cff_real_corpus_font() -> None:
    """C-3b, acceptance criterion: irs_publication_17.pdf embeds NotoSansCJKjp-Regular as
    CID-keyed CFF (CIDFontType0C) with live CJK (02-RESEARCH.md's PLAYA-DECISION.md-cited
    verification). Resolves through the CFF charset -- this font's /CIDToGIDMap key does
    not even exist, so a resolve_font that mistakenly consulted it would KeyError, not
    silently misclassify; the real assertion is the branch_id itself.

    MUTATION: swapping the returned branch_id from "C-3b" to "C-3a" for the CIDFontType0
    case flips this test red -- confirmed by running that swap once.
    """
    pdf = pikepdf.open(CORPUS_DIR / "irs_publication_17.pdf")
    try:
        font = _first_type0_descendant(pdf, "/CIDFontType0")
        verdict = resolve_font(font)
        assert verdict.branch_id == "C-3b"
        assert verdict.editable and not verdict.substitution
    finally:
        pdf.close()


def test_branch_c3a_cidfonttype2_identity(pdf: pikepdf.Pdf) -> None:
    font = _type0_font(pdf, cid_subtype="/CIDFontType2", cid_to_gid=pikepdf.Name("/Identity"))
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-3a"
    assert verdict.editable


def test_branch_c3a_cidfonttype2_binary_stream_not_just_identity(pdf: pikepdf.Pdf) -> None:
    """C-3a's other legal shape -- a binary big-endian 2-byte-per-CID stream. Handling
    only /Identity is correct on 9,760 of 10,114 measured corpus occurrences and garbage
    on the other 97; this proves the stream shape is accepted, not just the name."""
    stream = pdf.make_stream(struct.pack(">HHHH", 0, 5, 0, 6))
    font = _type0_font(pdf, cid_subtype="/CIDFontType2", cid_to_gid=stream)
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-3a"
    assert verdict.editable


def test_branch_c3a_malformed_cidtogidmap_stream_refuses(pdf: pikepdf.Pdf) -> None:
    """MUTATION PROOF for the stream-shape check: an odd-length stream is not a whole
    number of 2-byte GIDs and must refuse. Confirmed to go red if the `len(data) % 2`
    guard in `_cid_to_gid_map_ok` is deleted -- run once."""
    stream = pdf.make_stream(b"\x00\x05\x00")  # 3 bytes: not divisible by 2
    font = _type0_font(pdf, cid_subtype="/CIDFontType2", cid_to_gid=stream)
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-3a"
    assert not verdict.editable


def test_branch_c6_mixed_codespace_refuses(pdf: pikepdf.Pdf) -> None:
    """C-6, acceptance criterion: a CMap declaring both a 1-byte and a 2-byte codespace
    range (the classic Shift-JIS shape) must refuse rather than guess which width a given
    code uses.

    MUTATION: computing the width set from only the FIRST hex string instead of ALL of
    them (`{len(hexes[0]) // 2}`) hides the mismatch and this test goes red -- confirmed
    by running that mutation once.
    """
    cmap = _cmap_stream(pdf, [(b"\x00", b"\x80"), (b"\x81\x40", b"\xfe\xfc")])
    font = _type0_font(pdf, encoding=cmap)
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-6"
    assert not verdict.editable


def test_branch_c6_mixed_codespace_across_multiple_blocks_refuses(pdf: pikepdf.Pdf) -> None:
    """IMPORTANT 3: CMaps split codespace ranges across multiple begincodespacerange
    blocks (Adobe's 100-range-per-block limit). Same mismatch as the test above, but
    split across two separate blocks -- inspecting only the first block misses it.

    MUTATION: reverting `_parse_codespace_widths` to `re.search` (first block only,
    `_CODESPACE_RANGE_RE.search` instead of `.finditer`) flips this red -- confirmed by
    running that reversion once.
    """
    body = (
        b"1 begincodespacerange\n<00> <80>\nendcodespacerange\n"
        b"1 begincodespacerange\n<8140> <fefc>\nendcodespacerange\n"
    )
    cmap = pdf.make_stream(body)
    font = _type0_font(pdf, encoding=cmap)
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-6"
    assert not verdict.editable


def test_branch_c1_uniform_codespace_from_embedded_cmap_stream_resolves(pdf: pikepdf.Pdf) -> None:
    """C-1: a uniform-width codespace read off an embedded CMap stream (not just the
    Identity-H/V shortcut) resolves normally."""
    cmap = _cmap_stream(pdf, [(b"\x00\x00", b"\xff\xff")])
    font = _type0_font(pdf, encoding=cmap)
    verdict = resolve_font(font)
    assert verdict.editable


def test_branch_c1_named_cmap_without_resource_data_refuses(pdf: pikepdf.Pdf) -> None:
    """IMPORTANT 6: a predefined named CMap other than Identity-H/V has no resource data
    anywhere in the PDF object graph to resolve its codespace from -- refuse rather than
    assume 2 bytes. This fails at the bytes->code step (C-1), not code->CID (C-2): C-2 is
    a different, later question this module never reaches for an unresolvable CMap."""
    font = _type0_font(pdf, encoding=pikepdf.Name("/UniGB-UCS2-H"))
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-1"
    assert not verdict.editable


def test_branch_c3_unrecognised_cidfont_subtype_refuses(pdf: pikepdf.Pdf) -> None:
    """IMPORTANT 6: an unrecognised descendant /Subtype (neither CIDFontType0 nor
    CIDFontType2) is a C-3 (CID->GID) question -- which mechanism applies -- not a C-1
    (codespace) question; the codespace itself (Identity-H) resolved fine here."""
    font = _type0_font(pdf, cid_subtype="/CIDFontType9")
    verdict = resolve_font(font)
    assert verdict.branch_id == "C-3"
    assert not verdict.editable


def test_cid_width_w_array_and_dw_default(pdf: pikepdf.Pdf) -> None:
    """C-4: the nested run-length /W format, both shapes -- `c [w w w]` and
    `cFirst cLast w` -- plus the /DW default."""
    descendant = pikepdf.Dictionary(
        {
            "/W": pikepdf.Array([3, pikepdf.Array([100, 200, 300]), 10, 15, 500]),
            "/DW": 750,
        }
    )
    assert cid_width(descendant, 3) == 100.0
    assert cid_width(descendant, 4) == 200.0
    assert cid_width(descendant, 12) == 500.0
    assert cid_width(descendant, 999) == 750.0  # falls through to /DW


def test_cid_width_defaults_to_1000_never_missingwidth(pdf: pikepdf.Pdf) -> None:
    """C-4: default is 1000, and /MissingWidth (a simple-font-only key) must never leak
    in. MUTATION: reading /MissingWidth instead of /DW flips this red -- confirmed by
    running that swap once."""
    descendant = pikepdf.Dictionary({"/MissingWidth": 42})
    assert cid_width(descendant, 5) == 1000.0


def test_cid_width_malformed_w_does_not_raise(pdf: pikepdf.Pdf) -> None:
    """IMPORTANT 4: /W's shape is attacker-controlled (an untrusted upload) and must
    classify rather than crash. `/W [3 [100] 10]` has a dangling cFirst=10 with no
    cLast/width after it; `/W [3]` has a bare code with nothing after it at all. Both
    used to raise IndexError."""
    descendant = pikepdf.Dictionary(
        {"/W": pikepdf.Array([3, pikepdf.Array([100]), 10]), "/DW": 750}
    )
    assert cid_width(descendant, 999) == 750.0  # falls through past the malformed tail

    descendant2 = pikepdf.Dictionary({"/W": pikepdf.Array([3])})
    assert cid_width(descendant2, 999) == 1000.0  # falls through to the bare /DW default


# --------------------------------------------------------------------------------------
# Type3 (T3-a)
# --------------------------------------------------------------------------------------


def test_branch_t3a_always_editable(pdf: pikepdf.Pdf) -> None:
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/Type3"),
                "/CharProcs": pikepdf.Dictionary({"/g1": pdf.make_stream(b"1 0 0 1 0 0 d0")}),
                "/Encoding": pikepdf.Dictionary(
                    {"/Differences": pikepdf.Array([65, pikepdf.Name("/g1")])}
                ),
                "/FontMatrix": pikepdf.Array([0.001, 0, 0, 0.001, 0, 0]),
            }
        )
    )
    verdict = resolve_font(font)
    assert verdict.branch_id == "T3-a"
    assert verdict.editable and not verdict.substitution


def test_type3_char_proc_resolves_name_through_charprocs(pdf: pikepdf.Pdf) -> None:
    stream = pdf.make_stream(b"1 0 0 1 0 0 d0")
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            {
                "/Type": pikepdf.Name("/Font"),
                "/Subtype": pikepdf.Name("/Type3"),
                "/CharProcs": pikepdf.Dictionary({"/g1": stream}),
                "/Encoding": pikepdf.Dictionary(
                    {"/Differences": pikepdf.Array([65, pikepdf.Name("/g1")])}
                ),
            }
        )
    )
    proc = type3_char_proc(font, 65)
    assert proc is not None
    assert bytes(proc.read_bytes()) == b"1 0 0 1 0 0 d0"
    assert type3_char_proc(font, 66) is None  # no glyph name at that code


def test_type3_width_scaled_by_fontmatrix_not_divided_by_1000() -> None:
    """T3-a width, verified against playa's own displacement on two real fixtures with
    different /FontMatrix scales (02-RESEARCH.md Section 1: the verapdf fixture's
    FontMatrix 0.001 produces displacement 12.0 at `12 Tf`; govdocs1_000_000135.pdf's
    FontMatrix 1.0 produces displacement 1.92 -- both playa-verified). `type3_width`
    returns the per-em value BEFORE font-size scaling (Tf lives in the content stream,
    not the font dict), so the assertion multiplies by the known font size rather than
    comparing bare.

    MUTATION: dividing by 1000 instead of multiplying by /FontMatrix[0] gives 1.0 * 0.001
    = 0.001 on the verapdf fixture (should be 1.0) -- confirmed to go red by running that
    swap once.
    """
    pdf = pikepdf.open(CORPUS_DIR / "verapdf_type3_font_fixture.pdf")
    try:
        font = _first_type3_font(pdf)
        assert type3_width(font, 97) == pytest.approx(1.0)  # 1000 * 0.001
        assert type3_width(font, 97) * 12 == pytest.approx(12.0)  # "/F1 12 Tf" in the fixture
    finally:
        pdf.close()

    pdf = pikepdf.open(CORPUS_DIR / "govdocs1_000_000135.pdf")
    try:
        font = _first_type3_font(pdf)
        assert type3_width(font, 0) == pytest.approx(1.0)  # 1.0 * 1.0
    finally:
        pdf.close()


# --------------------------------------------------------------------------------------
# glyph_presence (A-6)
# --------------------------------------------------------------------------------------


def test_glyph_presence_cff_cid_keyed_present_and_absent() -> None:
    """A-6, acceptance criterion: real CID-keyed CFF data from irs_publication_17.pdf.
    CID 1 ("cid00001") is a real glyph in the embedded program; CID 999999 is not, and
    downgrades rather than refuses."""
    pdf = pikepdf.open(CORPUS_DIR / "irs_publication_17.pdf")
    try:
        font = _first_type0_descendant(pdf, "/CIDFontType0")
        verdict = resolve_font(font)
        assert verdict.branch_id == "C-3b"
        descendant = font.get("/DescendantFonts")[0]
        program = embedded_font_bytes(descendant.get("/FontDescriptor"))
        assert program is not None
    finally:
        pdf.close()

    present_editable, present_sub = glyph_presence(verdict, 1, program)
    assert present_editable and not present_sub

    missing_editable, missing_sub = glyph_presence(verdict, 999999, program)
    assert missing_editable and missing_sub  # A-6: downgrade, not a refusal


def test_glyph_presence_truetype_gid_present_and_absent() -> None:
    """Same shape, TrueType: irs_publication_17.pdf's embedded HelveticaWorld-Regular has
    1,862 glyphs (measured); GID 3 ("space") exists, GID 999999 does not."""
    pdf = pikepdf.open(CORPUS_DIR / "irs_publication_17.pdf")
    try:
        font = _first_type0_descendant(pdf, "/CIDFontType2")
        verdict = resolve_font(font)
        assert verdict.branch_id == "C-3a"
        descendant = font.get("/DescendantFonts")[0]
        program = embedded_font_bytes(descendant.get("/FontDescriptor"))
        assert program is not None
    finally:
        pdf.close()

    present_editable, present_sub = glyph_presence(verdict, 3, program)
    assert present_editable and not present_sub

    missing_editable, missing_sub = glyph_presence(verdict, 999999, program)
    assert missing_editable and missing_sub


def test_glyph_presence_type1_real_pdf_fontfile_finds_known_glyph() -> None:
    """CRITICAL 1/2: a PDF /FontFile is NOT a PFA or PFB -- it is the raw Type1 program
    segmented by /Length1//Length2//Length3 with a BINARY eexec section (ISO 32000-1
    Table 111). Writing raw bytes straight to a font-program reader fails on most real
    fonts (see the report for the full corpus-wide re-measurement).

    govdocs1_012_012087.pdf's embedded Type1 font has a real '.notdef' glyph. Finding it
    proves the fix on THIS font, not just the absence of a crash -- a downgrade
    (found=False) would pass just as silently as the bug this test exists to catch.

    NOT SUFFICIENT ON ITS OWN (round 2 review, confirmed): this font happens to be one
    that already worked before round 2's fix, so this test alone cannot see round 2's
    defect (trailer NUL / encoding / mandatory-Subrs). Only a corpus-wide rate can --
    see test_type1_fontfile_corpus_wide_parse_rate below, which is this defect's real
    acceptance test.
    """
    pdf = pikepdf.open(CORPUS_DIR / "govdocs1_012_012087.pdf")
    try:
        font = _first_font_with_program(pdf, ("/Type1", "/MMType1"), "/FontFile")
        verdict = resolve_font(font)
        program = embedded_font_bytes(font.get("/FontDescriptor"))
        assert program is not None
    finally:
        pdf.close()

    editable, substitution = glyph_presence(verdict, ".notdef", program)
    assert editable is True
    assert substitution is False  # found in the ORIGINAL program -- not downgraded


@pytest.mark.corpus
def test_type1_fontfile_corpus_wide_parse_rate() -> None:
    """CRITICAL 1, round 2's actual acceptance criterion: A-6's downgrade never refuses,
    so a single font passing proves nothing about the population -- the corpus-wide
    parse rate is the ONLY signal that exists for a regression on this code path.

    Measured through the real production path (embedded_font_bytes + glyph_presence),
    deduped by content sha256 across corpus/public: 176 unique embedded /FontFile
    programs (177 by (document, stream object) -- one exact byte-for-byte duplicate
    shared by two documents).

    MEASURED (round 2, all three fixes -- trailer-NUL strip, latin-1, bypassing
    t1Lib.T1Font's mandatory-but-optional /Subrs access): 176/176 (100%). Pinned at that
    ceiling: a rate that can only go DOWN from here is exactly the tripwire this needs.
    round 1's fix alone (PFB rewrap, no trailer/encoding/Subrs fix) measured 87/176.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())
    results: dict[str, bool] = {}

    for entry in manifest:
        path = CORPUS_DIR / entry["filename"]
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
                    if str(font.get("/Subtype")) not in ("/Type1", "/MMType1"):
                        continue
                    descriptor = font.get("/FontDescriptor")
                    if descriptor is None:
                        continue
                    font_file = descriptor.get("/FontFile")
                    if font_file is None:
                        continue
                    digest = hashlib.sha256(bytes(font_file.read_bytes())).hexdigest()
                    if digest in results:
                        continue  # already measured this exact program (cross-document dup)
                    program = embedded_font_bytes(descriptor)
                    assert program is not None
                    verdict = FontVerdict("T1-a", True, False)  # generic editable verdict
                    _editable, substitution = glyph_presence(verdict, ".notdef", program)
                    results[digest] = not substitution  # found in the ORIGINAL program
        except Exception:  # noqa: BLE001
            pass
        finally:
            pdf.close()

    total = len(results)
    parsed = sum(1 for ok in results.values() if ok)
    # Guards the denominator too: a shrunken local corpus silently measuring a smaller,
    # easier population would be exactly the vacuous-check trap this phase keeps finding.
    assert total >= 176, f"expected at least 176 unique embedded /FontFile programs, got {total}"
    assert parsed == total, (
        f"Type1 /FontFile parse rate regressed: {parsed}/{total} -- ceiling is 176/176"
    )


def test_glyph_presence_downgrades_on_unparseable_program() -> None:
    """A-6, controller ambiguity #1: bytes fontTools cannot parse at all downgrade
    (editable=True, substitution=True) -- the same shape as "parsed but glyph missing".
    See `glyph_presence`'s docstring for the mutation proof (returning (False, False)
    from the except branch), run once and confirmed to flip this red."""
    verdict = FontVerdict("TT-b", True, False)
    editable, substitution = glyph_presence(verdict, 5, FontProgram(b"not a font program"))
    assert editable is True
    assert substitution is True


def test_glyph_presence_no_program_downgrades(pdf: pikepdf.Pdf) -> None:
    """No program at all (e.g. T1-c/T1-d substitution fonts) is nothing to check
    presence against -- downgrades rather than crashing on empty bytes."""
    verdict = FontVerdict("T1-c", True, True)
    editable, substitution = glyph_presence(verdict, "A", None)
    assert editable is True
    assert substitution is True


def test_glyph_presence_honors_font_level_refusal() -> None:
    """IMPORTANT 5: a font resolve_font already refused (e.g. TT-c) must not have any of
    its glyphs reported as present/editable by glyph_presence -- it must agree with
    glyph_verdict, which already propagated font-level refusals the same way. Checked
    even with no program bytes at all, since the font-level check must come first.

    MUTATION PROOF: deleting the `if not font_verdict.editable: return False, False`
    guard flips this red (falls through to the no-program-bytes downgrade, `(True,
    True)`) -- confirmed by running that deletion once (see the report).
    """
    verdict = FontVerdict("TT-c", False, False, "TrueType symbolic with /Encoding present")
    editable, substitution = glyph_presence(verdict, 5, None)
    assert editable is False
    assert substitution is False


# --------------------------------------------------------------------------------------
# glyph_verdict (A-8, D-05)
# --------------------------------------------------------------------------------------


def test_glyph_verdict_a8_refuses_glyph_not_font_or_run() -> None:
    """A-8/D-05, acceptance criterion, on real data: govdocs1_000_000135.pdf's Type3
    glyphs have cid=0, text='' (no /ToUnicode and no AGL-derivable name -- playa's own
    resolution already tried and came up empty). glyph_verdict refuses that ONE glyph;
    the font's own verdict (T3-a, always editable) proves the refusal does not cascade.
    """
    doc = playa.open(str(CORPUS_DIR / "govdocs1_000_000135.pdf"))
    try:
        record = None
        for page in doc.pages:
            for rec in glyph_records(page, doc):
                if rec.code == 0 and rec.unicode == "":
                    record = rec
                    break
            if record is not None:
                break
    finally:
        doc.close()

    assert record is not None, "expected the known cid=0/text='' Type3 glyph"

    font_verdict = FontVerdict("T3-a", True, False)
    verdict = glyph_verdict(font_verdict, record)
    assert verdict.editable is False
    assert verdict.reason == "NOUNI"

    # IMPORTANT 7: `assert font_verdict.editable is True` here (the old version of this
    # assertion) is VACUOUS -- font_verdict is a frozen dataclass local variable nothing
    # above touches, so it is trivially True under every possible mutation, including a
    # real cascade bug. The real proof that the refusal did not cascade is re-resolving
    # the ACTUAL font dict from the ACTUAL document, independently of the glyph_verdict
    # call above, and confirming the font-level verdict is still editable.
    pdf = pikepdf.open(CORPUS_DIR / "govdocs1_000_000135.pdf")
    try:
        font = _first_type3_font(pdf)
        assert resolve_font(font).editable is True
    finally:
        pdf.close()


def test_glyph_verdict_falsy_not_just_none() -> None:
    """MUTATION PROOF: checking `unicode is None` instead of falsy passes a record whose
    unicode is '' straight through as editable, which is wrong -- confirmed by running
    that swap once against this exact case (mirrors the real govdocs1_000_000135.pdf
    shape above, as a fast synthetic check that doesn't depend on corpus data)."""
    record = GlyphRecord(
        code=CharCode(0),
        glyph=None,
        unicode=Unicode(""),
        x=0.0,
        y=0.0,
        advance=(0.0, 0.0),
        font_id=0,
        render_mode=0,
        visible=True,
        stream_id=0,
        operator_byte_offset=0,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )
    verdict = glyph_verdict(FontVerdict("T3-a", True, False), record)
    assert verdict.editable is False
    assert verdict.reason == "NOUNI"


def test_glyph_verdict_present_unicode_is_editable() -> None:
    record = GlyphRecord(
        code=CharCode(65),
        glyph=None,
        unicode=Unicode("A"),
        x=0.0,
        y=0.0,
        advance=(0.0, 0.0),
        font_id=0,
        render_mode=0,
        visible=True,
        stream_id=0,
        operator_byte_offset=0,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )
    verdict = glyph_verdict(FontVerdict("T1-a", True, False), record)
    assert verdict.editable is True
    assert verdict.reason is None


def test_glyph_verdict_propagates_font_level_refusal() -> None:
    """A font resolve_font already refused (e.g. TT-c) is refused per-glyph too -- not a
    new cascade, since the font was already refused before this is ever called."""
    record = GlyphRecord(
        code=CharCode(65),
        glyph=None,
        unicode=Unicode("A"),
        x=0.0,
        y=0.0,
        advance=(0.0, 0.0),
        font_id=0,
        render_mode=0,
        visible=True,
        stream_id=0,
        operator_byte_offset=0,
        item_index_within_tj=None,
        byte_offset_within_string=0,
    )
    verdict = glyph_verdict(FontVerdict("TT-c", False, False, "TT-c"), record)
    assert verdict.editable is False
    assert verdict.reason == "TT-c"


# --------------------------------------------------------------------------------------
# Pitfall 2 -- the permanent regression guard
# --------------------------------------------------------------------------------------


def _collapsed_is_refused(font: pikepdf.Object) -> bool:
    """The BUG, implemented deliberately: branch on `symbolic and has_encoding` BEFORE
    looking at /Subtype, so Type1 and TrueType share one rule."""
    descriptor = font.get("/FontDescriptor")
    flags = None if descriptor is None else descriptor.get("/Flags")
    symbolic = flags is not None and bool(int(flags) & 4)
    return symbolic and font.get("/Encoding") is not None


@pytest.mark.corpus
def test_pitfall_2_collapsed_branch_inflates_refusals() -> None:
    """02-RESEARCH.md Pitfall 2, measured: collapsing Type1 into TrueType's symbolic rule
    refuses ~23% of documents instead of ~2% at this branch.

    The stated warning sign is "the measured refusal rate lands near 23%". This test
    encodes both sides: the correct table must refuse TT-c on few documents, and the
    collapsed rule must refuse on an order of magnitude more. Goes red if resolve_font
    starts refusing T1-b -- the two populations converge and the ratio collapses.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())

    correct_refused: set[str] = set()
    collapsed_refused: set[str] = set()
    scanned = 0

    for entry in manifest:
        path = CORPUS_DIR / entry["filename"]
        if not path.exists():
            continue
        try:
            pdf = pikepdf.open(path)
        except Exception:  # noqa: BLE001 - encrypted/broken files are not this test's subject
            continue
        scanned += 1
        try:
            for page in pdf.pages:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                fonts = resources.get("/Font")
                if fonts is None:
                    continue
                for _key, font in fonts.items():
                    if resolve_font(font).branch_id == "TT-c":
                        correct_refused.add(entry["filename"])
                    if _collapsed_is_refused(font):
                        collapsed_refused.add(entry["filename"])
        except Exception:  # noqa: BLE001
            pass
        finally:
            pdf.close()

    correct_rate = len(correct_refused) / scanned
    collapsed_rate = len(collapsed_refused) / scanned

    assert correct_rate < 0.05, f"TT-c refusal rate {correct_rate:.1%} -- expected about 2%"
    assert collapsed_rate > 0.15, (
        f"the collapsed rule only refused {collapsed_rate:.1%}; if this is no longer the "
        f"inflated population, Pitfall 2 no longer reproduces and this guard is vacuous"
    )
    assert collapsed_rate > correct_rate * 5, (
        f"collapsed {collapsed_rate:.1%} vs correct {correct_rate:.1%} -- the two rules "
        f"have converged, which means resolve_font is refusing T1-b"
    )


# --------------------------------------------------------------------------------------
# 02-06 Task 3 -- corpus-wide branch coverage and the two-sided D-04 refusal-rate bound.
#
# Entirely about anti-vacuity (task brief): a corpus-wide check is not trusted until it
# has been demonstrated failing. Every assertion below names its reddening mutation in a
# comment; each one was actually run once (via a standalone script, never committed) to
# confirm it flips red -- see task-3-report.md for the full transcripts.
# --------------------------------------------------------------------------------------


def _walk_font_resources(
    resources: pikepdf.Object | None, seen_xobjects: set[tuple[int, int]]
) -> Iterator[pikepdf.Object]:
    """Yield every font dict directly in `resources` (/Font), plus font dicts nested in
    Form XObject /Resources, walked recursively -- matching the task brief's controller-
    measured census, which walks "page /Resources /Font plus nested XObject resources".
    `seen_xobjects` dedupes Form XObjects by (obj, gen) only, as cycle protection for a
    Form that (directly or indirectly) references itself; font DICTS themselves are never
    deduped here, since the census counts branch occurrences, not distinct font objects.
    """
    if resources is None:
        return
    fonts = resources.get("/Font")
    if fonts is not None:
        for _key, font in fonts.items():
            yield font
    xobjects = resources.get("/XObject")
    if xobjects is not None:
        for _key, xobject in xobjects.items():
            if str(xobject.get("/Subtype", "")) != "/Form":
                continue
            try:
                key = xobject.objgen
            except AttributeError:
                key = None
            if key is not None:
                if key in seen_xobjects:
                    continue
                seen_xobjects.add(key)
            yield from _walk_font_resources(xobject.get("/Resources"), seen_xobjects)


def _iter_corpus_fonts() -> Iterator[tuple[str, pikepdf.Object]]:
    """Yield (filename, font_dict) for every font dictionary across the full public
    corpus. Per controller resolution #3 (task brief), this walk belongs in the test, not
    in engine/encoding_table.py. A document that fails to open or traverse is skipped, not
    allowed to crash the run -- the same convention test_pitfall_2_... above already uses.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())
    for entry in manifest:
        path = CORPUS_DIR / entry["filename"]
        if not path.exists():
            continue
        try:
            pdf = pikepdf.open(path)
        except Exception:  # noqa: BLE001 - encrypted/broken files are not this walk's subject
            continue
        try:
            seen_xobjects: set[tuple[int, int]] = set()
            for page in pdf.pages:
                for font in _walk_font_resources(page.get("/Resources"), seen_xobjects):
                    yield entry["filename"], font
        except Exception:  # noqa: BLE001
            pass
        finally:
            pdf.close()


@pytest.mark.corpus
def test_every_corpus_font_fires_exactly_one_branch() -> None:
    """D-04 corpus-wide branch coverage. Every font dict across the full public corpus
    (217 documents, page /Resources /Font plus nested Form XObject resources) must resolve
    to exactly one branch_id and never raise -- "exactly one" per controller resolution #1
    means resolve_font returns exactly one FontVerdict per font dict, not that every
    branch fires on a unique font.

    Per the explicit anti-vacuity warning (02-VALIDATION.md TEXT-04 branch-coverage-
    vacuity, Phase 1's 0/0-pass failure mode, corroborated by Assumption A8's 10-distinct-
    combination floor), a per-font contract alone is not enough: this also asserts
    fonts_seen > 0 (the walk actually resolved something, guarding against a silently-
    empty corpus walk) and distinct_branches_fired >= 8 (per task-3-brief.md's controller-
    measured census: 11 distinct branches fire on this corpus -- comfortably above the
    floor, so this is a real gate, not a rubber stamp).

    A document-count floor guards the >= 8 gate itself: measured, 8 distinct branches are
    already reached after only 10 of 212 documents (round-1 review finding), so without a
    floor this test stays green on a corpus shrunk by 95%. `docs_seen >= 200` closes that
    (same floor as test_refusal_rate_within_recorded_bound below, same rationale).

    MUTATION 1: hardcoding resolve_font's dispatch to always return one fixed verdict
    (e.g. always FontVerdict("T1-a", True, False), regardless of input) still satisfies
    "exactly one branch_id, never raises" but collapses distinct_branches_fired from 11
    to 1, failing the >= 8 floor. Confirmed by running that hardcode against the same walk
    used here (standalone script, not committed): 35,071 fonts resolved, 1 distinct branch
    ('T1-a') -- the >= 8 assertion goes red as expected.

    MUTATION 2 (the document-count floor): a corpus shrunk to its first 10 documents still
    reaches 8 distinct branches, so distinct_branches_fired >= 8 alone stays green.
    Confirmed by running the same walk restricted to the manifest's first 10 documents
    (standalone script, not committed): 8 distinct branches fired but only 10 documents
    scanned -- `docs_seen >= 200` catches what the branch-count gate alone misses.
    """
    branch_counts: dict[str, int] = {}
    docs_seen: set[str] = set()
    fonts_seen = 0
    for filename, font in _iter_corpus_fonts():
        docs_seen.add(filename)
        verdict = resolve_font(font)  # must not raise
        assert isinstance(verdict.branch_id, str) and verdict.branch_id
        branch_counts[verdict.branch_id] = branch_counts.get(verdict.branch_id, 0) + 1
        fonts_seen += 1

    distinct_branches_fired = len(branch_counts)

    assert fonts_seen > 0, "corpus walk found no font dictionaries -- vacuous population"
    # Guards the branch-count gate against a shrunken corpus -- see MUTATION 2 above. 212
    # of 217 manifest documents yield >= 1 font (5 are font-less, confirmed legitimate);
    # 200 leaves 12 documents of slack against that real denominator.
    assert len(docs_seen) >= 200, f"expected close to the full corpus, scanned {len(docs_seen)} documents"
    assert distinct_branches_fired >= 8, (
        f"only {distinct_branches_fired} distinct branches fired: {sorted(branch_counts)} -- "
        f"expected >= 8 per the task brief's measured 11-branch census"
    )


@pytest.mark.corpus
def test_type1_symbolic_encoding_resolves_truetype_refuses() -> None:
    """The module's one ordering rule (docstring: branch on /Subtype BEFORE Symbolic),
    proven on REAL corpus fonts rather than the synthetic ones test_branch_t1_b_... and
    test_branch_tt_c_... already cover: a symbolic Type1 font with /Encoding present
    resolves editable (T1-b -- 1,016 occurrences / 48 docs per the task brief's census),
    while a symbolic TrueType font with /Encoding present refuses (TT-c -- 27 occurrences
    / 4 docs). Same shape (symbolic + /Encoding present), different /Subtype, opposite
    verdict -- exactly the distinction the ordering rule exists to get right, so this test
    fails if either population is empty on the real corpus (found = irs_1040_instructions.pdf
    for T1-b, mutopia_vocalise_abt.pdf for TT-c, at time of writing).

    MUTATION: the Pitfall-2 collapsed rule (`_collapsed_is_refused` above -- branch on
    `symbolic and has_encoding` before /Subtype) applied to the discovered T1-b font.
    Confirmed by running it once (standalone script, not committed): the collapsed rule
    says refused=True for the exact real T1-b font resolve_font correctly calls editable
    -- i.e. reversing the ordering rule flips this real font's verdict. The assertion
    below bakes that comparison in permanently, so it goes red the same way if the
    ordering rule regresses.
    """
    t1b: dict[str, object] | None = None
    ttc: dict[str, object] | None = None

    for filename, font in _iter_corpus_fonts():
        if t1b is not None and ttc is not None:
            break
        subtype = str(font.get("/Subtype", ""))
        if subtype not in ("/Type1", "/MMType1", "/TrueType"):
            continue
        descriptor = font.get("/FontDescriptor")
        if not (is_symbolic(descriptor) and font.get("/Encoding") is not None):
            continue

        verdict = resolve_font(font)
        if subtype in ("/Type1", "/MMType1") and verdict.branch_id == "T1-b" and t1b is None:
            t1b = {"filename": filename, "verdict": verdict, "collapsed_refused": _collapsed_is_refused(font)}
        if subtype == "/TrueType" and verdict.branch_id == "TT-c" and ttc is None:
            ttc = {"filename": filename, "verdict": verdict, "collapsed_refused": _collapsed_is_refused(font)}

    assert t1b is not None, "expected at least one real T1-b font (symbolic Type1 + /Encoding) in the corpus"
    assert ttc is not None, "expected at least one real TT-c font (symbolic TrueType + /Encoding) in the corpus"

    t1b_verdict = t1b["verdict"]
    ttc_verdict = ttc["verdict"]
    assert isinstance(t1b_verdict, FontVerdict) and isinstance(ttc_verdict, FontVerdict)

    assert t1b_verdict.branch_id == "T1-b"
    assert t1b_verdict.editable is True

    assert ttc_verdict.branch_id == "TT-c"
    assert ttc_verdict.editable is False

    # The reddening comparison: the same real T1-b font, run through the collapsed rule,
    # is wrongly refused -- proving the /Subtype-first ordering is what keeps it editable.
    assert t1b["collapsed_refused"] is True, (
        "the collapsed (Pitfall-2) rule no longer wrongly refuses this real T1-b font -- "
        "either the discovered font changed shape or the ordering-rule regression this "
        "guards against no longer reproduces"
    )


@pytest.mark.corpus
def test_refusal_rate_within_recorded_bound() -> None:
    """D-04: the corpus-wide refusal rate, measured and bounded two-sided.

    MEASURED (2026-08-14, against corpus/manifest.json + corpus/public, the same walk as
    test_every_corpus_font_fires_exactly_one_branch above -- page /Resources /Font plus
    nested Form XObject resources, 0 open/traversal errors): 26 of 212 documents (12.3%)
    have at least one font resolve_font refuses.

    DENOMINATOR, stated explicitly per round-1 review: 212, not the full 217-document
    manifest. `docs_scanned` below counts only documents that yield at least one font dict
    (page or nested-XObject) -- 5 corpus documents open cleanly but contain zero font
    entries (verapdf_isartor_malformed_trailer, verapdf_inline_image_fixture,
    govdocs1_002_002014, govdocs1_007_007030, vector_outlined_text_sample; confirmed
    legitimate, not a swallowed open/traversal error). The task brief's controller-measured
    census used 217 as its denominator (all documents scanned, whether or not they
    contained a font). The numerator (26) matches the brief's exactly; the denominator does
    not, because the two walks count "scanned" differently -- 26/212 = 12.3% is what this
    test's own denominator produces, recorded as such rather than restated to 26/217.

    Two-sided bound per 02-VALIDATION.md's "D-04 refusal rate must be bounded two-sided"
    warning: an upper bound alone stays green if the table stops refusing anything at all.
    Pinned range [5%, 20%], centred on the measured 12.3%:
      - lower 5%: wide enough to absorb the TT-d/TT-e contribution measured at 0% by
        tools/measure_truetype_cmap_gaps.py (02-02) -- i.e. even if that contribution had
        been nonzero, it fits -- while still excluding 0% (the table refusing nothing).
      - upper 20%: comfortably below the ~23.1% Pitfall-2 collapse regression
        (02-RESEARCH.md Section 1 / this file's module docstring), with margin so a small
        additional refusal source doesn't false-positive the guard.

    MUTATION 1 (upper bound, the Type1-vs-TrueType collapse -- `_collapsed_is_refused`
    above): applying the collapsed rule to the same corpus walk used here, confirmed by
    running it once (standalone script, not committed): 52/217 documents (24.0%) --
    outside the pinned upper bound of 20%, reproducing Pitfall 2 at the two-sided test's
    own scale (slightly above the 23.1%/1,012-occurrence figure quoted elsewhere in this
    file, which was measured on a page-only walk; this walk also includes XObject-nested
    fonts, so a marginally larger population is expected).

    MUTATION 2 (LOWER bound -- the one an upper-bound-only check cannot catch): a
    "resolve_font never refuses" stand-in (every verdict forced editable=True) applied to
    the same corpus walk. Confirmed by running it once (standalone script, not committed):
    0/217 documents (0.0%) -- outside the pinned lower bound of 5%. This is the exact
    scenario the two-sided requirement exists for: an upper-bound-only assertion
    (rate <= 0.20) would stay green at 0.0%, silently passing while the table has stopped
    refusing anything at all.
    """
    docs_with_refusal: set[str] = set()
    docs_scanned: set[str] = set()

    for filename, font in _iter_corpus_fonts():
        docs_scanned.add(filename)
        if not resolve_font(font).editable:
            docs_with_refusal.add(filename)

    scanned = len(docs_scanned)
    # Guards the denominator too -- a shrunken local corpus silently measuring a smaller
    # population would itself be a vacuous-check failure mode. The real denominator here
    # is 212 (documents yielding >= 1 font, not the full 217-document manifest -- see the
    # docstring), so 200 leaves 12 documents of slack, not the 17 it would appear to have
    # against 217.
    assert scanned >= 200, f"expected close to the full 212-document (font-bearing) corpus, scanned {scanned}"

    refusal_rate = len(docs_with_refusal) / scanned
    assert 0.05 <= refusal_rate <= 0.20, (
        f"corpus refusal rate {refusal_rate:.1%} ({len(docs_with_refusal)}/{scanned} docs) "
        f"fell outside the pinned two-sided bound [5%, 20%]"
    )
