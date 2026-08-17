"""TEXT-06, both halves.

Task 1: shared Form XObject detection reproduces the measured corpus counts, and a
resource-name-keyed detector is proven wrong on the same document. Those tests exercise
`shared_form_xobjects()` directly against pikepdf.

Task 2: the walker finds text in every location outside a page's own /Contents, addressed
to the stream it is actually in, bounded against cyclic and deeply-nested graphs. Those
tests drive `engine.walker.walk_document` / `located_glyph_records`.

Synthetic fixtures are built inline with pikepdf and parsed straight out of memory
(`playa.parse`), never committed as files -- following the precedent set by
`test_dedupe_and_form_filter_survive_mutation` below. Tests may import playa directly; the
one-module rule binds `engine/` only.
"""

import collections
import io
import json
import logging
from pathlib import Path

import pikepdf
import playa
import pytest

from engine.run_id import encode_run_id, resolve_run_id_offset
from engine.shared_xobjects import shared_form_xobjects
from engine.walker import (
    MAX_RECURSION_DEPTH,
    MAX_STREAMS_PER_PAGE,
    StreamPath,
    located_glyph_records,
    walk_document,
)

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

IRS_1040_INSTRUCTIONS = CORPUS_DIR / "irs_1040_instructions.pdf"
IRS_PUBLICATION_17 = CORPUS_DIR / "irs_publication_17.pdf"
GOVDOCS_013_013085 = CORPUS_DIR / "govdocs1_013_013085.pdf"

# irs_1040_instructions.pdf page 0 draws its cover headline through Form XObject /I1
# (objid 77024), one word-fragment per Tj: "Futu" then "r". Both offsets are offsets into
# I1's OWN decoded stream, and both were re-measured here rather than taken on faith.
I1_OBJID = 77024
I1_FUTU_OFFSET = 673
I1_R_OFFSET = 679

# Any 64 hex chars: these tests exercise the offset half of a run ID, not the hash half,
# which tests/test_run_id.py already covers.
FAKE_HASH = "0" * 64


def test_shared_form_xobject_detection_matches_measured_counts() -> None:
    """02-RESEARCH.md Section 5's measured table: irs_1040_instructions.pdf's most-shared
    Form XObject is referenced from 43 pages, irs_publication_17.pdf's from 47.

    MUTATION: swap the key in shared_form_xobjects from `xo.objgen[0]` (object identity)
    to the resource dictionary's local name (the TEXT-06 row of 02-RESEARCH.md's "Every
    check..." table). Confirmed by running it (see the report): the 43-page object is
    referenced under five different local names (/I1, /I2, /I3, /I4, /I5), and no single
    name's sub-count reaches 43 -- the best does 26. The test below this one pins that
    permanently rather than leaving it as a one-off manual run.
    """
    with pikepdf.open(str(IRS_1040_INSTRUCTIONS)) as pdf:
        shared = shared_form_xobjects(pdf)
        assert max(shared.values()) == 43

    with pikepdf.open(str(IRS_PUBLICATION_17)) as pdf:
        shared = shared_form_xobjects(pdf)
        assert max(shared.values()) == 47


def test_nested_form_xobject_reachable_only_through_another_forms_resources() -> None:
    """02-RESEARCH.md Section 5's prose (walk "every page's /Resources /XObject (plus
    nested XObject resources)") is the correct rule; its own code example omitted the
    nesting, and a faithful transcription of that example was a total false negative on
    this document: a page-only walk reports 0 shared / max 0, because every reference to
    the actually-shared Form XObject here is reached one level down, through a top-level
    Form XObject's own /Resources /XObject, never directly from a page.

    MUTATION: replace `_walk`'s recursive call with a single flat pass over just
    `page.get("/Resources")` (i.e. delete the nesting). Confirmed by running it (see the
    report): this document's count collapses from 7 shared / max 36 back to 0 shared / max
    0 -- "nothing is shared here" about a document with a header XObject on 36 of its
    pages, the wrong-direction failure this whole module exists to prevent.
    """
    with pikepdf.open(str(GOVDOCS_013_013085)) as pdf:
        shared = shared_form_xobjects(pdf)
        assert len(shared) == 7
        assert max(shared.values()) == 36


