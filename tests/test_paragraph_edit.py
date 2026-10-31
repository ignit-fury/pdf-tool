import pytest

from engine.paragraph_edit import line_ops, rebuild_text

SEGS = [('r1', 'Hello'), (None, ' '), ('r2', 'bold'), (None, ' '), ('r3', 'world')]


@pytest.mark.parametrize('new,expected', [
    ('Hello bold world', []),
    ('Hallo bold world', [('r1', 'Hallo')]),
    ('Hello BOLD world', [('r2', 'BOLD')]),
    ('Hello bold world!', [('r3', 'world!')]),
    ('Hello there world', [('r2', 'there')]),
    ('Hi world', [('r1', 'Hi'), ('r2', '')]),          # r3 untouched keeps its style
    ('Hello  bold world', [('r2', ' bold')]),
    ('', [('r1', ''), ('r2', ''), ('r3', '')]),
])
def test_line_ops_touch_only_changed_runs(new, expected):
    assert line_ops(SEGS, new) == expected


def test_line_ops_without_runs_is_none():
    assert line_ops([(None, ' ')], 'x') is None


def test_line_ops_keeps_graphemes_whole():
    assert line_ops([('r1', 'café')], 'cafés') == [('r1', 'cafés')]


def test_rebuild_text_joins_soft_wraps_with_spaces_and_keeps_new_breaks():
    assert rebuild_text(2, ['Left first longer', 'Left second']) == 'Left first longer Left second'
    assert rebuild_text(2, ['Left', 'first', 'Left second']) == 'Left\nfirst\nLeft second'
