"""Byte-level guard checks; pass a known stability-patched 2.9.2 EXE.

Reads the file without modifying it. Instruction-level checks are in
emulate_movement.py; these verify supported inputs and reversible edits.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from physics_timestep import configure, SITE_OFFSET, CAVE_OFFSET, guard_code
from local_station import OFFSET, ORIGINAL, LOCAL


def main():
    baseline = configure(Path(sys.argv[1]).read_bytes(), undo=True)
    for hostname in (ORIGINAL, LOCAL):
        original = baseline[:OFFSET] + hostname + baseline[OFFSET + len(hostname):]
        patched = configure(original)
        assert configure(patched) == patched
        assert configure(patched, undo=True) == original
        assert configure(original, undo=True) == original
        assert patched[OFFSET:OFFSET + len(hostname)] == hostname
        for offset in (SITE_OFFSET, CAVE_OFFSET, 0x1000):
            altered = bytearray(patched)
            altered[offset] ^= 1
            try:
                configure(bytes(altered))
            except ValueError:
                pass
            else:
                raise AssertionError(f"accepted modified input at {offset:#x}")
        allowed = set(range(SITE_OFFSET, SITE_OFFSET + 6))
        allowed.update(range(CAVE_OFFSET, CAVE_OFFSET + len(guard_code())))
        assert len(original) == len(patched)
        assert all(i in allowed for i, (a, b) in enumerate(zip(original, patched)) if a != b)
    print("Both hostname variants: exact undo, idempotence, bounded edits and corruption rejection passed")


if __name__ == "__main__":
    main()
