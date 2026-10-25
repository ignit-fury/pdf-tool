# HEIC conversion runtime

`POST /images/heic-decode` accepts a raw `image/heic` or `image/heif` body and
returns `image/png`. It has no document ID, password, job or cache entry. The
browser must disclose this image-only server operation before sending it.

The decoder is a separate file-in/file-out subprocess boundary in
`server/image_conversion.py`. It never enters the PDF worker and does not change
the PDF seccomp filter, actions or resource limits.

Development on macOS uses the installed `/usr/bin/sips`. Linux development can
use an existing `/usr/bin/heif-dec` or legacy `/usr/bin/heif-convert`. Set
`PDF_TOOL_HEIC_DECODER` to one of those exact platform paths to select it; other
paths, symlinks and non-executable files refuse. No PATH lookup, shell, user
filename, decoder plugin configuration or automatic installation is used.
Codec existence does not prove capability: each conversion must actually produce
a completely decoded PNG. The macOS smoke test also creates and decodes a real
tiny HEIC through the installed codec.

## Production status

**`PDF_TOOL_ENV=production` currently always returns `HEIC_UNAVAILABLE`.**
No configuration flag can claim the missing confinement is verified. This is
intentional fail-closed behavior pending Linux release verification. Development
subprocess/resource controls do not establish filesystem or network isolation.
Neither macOS smoke nor controlled child tests certify Linux production security.

A future reviewed Linux runtime must provide a separate native-code launcher
that denies egress and gives the decoder only its private input/output scratch,
read-only executable/libraries/plugins, no service credentials, no host filesystem
and no sibling job access. It must prove those denials with adversarial tests and
real codec conversion before production is enabled. Do not permit native exec in
the existing PDF seccomp filter to implement this.

The packaging candidate to verify is Debian 13/trixie `libheif-examples`
`1.23.6-2~deb13u1` from a dated Debian security snapshot, with its
exact transitive decoder/plugin closure and base-image digest pinned by the
release recipe. This version is listed in the [Debian trixie package metadata](https://packages.debian.org/trixie/libheif-examples).
This is a **configuration-only candidate, not a tested image or
an installation instruction**. Verify that exact package/version and distro
security updates before building; do not replace an unavailable name/version
without review. The newer upstream binary is `heif-dec`; a distro rename is not
assumed. Keep native security limits enabled; never pass `--disable-limits` or
`LIBHEIF_SECURITY_LIMITS=off`. No host/container install was performed here.

## Bounds and cleanup

- Input: 20 MiB, supported ISO-BMFF HEIC/HEIF brands, one `hvc1` item matching
  the primary image, one spatial extent. Sequences, grids, auxiliary/thumbnail
  references, protected items and external data references explicitly refuse.
  This deliberately narrow subset means some otherwise valid phone photos refuse.
- Image: at most 16,000,000 decoded pixels and 16,384 pixels per dimension;
  checked in container metadata, native probe where available and final PNG.
- PNG: at most 64 MiB; regular single-link file, signature, chunk sizes/CRC,
  non-animated single image, complete Pillow `verify()` and `load()` in the bounded
  child. Pillow is the existing PNG validator, not an in-process HEIF decoder.
- One 20-second wall deadline covers metadata preflight, native probe, conversion
  and full PNG validation. CPU limit is 20 seconds, descriptor limit 64, core dumps
  disabled, file size 64 MiB. Linux also limits child address space to 1 GiB.
  Probe diagnostics are bounded to 64 KiB, discarded and never returned/logged.
- Private random scratch uses the existing `PDF_TOOL_SCRATCH_ROOT` policy
  (`/dev/shm` on Linux; OS temporary directory for macOS development). Fixed
  internal filenames, minimal environment, closed FDs and one process group.
  Parent termination kills the group, waits for the direct child and removes
  scratch on every terminal path. Orphan descendants are killed; the OS reaps
  them. Request cancellation retains its shared worker slot until work finishes.

Errors contain only fixed codes: `HEIC_UNAVAILABLE`, `INVALID_HEIC`,
`IMAGE_LIMIT_EXCEEDED`, `IMAGE_CONVERSION_FAILED`, `IMAGE_CONVERSION_TIMEOUT`.
HTTP ingress/body errors retain their existing fixed codes. Responses use the
existing no-store, CSP, nosniff and CORS policy. No decoder stderr, filenames,
exceptions, image bytes or credentials enter error reporting.

## Verification

Run `pytest -q tests/test_image_conversion.py tests/test_heic_contract.py` with
the project virtual environment. The installed macOS codec may require OS access
outside an agent filesystem sandbox; a blocked real smoke is a failure to resolve,
not an excuse to skip an available codec. Linux CPU/address-space/tmpfs and native
filesystem/egress confinement remain unexecuted on the macOS workstation.
