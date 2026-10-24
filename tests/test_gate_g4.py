"""G4 local proof: full-document text changes and disjoint renderer masks.

The corpus fixture is a 40-page public technical document, not a legal contract.
Fast negative controls prevent a wide enclosing mask or unchanged output from
being mistaken for a successful batch-fidelity proof.
"""
import base64
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import resource
import subprocess
import sys
import time
from types import SimpleNamespace

from PIL import Image
import pikepdf
import pypdfium2 as pdfium
import pytest

from engine.index import RunIndex
from engine.playa_boundary import open_document
from engine.rewrite import _correlate
from engine.run_id import decode_run_id
from engine.search import project_search_text
from engine.walker import located_cluster_records
from harness.masked_diff import masked_pixel_diff
from harness.render_diff import RENDER_DPI, render_all
from server.isolation import run_worker
from test_find_replace_recipe import node_candidate
from tools.audit_corpus_edits import normalize

# Legacy harness modules import their siblings directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'harness'))
from run_corpus_harness import _cross_engine_pair_ok  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'corpus/public/govdocs1_013_013050.pdf'
DIGEST = 'd0a3b06606378733a2ec96cfa01e3b12c111d13059d070e3e039b751347a4529'


def _union_diff(before: Path, after: Path, masks: list[tuple[int, int, int, int]], scratch: Path) -> int:
    if not masks:
        return masked_pixel_diff(before, after)
    scratch.mkdir(parents=True, exist_ok=True)
    paths = []
    for number, source in enumerate((before, after)):
        with Image.open(source) as image:
            rgb = image.convert('RGB')
            for mask in masks:
                rgb.paste((0, 0, 0), mask)
            target = scratch / f'{number}.png'
            rgb.save(target)
            paths.append(target)
    return masked_pixel_diff(*paths)


def _assert_page_pixels(before: Path, after: Path, masks: list[tuple[int, int, int, int]], scratch: Path, *, changed: bool) -> tuple[int, int]:
    unmasked = masked_pixel_diff(before, after)
    outside = _union_diff(before, after, masks, scratch)
    assert outside == 0, f"outside-region changed pixels: {outside}"
    if changed:
        assert unmasked > 0, "batch output must have a nonvacuous visible change"
    return unmasked, outside


def _images(tmp_path, points):
    before = tmp_path / 'before.png'
    after = tmp_path / 'after.png'
    image = Image.new('RGB', (100, 100), 'white')
    image.save(before)
    for point in points:
        image.putpixel(point, (0, 0, 0))
    image.save(after)
    return before, after


def test_mask_union_excludes_only_each_edited_region(tmp_path):
    before, after = _images(tmp_path, [(15, 15), (85, 85)])
    assert _assert_page_pixels(before, after, [(10, 10, 20, 20), (80, 80, 90, 90)], tmp_path / 'masked', changed=True) == (2, 0)


def test_outside_change_between_disjoint_masks_is_detected(tmp_path):
    before, after = _images(tmp_path, [(15, 15), (50, 50), (85, 85)])
    assert _union_diff(before, after, [(10, 10, 20, 20), (80, 80, 90, 90)], tmp_path / 'masked') == 1


def test_nonvacuous_batch_cannot_pass_with_unchanged_output(tmp_path):
    before, after = _images(tmp_path, [])
    with pytest.raises(AssertionError, match='nonvacuous'):
        _assert_page_pixels(before, after, [(10, 10, 20, 20)], tmp_path / 'masked', changed=True)


def test_unchanged_page_is_compared_without_a_mask(tmp_path):
    before, after = _images(tmp_path, [(50, 50)])
    with pytest.raises(AssertionError, match='outside-region'):
        _assert_page_pixels(before, after, [], tmp_path / 'masked', changed=False)


