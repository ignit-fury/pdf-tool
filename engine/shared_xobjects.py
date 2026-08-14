"""TEXT-06: shared Form XObject detection -- the pages-per-object census.

A shared Form XObject is typically a running header or footer -- the most visible text on
a page, and the text a user is most likely to try to edit. Editing its content stream
rewrites it on every page that references it, which is almost never what the user meant.
This module is the *detector* only; 02-08's classifier decides what to do with the count
(mark `editable: false`, in the plan's current design). Per the Architectural
Responsibility Map, the walker never decides editability -- it is not this module's job
either, and this module does not import the walker.

## The one mistake this module exists to prevent

Key on `xobject.objgen[0]` (pikepdf's object identity), never on the resource dictionary's
local name. `/Fm0` on page 3 and `/Fm0` on page 9 are frequently *different objects*, and
the *same* object frequently carries *different* names on different pages -- a PDF writer
is free to name resources however it likes per page. A detector keyed by name instead of
identity both over- and under-counts: it can fuse two unrelated objects that happen to
share a name, and it can miss that one real object recurs under several names, which is
the undercount `test_resource_name_keyed_mutation_undercounts_irs_1040` in
tests/test_outside_contents.py pins.

This is the same defect class that already bit this project once: a Phase-1 producer
census keyed by a normalised string split one real product across two buckets and
understated its true share (02-RESEARCH.md's "Every check..." table, TEXT-06 row). The
negative-case test in tests/test_outside_contents.py is what makes the lesson permanent
rather than a comment.

## No playa import

pikepdf's own object graph (`/Resources /XObject`, `/Subtype`, `.objgen`) is enough for
this census; playa is the read-side decoder and is out of scope for a pikepdf-only,
object-identity question. `import playa` appears in exactly one file in this repo
(engine/playa_boundary.py), and a test asserts that.
"""

from __future__ import annotations

import collections

import pikepdf


def shared_form_xobjects(pdf: pikepdf.Pdf) -> dict[int, int]:
    """objid -> number of distinct pages referencing it, for every Form XObject referenced
    by more than one page.

    Only `/Resources /XObject` entries are walked (not resources nested inside those
    XObjects' own `/Resources`) -- Section 5's detection algorithm is defined over direct
    page resources, and that is what the measured corpus counts (43, 47) were produced
    against.

    Keyed by `xo.objgen[0]`, never by the resource dictionary's local name -- see the
    module docstring. `seen` counts each object once per page even if it appears under
    multiple names or multiple times in one page's `/XObject` dict, so the result is
    "pages referencing", not "references".
    """
    refs: collections.Counter[int] = collections.Counter()
    for page in pdf.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        seen: set[int] = set()
        for _key, xo in xobjects.items():
            if str(xo.get("/Subtype")) == "/Form":
                oid = xo.objgen[0]
                if oid and oid not in seen:
                    refs[oid] += 1
                    seen.add(oid)
    return {oid: n for oid, n in refs.items() if n > 1}


__all__ = ["shared_form_xobjects"]
