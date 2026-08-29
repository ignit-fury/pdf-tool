"""Phase 3 content-stream text replacement engine.

Opens a PDF with pikepdf, locates the target Tj/TJ operator by byte offset
(from a run_id decode), fits the replacement text into the original run's
advance width using uharfbuzz shaping, and rewrites the page's content stream.

Replacement flow per run:
  1. Decode run_id -> (page, part, byte_offset, subrange)
  2. Parse the page's content stream with pikepdf.parse_content_stream.
  3. Scan raw bytes to find which text-instruction index corresponds to
     byte_offset (pikepdf does not expose byte offsets on parsed instructions).
  4. For Tj: single string operand. Replace with new text (hex-literal form).
  5. For TJ: array operand. Replace string elements, preserve kerning numbers.
  6. Apply width fitting: shape replacement with uharfbuzz, read original
     advance from /Widths dict, absorb delta via trailing/inter-word kerns.
  7. Unparse modified instructions, rebuild page.Contents, save.

No playa import here — purely pikepdf + uharfbuzz + fontTools.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from pathlib import Path
from typing import Any

import pikepdf
import uharfbuzz as hb

from engine.run_id import decode_run_id

log = logging.getLogger(__name__)

_DELTA_TOLERANCE_PT = 0.5
_FONTS_DIR_DEFAULT = Path(__file__).parent / "fonts"

_TF_RE = re.compile(rb"/(\S+)\s+([+-]?\d+\.?\d*)\s+Tf\b")
_TEXT_OP_NAMES = frozenset(["Tj", "TJ", "'", '"'])


# ---------------------------------------------------------------------------
# Bundled font helpers
# ---------------------------------------------------------------------------


def bundled_font_path(bundled_dir: Path) -> Path:
    """Path to the primary bundled TTF for substitution (Liberation Sans)."""
    ttf = bundled_dir / "LiberationSans-Regular.ttf"
    if not ttf.exists():
        raise RuntimeError(f"bundled font not found: {ttf}")
    return ttf


# ---------------------------------------------------------------------------
# Width fitting (from spike/tj_refit_prototype.py, adapted for server use)
# ---------------------------------------------------------------------------


def shape_advance_pt(text: str, font_path: Path, font_size_pt: float) -> float:
    """Shape `text` with uharfbuzz, return kerned total advance in points."""
    blob = hb.Blob.from_file_path(str(font_path))
    face = hb.Face(blob)
    font = hb.Font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf)
    total_units = sum(pos.x_advance for pos in buf.glyph_positions)
    return total_units / face.upem * font_size_pt


def space_width_pt(font_path: Path, font_size_pt: float) -> float:
    return shape_advance_pt(" ", font_path, font_size_pt)


def fit_run(
    original_advance_pt: float,
    replacement_text: str,
    font_path: Path,
    font_size_pt: float,
) -> dict[str, Any]:
    """Compute kerning to fit replacement_text into original_advance_pt.

    Returns dict with:
        - "ok": bool
        - "refused": bool
        - "strategy": str ("trailing_kern" | "inter_word_kern" | "refused")
        - "kerns": list[float] — TJ kern values in thousandths of text space
        - "delta_pt": float — residual after fitting
        - "refusal_reason": str | None
    """
    shaped = shape_advance_pt(replacement_text, font_path, font_size_pt)
    delta = shaped - original_advance_pt
    space_w = space_width_pt(font_path, font_size_pt)

    # Priority 1: single trailing kern if |delta| <= ~1 space width.
    if abs(delta) <= space_w:
        kern = delta / font_size_pt * 1000.0
        return {
            "ok": True, "refused": False, "strategy": "trailing_kern",
            "kerns": [kern], "delta_pt": delta,
        }

    # Priority 2: distribute across inter-word gaps.
    gap_count = replacement_text.count(" ")
    if gap_count > 0:
        max_absorb = gap_count * space_w * 2.0  # 2x space width per gap
        if abs(delta) <= max_absorb:
            per_gap = (delta / gap_count) / font_size_pt * 1000.0
            return {
                "ok": True, "refused": False, "strategy": "inter_word_kern",
                "kerns": [per_gap] * gap_count, "delta_pt": delta,
            }

    # Priority 3: refuse.
    max_absorb = gap_count * space_w * 2.0 if gap_count > 0 else 0.0
    reason = (
        f"delta {delta:.2f}pt exceeds kern absorption range "
        f"(trailing: +/-{space_w:.2f}pt, inter-word: +/-{max_absorb:.2f}pt)"
    )
    return {
        "ok": False, "refused": True, "strategy": "refused",
        "kerns": [], "delta_pt": delta, "refusal_reason": reason,
    }


# ---------------------------------------------------------------------------
# Original advance from PDF font dictionary /Widths
# ---------------------------------------------------------------------------


def original_advance_pt(
    pdf: pikepdf.Pdf,
    page_index: int,
    font_resource_name: str,
    text: str,
    font_size_pt: float,
) -> float:
    """Read advance width from the PDF font dictionary's /Widths array.

    Uses the FONT DICTIONARY's /Widths (not the embedded font program's
    metrics) — the dictionary is what the viewer actually uses.
    Raises ValueError if a character code falls outside FirstChar..LastChar.
    Raises NotImplementedError for Type0/CID fonts.
    """
    page = pdf.pages[page_index]
    fonts = page.get("/Resources", {}).get("/Font", {})
    font = fonts.get("/" + font_resource_name)
    if font is None:
        raise ValueError(f"font /{font_resource_name} not in page Resources")

    if str(font.get("/Subtype", "")) == "/Type0":
        raise NotImplementedError(
            "Type0/CID width lookup not implemented in this prototype"
        )

    first_char = int(font["/FirstChar"])
    last_char = int(font["/LastChar"])
    widths = font["/Widths"]
    total_thousandths = 0.0
    for ch in text:
        code = ord(ch)
        if not (first_char <= code <= last_char):
            raise ValueError(
                f"code {code} ({ch!r}) outside FirstChar..LastChar "
                f"({first_char}..{last_char}) — refusing to fall through "
                f"to /MissingWidth"
            )
        total_thousandths += float(widths[code - first_char])
    return total_thousandths / 1000.0 * font_size_pt


# ---------------------------------------------------------------------------
# Raw byte helpers — pikepdf doesn't expose byte offsets on instructions
# ---------------------------------------------------------------------------


def page_stream_bytes(pdf: pikepdf.Pdf, page_index: int) -> bytes:
    """Raw decoded bytes of a page's content stream (coalescing arrays)."""
    page = pdf.pages[page_index]
    contents = page.get("/Contents")
    if contents is None:
        return b""
    if isinstance(contents, pikepdf.Array):
        return b"".join(bytes(s.read_bytes()) for s in contents)
    return bytes(contents.read_bytes())


