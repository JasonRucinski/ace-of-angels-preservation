"""Inventory/extract PE resources from the clients verified by compare_version_assets.

python -I tools/compare_client_resources.py [--evidence PATH]
Raw resource payloads are retained locally; no executable is run.
Paths are resolved from the repository root, whatever the working directory.
The report goes to work/evidence/asset-review/client-resources.json unless
--evidence names the file (the committed copy is evidence/asset-review/...).
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import pefile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cli_util  # noqa: E402

EVIDENCE = 'evidence/asset-review/client-resources.json'


def main(argv=None):
    ap = cli_util.parser(__doc__)
    ap.add_argument('--reports', type=Path, default=Path('evidence/asset-review'),
                    help='folder of compare_version_assets.py reports, repo-relative '
                         '(default: %(default)s; a fresh run writes work/evidence/asset-review)')
    cli_util.add_evidence_option(ap, EVIDENCE)
    a = ap.parse_args(argv)
    target = a.evidence.resolve() if a.evidence else None
    # The reports below record repo-relative paths; keep them that way.
    os.chdir(cli_util.ROOT)
    reports = {}
    for path in sorted(a.reports.glob('*.json')):
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
    if '2.9.2' not in reports:
        sys.exit('compare_client_resources: no 2.9.2 client report in evidence/asset-review '
                 '(run compare_version_assets.py first)')
    baseline = {r['sha256'] for r in reports['2.9.2']}
    for version, rows in reports.items():
        for row in rows:
            row['content_in_2.9.2'] = row['sha256'] in baseline
        print(version, len(rows), 'resources;', sum(not r['content_in_2.9.2'] for r in rows), 'different/absent')
    cli_util.evidence_target(target, EVIDENCE).write_text(json.dumps(reports, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(cli_util.run(main))