def test_dedupe_and_form_filter_survive_mutation() -> None:
    """Two behaviours the module docstring promises but neither pinned document can guard
    (02-RESEARCH.md's CLAS-02 precedent: a check that cannot go red on the corpus must not
    claim to) -- a synthetic fixture built inline, per that precedent, rather than adding a
    committed fixture file:

    1. Per-page dedupe: a page referencing the SAME Form XObject under two different local
       names must count as ONE reference from that page, not two.
    2. Subtype filter: a shared /Image XObject must never appear in the result -- only
       /Form.

    Fixture: 2 pages sharing one Form XObject (page 0 names it twice, page 1 once -- 3
    resource-dict entries, 2 distinct pages) and one Image XObject referenced from both
    pages.

    MUTATION 1 (dedupe): drop the `if objgen in visited: continue` guard's sibling --
    remove the per-page `seen` set entirely and count every dict entry. Confirmed by
    running it: the Form's count becomes 3 (one page counted twice), reddening the first
    assertion below.
    MUTATION 2 (subtype filter): change `if str(xo.get("/Subtype")) != "/Form": continue`
    to `if False: continue` (i.e. stop filtering). Confirmed by running it: the Image's
    objid appears in the result, reddening the second assertion below.
    """
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page()
    pdf.add_blank_page()

    form = pdf.make_stream(b"q Q")
    form.Subtype = pikepdf.Name("/Form")
    form.BBox = pikepdf.Array([0, 0, 1, 1])

    image = pdf.make_stream(b"\xff\xff\xff")
    image.Subtype = pikepdf.Name("/Image")
    image.Width = 1
    image.Height = 1

    pdf.pages[0].Resources = pikepdf.Dictionary(
        {"/XObject": pikepdf.Dictionary({"/F1": form, "/F2": form, "/Im1": image})}
    )
    pdf.pages[1].Resources = pikepdf.Dictionary(
        {"/XObject": pikepdf.Dictionary({"/F3": form, "/Im1": image})}
    )

    shared = shared_form_xobjects(pdf)

    assert shared[form.objgen[0]] == 2, "page 0's two names for the same Form must dedupe to one page"
    assert image.objgen[0] not in shared, "a shared Image XObject must never appear -- Form only"


def test_resource_name_keyed_mutation_undercounts_irs_1040() -> None:
    """The permanent negative case: keying by the resource dictionary's local NAME
    instead of object identity undercounts a shared Form XObject.

    irs_1040_instructions.pdf carries a Form XObject (the correct detector's own
    highest-count object) referenced from 43 pages -- but under five DIFFERENT local
    resource names across those pages ({'/I1', '/I2', '/I3', '/I4', '/I5'}, measured),
    because a PDF writer is free to name a page's resources however it likes. A detector
    keyed by name can therefore never assemble those 43 references into one bucket; the
    best any single name does is a strictly smaller sub-count. This is exactly the defect
    class named in 02-RESEARCH.md's "Every check..." table (TEXT-06 row): "Phase-1's
    producer cap keyed on a string that split one product into two buckets" -- here it is
    a shared header/footer XObject split across five buckets instead of a producer split
    across two.

    This test IS the mutation (inline, permanent) rather than a comment describing one
    that was run and discarded: `per_name` below re-walks the SAME object's own page
    references, keyed by `str(name)` instead of `xo.objgen[0]` -- exactly the change
    named in the module docstring as the one mistake to avoid.

    Deliberately restricted to this one object's own references, not a full
    name-keyed shared_form_xobjects rewrite: a full rewrite also merges *different*
    objects that happen to reuse the same local name (measured: a full name-keyed
    detector's overall max on this document is 81, driven by unrelated objects colliding
    on '/I1') -- a second, independent way name-keying is wrong, but conflating it with
    this test's claim would prove the wrong thing. This test isolates the undercount the
    task names: one object, split across names, so no single bucket reaches its true
    total.

    NOTE: `assert true_max_count == 43` below is documentation-by-measurement, not a
    second independent guard -- it fires for the same reason as
    test_shared_form_xobject_detection_matches_measured_counts under that test's own named
    mutation, so it does not add coverage on its own. `sum(per_name.values()) ==
    true_max_count` and the final undercount assertion are this test's actual, non-circular
    claims.
    """
    with pikepdf.open(str(IRS_1040_INSTRUCTIONS)) as pdf:
        correct = shared_form_xobjects(pdf)
        true_max_oid = max(correct, key=lambda oid: correct[oid])
        true_max_count = correct[true_max_oid]
        assert true_max_count == 43  # restated so this test stands alone; see NOTE above

        # The mutation: the true object's own page references, re-bucketed by resource
        # NAME instead of collapsed into one objgen-keyed bucket.
        per_name: collections.Counter[str] = collections.Counter()
        for page in pdf.pages:
            for name, xo in ((page.get("/Resources") or {}).get("/XObject") or {}).items():
                if str(xo.get("/Subtype")) == "/Form" and xo.objgen[0] == true_max_oid:
                    per_name[str(name)] += 1

        # Fixture assumption this test depends on: the shared object must actually carry
        # more than one local name, or the mutation would coincidentally still be correct.
        # Resource names are structural keys, not document text -- printing the count
        # rather than the names themselves stays inside the "no document content in
        # assertion messages" rule regardless.
        assert len(per_name) > 1, f"expected the shared object to carry >1 resource name, got {len(per_name)}"
        # Sanity: every one of the object's 43 page-references landed in exactly one
        # name bucket -- no page counted twice, none dropped.
        assert sum(per_name.values()) == true_max_count

        worst_case_name_keyed = max(per_name.values())
        assert worst_case_name_keyed < true_max_count, (
            f"best single-name bucket ({worst_case_name_keyed}) should undercount the "
            f"true objgen-keyed total ({true_max_count}) -- the undercount this test "
            f"exists to prove did not happen"
        )


