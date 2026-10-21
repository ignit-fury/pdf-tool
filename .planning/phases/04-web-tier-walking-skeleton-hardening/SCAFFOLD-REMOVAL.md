# Obsolete scaffold removal

Phase 4 uses the gate-tested `engine.recipe` as its only edit implementation.
Removed `server/engine_replace.py`, `font_subsetter.py`, `ephemeral.py`, diagnostic
scripts and the obsolete smoke script. The former replacement fork crashed before
writing and violated the atomic recipe contract; its scratch helper also retained
state outside the promised lifetime.

The previous `server/app.py` exposed unfinished image conversion, PDF/A, DOCX,
compression, split, merge, rotation, text and HTML export routes. Those routes belonged
to later phases and are removed. Their previous implementation remains in git history
at `0acd3eb`; it is prior art, not a supported API. `python-docx` was removed from runtime
dependencies. Phase 4 supports original/edited PDF download from the browser only.

Browser dependencies and the existing React/Vite architecture are retained. Installed
dependencies and generated build files belong outside source control.
