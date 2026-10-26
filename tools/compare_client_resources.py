"""Inventory/extract PE resources from the clients verified by compare_version_assets.

python -I tools/compare_client_resources.py
Raw resource payloads are retained locally; no executable is run.
"""
import hashlib
import json
from pathlib import Path
import pefile


def main():
    reports = {}
    for path in sorted(Path('evidence/asset-review').glob('*.json')):
        info = json.loads(path.read_text())
        if not isinstance(info, dict) or 'client' not in info:
            continue
        version = info['version']
        pe = pefile.PE(info['client'])
        rows = []
        out = Path('work/asset-review', version, 'client-resources')
        out.mkdir(parents=True, exist_ok=True)

        def walk(directory, ids):
            for entry in directory.entries:
                key = str(entry.name) if entry.name is not None else str(entry.id)
                parts = ids + [key]
                if hasattr(entry, 'directory'):
                    walk(entry.directory, parts)
                else:
                    data = pe.get_data(entry.data.struct.OffsetToData, entry.data.struct.Size)
                    assert len(data) == entry.data.struct.Size
                    dest = out / f'{len(rows):04d}.bin'
                    dest.write_bytes(data)
                    rows.append({'resource': '/'.join(parts), 'bytes': len(data),
                                 'sha256': hashlib.sha256(data).hexdigest(), 'path': dest.as_posix()})
        if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
            walk(pe.DIRECTORY_ENTRY_RESOURCE, [])
        reports[version] = rows
    baseline = {r['sha256'] for r in reports['2.9.2']}
    for version, rows in reports.items():
        for row in rows:
            row['content_in_2.9.2'] = row['sha256'] in baseline
        print(version, len(rows), 'resources;', sum(not r['content_in_2.9.2'] for r in rows), 'different/absent')
    Path('evidence/asset-review/client-resources.json').write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    main()
