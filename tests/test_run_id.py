"""Tests for engine.run_id -- the byte-offset run ID codec (TEXT-03, D-02).

Relies on [tool.pytest.ini_options] pythonpath = ["."] in pyproject.toml for
a bare `import engine`; unlike the older test files it does not need a
sys.path.insert side effect from another module to be collectable standalone.
"""

import pytest

from engine.records import GlyphRecord
from engine.run_id import decode_run_id, encode_run_id, resolve_run_id_offset
from engine.types import CharCode

HASH = "a" * 64


# --- round-trip: one case per optional-segment shape named in the grammar ---


def test_round_trip_bare_page_part() -> None:
    """{hash}:p{page}:c{part}:o{offset} -- no optional segments at all."""
    run_id = encode_run_id(HASH, page=2, part=0, byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_one_xobj_hop() -> None:
    run_id = encode_run_id(HASH, page=2, part=0, xobj_path=(17,), byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_multiple_xobj_hops() -> None:
    """xobj_path is a repeated segment -- [/x{xobjObjid}]*."""
    run_id = encode_run_id(HASH, page=2, part=0, xobj_path=(17, 42), byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_annotation() -> None:
    run_id = encode_run_id(HASH, page=2, part=0, annot=(3, "N"), byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_pattern() -> None:
    run_id = encode_run_id(HASH, page=2, part=0, pattern=9, byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_charproc() -> None:
    run_id = encode_run_id(HASH, page=2, part=0, charproc="A", byte_offset=57)
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_with_subrange() -> None:
    """The D-02 sub-run segment -- :g{start}-{end}."""
    run_id = encode_run_id(HASH, page=2, part=0, byte_offset=57, subrange=(1, 3))
    assert encode_run_id(**decode_run_id(run_id)) == run_id


def test_round_trip_every_optional_segment_together() -> None:
    run_id = encode_run_id(
        HASH,
        page=2,
        part=0,
        xobj_path=(17, 42),
        annot=(3, "N"),
        pattern=9,
        charproc="A",
        byte_offset=57,
        subrange=(1, 3),
    )
    assert encode_run_id(**decode_run_id(run_id)) == run_id


# --- decode_run_id: strict grammar match, typed ValueError on anything else ---


def test_decode_rejects_malformed_string() -> None:
    with pytest.raises(ValueError):
        decode_run_id("not-a-run-id")


def test_decode_rejects_short_hash() -> None:
    with pytest.raises(ValueError):
        decode_run_id("abc123:p0:c0:o5")


def test_decode_rejects_trailing_garbage() -> None:
    with pytest.raises(ValueError):
        decode_run_id(HASH + ":p0:c0:o5;drop table runs")


def test_decode_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        decode_run_id("")


# --- byte-offset addressing: the D-03/TEXT-03 core claim ---

_STREAM = b"1 0 0 1 36 738 Tm\n(Hello)Tj\nET"
_TJ_OFFSET = _STREAM.index(b"Tj")


def test_id_offset_points_at_operator_keyword() -> None:
    run_id = encode_run_id(HASH, page=0, part=0, byte_offset=_TJ_OFFSET)
    assert resolve_run_id_offset(run_id, {0: _STREAM}) is True


def test_off_by_one_offset_no_longer_finds_the_keyword() -> None:
    """Permanent negative case (required by the brief): a run ID that is off
    by a single byte must not resolve. This is what proves the offset
    addresses real bytes rather than being decorative -- an ordinal-based
    scheme has no equivalent failure mode to test against.

    Manually confirmed to go red when the defect is removed: stubbing
    resolve_run_id_offset's body to `return True` (deleting the actual
    keyword check) makes this test fail. See task-2-report.md for the
    transcript.
    """
    run_id = encode_run_id(HASH, page=0, part=0, byte_offset=_TJ_OFFSET + 1)
    assert resolve_run_id_offset(run_id, {0: _STREAM}) is False


def test_resolve_returns_false_for_missing_part() -> None:
    run_id = encode_run_id(HASH, page=0, part=1, byte_offset=_TJ_OFFSET)
    assert resolve_run_id_offset(run_id, {0: _STREAM}) is False


def test_resolve_returns_false_for_offset_past_end_of_part() -> None:
    run_id = encode_run_id(HASH, page=0, part=0, byte_offset=len(_STREAM) + 100)
    assert resolve_run_id_offset(run_id, {0: _STREAM}) is False


# --- GlyphRecord shape (TEXT-02 acceptance criterion) ---


def test_glyph_record_has_exactly_thirteen_fields() -> None:
    assert len(GlyphRecord.__dataclass_fields__) == 13


def test_glyph_record_missing_field_raises_type_error() -> None:
    with pytest.raises(TypeError):
        GlyphRecord(code=CharCode(1))  # type: ignore[call-arg]
