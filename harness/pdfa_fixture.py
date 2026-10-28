"""Deterministic, frozen G7a inputs. No converter or archival metadata is used.

Font timestamps are normalized for cross-machine reproduction; glyphs, widths,
encoding and embedding are built by the production Phase 3 font functions.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pikepdf
from fontTools.ttLib import TTFont

from engine.fonts import (BundledFamily, BundledVariant, embed_type0_font,
                          shape_cids, shape_glyph_names, subset_cid_widths,
                          subset_font_for_family)

ROOT = Path(__file__).resolve().parents[1]
POSITIVE_IDS = ('text-sans', 'text-serif', 'text-mono', 'text-bold',
                'text-italic', 'text-bold-italic', 'image-rgb', 'image-gray',
                'image-only', 'resources-inherited', 'geometry-rotate-crop',
                'multipage-mixed')
REFUSAL_IDS = ('refuse-missing-font', 'refuse-cmyk', 'refuse-active-content',
               'refuse-unknown-operator', 'refuse-malformed', 'refuse-inline-lzw')


def _font(pdf: pikepdf.Pdf, family: BundledFamily, variant: BundledVariant) -> tuple[pikepdf.Object, bytes]:
    text = 'Archival text 123'
    subset = subset_font_for_family(family, variant, frozenset(shape_glyph_names(family, variant, text)))
    font = TTFont(io.BytesIO(subset.data), recalcTimestamp=False)
    font['head'].created = font['head'].modified = 2082844800
    buffer = io.BytesIO()
    font.save(buffer)
    font.close()
    subset = replace(subset, data=buffer.getvalue())
    codes = shape_cids(subset, text)
    mapping = {cid: character for cid, character in codes}
    embedded = embed_type0_font(pdf, subset, subset_cid_widths(subset), mapping)
    encoded = b''.join(cid.to_bytes(2, 'big') for cid, _ in codes).hex().upper().encode('ascii')
    return embedded, b'BT /F1 14 Tf 24 140 Td <' + encoded + b'> Tj ET\n'


def _image(pdf: pikepdf.Pdf, *, gray: bool = False) -> pikepdf.Object:
    channels = 1 if gray else 3
    data = bytes((x * 11 + y * 7 + c * 53) % 256
                 for y in range(12) for x in range(16) for c in range(channels))
    image = pdf.make_stream(data)
    image.update(pikepdf.Dictionary(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
        Width=16, Height=12, BitsPerComponent=8,
        ColorSpace=pikepdf.Name.DeviceGray if gray else pikepdf.Name.DeviceRGB))
    return image


def _positive(path: Path, case: str) -> None:
    with pikepdf.Pdf.new() as pdf:
        family: BundledFamily = 'Serif' if case == 'text-serif' else 'Mono' if case == 'text-mono' else 'Sans'
        variants: dict[str, BundledVariant] = {'text-bold': 'Bold', 'text-italic': 'Italic',
                                             'text-bold-italic': 'BoldItalic'}
        variant = variants.get(case, 'Regular')
        font, text = _font(pdf, family, variant)
        resources = pdf.make_indirect(pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)))
        image_case = case in {'image-rgb', 'image-gray', 'image-only', 'multipage-mixed'}
        if image_case:
            resources.XObject = pikepdf.Dictionary(Im1=_image(pdf, gray=case == 'image-gray'))
        for number in range(2 if case in {'resources-inherited', 'multipage-mixed'} else 1):
            page = pdf.add_blank_page(page_size=(240, 180))
            page.obj.Resources = resources
            content = b'0.2 0.4 0.6 rg 24 20 80 30 re f\n'
            if case != 'image-only':
                content += b'0 g\n' + text
            if image_case:
                content += b'q 64 0 0 48 140 40 cm /Im1 Do Q\n'
            if case == 'geometry-rotate-crop':
                page.obj.CropBox = [12, 12, 228, 168]
                page.obj.Rotate = 90
                page.obj.UserUnit = 1.25
            page.obj.Contents = pdf.make_stream(content)
        if case == 'resources-inherited':
            pdf.Root.Pages.Resources = resources
            for page in pdf.pages:
                del page.obj.Resources
        if case == 'image-only':
            # No unused font resource masks the image-only coverage claim.
            del resources.Font
        pdf.save(path, static_id=True, compress_streams=False,
                 object_stream_mode=pikepdf.ObjectStreamMode.disable)


def _refusal(path: Path, case: str) -> None:
    if case == 'refuse-malformed':
        path.write_bytes(b'%PDF-1.7\nnot a parseable document\n')
        return
    if case == 'refuse-inline-lzw':
        path.write_bytes((ROOT / 'corpus/public/verapdf_inline_image_fixture.pdf').read_bytes())
        return
    with pikepdf.Pdf.new() as pdf:
        page = pdf.add_blank_page(page_size=(240, 180))
        content = b'0 g 24 24 60 30 re f\n'
        if case == 'refuse-missing-font':
            page.obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=pdf.make_indirect(
                pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                   BaseFont=pikepdf.Name.Helvetica))))
            content += b'BT /F1 12 Tf 20 100 Td (Missing font) Tj ET\n'
        elif case == 'refuse-cmyk':
            content = b'0 1 0 0 k 24 24 60 30 re f\n'
        elif case == 'refuse-active-content':
            pdf.Root.OpenAction = pikepdf.Dictionary(S=pikepdf.Name.JavaScript,
                                                    JS=pikepdf.String('app.alert(1)'))
        elif case == 'refuse-unknown-operator':
            content += b'1 UnknownOperator\n'
        page.obj.Contents = pdf.make_stream(content)
        pdf.save(path, static_id=True, compress_streams=False,
                 object_stream_mode=pikepdf.ObjectStreamMode.disable)


def build_fixtures(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for case in (*POSITIVE_IDS, *REFUSAL_IDS):
        path = directory / (case + '.pdf')
        (_positive if case in POSITIVE_IDS else _refusal)(path, case)
        result[case] = path
    return result


def materialize_manifest(manifest: dict[str, Any], directory: Path) -> list[tuple[dict[str, Any], Path]]:
    """Verify the frozen inputs before exposing any to the converter or oracle."""
    fixtures = manifest.get('fixtures')
    if (manifest.get('schema_version') != 1 or type(manifest.get('minimum_successes')) is not int
            or manifest.get('minimum_successes') != 12
            or manifest.get('positive_ids') != list(POSITIVE_IDS)
            or manifest.get('fixture_count') != 31 or not isinstance(fixtures, list)
            or len(fixtures) != 31):
        raise ValueError('G7a manifest policy changed')
    generated = build_fixtures(directory)
    ids: set[str] = set()
    positives: set[str] = set()
    generated_ids: set[str] = set()
    out: list[tuple[dict[str, Any], Path]] = []
    for case in fixtures:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str) or case['id'] in ids:
            raise ValueError('G7a duplicate or invalid fixture')
        ids.add(case['id'])
        if case.get('kind') == 'generated' and case.get('fixture') in generated:
            path = generated[case['fixture']]
            generated_ids.add(case['fixture'])
            expected = 'success' if case['fixture'] in POSITIVE_IDS else 'refusal'
            if case['id'] != case['fixture'] or case.get('expectation') != expected:
                raise ValueError('G7a generated expectation changed')
            if case.get('expectation') == 'success':
                positives.add(case['id'])
        elif case.get('kind') == 'public' and case.get('expectation') == 'probe':
            source = case.get('source')
            if not isinstance(source, str):
                raise ValueError('G7a invalid public source')
            path = (ROOT / source).resolve()
            if path.parent != (ROOT / 'corpus/public').resolve():
                raise ValueError('G7a source outside public corpus')
        else:
            raise ValueError('G7a invalid fixture source')
        if hashlib.sha256(path.read_bytes()).hexdigest() != case.get('sha256'):
            raise ValueError('G7a frozen source hash changed')
        out.append((case, path))
    if positives != set(POSITIVE_IDS) or generated_ids != set(generated):
        raise ValueError('G7a required coverage changed')
    return out


def freeze_manifest(directory: Path, selection_path: Path) -> dict[str, Any]:
    """One-time baseline preparation. Never called by product or test execution."""
    if (ROOT / 'engine/export/pdfa.py').exists():
        raise ValueError('freeze inputs before converter implementation')
    generated = build_fixtures(directory)
    fixtures: list[dict[str, Any]] = []
    for case, path in generated.items():
        fixtures.append({'id': case, 'kind': 'generated', 'fixture': case,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'categories': ['constructed'],
            'expectation': 'success' if case in POSITIVE_IDS else 'refusal'})
    for source in json.loads(selection_path.read_text()):
        fixtures.append({'id': 'public-' + Path(source['filename']).stem, 'kind': 'public',
            'source': 'corpus/public/' + source['filename'], 'sha256': source['sha256'],
            'categories': source['categories'], 'expectation': 'probe'})
    manifest = {'schema_version': 1, 'ceiling_commit': '60dd243',
        'created': '2026-10-28', 'minimum_successes': 12,
        'positive_ids': list(POSITIVE_IDS), 'fixture_count': len(fixtures), 'fixtures': fixtures}
    materialize_manifest(manifest, directory)
    return manifest
