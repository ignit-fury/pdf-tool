"""Type contract for the Code-to-Glyph vs Code-to-str distinction (TEXT-05).

A PDF font carries two different maps and conflating them is the classic bug
in this domain:

- /Encoding resolves a character code to a glyph. This decides what is drawn
  on the page.
- /ToUnicode resolves a character code to text. This is for display, search
  and copy-paste. It decides nothing about rendering.

/ToUnicode is also non-injective (a single code can map to "ffi"), frequently
absent, and sometimes simply wrong. Inverting /ToUnicode to decide output
bytes is unsound. CodeToGlyph and CodeToUnicode are distinct types so mypy
--strict rejects any attempt to use one where the other is required.
"""

from typing import NewType

CharCode = NewType("CharCode", int)  # a code as it appears in the content stream
GlyphId = NewType("GlyphId", int)  # a GID / CID in the font program
Unicode = NewType("Unicode", str)  # /ToUnicode output — DISPLAY AND SEARCH ONLY

CodeToGlyph = dict[CharCode, GlyphId]  # the FORWARD map. Decides pixels.
CodeToUnicode = dict[CharCode, Unicode]  # /ToUnicode. Decides nothing.


def encode_for_output(text: str, fwd: CodeToGlyph) -> bytes:
    raise NotImplementedError


def display_text(codes: list[CharCode], tou: CodeToUnicode) -> str:
    raise NotImplementedError