def find_text_op_index_at_offset(raw: bytes, byte_offset: int) -> int:
    """Count which text-showing operator (0-indexed) sits at byte_offset.

    Scans the raw content stream for Tj/TJ/'/" keyword tokens, and returns
    the count of text operators whose keyword starts at or before byte_offset.
    """
    if byte_offset < 0 or byte_offset >= len(raw):
        raise ValueError(f"byte_offset {byte_offset} out of range (raw len {len(raw)})")

    count = 0
    pos = 0
    max_pos = len(raw)
    while pos < max_pos:
        # Skip whitespace.
        while pos < max_pos and raw[pos] in b" \t\n\r\x00\x0c":
            pos += 1
        if pos >= max_pos:
            break
        start = pos
        # Read token — bounded scan.
        while pos < max_pos and raw[pos] not in b" \t\n\r\x00\x0c()<>[]{}/%":
            pos += 1
        token = raw[start:pos].decode("latin-1")
        if token in _TEXT_OP_NAMES:
            if start <= byte_offset < pos:
                return count
            count += 1
    raise ValueError(f"no text operator found at byte offset {byte_offset}")


def active_font_at_offset(pdf: pikepdf.Pdf, page_index: int, byte_offset: int) -> tuple[str, float]:
    """Return (font_resource_name, font_size_pt) for the Tf active at byte_offset.

    Scans the raw content stream for Tf operators up to byte_offset; the last
    one wins (PDF semantics: Tf applies until overridden).
    """
    raw = page_stream_bytes(pdf, page_index)
    last_match = None
    for m in _TF_RE.finditer(raw):
        if m.start() <= byte_offset:
            last_match = m
        else:
            break
    if last_match is None:
        raise ValueError(f"no Tf operator at or before byte offset {byte_offset}")

    font_name = last_match.group(1).decode("latin-1")
    font_size = float(last_match.group(2))
    return font_name, font_size


