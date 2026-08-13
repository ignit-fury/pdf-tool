"""The forward encoding decision table: font dictionary -> branch ID + editability verdict.

TEXT-04 requires the fired branch logged per font, never a guess. This module is a
structural determination from the font dictionary, run BEFORE and independently of the
walk. Per the Architectural Responsibility Map it must NOT call into the walker, and it
imports no playa: the "forward" direction (code -> glyph, what decides pixels) is a
separate question from playa's decode (code -> text, for display and search), and
conflating them is the TEXT-05 mistake this project types against.

## The one ordering rule that carries the whole table

**Branch on `/Subtype` BEFORE branching on the Symbolic flag.** ISO 32000-1 9.6.6.4's
"the Encoding entry shall be ignored" language is TrueType-specific; 9.6.6.2 gives Type1
a clear and different rule, where `/Differences` overlays the built-in encoding
unconditionally and Symbolic only selects which base it overlays.

Collapsing the two refuses **1,012 font occurrences across 50 of 216 corpus documents
(23.1%)** that are perfectly editable, and makes D-04's reported refusal rate a
measurement of this bug rather than of the spec. Correct is ~1.9% (the 4 real TT-c
documents). `test_pitfall_2_collapsed_branch_inflates_refusals` is the permanent guard;
02-RESEARCH.md Pitfall 2's stated warning sign is "the measured refusal rate lands near
23%".

## Scope of this module

Simple fonts (`/Type1`, `/MMType1`, `/TrueType`) and the refusals A-1, A-2, A-3, A-5,
A-7. `/Type0` and `/Type3` return an explicit DEFER verdict rather than a guess -- their
branches (C-1..C-6, T3-a), the A-6 glyph-presence downgrade and the A-8 per-glyph verdict
are the next task's. A DEFER verdict is never editable, so a caller that forgets to
handle it fails closed.

## Deviation from the plan's "pikepdf object access only"

A-2 (TT-d) and A-3 (TT-e) are *defined* in terms of the embedded font program's cmap
subtables -- "only a (3,1)" and "no cmap at all" are not visible anywhere in the PDF
object graph. So `resolve_font` reads the cmap subtable DIRECTORY (platformID/platEncID
pairs only) via fontTools, never decompiling a subtable body. That distinction is
load-bearing and was learned the expensive way: `TTFont()["cmap"]` decompiles every
subtable on first touch, and 31 corpus fonts have a malformed format-4 body behind a
perfectly readable directory. An earlier measurement that used the eager path
misclassified all 31 as unparseable and inverted the finding.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass

import pikepdf
from fontTools.agl import UV2AGL
from fontTools.encodings.MacRoman import MacRoman
from fontTools.encodings.StandardEncoding import StandardEncoding
from fontTools.ttLib.sfnt import SFNTReader

# ISO 32000-1 Table 123: the Symbolic flag is bit position 3, i.e. value 4.
SYMBOLIC_FLAG_BIT = 1 << 2

# ISO 32000-1 Annex D.2 / 9.6.2.2. Standard-14 base font names, in the un-subsetted
# spelling; a subset tag (ABCDEF+) is stripped before comparison.
STANDARD_14 = frozenset(
    {
        "Times-Roman",
        "Times-Bold",
        "Times-Italic",
        "Times-BoldItalic",
        "Helvetica",
        "Helvetica-Bold",
        "Helvetica-Oblique",
        "Helvetica-BoldOblique",
        "Courier",
        "Courier-Bold",
        "Courier-Oblique",
        "Courier-BoldOblique",
        "Symbol",
        "ZapfDingbats",
    }
)

SIMPLE_SUBTYPES = frozenset({"/Type1", "/MMType1", "/TrueType"})


def _build_win_ansi() -> tuple[str | None, ...]:
    """WinAnsiEncoding as a code -> glyph-name table.

    Derived from cp1252 through the Adobe Glyph List rather than hand-typed: a 256-entry
    literal is unreviewable and its errors are invisible until a document renders wrong.
    Two codes are NOT plain cp1252 -- ISO 32000-1 Annex D.2 footnotes override them, and
    they are the only two, so they are stated explicitly below and pinned in tests.
    """
    table: list[str | None] = [None] * 256
    for code in range(256):
        try:
            char = bytes([code]).decode("cp1252")
        except UnicodeDecodeError:
            continue  # cp1252 has five undefined slots; they stay None
        table[code] = UV2AGL.get(ord(char))
    # Annex D.2: NBSP is the same glyph as space, soft hyphen the same as hyphen. Without
    # these two, both slots derive to None and any text using them loses its glyph name.
    table[0xA0] = "space"
    table[0xAD] = "hyphen"
    return tuple(table)


WIN_ANSI_ENCODING = _build_win_ansi()
STANDARD_ENCODING = tuple(StandardEncoding)
MAC_ROMAN_ENCODING = tuple(MacRoman)

NAMED_BASE_ENCODINGS = {
    "/WinAnsiEncoding": WIN_ANSI_ENCODING,
    "/MacRomanEncoding": MAC_ROMAN_ENCODING,
    "/StandardEncoding": STANDARD_ENCODING,
}


@dataclass(frozen=True, slots=True)
class FontVerdict:
    """The logged outcome of one font's resolution.

    `editable=False` with `substitution=False` is a refusal and `reason` names it.
    `editable=True, substitution=True` is A-6's downgrade shape: the text can be replaced,
    but not in the original font program -- the caller must embed a bundled face.
    """

    branch_id: str
    editable: bool
    substitution: bool
    reason: str | None = None


def is_symbolic(font_descriptor: pikepdf.Object | None) -> bool:
    """The Symbolic flag, read the same way tools/probe_corpus.py reads it. Deliberately
    duplicated rather than imported: tools/ is measurement scaffolding and this module is
    standalone per the Architectural Responsibility Map."""
    if font_descriptor is None:
        return False
    flags = font_descriptor.get("/Flags")
    return flags is not None and bool(int(flags) & SYMBOLIC_FLAG_BIT)


def embedded_font_bytes(font_descriptor: pikepdf.Object | None) -> bytes | None:
    """The embedded font program, or None if the font is not embedded. /FontFile is
    Type1, /FontFile2 TrueType, /FontFile3 CFF or OpenType."""
    if font_descriptor is None:
        return None
    for key in ("/FontFile2", "/FontFile3", "/FontFile"):
        stream = font_descriptor.get(key)
        if stream is not None:
            try:
                return bytes(stream.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable stream is "not usable", not a crash
                return None
    return None


def parse_differences(differences: pikepdf.Object) -> dict[int, str]:
    """Overlay array -> {code: glyph_name}.

    `/Differences` is `[code name name ... code name ...]`: a MIXED array where each
    integer RESETS a running code counter and each name consumes the next code. A pairwise
    parse (zip of evens and odds) is wrong and produces an off-by-one that presents as
    "every letter shifted by one" -- the failure this function exists to not have.
    """
    out: dict[int, str] = {}
    code = 0
    for item in differences:
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            code = int(item)
        else:
            name = str(item)
            if name.startswith("/"):
                name = name[1:]
            out[code] = name
            code += 1
    return out


def base_encoding(font: pikepdf.Object) -> tuple[str, tuple[str | None, ...] | None]:
    """B1-B6: which base encoding array applies, before /Differences.

    Returns (step_id, table). The table is None for B4 and B6, where the spec says to use
    the font PROGRAM's built-in encoding -- which is not in the PDF object graph at all.
    None here means "ask the font program", not "unknown"; resolving it is the
    glyph-presence work in the next task.
    """
    encoding = font.get("/Encoding")
    symbolic = is_symbolic(font.get("/FontDescriptor"))

    if encoding is None:
        if symbolic:
            return "B6", None
        return "B5", STANDARD_ENCODING

    if isinstance(encoding, pikepdf.Name):
        return "B1", NAMED_BASE_ENCODINGS.get(str(encoding), STANDARD_ENCODING)

    # A dictionary (or a stream, which pikepdf also exposes dict-like).
    base = encoding.get("/BaseEncoding")
    if base is not None:
        return "B2", NAMED_BASE_ENCODINGS.get(str(base), STANDARD_ENCODING)
    if symbolic:
        return "B4", None
    return "B3", STANDARD_ENCODING


def encoding_map(font: pikepdf.Object) -> dict[int, str]:
    """code -> glyph name, base overlaid with /Differences.

    Codes whose base entry is `.notdef` or absent are omitted rather than mapped to a
    placeholder: a caller must be able to tell "this code has no glyph name" from "this
    code maps to a glyph literally named .notdef".
    """
    _step, table = base_encoding(font)
    out: dict[int, str] = {}
    if table is not None:
        for code, name in enumerate(table):
            if name and name != ".notdef":
                out[code] = name

    encoding = font.get("/Encoding")
    if encoding is not None and not isinstance(encoding, pikepdf.Name):
        differences = encoding.get("/Differences")
        if differences is not None:
            out.update(parse_differences(differences))
    return out


def cmap_subtable_ids(font_bytes: bytes) -> set[tuple[int, int]]:
    """The (platformID, platEncID) pairs in a TrueType cmap's subtable DIRECTORY.

    Reads only the directory, never a subtable body -- see the module docstring's
    deviation note for why that distinction decides whether 31 corpus fonts classify
    correctly or not. Raises on an unreadable sfnt/cmap directory; callers classify that
    as its own outcome rather than silently treating it as "no cmap".
    """
    reader = SFNTReader(io.BytesIO(font_bytes))
    if "cmap" not in reader:
        return set()
    cmap_bytes = reader["cmap"]
    _version, num_subtables = struct.unpack_from(">HH", cmap_bytes, 0)
    ids: set[tuple[int, int]] = set()
    offset = 4
    for _ in range(num_subtables):
        platform_id, plat_enc_id, _sub_offset = struct.unpack_from(">HHI", cmap_bytes, offset)
        ids.add((platform_id, plat_enc_id))
        offset += 8
    return ids


def _classify_cmap(ids: set[tuple[int, int]]) -> str | None:
    """A-2/A-3: "TT-e" (no cmap), "TT-d" (only a (3,1)), or None for a usable set."""
    if not ids:
        return "TT-e"
    if (3, 1) in ids and (3, 0) not in ids and (1, 0) not in ids:
        return "TT-d"
    return None


def _base_font_name(font: pikepdf.Object) -> str:
    """/BaseFont with any subset tag (six uppercase letters + '+') stripped."""
    base = font.get("/BaseFont")
    if base is None:
        return ""
    name = str(base).lstrip("/")
    if len(name) > 7 and name[6] == "+" and name[:6].isalpha() and name[:6].isupper():
        return name[7:]
    return name


def _resolve_type1(font: pikepdf.Object, symbolic: bool, embedded: bool) -> FontVerdict:
    """Type1/MMType1. Note what is NOT here: no branch on `symbolic and has_encoding`.
    9.6.6.2 makes /Differences authoritative over the built-in encoding unconditionally,
    so symbolic+/Encoding (T1-b) resolves exactly as T1-a does. It gets its own branch ID
    only so the 1,012-occurrence population stays visible in the logs."""
    has_encoding = font.get("/Encoding") is not None

    if not embedded:
        if symbolic:
            # A-5: no program to consult, so whatever the viewer substitutes decides the
            # pixels. An information gap, not a spec ambiguity.
            return FontVerdict("NOEMB", False, False, "symbolic simple font, not embedded")
        if _base_font_name(font) in STANDARD_14:
            return FontVerdict("T1-c", True, True)
        return FontVerdict("T1-d", True, True)

    if symbolic and has_encoding:
        return FontVerdict("T1-b", True, False)
    return FontVerdict("T1-a", True, False)


def _resolve_truetype(font: pikepdf.Object, symbolic: bool, program: bytes | None) -> FontVerdict:
    """TrueType. Every refusal in the table lives on the symbolic side."""
    has_encoding = font.get("/Encoding") is not None

    if not symbolic:
        # TT-a. /Encoding absent is not a separate branch: B5 supplies StandardEncoding
        # implicitly and the name -> AGL -> (3,1) path is identical.
        return FontVerdict("TT-a", True, False)

    if program is None:
        return FontVerdict("NOEMB", False, False, "symbolic simple font, not embedded")

    if has_encoding:
        # A-1. THE ambiguous branch: 9.6.6.4 says ignore /Encoding, real producers set
        # both, and pdf.js/PDFBox/PDFium each tie-break differently.
        return FontVerdict("TT-c", False, False, "TrueType symbolic with /Encoding present")

    try:
        ids = cmap_subtable_ids(program)
    except Exception:  # noqa: BLE001 - classified, not swallowed
        return FontVerdict("TT-f", False, False, "cmap subtable directory unreadable")

    unusable = _classify_cmap(ids)
    if unusable == "TT-e":
        return FontVerdict("TT-e", False, False, "TrueType with no cmap table")
    if unusable == "TT-d":
        return FontVerdict("TT-d", False, False, "symbolic TrueType with only a (3,1) cmap")

    return FontVerdict("TT-b", True, False)


def resolve_font(font: pikepdf.Object) -> FontVerdict:
    """Top-to-bottom, first match wins, branch ID always logged (TEXT-04, D-04).

    /Subtype is read FIRST -- see the module docstring's ordering rule. Reversing these
    two lines is the Pitfall-2 bug and costs 23% of the corpus.
    """
    subtype = str(font.get("/Subtype", ""))

    if subtype in ("/Type0", "/Type3"):
        # Explicit deferral, and not editable, so a caller that ignores it fails closed.
        return FontVerdict(
            f"DEFER{subtype}", False, False, "resolved by the Type0/Type3 branches (02-06 Task 2)"
        )

    if subtype not in SIMPLE_SUBTYPES:
        return FontVerdict("UNKNOWN", False, False, f"unrecognised /Subtype {subtype!r}")

    descriptor = font.get("/FontDescriptor")
    symbolic = is_symbolic(descriptor)
    program = embedded_font_bytes(descriptor)

    if subtype == "/TrueType":
        return _resolve_truetype(font, symbolic, program)
    return _resolve_type1(font, symbolic, program is not None)


def actualtext_verdict() -> FontVerdict:
    """A-7. A span covered by /ActualText is never an edit target: its user-visible text
    is not the concatenation of its glyphs' Unicode, so the glyph-level addressing this
    engine edits through does not describe what the reader sees. Display uses
    /ActualText; editing refuses. Called per span by the clusterer, not per font."""
    return FontVerdict("ACTUALTEXT", False, False, "span covered by /ActualText")


__all__ = [
    "FontVerdict",
    "actualtext_verdict",
    "base_encoding",
    "cmap_subtable_ids",
    "embedded_font_bytes",
    "encoding_map",
    "is_symbolic",
    "parse_differences",
    "resolve_font",
]
