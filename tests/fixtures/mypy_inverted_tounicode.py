"""Deliberately-wrong fixture: inverting /ToUnicode to decide output bytes.

This is the exact mistake TEXT-05's type separation exists to catch. Inverting
CodeToUnicode produces dict[Unicode, CharCode] -- not CodeToGlyph -- and
passing it to encode_for_output must be a mypy --strict error.

Not collected by pytest (filename doesn't match test_*.py). Exercised only via
`uv run --frozen mypy --strict tests/fixtures/mypy_inverted_tounicode.py` from
tests/test_types.py::test_mypy_rejects_inverted_tounicode.
"""

from engine.types import CharCode, CodeToUnicode, Unicode, encode_for_output

tou: CodeToUnicode = {CharCode(1): Unicode("a"), CharCode(2): Unicode("b")}

# The mistake: /ToUnicode is not injective and was never meant to decide
# rendering. Inverting it and feeding it to encode_for_output as if it were
# the forward (code -> glyph) map is unsound -- and must be a type error.
unicode_to_code = {v: k for k, v in tou.items()}

encode_for_output("ab", unicode_to_code)
