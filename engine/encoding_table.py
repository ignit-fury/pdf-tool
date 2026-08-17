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

Simple fonts (`/Type1`, `/MMType1`, `/TrueType`), Type0/CID composite fonts (C-1..C-6),
Type3 (T3-a), the font-level refusals A-1, A-2, A-3, A-5, A-7, the A-6 glyph-presence
downgrade, and the A-8 per-glyph verdict.

`glyph_presence` and `glyph_verdict` are deliberately NOT part of `resolve_font`: they
answer a per-glyph question ("does this specific glyph exist / have a mapping") that a
per-font dispatch cannot ask, and folding them in would be exactly the cascade A-8 exists
to prevent -- one bad glyph must never flip the whole font's verdict.

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
import re
import struct
from dataclasses import dataclass

import pikepdf
from fontTools.agl import UV2AGL
from fontTools.cffLib import CFFFontSet
from fontTools.encodings.MacRoman import MacRoman
from fontTools.encodings.StandardEncoding import StandardEncoding
from fontTools.misc import psLib
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import SFNTReader

from engine.records import GlyphRecord

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


@dataclass(frozen=True, slots=True)
class GlyphVerdict:
    """The logged outcome of ONE glyph's resolution (A-8, D-05).

    Deliberately its own type, not `FontVerdict` reused: a per-glyph verdict and a
    per-font verdict answer different questions, and conflating them is exactly how a
    single bad glyph's refusal would cascade into refusing the whole font or run --
    the failure A-8 exists to prevent (controller-resolved ambiguity #2).
    """

    editable: bool
    reason: str | None = None


def is_symbolic(font_descriptor: pikepdf.Object | None) -> bool:
    """The Symbolic flag, read the same way tools/probe_corpus.py reads it. Deliberately
    duplicated rather than imported: tools/ is measurement scaffolding and this module is
    standalone per the Architectural Responsibility Map."""
    if font_descriptor is None:
        return False
    flags = font_descriptor.get("/Flags")
    return flags is not None and bool(int(flags) & SYMBOLIC_FLAG_BIT)


@dataclass(frozen=True, slots=True)
class FontProgram:
    """An embedded font program's raw bytes, plus the /Length1//Length2//Length3 PDF
    stream keys a Type1 /FontFile needs to be re-segmented correctly.

    A PDF /FontFile is NOT a PFA or PFB file -- it is the raw Type1 program's three
    segments (ASCII cleartext header, BINARY eexec-encrypted charstrings, ASCII trailer)
    concatenated with no markers of their own; only these three lengths say where one
    segment ends and the next begins (ISO 32000-1 Table 111 / 9.9). `/FontFile2`
    (TrueType) and `/FontFile3` (CFF/OpenType) carry no such split, so they leave
    length1/length2/length3 `None`.
    """

    data: bytes
    length1: int | None = None
    length2: int | None = None
    length3: int | None = None


def embedded_font_bytes(font_descriptor: pikepdf.Object | None) -> FontProgram | None:
    """The embedded font program, or None if the font is not embedded. /FontFile is
    Type1, /FontFile2 TrueType, /FontFile3 CFF or OpenType."""
    if font_descriptor is None:
        return None
    for key in ("/FontFile2", "/FontFile3", "/FontFile"):
        stream = font_descriptor.get(key)
        if stream is not None:
            try:
                data = bytes(stream.read_bytes())
            except Exception:  # noqa: BLE001 - an unreadable stream is "not usable", not a crash
                return None
            if key != "/FontFile":
                return FontProgram(data)
            length1 = stream.get("/Length1")
            length2 = stream.get("/Length2")
            length3 = stream.get("/Length3")
            return FontProgram(
                data,
                int(length1) if length1 is not None else None,
                int(length2) if length2 is not None else None,
                int(length3) if length3 is not None else None,
            )
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


