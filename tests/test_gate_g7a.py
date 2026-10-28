"""Full frozen native archival gate; native tools and veraPDF are mandatory."""
from __future__ import annotations

import pytest

from harness.pdfa_fixture import POSITIVE_IDS


def test_coverage_is_non_vacuous():
    with pytest.raises(AssertionError):
        _assert_coverage([], [])
    with pytest.raises(AssertionError):
        _assert_coverage(list(POSITIVE_IDS[:-1]), [])
    with pytest.raises(AssertionError):
        _assert_coverage(list(POSITIVE_IDS), ['refuse-cmyk'])
    _assert_coverage(list(POSITIVE_IDS), [])
