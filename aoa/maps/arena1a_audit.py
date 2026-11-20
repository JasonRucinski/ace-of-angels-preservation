"""The pinned terrain-creation dispatch of the 2.9.2 client, from the Arena1a audit.

EXPECTED_DISPATCH is the ten-entry category jump table at 0x496790, as
recovered by archive/analysis/audit_arena1a.py (evidence/2.9.2/
arena1a_audit_20261021.json). aoa/emulation/check_terrain_nodes.py checks
the original client against it.
"""
EXPECTED_DISPATCH = [0x4964F8, 0x496423, 0x4964F8, 0x496280, 0x4964F8,
                     0x4962F7, 0x4963E4, 0x4964F8, 0x496141, 0x4964F8]
