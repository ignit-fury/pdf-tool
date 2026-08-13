"""Run ID codec -- addresses immutable original bytes, never a counted ordinal.

TEXT-03 / D-02. A run ID must still point at the same text after the document
is edited. If it encoded "the Nth operator on this page", deleting any
earlier operator -- even a non-text one -- shifts every later ordinal and
every stored ID silently points somewhere new. A byte offset into the
original, immutable bytes cannot drift: the project's rule is
(original bytes, recipe) -> output, and the output is a throwaway that is
never the input to the next edit.

Grammar (exact, from 02-RESEARCH.md Section 5):

    {sourceHash}:p{page}:c{part}[/x{xobjObjid}]*[/a{annotIdx}:{apState}]
        [/t{patternObjid}][/y{charProcName}]:o{byteOffset}[:g{start}-{end}]

`o` is the byte offset of the operator keyword token within its own decoded
content-stream *part* -- not a counted ordinal, and only meaningful alongside
the part index (never in coalesced space). `source_hash` is a SHA-256 hex
digest, matching corpus/manifest.json's existing sha256 convention.

This module is a pure string codec: no pikepdf import, no playa import.
Phase 4 will eventually echo run IDs back from an untrusted browser client,
so decode_run_id uses a strict regex match and raises a typed ValueError on
anything that does not match -- never eval, never unchecked str.split
indexing.
"""

import re
from typing import TypedDict

# The complete PDF content-stream operator keyword set (ISO 32000-1 Annex A).
# resolve_run_id_offset uses this to confirm a decoded byte offset lands on
# an operator token -- not mid-operand, mid-string, or mid-token.
_OPERATORS = frozenset(
    {
        "b", "B", "b*", "B*", "BDC", "BI", "BMC", "BT", "BX", "c", "cm", "CS",
        "cs", "d", "d0", "d1", "Do", "DP", "EI", "EMC", "ET", "EX", "f", "F",
        "f*", "G", "g", "gs", "h", "i", "ID", "j", "J", "k", "K", "l", "m",
        "M", "MP", "n", "q", "Q", "re", "RG", "rg", "ri", "s", "S", "SC",
        "sc", "SCN", "scn", "sh", "T*", "Tc", "Td", "TD", "Tf", "Tj", "TJ",
        "TL", "Tm", "Tr", "Ts", "Tw", "Tz", "v", "w", "W", "W*", "y", "'",
        '"',
    }
)

# PDF whitespace + delimiter bytes -- a token ends at the first one of these.
_TOKEN_BOUNDARY = frozenset(b"\x00\t\n\x0c\r ()<>[]{}/%")

_NAME_RE = r"[A-Za-z0-9_.+-]+"
_RUN_ID_RE = re.compile(
    r"^(?P<source_hash>[0-9a-f]{64})"
    r":p(?P<page>\d+)"
    r":c(?P<part>\d+)"
    r"(?P<xobj_path>(?:/x\d+)*)"
    rf"(?:/a(?P<annot_idx>\d+):(?P<ap_state>{_NAME_RE}))?"
    r"(?:/t(?P<pattern>\d+))?"
    rf"(?:/y(?P<charproc>{_NAME_RE}))?"
    r":o(?P<byte_offset>\d+)"
    r"(?::g(?P<g_start>\d+)-(?P<g_end>\d+))?$"
)
_XOBJ_RE = re.compile(r"/x(\d+)")


class RunIdParts(TypedDict):
    source_hash: str
    page: int
    part: int
    xobj_path: tuple[int, ...]
    annot: tuple[int, str] | None
    pattern: int | None
    charproc: str | None
    byte_offset: int
    subrange: tuple[int, int] | None


def encode_run_id(
    source_hash: str,
    page: int,
    part: int,
    *,
    xobj_path: tuple[int, ...] = (),
    annot: tuple[int, str] | None = None,
    pattern: int | None = None,
    charproc: str | None = None,
    byte_offset: int,
    subrange: tuple[int, int] | None = None,
) -> str:
    """Build a run ID. See module docstring for the exact grammar."""
    segments = [f"{source_hash}:p{page}:c{part}"]
    for objid in xobj_path:
        segments.append(f"/x{objid}")
    if annot is not None:
        annot_idx, ap_state = annot
        segments.append(f"/a{annot_idx}:{ap_state}")
    if pattern is not None:
        segments.append(f"/t{pattern}")
    if charproc is not None:
        segments.append(f"/y{charproc}")
    segments.append(f":o{byte_offset}")
    if subrange is not None:
        start, end = subrange
        segments.append(f":g{start}-{end}")
    return "".join(segments)


def decode_run_id(run_id: str) -> RunIdParts:
    """Parse a run ID produced by encode_run_id.

    encode_run_id(**decode_run_id(x)) == x for every shape the grammar
    permits. Raises ValueError on any string that does not match the
    grammar exactly -- this is the untrusted-input boundary Phase 4 will
    eventually hit, so it is a strict regex match, never eval or unchecked
    str.split indexing.
    """
    match = _RUN_ID_RE.match(run_id)
    if match is None:
        raise ValueError(f"malformed run id: {run_id!r}")

    xobj_path = tuple(int(o) for o in _XOBJ_RE.findall(match.group("xobj_path")))

    annot: tuple[int, str] | None = None
    annot_idx = match.group("annot_idx")
    if annot_idx is not None:
        annot = (int(annot_idx), match.group("ap_state"))

    pattern_str = match.group("pattern")
    pattern = int(pattern_str) if pattern_str is not None else None

    subrange: tuple[int, int] | None = None
    g_start = match.group("g_start")
    if g_start is not None:
        subrange = (int(g_start), int(match.group("g_end")))

    return RunIdParts(
        source_hash=match.group("source_hash"),
        page=int(match.group("page")),
        part=int(match.group("part")),
        xobj_path=xobj_path,
        annot=annot,
        pattern=pattern,
        charproc=match.group("charproc"),
        byte_offset=int(match.group("byte_offset")),
        subrange=subrange,
    )


def resolve_run_id_offset(run_id: str, original_bytes_by_part: dict[int, bytes]) -> bool:
    """Seek to the decoded byte offset and confirm an operator keyword starts there.

    This is the proof that a run ID addresses real, immutable bytes rather
    than a counted ordinal that could silently drift after an edit: add 1 to
    the encoded byte offset and this must return False.
    """
    parts = decode_run_id(run_id)
    part_bytes = original_bytes_by_part.get(parts["part"])
    if part_bytes is None:
        return False

    offset = parts["byte_offset"]
    if offset < 0 or offset >= len(part_bytes):
        return False

    # Must be a token *start*: preceded by a boundary, or at position 0.
    # Without this, an offset that lands mid-token (e.g. the "j" in "Tj")
    # can accidentally match a real single-character operator ("j" is line
    # join) and falsely resolve -- forward scanning alone is not enough.
    if offset > 0 and part_bytes[offset - 1] not in _TOKEN_BOUNDARY:
        return False

    end = offset
    while end < len(part_bytes) and part_bytes[end] not in _TOKEN_BOUNDARY:
        end += 1

    token = part_bytes[offset:end].decode("latin-1")
    return token in _OPERATORS
