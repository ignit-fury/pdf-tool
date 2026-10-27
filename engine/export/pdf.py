"""Native PDF exports. Call only inside the existing disposable PDF worker."""
from __future__ import annotations

from collections.abc import Buffer
from dataclasses import dataclass
import io
import math

import pikepdf
from PIL import Image

MAX_EXPORT_BYTES = 48 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_EDGE = 1600


class ExportRefusal(Exception):
    """Fixed public codes only; never contain source data or library messages."""


@dataclass(frozen=True, slots=True)
class PdfExport:
    data: bytes
    notices: tuple[str, ...] = ()
    changed_images: int = 0


class _BoundedOutput(io.BytesIO):
    def write(self, buffer: Buffer, /) -> int:
        if self.tell() + memoryview(buffer).nbytes > MAX_EXPORT_BYTES:
            raise ExportRefusal('EXPORT_LIMIT')
        return super().write(buffer)


def _save(pdf: pikepdf.Pdf) -> bytes:
    output = _BoundedOutput()
    pdf.save(output, object_stream_mode=pikepdf.ObjectStreamMode.generate,
             recompress_flate=True)
    return output.getvalue()


def _protected_image_roles(pdf: pikepdf.Pdf) -> set[tuple[int, int]]:
    """Opacity/alternative roles take precedence over ordinary image aliases."""
    pending: list[pikepdf.Object] = []
    discovery_count = 0
    for index, obj in enumerate(pdf.objects):
        if index > 100_000:
            raise ExportRefusal('EXPORT_LIMIT')
        # Indirect objects appear in pdf.objects. Direct nested containers do
        # not: discover roles inside resources/ExtGState and direct arrays too.
        direct = [obj]
        while direct:
            owner = direct.pop()
            discovery_count += 1
            if discovery_count > 100_000:
                raise ExportRefusal('EXPORT_LIMIT')
            if isinstance(owner, (pikepdf.Dictionary, pikepdf.Stream)):
                for key, value in owner.items():
                    discovery_count += 1
                    if discovery_count > 100_000:
                        raise ExportRefusal('EXPORT_LIMIT')
                    if key in ('/Mask', '/SMask', '/Alternates', '/OPI'):
                        pending.append(value)
                    if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)) and value.objgen == (0, 0):
                        direct.append(value)
            elif isinstance(owner, pikepdf.Array):
                discovery_count += len(owner)
                if discovery_count > 100_000:
                    raise ExportRefusal('EXPORT_LIMIT')
                direct.extend(value for value in owner
                    if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)) and value.objgen == (0, 0))
    protected: set[tuple[int, int]] = set()
    seen: set[tuple[int, int]] = set()
    count = 0
    while pending:
        obj = pending.pop()
        count += 1
        if count + len(pending) > 100_000:
            raise ExportRefusal('EXPORT_LIMIT')
        if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream, pikepdf.Array)):
            continue
        if obj.objgen != (0, 0):
            if obj.objgen in seen:
                continue
            seen.add(obj.objgen)
        if isinstance(obj, pikepdf.Stream) and obj.get('/Subtype') == pikepdf.Name.Image:
            protected.add(obj.objgen)
        if isinstance(obj, pikepdf.Array):
            if len(obj) + len(pending) + count > 100_000:
                raise ExportRefusal('EXPORT_LIMIT')
            pending.extend(obj)
        else:
            pending.extend(value for key, value in obj.items() if key not in ('/Parent', '/P', '/Pg'))
    return protected


def _reduce_images(pdf: pikepdf.Pdf) -> tuple[int, int]:
    changed = skipped = count = 0
    protected = _protected_image_roles(pdf)
    # pdf.objects visits each actual object once; shared page resources do not
    # cause the same image to be resampled repeatedly.
    for stream in pdf.objects:
        if not isinstance(stream, pikepdf.Stream) or stream.get('/Subtype') != pikepdf.Name.Image:
            continue
        count += 1
        if count > 1000:
            raise ExportRefusal('EXPORT_LIMIT')
        if stream.objgen in protected:
            skipped += 1
            continue
        try:
            width, height = int(stream.get('/Width', 0)), int(stream.get('/Height', 0))
        except (TypeError, ValueError, OverflowError):
            raise ExportRefusal('EXPORT_UNSUPPORTED') from None
        if width <= 0 or height <= 0 or max(width, height) > 16384 or width * height > MAX_IMAGE_PIXELS:
            raise ExportRefusal('EXPORT_LIMIT')
        filters = stream.get('/Filter')
        if isinstance(filters, pikepdf.Array):
            allowed_filters = all(str(item) in {'/FlateDecode', '/DCTDecode'} for item in filters)
        else:
            allowed_filters = filters is None or str(filters) in {'/FlateDecode', '/DCTDecode'}
        if (stream.get('/ColorSpace') not in (pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray)
                or stream.get('/BitsPerComponent') != 8 or not allowed_filters
                or any(key in stream for key in ('/Decode', '/Mask', '/SMask', '/SMaskInData', '/Alternates', '/OPI', '/ImageMask'))):
            skipped += 1
            continue
        if max(width, height) <= MAX_IMAGE_EDGE:
            continue
        with pikepdf.PdfImage(stream).as_pil_image() as image:
            if image.size != (width, height) or image.mode not in ('RGB', 'L'):
                raise ExportRefusal('EXPORT_UNSUPPORTED')
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            encoded = _BoundedOutput()
            image.save(encoded, format='JPEG', quality=80)
            stream.write(encoded.getvalue(), filter=pikepdf.Name.DCTDecode)
            stream.Width, stream.Height = image.size
        changed += 1
    return changed, skipped