# ---------------------------------------------------------------------------
# Instruction reconstruction
# ---------------------------------------------------------------------------


def _hex_literal_bytes(text: str) -> bytes:
    """ISO 32000-1 hex-string form for the UTF-8 bytes of `text`."""
    return b"<" + text.encode("utf-8").hex().upper().encode("ascii") + b">"


def _new_tj_instruction(new_text: str) -> pikepdf.ContentStreamInstruction:
    """A Tj instruction whose operand is the hex-literal form of new_text."""
    hex_bytes = _hex_literal_bytes(new_text)
    # pikepdf.String.from_bytes with the raw bytes; it will be unparsed
    # as a hex literal when we call unparse_content_stream on the rebuilt ops.
    operand = pikepdf.String.from_bytes(hex_bytes)
    return pikepdf.ContentStreamInstruction(
        operator=pikepdf.Name("Tj"),
        operands=[operand],
    )


def _new_tj_array_instruction(
    new_text: str,
    trailing_kern: float | None = None,
) -> pikepdf.ContentStreamInstruction:
    """A TJ instruction wrapping new_text as a single hex-literal string,
    optionally followed by a trailing kern number."""
    hex_bytes = _hex_literal_bytes(new_text)
    arr = pikepdf.Array()
    arr.append(pikepdf.String.from_bytes(hex_bytes))
    if trailing_kern is not None:
        arr.append(trailing_kern)
    return pikepdf.ContentStreamInstruction(
        operator=pikepdf.Name("TJ"),
        operands=[arr],
    )


# ---------------------------------------------------------------------------
# Main replacement entry point
# ---------------------------------------------------------------------------


def replace_text_in_pdf(
    pdf_path: str | Path,
    output_path: str | Path,
    replacements: list[tuple[str, str]],
    bundled_fonts_dir: Path | None = None,
) -> dict[str, Any]:
    """Apply text replacements to a PDF and write the result.

    Args:
        pdf_path: Source PDF.
        output_path: Destination PDF.
        replacements: List of (run_id, new_text) pairs.
        bundled_fonts_dir: Directory with bundled TTFs for substitution.
            Defaults to server/fonts/.

    Returns:
        dict with "replaced" (int), "refused" (list of {run_id, reason}),
        "output_path" (str).
    """
    bundled_dir = bundled_dir or _FONTS_DIR_DEFAULT
    pdf = pikepdf.open(pdf_path)
    try:
        replaced_count = 0
        refused_list: list[dict[str, str]] = []

        for run_id, new_text in replacements:
            try:
                parts = decode_run_id(run_id)
            except ValueError as exc:
                refused_list.append({"run_id": run_id, "reason": f"bad run_id: {exc}"})
                continue

            page_idx = parts["page"]
            byte_offset = parts["byte_offset"]
            subrange = parts.get("subrange")

            try:
                _apply_one_replacement(pdf, page_idx, byte_offset, new_text, bundled_dir)
                replaced_count += 1
            except ValueError as exc:
                refused_list.append({"run_id": run_id, "reason": str(exc)})
            except NotImplementedError as exc:
                refused_list.append({"run_id": run_id, "reason": str(exc)})
            except Exception as exc:  # noqa: BLE001
                log.warning("run_id=... replacement failed: %s", exc)
                refused_list.append({"run_id": run_id, "reason": "replacement failed"})

        pdf.save(str(output_path))
        log.info("saved %d replacements to %s", replaced_count, output_path)
        return {
            "replaced": replaced_count,
            "refused": refused_list,
            "output_path": str(output_path),
        }
    finally:
        pdf.close()


