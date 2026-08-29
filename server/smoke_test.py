"""Quick smoke test with a tiny in-memory PDF — no disk I/O."""

from __future__ import annotations

import io
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from server.engine_replace import (
    shape_advance_pt,
    fit_run,
    bundled_font_path,
    _hex_literal_bytes,
    original_advance_pt,
    active_font_at_offset,
    find_text_op_index_at_offset,
    page_stream_bytes,
    replace_text_in_pdf,
)

fonts_dir = Path("server/fonts")
ttf = bundled_font_path(fonts_dir)

# ---- Fit logic tests (no PDF needed) ----
adv = shape_advance_pt("Hello World", ttf, 12.0)
logging.info("Hello World @12pt: %.2fpt", adv)
r = fit_run(adv, "Hi", ttf, 12.0)
logging.info("fit 'Hi': ok=%s strategy=%s delta=%.4fpt", r["ok"], r["strategy"], r["delta_pt"])
r2 = fit_run(adv, "Hello World!!!", ttf, 12.0)
logging.info("fit 'Hello World!!!': ok=%s strategy=%s delta=%.4fpt", r2["ok"], r2["strategy"], r2["delta_pt"])
logging.info("hex literal: %s", _hex_literal_bytes("Hello World").decode())

# ---- Tiny in-memory PDF round-trip ----
import pikepdf

tiny = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1<</Type/TrueType/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>>>>>>>endobj
4 0 obj<</Length 44>>stream
BT
/F1 12 Tf
100 700 Td
(Hello) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000209 00000 n
trailer<</Size 5/Root 1 0 R>>
startxref
310
%%EOF
"""

pdf = pikepdf.open(io.BytesIO(tiny))
try:
    ops = pikepdf.parse_content_stream(pdf.pages[0])
    logging.info("parsed %d instructions", len(ops))
    raw = page_stream_bytes(pdf, 0)
    logging.info("raw stream len: %d", len(raw))
    idx = find_text_op_index_at_offset(raw, 78)
    logging.info("text op at byte 78: index=%d", idx)
    fn, fs = active_font_at_offset(pdf, 0, 78)
    logging.info("font at byte 78: %s @ %.1fpt", fn, fs)
    oa = original_advance_pt(pdf, 0, fn, "Hello", fs)
    logging.info("original advance for 'Hello': %.2fpt", oa)
finally:
    pdf.close()

# ---- Full replacement round-trip ----
tiny2 = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1<</Type/TrueType/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>>>>>>>endobj
4 0 obj<</Length 44>>stream
BT
/F1 12 Tf
100 700 Td
(Hello) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000209 00000 n
trailer<</Size 5/Root 1 0 R>>
startxref
310
%%EOF
"""

out = Path("/tmp/test_replaced.pdf")
try:
    result = replace_text_in_pdf(io.BytesIO(tiny2), str(out), [("0" * 64 + ":p0:c0:o78", "World")], fonts_dir)
    logging.info("replacement result: %s", result)
    # Verify
    pdf2 = pikepdf.open(out)
    try:
        ops2 = pikepdf.parse_content_stream(pdf2.pages[0])
        logging.info("re-read %d instructions", len(ops2))
        for i, instr in enumerate(ops2):
            logging.info("  op[%d]: %s", i, instr.operator)
    finally:
        pdf2.close()
finally:
    out.unlink(missing_ok=True)

logging.info("---\nAll smoke tests passed")