# ---------------------------------------------------------------------------
# Task 2: the walker's recursion into text outside /Contents
# ---------------------------------------------------------------------------


def _helvetica() -> pikepdf.Dictionary:
    return pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type1,
        BaseFont=pikepdf.Name.Helvetica,
    )


def _show(text: bytes, font: bytes = b"/Helv") -> bytes:
    """One complete, minimal text-showing sequence."""
    return b"BT " + font + b" 12 Tf 10 10 Td (" + text + b") Tj ET\n"


def _parse(pdf: pikepdf.Pdf) -> playa.Document:
    """Serialise an in-memory pikepdf fixture straight into playa -- no file on disk."""
    buf = io.BytesIO()
    pdf.save(buf)
    return playa.parse(buf.getvalue())


def _form(pdf: pikepdf.Pdf, body: bytes, resources: pikepdf.Object) -> pikepdf.Object:
    form = pdf.make_stream(body)
    form.Type = pikepdf.Name.XObject
    form.Subtype = pikepdf.Name.Form
    form.BBox = pikepdf.Array([0, 0, 200, 200])
    form.Resources = resources
    return form


def test_form_xobject_glyphs_address_the_xobjects_own_stream() -> None:
    """The acceptance criterion, and Pitfall 4's discrimination, in one test.

    irs_1040_instructions.pdf page 0 draws its cover headline from inside Form XObject /I1
    one fragment per `Tj`: "Futu" at 673, "r" at 679. Re-measured from the file here rather
    than carried forward on faith -- they are offsets of the two `Tj` KEYWORDS within I1's
    OWN decoded stream.

    The second half is what makes this a Pitfall 4 test and not a count test: the run ID
    assembled from the record resolves against I1's own bytes and does NOT resolve against
    the page's /Contents. Had the walker delegated to `Page.flatten()`, every one of these
    records would carry a page-stream address -- a plausible integer pointing at different
    bytes -- and Phase 3 would rewrite the wrong operator.

    MUTATION (ran it): delete the `isinstance(item, XObjectObject)` recursion branch in
    `walker._walk_level`. Page 0 falls from 984 records to 435, none carrying an
    `xobj_path`, and `inside_i1` is empty -- every assertion below goes red.
    """
    with playa.open(str(IRS_1040_INSTRUCTIONS)) as doc:
        page = doc.pages[0]
        located = list(located_glyph_records(page, 0, doc))
        page_bytes = b"\n".join(bytes(s.buffer) for s in page.streams)

    inside_i1 = [(p, r) for p, r in located if p.xobj_path == (I1_OBJID,)]
    assert inside_i1, "no records addressed to Form XObject I1"
    offsets = {r.operator_byte_offset for _p, r in inside_i1}
    assert {I1_FUTU_OFFSET, I1_R_OFFSET} <= offsets, (
        f"expected the measured I1 offsets in {sorted(offsets)[:8]}..."
    )

    with pikepdf.open(str(IRS_1040_INSTRUCTIONS)) as pdf:
        i1_bytes = bytes(pdf.get_object((I1_OBJID, 0)).read_bytes())

    for path, record in inside_i1:
        if record.operator_byte_offset not in (I1_FUTU_OFFSET, I1_R_OFFSET):
            continue
        run_id = encode_run_id(
            FAKE_HASH,
            path.page,
            record.stream_id,
            xobj_path=path.xobj_path,
            annot=path.annot,
            pattern=path.pattern,
            charproc=path.charproc,
            byte_offset=record.operator_byte_offset,
        )
        assert resolve_run_id_offset(run_id, {record.stream_id: i1_bytes}), (
            "the offset must land on an operator keyword in I1's own stream"
        )
        assert not resolve_run_id_offset(run_id, {record.stream_id: page_bytes}), (
            "the offset must NOT be a page-/Contents address -- that is Pitfall 4"
        )


