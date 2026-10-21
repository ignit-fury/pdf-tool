"""Small generated security fixtures; no large hostile artifact is checked in.

The signed fixture carries signature structures, not a cryptographic attestation.
The compressed fixture expands past the service's explicit stream budget.
"""
from __future__ import annotations

import io
from pathlib import Path
import zlib

import pikepdf
from fontTools.ttLib import TTFont


def text_pdf(text: bytes = b"Security canary") -> bytes:
    with TTFont(Path(__file__).resolve().parents[1] / "fonts/LiberationSans-Regular.ttf") as font:
        cmap = font.getBestCmap()
        upem = font["head"].unitsPerEm
        widths = [font["hmtx"].metrics[cmap[code]][0] * 1000 / upem for code in range(32, 127)]
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(300, 200))
        page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(
            F1=pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                 BaseFont=pikepdf.Name.Helvetica,
                                 Encoding=pikepdf.Name.WinAnsiEncoding,
                                 FirstChar=32, LastChar=126,
                                 Widths=pikepdf.Array(widths))))
        page.Contents = pdf.make_stream(b"BT /F1 12 Tf 20 100 Td (" + text + b") Tj ET")
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def password_pdf(password: str = "canary-password") -> bytes:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        out = io.BytesIO()
        pdf.save(out, encryption=pikepdf.Encryption(owner="fixture-owner", user=password, R=6))
        return out.getvalue()


def signed_pdf(*, flags: int = 1, field: bool = True) -> bytes:
    with pikepdf.open(io.BytesIO(text_pdf())) as pdf:
        fields = pikepdf.Array()
        if field:
            signature = pikepdf.Dictionary(Type=pikepdf.Name.Sig,
                ByteRange=pikepdf.Array([0, 1, 2, 3]), Contents=pikepdf.String(b"fixture"))
            fields.append(pdf.make_indirect(pikepdf.Dictionary(
                FT=pikepdf.Name.Sig, T=pikepdf.String("Signature"), V=signature)))
        pdf.Root.AcroForm = pikepdf.Dictionary(SigFlags=flags, Fields=fields)
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def _raw_pdf(objects: list[bytes]) -> bytes:
    result = bytearray(b"%PDF-1.7\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    offset = len(result)
    result.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for value in offsets[1:]:
        result.extend(f"{value:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n".encode())
    return bytes(result)


def cyclic_page_tree() -> bytes:
    return _raw_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [2 0 R] /Count 1 >>",
    ])


def decompression_bomb(expanded_bytes: int = 20 * 1024 * 1024, *, safe_first_page: bool = False) -> bytes:
    # Stream compression uses a fixed 64KiB allocation irrespective of expansion size.
    compressor = zlib.compressobj(9)
    encoded = bytearray()
    remaining = expanded_bytes
    block = b" " * 65536
    while remaining:
        count = min(remaining, len(block))
        encoded.extend(compressor.compress(block[:count]))
        remaining -= count
    encoded.extend(compressor.flush())
    if safe_first_page:
        return _raw_pdf([
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [5 0 R 3 0 R] /Count 2 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R >>",
            f"<< /Filter /FlateDecode /Length {len(encoded)} >>\nstream\n".encode()
            + bytes(encoded) + b"\nendstream",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 6 0 R /Resources << >> >>",
            b"<< /Length 0 >>\nstream\n\nendstream",
        ])
    return _raw_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R >>",
        f"<< /Filter /FlateDecode /Length {len(encoded)} >>\nstream\n".encode()
        + bytes(encoded) + b"\nendstream",
    ])


def self_referencing_form() -> bytes:
    with pikepdf.Pdf.new() as pdf:
        form = pdf.make_stream(b"/Self Do")
        form.Type = pikepdf.Name.XObject
        form.Subtype = pikepdf.Name.Form
        form.BBox = pikepdf.Array([0, 0, 100, 100])
        form.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Self=form))
        page = pdf.add_blank_page(page_size=(300, 200))
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Form=form))
        page.Contents = pdf.make_stream(b"/Form Do")
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
