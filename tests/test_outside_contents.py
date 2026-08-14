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
    """
    with pikepdf.open(str(IRS_1040_INSTRUCTIONS)) as pdf:
        correct = shared_form_xobjects(pdf)
        true_max_oid = max(correct, key=lambda oid: correct[oid])
        true_max_count = correct[true_max_oid]
        assert true_max_count == 43  # pinned above too; restated so this test stands alone

        # The mutation: the true object's own page references, re-bucketed by resource
        # NAME instead of collapsed into one objgen-keyed bucket.
        per_name: collections.Counter[str] = collections.Counter()
        for page in pdf.pages:
            for name, xo in ((page.get("/Resources") or {}).get("/XObject") or {}).items():
                if str(xo.get("/Subtype")) == "/Form" and xo.objgen[0] == true_max_oid:
                    per_name[str(name)] += 1

        # Fixture assumption this test depends on: the shared object must actually carry
        # more than one local name, or the mutation would coincidentally still be correct.
        assert len(per_name) > 1, f"expected the shared object to carry >1 resource name, got {per_name!r}"
        # Sanity: every one of the object's 43 page-references landed in exactly one
        # name bucket -- no page counted twice, none dropped.
        assert sum(per_name.values()) == true_max_count

        worst_case_name_keyed = max(per_name.values())
        assert worst_case_name_keyed < true_max_count, (
            f"best single-name bucket ({worst_case_name_keyed}) should undercount the "
            f"true objgen-keyed total ({true_max_count}) -- the undercount this test "
            f"exists to prove did not happen"
        )