def test_self_referencing_form_xobject_walks_to_completion(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T-02-02 (CVE-2026-48155 shape). A Form XObject that `Do`-invokes itself, on a
    2-page document so the per-BRANCH visited set is exercised rather than a global one.

    Two claims:
    1. The walk terminates, with no RecursionError, and the text before the self-`Do` is
       still collected -- only the cyclic branch is cut, not the page.
    2. Exactly ONE record per page. The same XObject reappearing on page 2 is not a cycle
       and must not be suppressed: `parents` is rebuilt per branch for exactly this reason.

    MUTATION A (ran it): delete `if key in parents` from `_walk_level`. The walk still
    terminates -- the depth cap catches it -- but emits 65 records per page instead of 1
    (one per level down to MAX_RECURSION_DEPTH), reddening the count assertion.
    MUTATION B (ran it): delete BOTH the visited set and the depth cap. RecursionError.
    MUTATION C (ran it): make `parents` a single global set shared across pages instead of
    per branch. Page 1's record disappears -- 1 record instead of 2 -- which is real text
    silently lost, the failure the per-branch rule exists to prevent.
    """
    pdf = pikepdf.Pdf.new()
    resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    form = _form(pdf, _show(b"X") + b"/Fself Do\n", resources)
    # The self-reference, added after construction because it needs the object to exist.
    form.Resources.XObject = pikepdf.Dictionary(Fself=form)
    for _ in range(2):
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pdf.make_stream(b"/Fx Do\n")
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fx=form))

    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))

    assert len(records) == 2, "one glyph per page: the cycle is cut, the text is not"
    assert {p.page for p, _r in records} == {0, 1}
    assert all(len(p.xobj_path) == 1 for p, _r in records)
    assert any("cycle guard" in m for m in caplog.messages), "the abort must be logged"
    assert not any("X" in m for m in caplog.messages), "T-02-04: no glyph text in logs"


def test_mutually_referencing_form_xobjects_terminate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The A->B->A shape, which a naive "is this stream its own parent?" check misses.

    A shows "A" then invokes B; B shows "B" then invokes A. The walk must collect exactly
    one "A" and one "B" and stop -- the second entry into A is the cycle.

    MUTATION (ran it): replace the `key in parents` set membership with `key == parent_key`
    (self-reference only). The walk emits 64 alternating records instead of 2, stopped only
    by the depth cap, reddening the count assertion.
    """
    pdf = pikepdf.Pdf.new()
    fonts = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    form_a = _form(pdf, _show(b"A") + b"/Fb Do\n", pikepdf.Dictionary(fonts))
    form_b = _form(pdf, _show(b"B") + b"/Fa Do\n", pikepdf.Dictionary(fonts))
    form_a.Resources.XObject = pikepdf.Dictionary(Fb=form_b)
    form_b.Resources.XObject = pikepdf.Dictionary(Fa=form_a)
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"/Fa Do\n")
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fa=form_a))

    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))

    assert [r.unicode for _p, r in records] == ["A", "B"]
    assert any("cycle guard" in m for m in caplog.messages)


