"""Generate the sole search Unicode contract; no network or runtime dependencies."""
import argparse
import json
from pathlib import Path
import unicodedata

VERSION = 'ucd-15.1.0-nfkd-fullfold-v1'
DESTINATION = Path(__file__).resolve().parents[1] / 'engine/data/search-unicode-15.1.json'


def generate() -> str:
    if unicodedata.unidata_version != '15.1.0':
        raise RuntimeError('Search data must be generated with Unicode 15.1.0')
    nfkd, casefold, combining = {}, {}, {}
    for code in range(0x110000):
        if 0xD800 <= code <= 0xDFFF:
            continue
        char = chr(code)
        normalized = unicodedata.normalize('NFKD', char)
        if normalized != char:
            nfkd[str(code)] = normalized
        folded = char.casefold()
        if folded != char:
            casefold[str(code)] = folded
        ccc = unicodedata.combining(char)
        if ccc:
            combining[str(code)] = ccc
    return json.dumps(dict(version=VERSION, unicode_version='15.1.0', nfkd=nfkd, casefold=casefold, combining=combining), ensure_ascii=False, separators=(',', ':')) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = generate()
    if args.check:
        if not DESTINATION.exists() or DESTINATION.read_text() != content:
            raise SystemExit('Search Unicode data drifted; regenerate with Python Unicode 15.1.0')
        print('Search Unicode 15.1.0 data is current')
    else:
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_text(content)