def _apply_one_replacement(
    pdf: pikepdf.Pdf,
    page_index: int,
    byte_offset: int,
    new_text: str,
    bundled_dir: Path,
) -> None:
    """Replace text at byte_offset on page_index with new_text, in place."""
    page = pdf.pages[page_index]
    raw = page_stream_bytes(pdf, page_index)

    # 1. Find which text operator this is.
    op_index = find_text_op_index_at_offset(raw, byte_offset)
    ops = pikepdf.parse_content_stream(page)
    if op_index >= len(ops):
        raise ValueError(
            f"text op index {op_index} out of range (parsed {len(ops)} text ops)"
        )

    instr = ops[op_index]
    op_name = str(instr.operator)
    if op_name not in _TEXT_OP_NAMES:
        raise ValueError(f"byte offset {byte_offset} does not point to a text operator")

    # 2. Read the active font and size.
    font_name, font_size_pt = active_font_at_offset(pdf, page_index, byte_offset)

    # 3. Get the original text from the instruction.
    original_text = _extract_original_text(instr, op_name)
    if original_text is None:
        raise ValueError("could not extract original text from instruction")

    # 4. Try to fit the replacement (read original advance, shape new text).
    fit_result: dict[str, Any] | None = None
    try:
        bundled_font = bundled_font_path(bundled_dir)
        orig_advance = original_advance_pt(pdf, page_index, font_name, original_text, font_size_pt)
        fit_result = fit_run(orig_advance, new_text, bundled_font, font_size_pt)
    except (ValueError, NotImplementedError, KeyError) as exc:
        log.debug("width fitting skipped for offset %d: %s", byte_offset, exc)
        # Without the original advance we can't fit; just replace the text
        # without kerning adjustment. This may cause visible shift.

    # 5. Build the new instruction.
    if op_name == "Tj":
        new_instr = _new_tj_instruction(new_text)
    elif op_name == "TJ":
        kern = None
        if fit_result and not fit_result["refused"] and fit_result["kerns"]:
            kern = fit_result["kerns"][-1]  # trailing kern from fit
        new_instr = _new_tj_array_instruction(new_text, trailing_kern=kern)
    elif op_name in ("'", '"'):
        # These prepend aw/ac; replace the trailing string operand.
        new_instr = _clone_instruction_replace_string(instr, new_text)
    else:
        raise ValueError(f"unexpected text operator: {op_name}")

    # 6. Replace in ops list and rebuild.
    ops[op_index] = new_instr
    new_bytes = pikepdf.unparse_content_stream(ops)
    page.Contents = pdf.make_stream(new_bytes)


def _clone_instruction_replace_string(
    instr: pikepdf.ContentStreamInstruction,
    new_text: str,
) -> pikepdf.ContentStreamInstruction:
    """Clone an instruction, replacing its trailing string operand."""
    new_op = pikepdf.Name(str(instr.operator))
    new_operands: list[pikepdf.Object] = []
    string_replaced = False
    for op in instr.operands:
        if not string_replaced and isinstance(op, pikepdf.String):
            new_operands.append(pikepdf.String.from_bytes(_hex_literal_bytes(new_text)))
            string_replaced = True
        else:
            new_operands.append(op)
    if not string_replaced:
        raise ValueError("no string operand found in instruction")
    return pikepdf.ContentStreamInstruction(operator=new_op, operands=new_operands)


def _extract_original_text(
    instr: pikepdf.ContentStreamInstruction,
    op_name: str,
) -> str | None:
    """Extract the original displayed text from a text-showing instruction."""
    operands = instr.operands
    if op_name == "Tj":
        if operands and isinstance(operands[0], pikepdf.String):
            raw = operands[0].tobytes()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin-1", errors="replace")
    elif op_name == "TJ":
        if operands and isinstance(operands[0], pikepdf.Array):
            parts: list[str] = []
            for el in operands[0]:
                if isinstance(el, pikepdf.String):
                    raw = el.tobytes()
                    try:
                        parts.append(raw.decode("utf-8"))
                    except UnicodeDecodeError:
                        parts.append(raw.decode("latin-1", errors="replace"))
            return "".join(parts)
    elif op_name in ("'", '"'):
        for op in reversed(operands):
            if isinstance(op, pikepdf.String):
                raw = op.tobytes()
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("latin-1", errors="replace")
    return None
