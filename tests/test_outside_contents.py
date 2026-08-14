"""TEXT-06: shared Form XObject detection reproduces the measured corpus counts, and a
resource-name-keyed detector is proven wrong on the same document.

Only engine/shared_xobjects.py is under test here (Task 1 of 02-05-PLAN.md). The walker
does not consume this module yet -- that is Task 2 -- so these tests exercise
shared_form_xobjects() directly against pikepdf.
"""

import collections
from pathlib import Path

import pikepdf

from engine.shared_xobjects import shared_form_xobjects

REPO_ROOT = Path(__file__).parent.parent
CORPUS_DIR = REPO_ROOT / "corpus" / "public"

IRS_1040_INSTRUCTIONS = CORPUS_DIR / "irs_1040_instructions.pdf"
IRS_PUBLICATION_17 = CORPUS_DIR / "irs_publication_17.pdf"
GOVDOCS_013_013085 = CORPUS_DIR / "govdocs1_013_013085.pdf"


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
