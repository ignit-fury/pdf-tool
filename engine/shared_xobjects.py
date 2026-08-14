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

## Nested XObject resources

02-RESEARCH.md Section 5's prose says to walk "every page's `/Resources /XObject` (plus
nested XObject resources)"; its own code example omits the nesting. The doc contradicts
itself and the prose is correct: a Form XObject's `/Resources /XObject` can itself
reference further Form XObjects, and a page-only walk silently misses them. Measured on
the public corpus, this is a total, not a partial, miss on the one document it affects:
govdocs1_013_013085.pdf reports 0 shared / max 0 flat, versus 7 shared / max 36 with
nesting walked -- "nothing is shared here" about a document with a header XObject on 36
pages is exactly the wrong-direction failure this detector exists to prevent. `_walk`
below recurses into each Form XObject's own `/Resources`, with a per-page `visited`
cycle guard (keyed on the full `objgen`, not just objid, matching the convention in
tests/test_encoding_table.py's `_walk_font_resources`) and a depth cap, since a
self- or mutually-referencing Form chain must not recurse unboundedly.

## No playa import

pikepdf's own object graph (`/Resources /XObject`, `/Subtype`, `.objgen`) is enough for
this census; playa is the read-side decoder and is out of scope for a pikepdf-only,
object-identity question. `import playa` appears in exactly one file in this repo
(engine/playa_boundary.py), and a test asserts that.
"""

from __future__ import annotations

import collections

import pikepdf


# A page's own /Resources -> nested Form /Resources -> nested Form /Resources chain has
# never been observed past depth 2 on the corpus (see the module docstring's measured
# example). 64 is a generous bound well under Python's default recursion limit, guarding
# against a pathological or adversarial upload without touching any real document.
_MAX_XOBJECT_DEPTH = 64


def _walk(
    resources: pikepdf.Object | None,
    seen: set[int],
    visited: set[tuple[int, int]],
    depth: int,
) -> None:
    """Add every Form XObject objid reachable from `resources` to `seen` (one page's
    worth), recursing into each Form's own /Resources for nested Form XObjects.

    `visited` is a per-page cycle guard keyed on the full `objgen` (id, gen) -- a
    self-referencing Form must not recurse into itself again. `depth` bounds recursion
    independent of cycles, for a chain that is deep but not cyclic.
    """
    if resources is None or depth > _MAX_XOBJECT_DEPTH:
        return
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return
    for _key, xo in xobjects.items():
        if str(xo.get("/Subtype")) != "/Form":
            continue
        objgen = xo.objgen
        oid = objgen[0]
        if oid:
            seen.add(oid)
        if objgen in visited:
            continue
        visited.add(objgen)
        _walk(xo.get("/Resources"), seen, visited, depth + 1)


def shared_form_xobjects(pdf: pikepdf.Pdf) -> dict[int, int]:
    """objid -> number of distinct pages referencing it, for every Form XObject referenced
    by more than one page -- including Form XObjects reachable only through another Form
    XObject's own /Resources (see the module docstring's "Nested XObject resources"
    section).

    Keyed by `xo.objgen[0]`, never by the resource dictionary's local name -- see the
    module docstring. `seen` counts each object once per page even if it appears under
    multiple names, multiple times, or at multiple nesting depths within one page's
    reachable XObject tree, so the result is "pages referencing", not "references".
    """
    refs: collections.Counter[int] = collections.Counter()
    for page in pdf.pages:
        seen: set[int] = set()
        _walk(page.get("/Resources"), seen, set(), 0)
        for oid in seen:
            refs[oid] += 1
    return {oid: n for oid, n in refs.items() if n > 1}


__all__ = ["shared_form_xobjects"]
