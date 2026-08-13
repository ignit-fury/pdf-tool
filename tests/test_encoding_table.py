"""TEXT-04 / D-04: the forward encoding decision table resolves every named branch.

TT-d and TT-e have ZERO instances in the 217-document corpus (measured by
tools/measure_truetype_cmap_gaps.py: 80 TT-b fonts, TT-d 0, TT-e 0). Asserting them
against real documents is therefore impossible, and asserting them against a counter that
is always 0 is the vacuous-check failure this phase keeps finding. They get synthetic
font programs instead, built here by packing a minimal sfnt.
"""

import io
import json
import struct
from pathlib import Path

import pikepdf
import pytest

from engine.encoding_table import (
    STANDARD_ENCODING,
    WIN_ANSI_ENCODING,
    base_encoding,
    encoding_map,
    parse_differences,
    resolve_font,
)

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


def test_type0_and_type3_defer_and_fail_closed(pdf: pikepdf.Pdf) -> None:
    """Not this task's branches. The deferral must be non-editable so a caller that
    ignores it refuses rather than silently editing through an unresolved font."""
    for subtype in ("/Type0", "/Type3"):
        verdict = resolve_font(_font(pdf, subtype))
        assert verdict.branch_id == f"DEFER{subtype}"
        assert not verdict.editable


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
