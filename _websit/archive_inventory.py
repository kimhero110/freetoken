"""Verify the distributable archive without reading private runtime records."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    failures = []
    for item in manifest['files']:
        path = ROOT / item['path']
        if not path.is_file() or digest(path) != item['sha256']:
            failures.append(item['path'])
    if failures:
        raise SystemExit('Archive mismatch: ' + ', '.join(failures))
    print(f"Verified {len(manifest['files'])} archived files")


if __name__ == '__main__':
    verify()
