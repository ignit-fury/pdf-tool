"""Substitution refuses shaping that the CID-to-Unicode contract cannot preserve."""
import pytest

from engine import fonts


def test_combining_cluster_is_refused_before_unicode_is_truncated() -> None:
    assert fonts.substitution_unicode_reason("Sans", "Regular", ("e\u0301",)) == "multi_character_shaping_unsupported"


def test_shared_glyph_cannot_overwrite_another_operations_unicode() -> None:
    # HarfBuzz renders soft hyphen as the space glyph in this actual bundled face.
    # One shared CID would otherwise acquire whichever ToUnicode value was last.
    assert fonts.substitution_unicode_reason("Sans", "Regular", (" ", "\u00ad")) == "ambiguous_glyph_unicode_mapping"


@pytest.mark.parametrize("texts", [("Hello world", "Hallo world"), ("café",), ("",), ()])
def test_one_to_one_unicode_remains_supported(texts: tuple[str, ...]) -> None:
    assert fonts.substitution_unicode_reason("Sans", "Regular", texts) is None


def test_subset_shaper_cannot_silently_truncate_combining_cluster() -> None:
    text = "e\u0301"
    subset = fonts.subset_font_for_family("Sans", "Regular", frozenset(fonts.shape_glyph_names("Sans", "Regular", text)))
    with pytest.raises(ValueError, match="multi_character_shaping_unsupported"):
        fonts.shape_cids(subset, text)
