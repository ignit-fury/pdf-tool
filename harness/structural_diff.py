"""Targeted structural content-stream diff -- the fix for 03-RESEARCH.md's own Pitfall 3.

This is NOT a byte-level diff of the whole file. A whole-file `qpdf --qdf` + `diff` was measured
directly this session (spike/fixtures/tj_refit_sample.pdf, an 8-part array `/Contents`, one `Tj`
string mutated then coalesced to a single stream): 13,689 lines of diff for a single-word text
change, dominated by object renumbering cascading through image/font/annotation objects that were
never touched. That whole-file approach fails G2a's own diff-confinement criterion on the 52.5%
of the corpus that has an array `/Contents`.

This module instead compares only the touched content-stream part's OWN decoded instructions,
position-wise, old vs new -- never a real page, never a real `/Contents` array, never the rest of
the file. It reuses the exact parse/unparse sequence `engine/identity_rewrite.py`'s
`null_edit_rewrite` already proved: `pikepdf.parse_content_stream()` to decode, and
`pikepdf.unparse_content_stream([instr])` per single instruction to compare serializations.
"""

from __future__ import annotations

import pikepdf

__all__ = ["confined_instruction_diff"]


def confined_instruction_diff(old_stream_bytes: bytes, new_stream_bytes: bytes) -> tuple[int, int]:
    """Compare two content-stream parts' own decoded instructions, position-wise.

    Returns `(changed_instruction_count, total_instruction_count)`.

    A throwaway `pikepdf.Pdf.new()` is used only as a container to call `make_stream` /
    `parse_content_stream` on raw bytes -- no real page or `/Contents` array is ever touched.
    """
    scratch = pikepdf.Pdf.new()
    old_stream_obj = scratch.make_stream(old_stream_bytes)
    new_stream_obj = scratch.make_stream(new_stream_bytes)
    old_ops = pikepdf.parse_content_stream(old_stream_obj)
    new_ops = pikepdf.parse_content_stream(new_stream_obj)

    if len(old_ops) != len(new_ops):
        # An operator was inserted or removed. Position-wise comparison is not meaningful when
        # lengths differ, so degrade to the safe worst-case answer: an instruction-count-changing
        # rewrite is definitionally not confined -- report everything as changed.
        total = max(len(old_ops), len(new_ops))
        return total, total

    changed = 0
    for i in range(len(old_ops)):
        old_bytes = pikepdf.unparse_content_stream([old_ops[i]])
        new_bytes = pikepdf.unparse_content_stream([new_ops[i]])
        if old_bytes != new_bytes:
            changed += 1
    return changed, len(old_ops)


if __name__ == "__main__":
    import sys

    # Minimal self-check, mirroring harness/masked_diff.py's own style: identical streams diff
    # to (0, N); a single-instruction operand change diffs to (1, N).
    identical_old = b"BT\n(Hello) Tj\nET"
    identical_new = b"BT\n(Hello) Tj\nET"
    one_changed_old = b"BT\n(Hello) Tj\nET"
    one_changed_new = b"BT\n(World) Tj\nET"

    changed, total = confined_instruction_diff(identical_old, identical_new)
    assert (changed, total) == (0, 3), f"expected (0, 3), got {(changed, total)}"

    changed, total = confined_instruction_diff(one_changed_old, one_changed_new)
    assert (changed, total) == (1, 3), f"expected (1, 3), got {(changed, total)}"

    print("OK: confined_instruction_diff discriminates identical vs single-instruction-changed streams")
    sys.exit(0)