def _resolve_truetype(
    font: pikepdf.Object, symbolic: bool, program: FontProgram | None
) -> FontVerdict:
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
        ids = cmap_subtable_ids(program.data)
    except Exception:  # noqa: BLE001 - classified, not swallowed
        return FontVerdict("TT-f", False, False, "cmap subtable directory unreadable")

    unusable = _classify_cmap(ids)
    if unusable == "TT-e":
        return FontVerdict("TT-e", False, False, "TrueType with no cmap table")
    if unusable == "TT-d":
        return FontVerdict("TT-d", False, False, "symbolic TrueType with only a (3,1) cmap")

    return FontVerdict("TT-b", True, False)


_CODESPACE_RANGE_RE = re.compile(rb"begincodespacerange(.*?)endcodespacerange", re.DOTALL)
_HEX_STRING_RE = re.compile(rb"<([0-9A-Fa-f]+)>")


def _parse_codespace_widths(cmap_bytes: bytes) -> set[int] | None:
    """The byte-width(s) declared across EVERY `begincodespacerange` block in an embedded
    CMap stream. A narrow, bounded extraction of ONE structural fact (how many bytes does
    each range's bound take) -- not a CMap interpreter; resolving code->CID is playa's
    job everywhere except this structural determination (Architectural Responsibility
    Map). None if no codespacerange block is found at all.

    Adobe's CMap resources cap each `begincodespacerange`/`endcodespacerange` block at
    100 ranges, so a CMap with more than that splits across multiple blocks -- `finditer`
    + union, not the first match alone, or a mixed-width font whose mismatch starts in
    block 2 silently resolves as uniform (IMPORTANT 3, measured: a synthetic 1-byte-then-
    2-byte CMap split across two blocks returned `{1}` under `re.search`, hiding the C-6
    refusal it should have triggered).
    """
    matches = list(_CODESPACE_RANGE_RE.finditer(cmap_bytes))
    if not matches:
        return None
    widths: set[int] = set()
    for match in matches:
        widths.update(len(hex_str) // 2 for hex_str in _HEX_STRING_RE.findall(match.group(1)))
    return widths or None


def _codespace_widths(encoding: pikepdf.Object | None) -> set[int] | None:
    """C-1/C-2: the CMap's codespace byte-width set, never hardcoded to 2.

    Identity-H/Identity-V are uniformly 2-byte by definition (ISO 32000-1 9.7.5.2) and
    need no CMap data to know that. An embedded CMap stream is parsed for its own
    codespacerange widths. A predefined named CMap OTHER than Identity-H/V has no
    resource data anywhere in the PDF object graph -- returning None here (rather than
    guessing 2) is what keeps C-6 honest: "unknown" and "known-mixed" are both refused,
    but they are refused for different, correctly distinct reasons.
    """
    if encoding is None:
        return None
    if isinstance(encoding, pikepdf.Name):
        if str(encoding) in ("/Identity-H", "/Identity-V"):
            return {2}
        return None
    try:
        cmap_bytes = bytes(encoding.read_bytes())
    except Exception:  # noqa: BLE001 - an unreadable CMap stream classifies, doesn't crash
        return None
    return _parse_codespace_widths(cmap_bytes)


def _cid_to_gid_map_ok(value: pikepdf.Object | None) -> tuple[bool, str | None]:
    """C-3a: `/Identity` (or absent, which ISO 32000-1 9.7.4.2 defaults to Identity), or a
    binary stream of big-endian 2-byte GIDs indexed by CID -- handling only Identity is
    correct on 9,760 of 10,114 corpus CIDFontType2 occurrences and garbage on the other 97
    (measured). This only validates the stream's SHAPE (even byte length); decoding
    individual CID->GID entries is the walker's job, not this structural determination's.
    """
    if value is None:
        return True, None
    if isinstance(value, pikepdf.Name):
        if str(value) == "/Identity":
            return True, None
        return False, f"unrecognised /CIDToGIDMap name {str(value)!r}"
    try:
        data = bytes(value.read_bytes())
    except Exception:  # noqa: BLE001 - unreadable stream classifies, doesn't crash
        return False, "CIDToGIDMap stream unreadable"
    if len(data) % 2 != 0:
        return False, "CIDToGIDMap stream not a whole number of 2-byte GIDs"
    return True, None


def _resolve_type0(font: pikepdf.Object) -> FontVerdict:
    """C-1..C-6: Type0/CID composite fonts.

    IMPORTANT 6 (branch-id audit): branch_id feeds the D-04 census, so a wrong label
    corrupts a measurement, not just a log line. Each id below now means exactly what
    02-RESEARCH.md Section 1's C-table says it means:
    - "NODESC" (not a C-step at all -- no /DescendantFonts means none of C-1..C-6 can
      even begin) replaces a borrowed "C-1".
    - "C-1" (bytes->code, codespace ranges) is what actually fails when the codespace
      can't be resolved -- it replaces a borrowed "C-2" (code->CID is a DIFFERENT
      question this module never reaches for an unresolvable CMap, since it can't even
      get past bytes->code first).
    - "C-3" (an unrecognised descendant /Subtype -- neither CIDFontType0 nor
      CIDFontType2, so neither C-3a nor C-3b answers) replaces a borrowed "C-1"; CID->GID
      is what's undetermined, not the codespace.
    C-2 itself (Identity vs a named-CMap table lookup) has no failure path of its own in
    this module: an embedded CMap stream's codespace is validated at C-1 but its cidrange
    table is never parsed here (out of scope -- resolving individual CID values is the
    walker's job, not this structural verdict's), so C-2 cannot fail independently of C-1
    given this module's actual scope. Left unused rather than forced onto an unrelated
    path, the same way C-5 is documented out of scope rather than stubbed.
    """
    descendants = font.get("/DescendantFonts")
    if not descendants:
        return FontVerdict("NODESC", False, False, "Type0 with no /DescendantFonts")
    descendant = descendants[0]

    widths = _codespace_widths(font.get("/Encoding"))
    if widths is None:
        # C-1: bytes->code itself is unresolvable (no CMap data to consult).
        return FontVerdict(
            "C-1", False, False, "CMap codespace not resolvable from the font dictionary"
        )
    if len(widths) > 1:
        # C-6. Writing into a mixed-byte-width codespace is out of scope; refuse rather
        # than guess which width applies to which code.
        return FontVerdict("C-6", False, False, "mixed-byte-width codespace ranges")

    program = embedded_font_bytes(descendant.get("/FontDescriptor"))
    if program is None:
        return FontVerdict("NOEMB", False, False, "Type0 descendant font not embedded")

    subtype = str(descendant.get("/Subtype", ""))
    if subtype == "/CIDFontType0":
        # C-3b. Through the CFF charset, never /CIDToGIDMap -- that key does not apply to
        # CIDFontType0 at all.
        return FontVerdict("C-3b", True, False)
    if subtype == "/CIDFontType2":
        ok, reason = _cid_to_gid_map_ok(descendant.get("/CIDToGIDMap"))
        if not ok:
            return FontVerdict("C-3a", False, False, reason)
        return FontVerdict("C-3a", True, False)
    # C-3's dispatch (CIDFontType0 vs CIDFontType2) found neither -- still a C-3 (CID->GID)
    # question, just one neither C-3a nor C-3b answers.
    return FontVerdict("C-3", False, False, f"unrecognised CIDFont /Subtype {subtype!r}")


def _resolve_type3(font: pikepdf.Object) -> FontVerdict:
    """T3-a: always resolves via /Encoding /Differences -> /CharProcs. Type3 has no
    embedded font PROGRAM to be missing -- /CharProcs streams live directly in the PDF --
    so there is no NOEMB analogue here, unlike Type1/TrueType."""
    if font.get("/CharProcs") is None:
        return FontVerdict("T3-a", False, False, "Type3 font with no /CharProcs")
    return FontVerdict("T3-a", True, False)


def type3_char_proc(font: pikepdf.Object, code: int) -> pikepdf.Object | None:
    """T3-a's resolution mechanism: code -> glyph name (via `encoding_map`, reused rather
    than reimplemented) -> that name indexes /CharProcs, whose value is the glyph's own
    content stream. None if the code has no name, or the name has no /CharProcs entry --
    both are per-glyph absences, not a font-wide refusal; T3-a always resolves at the font
    level, and a missing individual CharProc is exactly what `glyph_verdict`'s A-8 catches
    downstream."""
    name = encoding_map(font).get(code)
    if name is None:
        return None
    char_procs = font.get("/CharProcs")
    if char_procs is None:
        return None
    return char_procs.get("/" + name)


def type3_width(font: pikepdf.Object, code: int) -> float | None:
    """T3-a width: /Widths (indexed from /FirstChar) is in GLYPH space, scaled by
    /FontMatrix[0] -- never divided by 1000. That /1000 convention is Type1/TrueType's
    font-unit convention and does not apply to Type3, whose /FontMatrix varies per font
    (0.001 and 1.0 both appear in this corpus; dividing by 1000 unconditionally is the
    documented trap). Returns the per-em value BEFORE font-size (Tf) scaling, which lives
    in the content stream, not the font dictionary."""
    first_char = font.get("/FirstChar")
    widths = font.get("/Widths")
    if first_char is None or widths is None:
        return None
    index = code - int(first_char)
    if index < 0 or index >= len(widths):
        return None
    glyph_width = float(widths[index])
    matrix = font.get("/FontMatrix")
    scale = float(matrix[0]) if matrix is not None else 0.001
    return glyph_width * scale


def cid_width(descendant_font: pikepdf.Object, cid: int) -> float:
    """C-4: /W's nested run-length format -- `[c [w w w] cFirst cLast w ...]` -- with /DW
    default 1000. Never /Widths, never /MissingWidth: those are the SIMPLE-font width keys
    and do not apply to CIDFonts at all.

    IMPORTANT 4: /W's shape is attacker-controlled (an untrusted upload), so a truncated
    array -- `[3 [100] 10]` (a dangling `cFirst` with no `cLast`/width after it) or `[3]`
    (a bare code with nothing after it at all) -- must classify (fall through to /DW)
    rather than raise IndexError. Every other helper in this module wraps untrusted-shape
    access the same way; this one previously didn't.
    """
    w = descendant_font.get("/W")
    if w is not None:
        items = list(w)
        i = 0
        while i + 1 < len(items):
            first = int(items[i])
            nxt = items[i + 1]
            if isinstance(nxt, pikepdf.Array):
                run = list(nxt)
                if first <= cid < first + len(run):
                    return float(run[cid - first])
                i += 2
            else:
                if i + 2 >= len(items):
                    break  # malformed: cFirst cLast with no width value after it
                last = int(nxt)
                width = float(items[i + 2])
                if first <= cid <= last:
                    return width
                i += 3
    dw = descendant_font.get("/DW")
    return float(dw) if dw is not None else 1000.0


def resolve_font(font: pikepdf.Object) -> FontVerdict:
    """Top-to-bottom, first match wins, branch ID always logged (TEXT-04, D-04).

    /Subtype is read FIRST -- see the module docstring's ordering rule. Reversing these
    two lines is the Pitfall-2 bug and costs 23% of the corpus.
    """
    subtype = str(font.get("/Subtype", ""))

    if subtype == "/Type0":
        return _resolve_type0(font)
    if subtype == "/Type3":
        return _resolve_type3(font)

    if subtype not in SIMPLE_SUBTYPES:
        return FontVerdict("UNKNOWN", False, False, f"unrecognised /Subtype {subtype!r}")

    descriptor = font.get("/FontDescriptor")
    symbolic = is_symbolic(descriptor)
    program = embedded_font_bytes(descriptor)

    if subtype == "/TrueType":
        return _resolve_truetype(font, symbolic, program)
    return _resolve_type1(font, symbolic, program is not None)


def _type1_glyph_names(program: FontProgram) -> list[str]:
    """Type1 glyph names, via `psLib.suckfont` DIRECTLY on the re-segmented bytes -- not
    via `t1Lib.T1Font.parse()`/`.getGlyphSet()`.

    A /FontFile is the three Type1 segments (ASCII cleartext header, BINARY eexec
    ciphertext, ASCII trailer) concatenated with no markers of their own -- only
    Length1/Length2/Length3 say where one ends and the next begins (ISO 32000-1 Table
    111). Round 1 fixed *locating* those boundaries (a PFB round-trip through
    `t1Lib.T1Font`, 36/147 -> 69/147). Round 2's re-review found that still left three
    independent bugs on the SAME path, each measured on the same corpus:

    1. **Trailer NUL (82 of 89 round-1 failures).** The trailer segment often carries a
       trailing NUL byte after "cleartomark". `cleartomark` is a defined systemdict
       operator; `"cleartomark\\x00"` is an undefined NAME, because psLib's tokenizer
       folds the NUL into the token. `.rstrip(b"\\x00")` on segment 3 before use fixes it.
    2. **ASCII encoding (2 of 89).** `T1Font`/`psLib` default to `encoding="ascii"`; a
       real font with a non-ASCII byte anywhere in its cleartext portions (e.g. a
       copyright glyph, 0xA9, in a comment) raises `UnicodeDecodeError`. `"latin-1"`
       accepts every byte value and fixes it generically.
    3. **Mandatory /Subrs (5 of 89, and this is the one that matters most).**
       `T1Font.parse()` does `self.font["Private"]["Subrs"]` unconditionally, AFTER
       `psLib.suckfont` has already populated `CharStrings` -- but `/Subrs` is OPTIONAL
       in a Type1 Private dict (it holds subroutines a charstring may reference; a font
       with none simply has none). A presence check only needs glyph NAMES
       (`CharStrings.keys()`), never the decrypted charstrings or subroutines
       `T1Font.parse()` goes on to build. Calling `psLib.suckfont` directly -- the exact
       call `T1Font.parse()` itself makes, one line before the `/Subrs` access --  gets
       the names without ever reaching that line, and needs no tempfile: `suckfont` takes
       bytes, not a path.

    Fixing only 1 and 2 does not move the needle: it converts the 82 `cleartomark`
    failures into `Subrs` `KeyError`s (measured). All three together reach 176/176 on the
    corpus (see the report for the full re-measurement and the red-then-green transcript
    for the corpus-rate test this enables).
    """
    if program.length1 is None or program.length2 is None:
        raise ValueError("Type1 program missing /Length1 or /Length2")
    length3 = program.length3
    if length3 is None:
        length3 = len(program.data) - program.length1 - program.length2
    seg1 = program.data[: program.length1]
    seg2 = program.data[program.length1 : program.length1 + program.length2]
    seg3_end = program.length1 + program.length2 + length3
    seg3 = program.data[program.length1 + program.length2 : seg3_end].rstrip(b"\x00")
    result = psLib.suckfont(seg1 + seg2 + seg3, encoding="latin-1")
    names: list[str] = list(result["CharStrings"].keys())
    return names


def _glyph_present(code: int | str, program: FontProgram) -> bool:
    """Sniffs the embedded program's format from its own bytes, not from a branch_id --
    resolve_font's branches span more than one underlying format each (T1-a covers both
    raw Type1 /FontFile and CFF-flavoured /FontFile3 Type1C), so trusting the branch name
    here would be wrong more often than right. `code` is a glyph NAME for name-keyed
    programs (Type1, CFF) or a numeric GID/CID for TrueType and CID-keyed CFF.
    """
    data = program.data
    if data[:4] == b"OTTO" or data[:4] == b"\x00\x01\x00\x00" or data[:4] in (b"true", b"typ1"):
        font = TTFont(io.BytesIO(data), fontNumber=0, lazy=True)
        order = font.getGlyphOrder()
        if isinstance(code, str):
            return code in order
        return 0 <= code < len(order)

    if data[:1] == b"\x01":  # bare CFF major version 1 -- both Type1C and CIDFontType0C
        cff = CFFFontSet()
        cff.decompile(io.BytesIO(data), None)
        top_dict = cff[cff.fontNames[0]]
        charset = top_dict.charset
        if isinstance(code, str):
            return code in charset
        if getattr(top_dict, "ROS", None) is not None:
            # CID-keyed: charset entries are "cidNNNNN" names, indexed by CID.
            return f"cid{code:05d}" in charset
        return 0 <= code < len(charset)

    if data[:2] == b"%!" or data[:1] == b"\x80":  # Type1 -- see _type1_glyph_names's docstring
        names = _type1_glyph_names(program)  # raises on missing lengths; caught below
        if isinstance(code, str):
            return code in names
        return 0 <= code < len(names)

    raise ValueError("unrecognised embedded font program format")


def glyph_presence(
    font_verdict: FontVerdict, code: int | str, font_program_bytes: FontProgram | None
) -> tuple[bool, bool]:
    """A-6: does the resolved glyph `code` exist in the embedded program `font_verdict`
    already classified as usable? Returns (editable, substitution) -- and NEVER a
    refusal, UNLESS `font_verdict` itself is already a refusal (see IMPORTANT 5 below).

    Both "the glyph is genuinely absent" and "the program could not be parsed at all"
    reach the same (True, True) downgrade. This is deliberate (controller-resolved
    ambiguity #1): an unparseable program is *strictly less informative* than a parsed
    program that lacks the glyph, so it cannot warrant a harsher verdict than the
    missing-glyph case already gets. A-6's whole point is that the missing-glyph case is
    resolvable by substitution, not a refusal.

    IMPORTANT 5: a font `resolve_font` already refused must not have any of its glyphs
    reported as present/editable -- this now agrees with `glyph_verdict`, which already
    propagated font-level refusals the same way. Checked FIRST, before even looking at
    `font_program_bytes`: an already-refused font's bytes are not this function's
    business to interpret at all.

    MUTATION PROOF: returning (False, False) from the except branch below (refusing
    instead of downgrading) flips `test_glyph_presence_downgrades_on_unparseable_program`
    red -- confirmed by running that mutation once (see the report).
    """
    if not font_verdict.editable:
        return False, False
    if not font_program_bytes:
        return True, True
    try:
        present = _glyph_present(code, font_program_bytes)
    except Exception:  # noqa: BLE001 - corrupt/unsupported program: downgrade, never refuse
        return True, True
    return True, not present


def glyph_verdict(font_verdict: FontVerdict, glyph_record: GlyphRecord) -> GlyphVerdict:
    """A-8/D-05: refuse exactly ONE glyph, never its font or run.

    `glyph_record.unicode` is playa's own best-effort resolution: it already tries
    /ToUnicode and falls back through the Adobe Glyph List for named encodings (Don't
    Hand-Roll: `playa.encodingdb`). So an empty result here already IS "no /ToUnicode
    mapping and no AGL-derivable name" collapsed into the one signal GlyphRecord actually
    carries -- a second, separate glyph-name check would be redundant, not missing.
    Falsy (`None` OR `""`) both count as empty: govdocs1_000_000135.pdf's Type3 glyphs
    resolve to `unicode=""`, not `None` (MUTATION PROOF: checking `is None` instead of
    falsy passes on that fixture's font-level shape but fails to refuse its actual
    glyphs -- confirmed by running that mutation once, see the report).

    A font that resolve_font already refused propagates that refusal per-glyph too (not a
    new cascade -- the font was already refused before this function is ever called).
    """
    if not font_verdict.editable:
        return GlyphVerdict(False, font_verdict.reason)
    if not glyph_record.unicode:
        return GlyphVerdict(False, "NOUNI")
    return GlyphVerdict(True, None)


def actualtext_verdict() -> FontVerdict:
    """A-7. A span covered by /ActualText is never an edit target: its user-visible text
    is not the concatenation of its glyphs' Unicode, so the glyph-level addressing this
    engine edits through does not describe what the reader sees. Display uses
    /ActualText; editing refuses. Called per span by the clusterer, not per font."""
    return FontVerdict("ACTUALTEXT", False, False, "span covered by /ActualText")


__all__ = [
    "FontProgram",
    "FontVerdict",
    "GlyphVerdict",
    "actualtext_verdict",
    "base_encoding",
    "cid_width",
    "cmap_subtable_ids",
    "embedded_font_bytes",
    "encoding_map",
    "glyph_presence",
    "glyph_verdict",
    "is_symbolic",
    "parse_differences",
    "resolve_font",
    "type3_char_proc",
    "type3_width",
]