def _pixel_mask(run):
    """One run's device-space em bounds, outward rounded with 3pt ink padding.

    Device glyphs already include page rotation and y reflection. The normal is
    chosen from the recorded page CTM, as in the existing selection geometry.
    Masks remain separate even when a page contains many edited text runs.
    """
    assert run.effective_em and run.effective_em > 0
    em = run.effective_em
    a, b, c, d, _e, _f = run.page_ctm
    direction = run.direction or run.glyphs[0].advance
    length = math.hypot(*direction)
    ux, uy = (direction[0] / length, direction[1] / length) if length else (1.0, 0.0)
    sign = 1 if a * d - b * c > 0 else -1
    nx, ny = -uy * sign, ux * sign
    points = [(x + nx * pad, y + ny * pad)
              for glyph in run.glyphs
              for x, y in ((glyph.x, glyph.y),
                           (glyph.x + glyph.advance[0], glyph.y + glyph.advance[1]))
              for pad in (-0.2 * em, 0.8 * em)]
    scale = RENDER_DPI / 72
    return (math.floor((min(x for x, _ in points) - 3) * scale),
            math.floor((min(y for _, y in points) - 3) * scale),
            math.ceil((max(x for x, _ in points) + 3) * scale),
            math.ceil((max(y for _, y in points) + 3) * scale))


def _pdfium_text(source, number):
    with pdfium.PdfDocument(source) as document:
        page = document[number]
        text = page.get_textpage()
        try:
            return text.get_text_range()
        finally:
            text.close()
            page.close()


def test_mask_union_geometry_rounds_outward_in_device_space():
    run = SimpleNamespace(effective_em=10.0, direction=(12.0, 0.0),
                          page_ctm=(1, 0, 0, -1, 0, 100),
                          glyphs=[SimpleNamespace(x=10.1, y=20.2, advance=(4.1, 0.0))])
    assert _pixel_mask(run) == (14, 19, 36, 53)
    run.direction = (0.0, 12.0)
    run.page_ctm = (0, 1, 1, 0, 0, 0)
    run.glyphs[0].advance = (0.0, 4.1)
    assert _pixel_mask(run) == (10, 35, 44, 57)


def _expected_characters(before, changes):
    expected = Counter(normalize(before))
    for old, new in changes:
        expected.subtract(normalize(old))
        expected.update(normalize(new))
    return expected


def test_independent_character_delta_detects_dropped_unrelated_text():
    expected = _expected_characters('the cat the dog', [('the cat', 'a cat')])
    assert expected == Counter(normalize('a cat the dog'))
    assert expected != Counter(normalize('a cat dog'))


def _operator_groups(runs):
    groups = defaultdict(dict)
    for run in runs:
        address = decode_run_id(run.run_id)
        assert not address['xobj_path']  # This source's acceptance workload is page text.
        for glyph in run.glyphs:
            groups[(address['part'], glyph.operator_byte_offset)][
                (-1 if glyph.item_index_within_tj is None else glyph.item_index_within_tj,
                 glyph.byte_offset_within_string)] = glyph
    return {key: [glyph for _, glyph in sorted(values.items())] for key, values in groups.items()}


def _assert_written_text(original, expected, groups):
    part = decode_run_id(original.run_id)['part']
    first = original.glyphs[0]
    found = [glyphs for (number, _offset), glyphs in groups.items()
             if number == part and glyphs and abs(glyphs[0].x - first.x) <= 1e-6
             and abs(glyphs[0].y - first.y) <= 1e-6
             and ''.join(g.unicode or '' for g in glyphs) == expected]
    assert len(found) == 1, f'written text anchor matches: {len(found)}; page: {original.page}'


def _assert_untouched_instructions(original, output, source_runs, operations):
    """Every non-target instruction survives in its part and relative order."""
    targets = defaultdict(set)
    instructions = {}
    for operation in operations:
        run = next(row for row in source_runs[decode_run_id(operation['run_id'])['page']]
                   if row.run_id == operation['run_id'])
        key = run.page, decode_run_id(run.run_id)['part']
        correlated = _correlate(original, run.page, run, source_runs[run.page])
        assert isinstance(correlated, tuple)
        parsed, touched = correlated
        instructions[key] = parsed
        targets[key].update(touched)
    checked = 0
    for number, (before, after) in enumerate(zip(original.pages, output.pages)):
        contents_a = before.obj.get('/Contents')
        contents_b = after.obj.get('/Contents')
        parts_a = list(contents_a) if isinstance(contents_a, pikepdf.Array) else [contents_a]
        parts_b = list(contents_b) if isinstance(contents_b, pikepdf.Array) else [contents_b]
        assert len(parts_a) == len(parts_b)
        for part, (a, b) in enumerate(zip(parts_a, parts_b)):
            if a is None:
                assert b is None
                continue
            key = number, part
            if key not in targets:
                assert a.read_bytes() == b.read_bytes()
                checked += 1
                continue
            kept = [pikepdf.unparse_content_stream([item])
                    for index, item in enumerate(instructions[key]) if index not in targets[key]]
            actual = [pikepdf.unparse_content_stream([item])
                      for item in pikepdf.parse_content_stream(output.make_stream(b.read_bytes()))]
            cursor = 0
            for item in actual:
                if cursor < len(kept) and item == kept[cursor]:
                    cursor += 1
            assert cursor == len(kept), f'untouched instructions missing on page {number}, part {part}'
            checked += len(kept)
    return checked


