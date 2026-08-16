"""CLAS-04/CLAS-05: per-run editability verdict, and the whole-document orchestration.

The last module of Phase 2 -- it connects every earlier piece: `engine.run_id` decodes a
run's own address, `engine.shared_xobjects` says which Form XObjects are running
headers/footers, `engine.encoding_table` says whether a font (and a glyph within it) can
be edited, `engine.clusterer`/`engine.classify_page` produce the runs and page buckets
this module classifies. Nothing here imports playa directly -- `import playa` stays
confined to `engine.playa_boundary`; this module reaches it only through
`engine.playa_boundary.open_document` and the walker/clusterer functions that already
wrap it.

## DEVIATION from 02-08-PLAN.md's stated `classify_document(pdf: pikepdf.Pdf)` signature

`classify_document` needs BOTH a pikepdf handle (for `shared_form_xobjects` and this
module's own font-resolution path below) AND a playa `Document` (for
`located_cluster_records`/`cluster_page`) -- two independent views of the same bytes, and
nothing converts one into the other. Taking only `pikepdf.Pdf` as the plan literally
specified leaves no way to obtain the playa side. Takes a `path` instead and opens both
internally from the same bytes.

## How a FontVerdict is resolved per glyph

`GlyphRecord.font_id` is an opaque integer, interned fresh per page walk
(`engine.walker._FontIds`, private, no reverse lookup) -- there is no route from it back to
a pikepdf font dict. Instead: for each glyph, its OWN `StreamPath` (already known before
clustering -- `located_cluster_records` yields `(StreamPath, GlyphRecord, ClusterAttrs)`)
gives `xobj_path`; its `operator_byte_offset`/`stream_id` locate the exact stream and
position. Find the LAST `/Name size Tf` occurrence at or before that byte offset via a
direct regex scan of the DECODED stream bytes -- `Tf`'s syntax (`/Name number Tf`) is fixed
by ISO 32000-1 with no exceptions, so this is exact, not a heuristic.
`pikepdf.parse_content_stream` was considered and rejected: it gives operators in stream
order but exposes no byte position for any of them, so it cannot answer "which Tf came
before THIS byte offset" -- only a raw scan over the same bytes `resolve_run_id_offset`
already trusts can.

This must run BEFORE clustering, not after: `cluster_page`'s `glyph_verdict_fn` parameter
(D-05's bad-glyph split signal) needs a verdict per glyph as clustering happens, so a
run's own font cannot be resolved only after the run exists -- it is resolved once per
glyph (cached per `(stream identity, resource name)`, since a page typically has very few
distinct fonts) and a run's own verdict, after clustering, is simply its first glyph's
(D-01 breaks a run on font change, so this is exact, not an approximation).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pikepdf

from engine.classify_page import Bucket, classify_page
from engine.clusterer import cluster_page
from engine.encoding_table import FontVerdict, GlyphVerdict, glyph_verdict, resolve_font
from engine.playa_boundary import open_document
from engine.records import GlyphRecord, RunRecord
from engine.shared_xobjects import shared_form_xobjects
from engine.walker import StreamPath, located_cluster_records

RunState = Literal["editable_original", "editable_substitution", "not_editable"]

# ISO 32000-1 Table 105/9.3: `/Name size Tf`. A PDF name has no embedded whitespace by
# spec, so this cannot mis-split a name into two tokens.
_TF_RE = re.compile(rb"/([^\s/\[\](){}<>%]+)\s+[+-]?[0-9.]+\s+Tf\b")


@dataclass(frozen=True, slots=True)
class RunVerdict:
    """CLAS-04's three-state per-run verdict. `reason` is populated only when
    `state == "not_editable"` -- symbolic, Type3, no-ToUnicode, shared-Form-XObject and
    RTL each get their own distinct string, never a generic "not editable" (mirrors
    `FontVerdict`/`GlyphVerdict`'s established shape in `engine.encoding_table`)."""

    state: RunState
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentClassification:
    """CLAS-05's shape: refusal lives at the page or run level, never the document.
    `page_buckets[i]` is `classify_page`'s verdict for page `i`; `runs` is every
    `RunRecord` the document produced, paired with its `classify_run` verdict. A page in
    a scan/empty/vector-outlined bucket contributes ZERO entries to `runs` by
    construction -- clustering only clusters glyphs that exist, and those buckets are
    defined by having none. That is not a gap: the page bucket already says so, which is
    exactly the "per-page" granularity CLAS-05 permits."""

    page_buckets: list[Bucket]
    runs: list[tuple[RunRecord, RunVerdict]]


def _find_active_font_name(stream_bytes: bytes, byte_offset: int) -> bytes | None:
    """The resource name of the LAST `Tf` at or before `byte_offset` in `stream_bytes`.
    `None` if no `Tf` precedes it."""
    name: bytes | None = None
    for match in _TF_RE.finditer(stream_bytes):
        if match.start() > byte_offset:
            break
        name = match.group(1)
    return name


def _stream_bytes_and_resources(
    pdf: pikepdf.Pdf, page_index: int, part: int, xobj_path: tuple[int, ...]
) -> tuple[bytes, pikepdf.Object | None]:
    """The raw bytes and `/Resources` dict of the ONE stream a glyph's provenance
    addresses. Mirrors `engine.playa_boundary._walk_level`'s own inheritance rule: an
    XObject with no `/Resources` of its own inherits the page's. Form XObjects never
    have a `/Contents` array -- the XObject stream itself IS the content, so `part` is
    only meaningful for the page's own `/Contents` (which may be a single stream or an
    array).
    """
    page = pdf.pages[page_index]
    if not xobj_path:
        contents = page.obj.get("/Contents")
        if contents is None:
            return b"", page.obj.get("/Resources")
        stream = contents[part] if isinstance(contents, pikepdf.Array) else contents
        return bytes(stream.read_bytes()), page.obj.get("/Resources")

    xobj = pdf.get_object((xobj_path[-1], 0))
    resources = xobj.get("/Resources")
    if resources is None:
        resources = page.obj.get("/Resources")
    return bytes(xobj.read_bytes()), resources


def _resolve_font_for_glyph(
    pdf: pikepdf.Pdf,
    page_index: int,
    path: StreamPath,
    glyph: GlyphRecord,
    cache: dict[tuple[int, bytes], FontVerdict],
) -> FontVerdict:
    """The `FontVerdict` for whichever font was active at this glyph's own operator. A
    glyph the font-lookup itself cannot resolve (no `Tf` found, or the name is not in
    `/Resources /Font`) refuses with its own distinct reason -- never silently treated
    as editable, and never conflated with `resolve_font`'s own named refusal branches."""
    stream_bytes, resources = _stream_bytes_and_resources(
        pdf, page_index, glyph.stream_id, path.xobj_path
    )
    name = _find_active_font_name(stream_bytes, glyph.operator_byte_offset)
    if name is None:
        return FontVerdict("NO-TF", False, False, "no /Tf operator precedes this glyph")

    fonts = resources.get("/Font") if resources is not None else None
    font_dict = fonts.get("/" + name.decode("latin-1")) if fonts is not None else None
    if font_dict is None:
        return FontVerdict(
            "NO-TF", False, False, "active font resource name not found in /Resources /Font"
        )

    cache_key = (id(resources), name)
    if cache_key not in cache:
        cache[cache_key] = resolve_font(font_dict)
    return cache[cache_key]


def _is_rtl(display_text: str) -> bool:
    """02-RESEARCH.md Section 3: PDF has no RTL text state, so a producer emits RTL
    glyphs in visual (already-correct) stream order -- detection is purely a property of
    the DECODED TEXT's own Unicode bidi class, per 02-07's own carry-forward ("the
    editable=False/reason=right-to-left-text VERDICT itself is 02-08's job, not produced
    here")."""
    for ch in display_text:
        cls = unicodedata.bidirectional(ch)
        if cls in ("AL", "R"):
            return True
        if cls == "L":
            return False
    return False


def classify_run(
    run_record: RunRecord,
    font_verdict: FontVerdict,
    shared_xobject_ids: dict[int, int],
    xobj_path: tuple[int, ...] = (),
) -> RunVerdict:
    """CLAS-04. Checked in this order, first match wins: a run's OWN xobj_path first
    (D-01/D-02's addressing model is about WHERE a run lives; a shared, editable-in-
    isolation Type3 header is still, first and foremost, a shared header), then Type3
    (always refused regardless of `font_verdict.editable` -- rewriting a glyph means
    rewriting its own CharProc content stream, a materially larger Phase 3 operation than
    swapping a `Tj` string), then the font's own refusal, then RTL, then a defensive
    per-glyph re-check (D-05's isolation happens upstream in the clusterer; this does not
    trust that blindly), else editable.

    `xobj_path` is passed separately rather than decoded from `run_record.run_id` here:
    the caller (`classify_document`) already has it from the same `StreamPath` used to
    build the run, and decoding a string this function's own caller just encoded would be
    redundant round-tripping.
    """
    if xobj_path and any(oid in shared_xobject_ids for oid in xobj_path):
        share_count = shared_xobject_ids[xobj_path[-1]]
        return RunVerdict(
            "not_editable",
            f"shared Form XObject, referenced by {share_count} pages",
        )

    if font_verdict.branch_id == "T3-a":
        return RunVerdict("not_editable", "Type3")

    if not font_verdict.editable:
        return RunVerdict("not_editable", font_verdict.reason)

    if _is_rtl(run_record.display_text):
        return RunVerdict("not_editable", "right-to-left text")

    for glyph in run_record.glyphs:
        verdict = glyph_verdict(font_verdict, glyph)
        if not verdict.editable:
            return RunVerdict("not_editable", verdict.reason)

    state: RunState = (
        "editable_substitution" if font_verdict.substitution else "editable_original"
    )
    return RunVerdict(state)


def classify_document(path: str | Path) -> DocumentClassification:
    """CLAS-05: walk every page, cluster every run, classify every run. Refusal is
    always per-page (`page_buckets`) or per-run (`runs`) -- never a whole-document
    verdict; there is no field on `DocumentClassification` that could express one.
    """
    pdf = pikepdf.open(path)
    shared = shared_form_xobjects(pdf)
    font_cache: dict[tuple[int, bytes], FontVerdict] = {}

    page_buckets: list[Bucket] = []
    runs: list[tuple[RunRecord, RunVerdict]] = []

    try:
        with open_document(path) as doc:
            for page_index, page in enumerate(doc.pages):
                located = list(located_cluster_records(page, page_index, doc))
                glyph_only = [record for _path, record, _attrs in located]
                page_buckets.append(classify_page(glyph_only, page))

                # Resolved once per glyph, before clustering -- see module docstring.
                # A closure-local dict keyed by id(glyph) is safe here: it is built and
                # fully consumed within this one page's iteration, never stored or
                # compared beyond it, unlike a persisted GlyphRecord-keyed structure.
                glyph_font: dict[int, FontVerdict] = {}
                glyph_path: dict[int, tuple[int, ...]] = {}
                for stream_path, record, _attrs in located:
                    glyph_font[id(record)] = _resolve_font_for_glyph(
                        pdf, page_index, stream_path, record, font_cache
                    )
                    glyph_path[id(record)] = stream_path.xobj_path

                def _verdict_fn(record: GlyphRecord) -> GlyphVerdict:
                    return glyph_verdict(glyph_font[id(record)], record)

                source_hash = "0" * 64  # classify_document never decodes an ID to bytes
                page_runs = cluster_page(page_index, located, source_hash, _verdict_fn)
                for run in page_runs:
                    first_glyph_id = id(run.glyphs[0])
                    run_font_verdict = glyph_font.get(first_glyph_id)
                    run_xobj_path = glyph_path.get(first_glyph_id, ())
                    if run_font_verdict is None:
                        # The clustered glyph is not object-identical to any glyph in
                        # `located` -- would only happen if clustering copied records,
                        # which it does not (verified: cluster_page slices the same
                        # GlyphRecord instances it was given). Refuse loudly rather than
                        # silently treat as editable.
                        runs.append(
                            (
                                run,
                                RunVerdict(
                                    "not_editable", "font resolution lost across clustering"
                                ),
                            )
                        )
                        continue
                    runs.append(
                        (run, classify_run(run, run_font_verdict, shared, run_xobj_path))
                    )
    finally:
        pdf.close()

    return DocumentClassification(page_buckets=page_buckets, runs=runs)


__all__ = [
    "DocumentClassification",
    "RunVerdict",
    "classify_document",
    "classify_run",
]
