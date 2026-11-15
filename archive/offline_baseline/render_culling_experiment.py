"""Reversible culling correction restricted to the isolated offline baseline (archived).

Superseded by visibility-math-v1. Its bytes (code(), regions()) stay in
aoa/client/experiments/render_culling_experiment.py for aoa.emulation.render_pipeline.
"""
import argparse
import json

from aoa.client import prepare
from aoa.client.experiments.render_culling_experiment import regions
from archive.offline_baseline import render_clock_experiment as clock
from aoa.paths import ROOT


def configure(data, enabled=True):
    original = bytearray(data)
    states = []
    for offset, old, new in regions():
        actual = data[offset:offset+len(old)]
        if actual not in (old,new):
            raise ValueError('unexpected culling code or cave')
        states.append(actual == new)
        original[offset:offset+len(old)] = old
    if len(set(states)) != 1:
        raise ValueError('partial culling patch')
    # Clock normalization verifies the complete known image, while preserving
    # whether the caller currently has the clock experiment enabled.
    clock.configure(bytes(original),False)
    result = bytearray(original)
    if enabled:
        for offset, old, new in regions():
            result[offset:offset+len(old)] = new
    return bytes(result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--undo',action='store_true')
    args = parser.parse_args(argv)
    exe = ROOT/'game/offline-baseline-2.9.2/AOACLIENT.EXE'
    source = exe.read_bytes()
    original = configure(source,False)
    backup = exe.with_suffix('.EXE.before-culling')
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError('culling backup does not match normalized image')
    if not backup.exists():
        prepare.atomic_write(backup,original)
    result = configure(source,not args.undo)
    if result != source:
        prepare.atomic_write(exe,result)
    if exe.read_bytes() != result:
        raise ValueError('culling patch verification failed')
    record = {'enabled':not args.undo,'sha256':prepare.sha(result),
              'undo_sha256':prepare.sha(original),'scope':'isolated offline baseline; full-frame validation pending'}
    prepare.atomic_write(exe.parent/'_render_culling.json',(json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps(record,indent=2))


if __name__ == '__main__':
    main()
