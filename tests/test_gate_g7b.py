"""Scope and non-vacuity controls established before the PDF/A implementation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docx_scope_ceiling_records_inclusions_exclusions_and_provenance() -> None:
    ceiling = (ROOT / '.planning/phases/08-pdf-a-then-docx/DOCX-CEILING.md').read_text()
    for phrase in ('## Decision', 'single-column body text', 'font-size',
                   'bold/italic', 'inline images', 'ruled tables only',
                   'unruled tables', 'multi-column reading order',
                   'header/footer reconstruction', 'round-trip back into the tool',
                   'independently cuttable', '## What was NOT tested', '2026-10-28'):
        assert phrase in ceiling
    manifest = json.loads((ROOT / 'harness/pdfa-manifest.json').read_text())
    assert manifest['ceiling_commit'] == '60dd243'


def test_frozen_manifest_has_all_twelve_positive_ids_and_public_risk_strata(tmp_path: Path) -> None:
    from harness.pdfa_fixture import POSITIVE_IDS, materialize_manifest
    manifest = json.loads((ROOT / 'harness/pdfa-manifest.json').read_text())
    assert manifest['minimum_successes'] == 12
    cases = materialize_manifest(manifest, tmp_path)
    successes = {case['id'] for case, _ in cases if case['expectation'] == 'success'}
    assert successes == set(POSITIVE_IDS)
    assert len(successes) == 12
    public = [case for case, _ in cases if case['kind'] == 'public']
    assert len(public) >= 13
    strata = {tag for case in public for tag in case['categories']}
    assert {'annotation_appearance_streams', 'type3', 'cid_keyed_cff',
            'type0_identity_h', 'inline_images', 'subset_fonts',
            'vector_outlined_text'} <= strata
    assert {case['id'] for case, _ in cases if case['expectation'] == 'refusal'} >= {
        'refuse-missing-font', 'refuse-cmyk', 'refuse-active-content',
        'refuse-unknown-operator', 'refuse-malformed', 'refuse-inline-lzw'}
    for case, path in cases:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case['sha256']


def test_generated_source_bytes_are_repeatable(tmp_path: Path) -> None:
    from harness.pdfa_fixture import build_fixtures
    first = build_fixtures(tmp_path / 'first')
    second = build_fixtures(tmp_path / 'second')
    assert first.keys() == second.keys()
    for key in first:
        assert first[key].read_bytes() == second[key].read_bytes(), key


def test_manifest_rejects_missing_duplicate_changed_or_lowered_cases(tmp_path: Path) -> None:
    import copy
    import pytest
    from harness.pdfa_fixture import materialize_manifest
    good = json.loads((ROOT / 'harness/pdfa-manifest.json').read_text())
    for mutate in (lambda m: m.update(minimum_successes=0),
                   lambda m: m['fixtures'].pop(),
                   lambda m: m['fixtures'].append(m['fixtures'][0]),
                   lambda m: m['fixtures'][0].update(sha256='0' * 64)):
        bad = copy.deepcopy(good)
        mutate(bad)
        with pytest.raises(ValueError):
            materialize_manifest(bad, tmp_path)


def test_frozen_baseline_measures_every_input_before_converter_exists() -> None:
    manifest = json.loads((ROOT / 'harness/pdfa-manifest.json').read_text())
    baseline = json.loads((ROOT / 'harness/pdfa-baseline.json').read_text())
    assert baseline['measurement_complete'] is True
    assert baseline['converter_existed_at_measurement'] is False
    assert baseline['validator_version'] == '1.30.3'
    assert {r['id']: r['sha256'] for r in baseline['records']} == {
        case['id']: case['sha256'] for case in manifest['fixtures']}
    malformed = [r for r in baseline['records'] if r['infrastructure_errors']]
    assert len(malformed) == 1 and malformed[0]['id'] == 'refuse-malformed'
    assert malformed[0]['returncode'] == 7 and malformed[0]['verdicts'] == []
    assert sum(v['compliant'] for r in baseline['records'] for v in r['verdicts']) == 1
    assert baseline['passed'] is False  # Preserve the real CLI result; not a conversion gate.
