"""The cross-engine baseline tolerates recorded disagreement only, and never a worse one."""
from harness.run_corpus_harness import BASELINE, BASELINE_MARGIN_PCT, _baselined


def test_recorded_pair_passes_until_it_gets_worse() -> None:
    filename, pairs = next(iter(BASELINE['cross_engine'].items()))
    pair, recorded = next(iter(pairs.items()))
    assert _baselined(filename, pair, f'{pair}: {recorded:.3f}% (threshold 8.0%)')
    assert not _baselined(filename, pair, f'{pair}: {recorded + BASELINE_MARGIN_PCT + 0.1:.3f}% (threshold 8.0%)')


def test_unrecorded_file_or_pair_is_not_baselined() -> None:
    assert not _baselined('not-in-corpus.pdf', 'page0:pdfium-vs-mupdf', 'page0:pdfium-vs-mupdf: 9.000%')
    filename = next(iter(BASELINE['cross_engine']))
    assert not _baselined(filename, 'page19:pdfium-vs-mupdf', 'page19:pdfium-vs-mupdf: 9.000%')
