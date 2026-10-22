"""A stream's Tf history is parsed once rather than rescanned for every glyph."""
import engine.classify_run as classify_module
import engine.recipe as recipe_module


def test_classification_font_history_is_scanned_once(monkeypatch) -> None:
    raw = b'BT /F1 12 Tf (First) Tj /F2 10 Tf (Second) Tj ET'
    original = classify_module._TF_RE
    reads = []

    class Pattern:
        def finditer(self, data):
            reads.append(data)
            return original.finditer(data)

    monkeypatch.setattr(classify_module, '_TF_RE', Pattern())
    for _ in range(4):
        assert classify_module._find_active_font_name(raw, raw.index(b'(First)')) == b'F1'
        assert classify_module._find_active_font_name(raw, raw.index(b'(Second)')) == b'F2'
    assert len(reads) == 1


def test_recipe_font_history_is_scanned_once_and_keeps_invalid_size(monkeypatch) -> None:
    raw = b'BT /F1 12 Tf (One) Tj /Bad 1.2.3 Tf (Two) Tj /F2 10 Tf (Three) Tj ET'
    original = recipe_module._TF_NAME_SIZE_RE
    reads = []

    class Pattern:
        def finditer(self, data):
            reads.append(data)
            return original.finditer(data)

    monkeypatch.setattr(recipe_module, '_TF_NAME_SIZE_RE', Pattern())
    for _ in range(4):
        assert recipe_module.active_font_name_and_size(raw, raw.index(b'(One)')) == (b'F1', 12)
        assert recipe_module.active_font_name_and_size(raw, raw.index(b'(Two)')) is None
        assert recipe_module.active_font_name_and_size(raw, raw.index(b'(Three)')) == (b'F2', 10)
    assert len(reads) == 1
