"""Inventory filled and unfilled nodes in every recovered 2.9.2 layout.

python -I tools/audit_map_nodes.py
Full positions stay in ignored work/; evidence contains only counts and names.
This audits assets, not gameplay implementation or live-client acceptance.
"""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene2obj

ROOT = Path(__file__).resolve().parents[1]


def classify(node, objects):
    category = node['category']
    if 'nested_layout' in node:
        return 'expanded_layout'
    if category in (1, 3):
        return 'turret_marker_no_gameplay'
    if category == 5:
        return 'flag_marker_no_gameplay'
    if category == 6:
        return 'warp_marker_links_unverified'
    if category == 7:
        return 'safe_zone'
    if category == 4:
        return 'navigation_marker'
    if category != 9:
        return 'other_category'
    token = re.sub(r'[0-9]+$', '', node['name'].split()[0]).casefold()
    if any(key.startswith(token) for key in objects):
        return 'object_asset_available'
    if token.startswith(('za', 'zmissile', 'zrepair', 'zshield')):
        return 'service_marker_definition_missing'
    if token.startswith(('group', 'dummy', 'warptgt')) or token == 'home':
        return 'helper_marker'
    return 'unresolved_reference'


def main():
    source = ROOT / 'work/2.9.2/export/AOAOBJECTS'
    out = ROOT / 'work/map-node-review'
    out.mkdir(parents=True, exist_ok=True)
    objects = scene2obj.sco_models(source)
    layouts, ordered = scene2obj.layout_catalog(source)
    if not layouts or not ordered:
        raise ValueError('requires exported assets with complete _export.json archive order')
    report = {'scope': 'Static asset resolution; no gameplay or live-client changes',
              'prefix_evidence': ['0x496187 trailing digits', '0x4CDD30 first graphics match',
                                  '0x5270C0 query-length case-insensitive comparison'],
              'maps': {}}
    for path in layouts:
        nodes = list(scene2obj.expanded_nodes(source, path.stem, True))
        for node in nodes:
            node['resolution'] = classify(node, objects)
        (out / (path.stem + '_nodes.json')).write_text(json.dumps(nodes, indent=2) + '\n', encoding='utf-8')
        recovered = [n for n in nodes if n.get('nested_layout') and
                     n['layout_lookup'].casefold() != n['nested_layout'].casefold()]
        report['maps'][path.stem] = {
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'root_records': len(scene2obj.read_nodes(path.read_bytes())),
            'expanded_records': len(nodes),
            'resolution_counts': dict(collections.Counter(n['resolution'] for n in nodes)),
            'recovered_prefix_references': [{'node': n['name'], 'layout': n['nested_layout']} for n in recovered],
            'unresolved_references': sorted({n['name'] for n in nodes if n['resolution'] == 'unresolved_reference'}),
        }
    target = ROOT / 'evidence/2.9.2/map_nodes_20261026.json'
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
