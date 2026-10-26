"""Verify known packages and compare pristine decoded assets with 2.9.2.

Run from the repository root: python -I tools/compare_version_assets.py
Never executes downloaded binaries or writes to the active game directory.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoapack

ROOT = Path('work/asset-review')
EVIDENCE = Path('evidence/asset-review')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest = json.loads(Path('manifest/downloads.json').read_text())['downloads']
    key = aoapack.builtin_key('work/2.7.1/members/15_AOACLIENT.EXE')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    reports = {}
    for spec in manifest:
        version = spec['runtime_version']
        candidates = list(Path('originals', version).glob('*.exe'))
        candidates += list(Path('builds/asset-review', version).glob('*.exe'))
        source = next(p for p in candidates if sha(p.read_bytes()) == spec['sha256'])
        assert source.stat().st_size == spec['bytes'], source
        out = ROOT / version
        members = out / 'members'
        members.mkdir(parents=True, exist_ok=True)
        report = {'version': version, 'source': source.as_posix(),
                  'sha256': sha(source.read_bytes()), 'bytes': source.stat().st_size,
                  'source_url': spec.get('direct_url', spec.get('catalog_url')),
                  'kind': spec['kind'], 'members': [], 'archives': [], 'assets': []}
        if spec['kind'] == 'replacement_client_only':
            report['client'] = source.as_posix()
            report['client_sha256'] = sha(source.read_bytes())
            assert report['client_sha256'] == spec['client_sha256']
            reports[version] = report
            continue
        with zipfile.ZipFile(source) as zf:
            for i, zi in enumerate(zf.infolist()):
                data = zf.read(zi)  # ZipFile validates each member CRC.
                name = zi.filename.replace('\\', '/').split('/')[-1].upper()
                dest = members / f'{i:02d}_{name}'
                dest.write_bytes(data)
                report['members'].append({'name': name, 'bytes': len(data),
                                          'sha256': sha(data), 'path': dest.as_posix()})
                if name == 'AOACLIENT.EXE':
                    assert sha(data) == spec['client_sha256']
                    report['client'] = dest.as_posix()
                    report['client_sha256'] = sha(data)
        for member in report['members']:
            if Path(member['name']).suffix not in ('.AOA', '.ODB'):
                continue
            d, k, fmt, entries = aoapack.read_archive(member['path'], key)
            assert fmt == 0x0402, (version, member['name'], fmt)
            assert 260 + 280 * len(entries) <= len(d)
            archive = Path(member['name']).stem
            folder = out / 'assets' / archive
            folder.mkdir(parents=True, exist_ok=True)
            records = []
            for entry in entries:
                assert entry['offset'] >= 260 + 280 * len(entries)
                assert entry['offset'] + entry['size'] <= len(d)
                raw, info = aoapack.entry_bytes(d, k, key, entry)
                assert info.get('crc_ok') is True, (version, archive, entry['name'])
                dest = folder / aoapack.safe_name(entry['index'], entry['name'])
                dest.write_bytes(raw)
                record = {**entry, **info, 'out_bytes': len(raw), 'sha256': sha(raw),
                          'extracted_to': dest.as_posix()}
                records.append(record)
                report['assets'].append({'archive': archive, 'name': entry['name'],
                                         'bytes': len(raw), 'sha256': sha(raw),
                                         'path': dest.as_posix()})
            index = {'archive': member['path'], 'version': hex(fmt), 'entries': records,
                     'count': len(records), 'crc_checked': len(records), 'crc_ok': len(records)}
            (folder / '_index.json').write_text(json.dumps(index, indent=2))
            report['archives'].append({k: v for k, v in index.items() if k != 'entries'})
        reports[version] = report
        print(version, len(report['members']), 'members;', len(report['assets']), 'CRC-valid assets', flush=True)
    baseline = reports['2.9.2']['assets']
    by_name = {(r['archive'].casefold(), r['name'].casefold()): r for r in baseline}
    by_hash = collections.defaultdict(list)
    for r in baseline:
        by_hash[r['sha256']].append(r['archive'] + '/' + r['name'])
    summary = {}
    for version, report in reports.items():
        for r in report['assets']:
            match = by_name.get((r['archive'].casefold(), r['name'].casefold()))
            r['comparison'] = ('identical' if match and match['sha256'] == r['sha256'] else
                               'renamed_identical' if r['sha256'] in by_hash else
                               'changed' if match else 'absent_name_and_content')
            if r['sha256'] in by_hash:
                r['baseline_content_matches'] = by_hash[r['sha256']]
        summary[version] = {'installer_members': len(report['members']),
                            'decoded_assets': len(report['assets']),
                            'comparison': dict(collections.Counter(r['comparison'] for r in report['assets']))}
        (EVIDENCE / f'{version}.json').write_text(json.dumps(report, indent=2) + '\n')
    (EVIDENCE / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
