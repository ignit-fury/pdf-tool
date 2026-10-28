"""Opt-in bounded image facts, alongside the existing text page parse."""
from __future__ import annotations

from dataclasses import dataclass
import io
import math

import pikepdf
from PIL import Image

Matrix = tuple[float, float, float, float, float, float]


class ImageLimitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ImagePlacement:
    image_id: str
    bbox: tuple[float, float, float, float]
    pixel_width: int
    pixel_height: int
    media_type: str
    data: bytes


def page_images(page: pikepdf.Page, page_ctm: Matrix, page_index: int,
                remaining: tuple[int, int, int]) -> tuple[tuple[ImagePlacement, ...], bool, int | None, tuple[int, int, int]]:
    """Unknown forms/clipping/masks are disclosed, never guessed absent."""
    images: list[ImagePlacement] = []
    unsupported = 0
    annotations = page.obj.get('/Annots')
    unknown = annotations is not None and (not isinstance(annotations, pikepdf.Array) or len(annotations) > 0)
    pixels = size = encountered = 0
    ctm, complex_state = page_ctm, False
    stack: list[tuple[Matrix, bool]] = []
    try:
        resources = page.obj.get('/Resources', pikepdf.Dictionary())
        xobjects = resources.get('/XObject', pikepdf.Dictionary())
        def point(x: float, y: float) -> tuple[float, float]:
            a, b, c, d, e, f = ctm
            return a*x+c*y+e, b*x+d*y+f
        box = [float(n) for n in page.cropbox]
        corners = [point(box[x], box[y]) for x, y in ((0, 1), (0, 3), (2, 1), (2, 3))]
        bounds = (min(x for x, y in corners), min(y for x, y in corners),
                  max(x for x, y in corners), max(y for x, y in corners))
        for count, instruction in enumerate(pikepdf.parse_content_stream(page)):
            if count >= 100_000:
                raise ImageLimitError('export-image-operator-limit')
            if isinstance(instruction, pikepdf.ContentStreamInlineImage):
                unsupported += 1
                encountered += 1
                if encountered > remaining[0]:
                    raise ImageLimitError('export-image-count-limit')
                continue
            op, args = str(instruction.operator), instruction.operands
            if op == 'q':
                if len(stack) >= 128:
                    raise ImageLimitError('export-image-state-limit')
                stack.append((ctm, complex_state))
            elif op == 'Q':
                if not stack:
                    unknown = True
                    break
                ctm, complex_state = stack.pop()
            elif op == 'cm':
                a,b,c,d,e,f = (float(n) for n in args)
                g,h,i,j,k,l = ctm
                ctm = (a*g+b*i, a*h+b*j, c*g+d*i, c*h+d*j, e*g+f*i+k, e*h+f*j+l)
                if not all(math.isfinite(v) for v in ctm):
                    unknown = True
                    break
            elif op in {'W', 'W*', 'gs'}:
                complex_state = True
            elif op == 'Do':
                encountered += 1
                if encountered > remaining[0]:
                    raise ImageLimitError('export-image-count-limit')
                obj = xobjects.get(str(args[0])) if len(args) == 1 else None
                if not isinstance(obj, pikepdf.Stream) or obj.get('/Subtype') != pikepdf.Name.Image:
                    unknown = True
                    continue
                width, height = int(obj.get('/Width', 0)), int(obj.get('/Height', 0))
                if width <= 0 or height <= 0 or width * height > 16_000_000:
                    raise ImageLimitError('export-image-pixel-limit')
                pixels += width * height
                if pixels > remaining[1]:
                    raise ImageLimitError('export-image-pixel-limit')
                points = [point(x,y) for x,y in ((0,0),(1,0),(0,1),(1,1))]
                bbox = (min(p[0] for p in points), min(p[1] for p in points),
                        max(p[0] for p in points), max(p[1] for p in points))
                filter_value = obj.get('/Filter')
                filters: list[object] = list(filter_value) if isinstance(filter_value, pikepdf.Array) else [filter_value]
                if (complex_state or abs(ctm[1]) > .001 or abs(ctm[2]) > .001
                        or ctm[0] <= 0 or ctm[3] * page_ctm[3] <= 0
                        or any(key in obj for key in ('/SMask', '/Mask', '/Decode', '/OC', '/Alternates', '/OPI', '/SMaskInData'))
                        or bool(obj.get('/ImageMask', False)) or obj.get('/BitsPerComponent') != 8
                        or obj.get('/ColorSpace') not in (pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray)
                        or any(f not in (None, pikepdf.Name.FlateDecode, pikepdf.Name.DCTDecode) for f in filters)
                        or bbox[0] < bounds[0]-.01 or bbox[1] < bounds[1]-.01
                        or bbox[2] > bounds[2]+.01 or bbox[3] > bounds[3]+.01):
                    unsupported += 1
                    continue
                try:
                    with pikepdf.PdfImage(obj).as_pil_image() as decoded:
                        if decoded.size != (width, height) or decoded.mode not in ('RGB', 'L'):
                            unsupported += 1
                            continue
                        converted = decoded.convert('RGB')
                        try:
                            converted.info.clear()
                            output = io.BytesIO()
                            converted.save(output, format='PNG')
                            data = output.getvalue()
                        finally:
                            converted.close()
                except (pikepdf.PdfError, OSError, ValueError, NotImplementedError, Image.DecompressionBombError):
                    unsupported += 1
                    continue
                size += len(data)
                if size > remaining[2]:
                    raise ImageLimitError('export-image-byte-limit')
                images.append(ImagePlacement(f'p{page_index}-image{count}', bbox, width, height, 'image/png', data))
        if stack:
            unknown = True
    except ImageLimitError:
        raise
    except (pikepdf.PdfError, ValueError, TypeError, IndexError, KeyError, AttributeError, OverflowError):
        unknown = True
    return (tuple(images), not unknown and unsupported == 0,
            None if unknown else unsupported, (encountered, pixels, size))