def _rectangle(value: object) -> None:
    if not isinstance(value, pikepdf.Array) or len(value) != 4:
        raise ExportRefusal('EXPORT_UNSUPPORTED')
    try:
        coords = [float(item) for item in value]
    except (TypeError, ValueError, OverflowError):
        raise ExportRefusal('EXPORT_UNSUPPORTED') from None
    if (not all(math.isfinite(item) and abs(item) <= 10_000_000 for item in coords)
            or coords[2] <= coords[0] or coords[3] <= coords[1]):
        raise ExportRefusal('EXPORT_UNSUPPORTED')


def _check_appearances(pdf: pikepdf.Pdf) -> None:
    form = pdf.Root.get('/AcroForm')
    if form is not None and '/XFA' in form:
        raise ExportRefusal('EXPORT_UNSUPPORTED')
    count = 0
    for page in pdf.pages:
        for annot in page.obj.get('/Annots', []):
            count += 1
            if count > 10000:
                raise ExportRefusal('EXPORT_LIMIT')
            if not isinstance(annot, pikepdf.Dictionary):
                raise ExportRefusal('EXPORT_UNSUPPORTED')
            ap = annot.get('/AP')
            appearance = ap.get('/N') if isinstance(ap, pikepdf.Dictionary) else None
            if isinstance(appearance, pikepdf.Dictionary):
                state = annot.get('/AS')
                appearance = appearance.get(str(state)) if state is not None else None
            if not isinstance(appearance, pikepdf.Stream):
                # Links/popups without appearance streams have no saved visual
                # content to burn. Their nonvisual PDF semantics may remain.
                if str(annot.get('/Subtype')) in ('/Link', '/Popup') and appearance is None:
                    continue
                raise ExportRefusal('FLATTEN_APPEARANCE_REQUIRED')
            _rectangle(annot.get('/Rect'))
            _rectangle(appearance.get('/BBox'))
            matrix = appearance.get('/Matrix', pikepdf.Array([1, 0, 0, 1, 0, 0]))
            if not isinstance(matrix, pikepdf.Array) or len(matrix) != 6:
                raise ExportRefusal('EXPORT_UNSUPPORTED')
            try:
                a, b, c, d, e, f = (float(item) for item in matrix)
            except (TypeError, ValueError, OverflowError):
                raise ExportRefusal('EXPORT_UNSUPPORTED') from None
            if (not all(math.isfinite(item) and abs(item) <= 10_000_000 for item in (a, b, c, d, e, f))
                    or a * d - b * c == 0):
                raise ExportRefusal('EXPORT_UNSUPPORTED')


def _flatten(pdf: pikepdf.Pdf) -> None:
    _check_appearances(pdf)
    geometry = [(tuple(page.mediabox), tuple(page.cropbox),
                 page.obj.get('/Rotate', 0), page.obj.get('/UserUnit', 1)) for page in pdf.pages]
    pdf.flatten_annotations(mode='all')
    for page in pdf.pages:
        for annot in page.obj.get('/Annots', []):
            if str(annot.get('/Subtype')) not in ('/Link', '/Popup') or '/AP' in annot:
                raise ExportRefusal('EXPORT_UNSUPPORTED')
    # No widgets remain: remove even orphaned interactive form roots/calculation
    # order rather than publish a file with apparently live form fields.
    if '/AcroForm' in pdf.Root:
        del pdf.Root['/AcroForm']
    after = [(tuple(page.mediabox), tuple(page.cropbox),
              page.obj.get('/Rotate', 0), page.obj.get('/UserUnit', 1)) for page in pdf.pages]
    if geometry != after:
        raise ExportRefusal('EXPORT_UNSUPPORTED')


def export_pdf(pdf: pikepdf.Pdf, source: bytes, operation: str, *, downsample: bool = False) -> PdfExport:
    if operation not in ('compress', 'flatten') or not isinstance(downsample, bool) or (downsample and operation != 'compress'):
        raise ExportRefusal('EXPORT_OPTIONS_INVALID')
    notices: list[str] = []
    changed = 0
    encrypted = pdf.is_encrypted
    if operation == 'flatten':
        _flatten(pdf)
        notices.append('ANNOTATIONS_FLATTENED')
    elif downsample:
        changed, skipped = _reduce_images(pdf)
        if skipped:
            notices.append('IMAGES_SKIPPED')
    candidate = _save(pdf)
    if operation == 'compress' and not downsample and len(candidate) >= len(source):
        if len(source) > MAX_EXPORT_BYTES:
            raise ExportRefusal('EXPORT_LIMIT')
        return PdfExport(source, ('NO_SIZE_REDUCTION',))
    if encrypted:
        notices.append('UNLOCKED_COPY')
    return PdfExport(candidate, tuple(notices), changed)
