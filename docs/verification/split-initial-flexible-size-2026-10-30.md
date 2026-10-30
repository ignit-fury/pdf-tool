# Split-initial flexible replacement — local verification

The FAR title stores its oversized `F` and smaller `EDERAL` as separate source
runs. When Preserve layout cannot fit a longer replacement, the flexible text
box now retains the first character's detected point size separately from the
remaining text. The preview and saved box use one selected bundled font, so a
missing Times New Roman font program is still substituted and disclosed.

The browser draft exposes both numeric sizes. The native PDF writer measures
the large initial during wrapping and switches text size within the content
stream; the whole replacement stays searchable and one owned box can be
reopened. It does not move other PDF content or reconstruct arbitrary mixed
formatting beyond this split-initial pattern.

Verification on this checkout:

- FAR page 1 `FEDERALS` replacement: PDFium finds the full word; reindexing
  reports `F` at 75 pt and `EDERALS` at 60 pt. A rendered preview was visually
  inspected for clipping.
- Python regression: 871 passed, 3 skipped and 34 deselected in the sandbox;
  the six OS-restricted failures passed when rerun with the required local
  permissions (877 passing results in total across the two runs).
- Client suite: 202 passed, plus the added mixed-size preview validator test
  passed in a focused 15-test run. Vite build and strict mypy passed.
- Browser interaction reached the split-word draft and showed 75/60 pt sizes.
  The first exact-preview attempt exposed a client response-validator gap,
  which was fixed and covered by a controller test. A fresh browser retry
  could not be completed because the test browser's file chooser did not
  return a file selection event; the server and controller preview paths were
  verified independently.

No deployment or dependency migration was performed.