def _worker(source, operations, dry_run):
    body = json.dumps(operations, separators=(',', ':')).encode()
    assert len(body) <= 1024 * 1024
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    result = run_worker('edit', source, recipe=body, dry_run=dry_run)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    elapsed = time.monotonic() - started
    cpu = after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    print(json.dumps({'stage': 'preview' if dry_run else 'apply', 'ops': len(operations),
                      'body_bytes': len(body), 'wall_seconds': round(elapsed, 3),
                      'cpu_seconds': round(cpu, 3), 'ok': result.get('ok'), 'error': result.get('error')}), flush=True)
    assert 'error' not in result
    assert elapsed < 30 and cpu < 20
    return result


@pytest.mark.corpus
def test_g4_full_40page_batch_text_and_all_renderer_pages(tmp_path):
    if not SOURCE.exists():
        pytest.skip('public 40-page technical acceptance proxy absent')
    started = time.monotonic()
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == DIGEST
    original_runs = {}
    pages = {}
    with RunIndex(SOURCE) as index:
        assert index.page_count == 40
        for number in range(40):
            indexed = index.page(number)
            original_runs[number] = [run for run, _ in indexed.runs]
            pages[number + 1] = {'runs': [
                {'run_id': run.run_id, 'text': run.display_text, 'state': verdict.state,
                 'reason': verdict.reason, 'search': project_search_text(run.display_text)}
                for run, verdict in indexed.runs]}
    initial = node_candidate(pages, query='the')
    assert len(initial['matches']) == 1029
    assert sum(len(rows) for rows in original_runs.values()) == 3000
    assert len({match['runId'] for match in initial['matches']}) == 772
    # The client now detects ambiguous shared source addresses before preview.
    # These 69 rows remain visible and disabled; all 675 safe run operations
    # still reach the full worker workload after the remaining refusals.
    early_refusals = {match['runId']: match['reason'] for match in initial['matches'] if match['reason']}
    assert len(early_refusals) == 69
    assert set(early_refusals.values()) == {'operator_shared_by_multiple_runs'}
    assert len(initial['candidate']['recipe']) == 703
    failed = _worker(source, initial['candidate']['recipe'], True)
    assert failed['ok'] is False and failed['pdf'] is None
    worker_refusals = {row['run_id']: row['reason'] for row in failed['resolved'] if not row['ok']}
    assert len(worker_refusals) == 28
    assert Counter(worker_refusals.values())['operator_shared_by_multiple_runs'] == 6
    refusals = {**early_refusals, **worker_refusals}
    assert len(refusals) == 97
    assert Counter(refusals.values())['operator_shared_by_multiple_runs'] == 75
    assert sum(reason.startswith('no mapping table entry') for reason in refusals.values()) == 22
    accepted = node_candidate(pages, query='the', refused_ids=refusals)
    assert len(accepted['candidate']['recipe']) == 675
    chosen = next(change for change in accepted['candidate']['changes'] if len(change['matchIds']) > 1)
    excluded = chosen['matchIds'][0]
    source_by_id = {run.run_id: run for rows in original_runs.values() for run in rows}
    prior = [{'run_id': chosen['runId'], 'new_text': chosen['before'], 'style': {'color': [0.4, 0.2, 0.1]}}]
    prior_preview = _worker(source, prior, True)
    assert prior_preview['ok'] is True and prior_preview['pdf'] is None
    assert _worker(source, prior, False)['ok'] is True
    final = node_candidate(pages, query='the', recipe=prior, excluded_ids=[excluded], refused_ids=refusals)
    candidate = final['candidate']
    assert len(final['matches']) == 1029  # Excluded/refused rows are never hidden.
    assert len(candidate['recipe']) == len(candidate['changes']) == 675
    assert candidate['selectedCount'] == accepted['candidate']['selectedCount'] - 1
    assert candidate['recipe'][0]['style'] == prior[0]['style']
    assert candidate['recipe'][0]['run_id'] == prior[0]['run_id']
    assert len({op['run_id'] for op in candidate['recipe']}) == 675
    preview = _worker(source, candidate['recipe'], True)
    assert preview['ok'] is True and preview['pdf'] is None
    applied = _worker(source, candidate['recipe'], False)
    assert applied['ok'] is True and applied['resolved'] == preview['resolved']
    output_bytes = base64.b64decode(applied['pdf'])
    output_path = tmp_path / 'batch.pdf'
    output_path.write_bytes(output_bytes)
    checked = subprocess.run(['qpdf', '--check', str(output_path)], capture_output=True, timeout=30)
    assert checked.returncode == 0
    operations = {op['run_id']: op for op in candidate['recipe']}
    changes_by_page = defaultdict(list)
    for change in candidate['changes']:
        changes_by_page[change['page'] - 1].append(change)
    assert len(changes_by_page) > 1
    excluded_match = next(match for match in final['matches'] if match['id'] == excluded)
    opted_run = operations[excluded_match['runId']]['new_text']
    assert opted_run.casefold().count('the') == 1
    with RunIndex(output_path) as output_index:
        assert output_index.page_count == 40
        for number in range(40):
            current = [run for run, _ in output_index.page(number).runs]
            groups = _operator_groups(current)
            for change in changes_by_page[number]:
                _assert_written_text(source_by_id[change['runId']], change['after'], groups)
            expected = _expected_characters(_pdfium_text(source, number),
                [(change['before'], change['after']) for change in changes_by_page[number]])
            assert Counter(normalize(_pdfium_text(output_bytes, number))) == expected, f'independent text delta page {number}'
    styled = source_by_id[chosen['runId']]
    anchor = styled.glyphs[0]
    with open_document(output_path) as document:
        colors = [attrs.fill_color[0]
                  for _path, glyph, attrs in located_cluster_records(document.pages[styled.page], styled.page, document)
                  if abs(glyph.x - anchor.x) <= 1e-6 and abs(glyph.y - anchor.y) <= 1e-6]
    assert (0.4, 0.2, 0.1) in colors  # Preserve the actual earlier style, not only recipe JSON.
    with pikepdf.open(io.BytesIO(source)) as original, pikepdf.open(output_path) as output:
        assert len(original.pages) == len(output.pages) == 40
        structural = _assert_untouched_instructions(original, output, original_runs, candidate['recipe'])
        assert structural > 0
        # This pinned source has no CropBox displacement. Device coordinates from
        # the interpreter therefore map directly to each harness renderer's crop.
        assert all(list(page.cropbox) == list(page.mediabox) for page in original.pages)
    render_counts = Counter()
    for number in range(40):
        before = render_all(SOURCE, number, tmp_path / f'original-{number}')
        after = render_all(output_path, number, tmp_path / f'edited-{number}')
        masks = [_pixel_mask(source_by_id[change['runId']]) for change in changes_by_page[number]]
        for label, a, b in zip(('pdfium', 'poppler', 'mupdf'), before, after):
            unmasked, outside = _assert_page_pixels(a, b, masks, tmp_path / f'masked-{number}-{label}',
                                                  changed=bool(changes_by_page[number]))
            render_counts[label] += 1
            print(json.dumps({'page': number + 1, 'engine': label, 'unmasked_pixels': unmasked,
                              'outside_pixels': outside, 'edit_regions': len(masks)}), flush=True)
        for (left, right) in ((0, 1), (0, 2), (1, 2)):
            ok, detail = _cross_engine_pair_ok(f'page {number + 1}', after[left], after[right])
            assert ok, detail
    assert render_counts == {'pdfium': 40, 'poppler': 40, 'mupdf': 40}
    assert SOURCE.read_bytes() == source
    print(json.dumps({'gate': 'G4-technical-proxy', 'pages': 40, 'changed_pages': len(changes_by_page),
                      'matches': 1029, 'selected_matches': candidate['selectedCount'], 'ops': 675,
                      'refused_runs': 97, 'excluded_matches': 1, 'untouched_instructions': structural,
                      'same_engine_page_pairs': 120, 'seconds': round(time.monotonic() - started, 3)}), flush=True)