def test_deep_form_xobject_chain_stops_at_the_depth_cap(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T-02-03. A 200-deep acyclic chain -- no visited set can stop this one, and Python's
    own recursion limit is the thing being defended.

    Each link shows one glyph and invokes the next, so the record count IS the depth
    reached: exactly MAX_RECURSION_DEPTH levels are walked (depths 1..64), the 65th is
    refused, and nothing propagates to the caller.

    MUTATION (ran it): delete the `depth > MAX_RECURSION_DEPTH` check. All 200 levels are
    walked -- 200 records, not 64 -- and the assertion goes red; at chain lengths past
    roughly 300 the same mutation turns into a RecursionError instead.
    """
    pdf = pikepdf.Pdf.new()
    chain_length = 200
    # Built deepest-first: each new link is a distinct object that shows one glyph and
    # invokes the link below it.
    link = _form(pdf, _show(b"z"), pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica())))
    for _ in range(chain_length - 1):
        parent = _form(
            pdf,
            _show(b"z") + b"/Fn Do\n",
            pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica())),
        )
        parent.Resources.XObject = pikepdf.Dictionary(Fn=link)
        link = parent
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"/F0 Do\n")
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(F0=link))

    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))

    assert len(records) == MAX_RECURSION_DEPTH
    assert any("depth cap" in m for m in caplog.messages)


def _type3_font(pdf: pikepdf.Pdf, charprocs: dict[str, bytes]) -> pikepdf.Object:
    """A Type3 font whose CharProcs each show text, with NO /Resources of its own -- so
    each CharProc inherits the page's and re-declares all of its siblings. That is the real
    corpus shape (govdocs1_004_004050.pdf) that `declared_seen` and the pending queue exist
    to bound."""
    procs = pikepdf.Dictionary(
        {
            f"/{name}": pdf.make_stream(b"10 0 0 0 10 10 d1\n" + body)
            for name, body in charprocs.items()
        }
    )
    names = sorted(charprocs)
    return pikepdf.Dictionary(
        Type=pikepdf.Name.Font,
        Subtype=pikepdf.Name.Type3,
        FontBBox=pikepdf.Array([0, 0, 10, 10]),
        FontMatrix=pikepdf.Array([0.001, 0, 0, 0.001, 0, 0]),
        CharProcs=procs,
        Encoding=pikepdf.Dictionary(
            Type=pikepdf.Name.Encoding,
            Differences=pikepdf.Array([97, *[pikepdf.Name(f"/{n}") for n in names]]),
        ),
        FirstChar=97,
        LastChar=97 + len(names) - 1,
        Widths=pikepdf.Array([1000] * len(names)),
    )


def test_declared_charprocs_are_siblings_not_a_chain() -> None:
    """The controller's finding, pinned. 100 CharProcs, each showing one glyph, none with
    /Resources of its own -- so each inherits the page's and re-declares all 100.

    All 100 must be entered. Asserting on the COUNT ENTERED, not on elapsed time: the
    defective version finishes in 0.04s precisely *because* it stops early, so a timing
    assertion would not have caught this at all.

    MUTATION (ran it): drain `pending` at the end of `_walk_level` at `depth + 1` instead
    of flat in `located_glyph_records` -- i.e. descend into each declared sibling, which is
    what the code did before this test existed. The 100 siblings become a 100-deep chain,
    `MAX_RECURSION_DEPTH` truncates it, and only 64 records appear.
    MEASURED with the same mutation on corpus/public/govdocs1_004_004050.pdf page 0: 424
    distinct CharProc streams reached, 64 walked, 360 aborted at the depth cap, max depth
    65. Queued: 424 walked, 0 aborted, max depth 0.
    """
    count = 100
    pdf = pikepdf.Pdf.new()
    font = _type3_font(
        pdf, {f"c{i}": _show(b"x") for i in range(count)}
    )
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"BT /T3 12 Tf 10 10 Td (a) Tj ET\n")
    page.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(T3=font, Helv=_helvetica())
    )

    records = list(walk_document(_parse(pdf)))
    from_charprocs = [p for p, _r in records if p.charproc is not None]

    assert len(from_charprocs) == count, (
        f"every declared CharProc must be entered exactly once; got {len(from_charprocs)}"
    )
    assert len({p.charproc for p in from_charprocs}) == count, "and each exactly once"


def test_tiling_pattern_and_type3_charproc_text_is_found() -> None:
    """The two locations the corpus cannot exercise at all: across all 217 documents,
    `walk_document` produces zero records from a tiling pattern and zero from a Type3
    CharProc (measured -- CharProcs in this corpus are bitmap and vector glyphs). Without a
    synthetic fixture both branches would ship never having run.

    MUTATION (ran it): delete the `tiling_patterns(...)` loop from `_walk_level`; the
    pattern assertion goes red. Delete the `type3_charprocs(...)` loop; the CharProc
    assertion goes red.
    """
    pdf = pikepdf.Pdf.new()
    pattern = pdf.make_stream(_show(b"P"))
    pattern.Type = pikepdf.Name.Pattern
    pattern.PatternType = 1
    pattern.PaintType = 1
    pattern.TilingType = 1
    pattern.BBox = pikepdf.Array([0, 0, 10, 10])
    pattern.XStep = 10
    pattern.YStep = 10
    pattern.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))

    font = _type3_font(pdf, {"a": _show(b"C")})
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(
        b"/Pattern cs /P0 scn 0 0 50 50 re f\nBT /T3 12 Tf 10 10 Td (a) Tj ET\n"
    )
    page.Resources = pikepdf.Dictionary(
        Font=pikepdf.Dictionary(T3=font, Helv=_helvetica()),
        Pattern=pikepdf.Dictionary(P0=pattern),
    )

    records = list(walk_document(_parse(pdf)))
    by_where = {
        ("pattern" if p.pattern is not None else "charproc" if p.charproc else "page"): r
        for p, r in records
    }
    assert by_where["pattern"].unicode == "P", "text inside a tiling pattern must be found"
    assert by_where["charproc"].unicode == "C", "text inside a Type3 CharProc must be found"
    # The pattern segment is an objid, and it is the objid in the SAVED file -- pikepdf
    # renumbers on save, so this deliberately does not compare against the pre-save
    # `pattern.objgen`. That the objid is the right one is pinned exactly, against a real
    # file, by test_form_xobject_glyphs_address_the_xobjects_own_stream (I1 = 77024).
    pattern_segments = [p.pattern for p, _r in records if p.pattern is not None]
    assert len(set(pattern_segments)) == 1 and pattern_segments[0] > 0, (
        "the pattern path segment is t{objid}"
    )
    assert [p.charproc for p, _r in records if p.charproc] == ["a"], (
        "the CharProc path segment is y{name}"
    )


def test_annotation_appearance_is_selected_by_as() -> None:
    """/AP /N may be a stream OR a dict of states keyed by /AS (ISO 32000-1 12.5.5).

    The corpus cannot pin the selection: measured across all 13
    annotation_appearance_streams documents, every state dict is a checkbox whose /AS is
    /Off while /AP /N defines only the "on" state, so the correct answer is always "render
    nothing" and a detector that ignored /AS entirely would look identical.

    MUTATION (ran it): ignore /AS in `annotation_appearances` and take the dict's first
    entry. The second case below goes red -- text appears for an annotation whose current
    appearance state is Off, i.e. text no viewer is displaying.
    """
    for state, expected in (("On", ["A"]), ("Off", [])):
        pdf = pikepdf.Pdf.new()
        resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
        on = _form(pdf, _show(b"A"), resources)
        page = pdf.add_blank_page(page_size=(200, 200))
        page.Contents = pdf.make_stream(b"")
        page.Resources = pikepdf.Dictionary()
        page.Annots = pikepdf.Array(
            [
                pdf.make_indirect(
                    pikepdf.Dictionary(
                        Type=pikepdf.Name.Annot,
                        Subtype=pikepdf.Name.Widget,
                        Rect=pikepdf.Array([0, 0, 100, 100]),
                        AS=pikepdf.Name(f"/{state}"),
                        AP=pikepdf.Dictionary(N=pikepdf.Dictionary({"/On": on})),
                    )
                )
            ]
        )

        records = list(walk_document(_parse(pdf)))
        assert [r.unicode for _p, r in records] == expected, f"/AS /{state}"
        if expected:
            assert records[0][0].annot == (0, "On"), "path segment is a{index}:{state}"


@pytest.mark.corpus
def test_walk_document_completes_across_the_corpus_categories() -> None:
    """The acceptance criterion: `walk_document` completes without exception across all 19
    `form_xobjects` and all 13 `annotation_appearance_streams` corpus documents.

    Two documents in the wider corpus fail to OPEN, both pre-existing and both documented
    in tests/test_walker.py's module docstring (`irs_form_w9_encrypted.pdf` needs
    playa-pdf[crypto]; `govdocs1_011_011089.pdf` raises PDFSyntaxError from playa's
    inline-image handling). Neither is in these two categories, so no allowlist is needed
    here -- if one appears, that is a new finding and this test should fail.

    MUTATION (ran it): none needed as a red-check -- this went red for real during
    development, on govdocs1_004_004050.pdf, when the declared-stream walk was unbounded
    (it did not terminate). That is what `declared_seen` and the pending queue fixed.
    """
    manifest = json.loads((REPO_ROOT / "corpus" / "manifest.json").read_text())
    wanted = {"form_xobjects", "annotation_appearance_streams"}
    documents = [d for d in manifest if wanted & set(d.get("categories", []))]
    by_category = collections.Counter(
        c for d in documents for c in d["categories"] if c in wanted
    )
    # 19 + 13 = 32 category memberships over 30 distinct files: govdocs1_007_007081.pdf and
    # govdocs1_011_011098.pdf each carry both categories.
    assert by_category["form_xobjects"] == 19
    assert by_category["annotation_appearance_streams"] == 13
    assert len(documents) == 30

    outside = collections.Counter()
    for entry in documents:
        path = REPO_ROOT / "corpus" / entry["tier"] / entry["filename"]
        with playa.open(str(path)) as doc:
            for stream_path, _record in walk_document(doc):
                if stream_path.xobj_path:
                    outside["xobj"] += 1
                if stream_path.annot:
                    outside["annot"] += 1

    # Completing is the criterion; these confirm the walk actually reached outside
    # /Contents on this set rather than completing by finding nothing.
    assert outside["xobj"] > 0 and outside["annot"] > 0


def test_doubling_fan_out_is_bounded_by_the_stream_budget(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The XObject bomb: every level `Do`-invokes the next TWICE.

    Every branch is acyclic, so the per-branch visited set never fires; every branch is
    shallow (16 <= 64), so the depth cap never fires. The work is still 2^levels. Review
    measured the unbounded shape at 65,535 records / 4.7s for 16 levels, 4,194,303 / 383s
    for 22, and ~10^9 walks for a ~7 KB file with 30 such objects -- `list(walk_document())`
    OOMs. Two correct bounds, both reading the shape of one path, neither able to see the
    size of the tree.

    `MAX_STREAMS_PER_PAGE` counts what they cannot. Every level spends one unit from a
    single per-page allowance, so the walk stops at 8,192 levels: 8,191 records here,
    because the page's own /Contents shows no text and every Form XObject shows one glyph.

    MUTATION (ran it): delete the `budget.spend()` check at the top of `_walk_level`. This
    test yields 65,535 records instead of 8,191 and takes ~8x as long; at 22 levels the same
    mutation takes 383s, and at 30 it does not finish.
    """
    levels = 16
    pdf = pikepdf.Pdf.new()
    link = _form(
        pdf, _show(b"z"), pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica()))
    )
    for _ in range(levels - 1):
        parent = _form(
            pdf,
            _show(b"z") + b"/Fn Do\n/Fn Do\n",
            pikepdf.Dictionary(Font=pikepdf.Dictionary(Helv=_helvetica())),
        )
        parent.Resources.XObject = pikepdf.Dictionary(Fn=link)
        link = parent
    page = pdf.add_blank_page(page_size=(200, 200))
    page.Contents = pdf.make_stream(b"/F0 Do\n")
    page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(F0=link))

    with caplog.at_level(logging.WARNING, logger="engine.walker"):
        records = list(walk_document(_parse(pdf)))

    assert len(records) == MAX_STREAMS_PER_PAGE - 1, (
        f"the budget bounds the walk at {MAX_STREAMS_PER_PAGE} levels; "
        f"unbounded this fixture yields {2**levels - 1}"
    )
    budget_lines = [m for m in caplog.messages if "stream budget" in m]
    assert len(budget_lines) == 1, (
        "exhaustion is logged exactly once -- a line per abandoned branch would be a "
        "log flood built out of the DoS mitigation itself"
    )
    assert "z" not in budget_lines[0], "T-02-04: no glyph text in logs"
