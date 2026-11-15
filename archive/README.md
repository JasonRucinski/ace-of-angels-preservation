# Archive

One-off scripts whose results are already committed, kept so that every
result can be reproduced. Nothing in `aoa/` imports them (the layering test,
`tests/test_layering.py`, checks this); `tests/test_cli_help.py` still runs
each one's `--help`, and imports `inventory` for one behaviour check.

Run one through the module runner, from the repository root:

```
python -I tools/run.py archive.analysis.inventory --help
```

They need the same inputs as when they were written (the original client
executables, `work/` exports), which this repository does not contain.

## analysis/

| Script | Frozen output |
|---|---|
| `arena_inventory.py` | `evidence/2.9.2/arena_inventory.json` |
| `audit_arena1a.py` | `evidence/2.9.2/arena1a_audit_20261021.json` (its dispatch table stays in `aoa/maps/arena1a_audit.py`) |
| `audit_arena1a_rebuild.py` | `evidence/2.9.2/arena1a_rebuild_20261026.json` |
| `audit_level_data.py` | `evidence/asset-review/level-data.json` |
| `audit_map_nodes.py` | `evidence/2.9.2/map_nodes_20261026.json` |
| `audit_turret_groups.py` | `evidence/2.9.2/turret_groups_20261026.json` (`hierarchy()` stays in `aoa/maps/turret_hierarchy.py`) |
| `audit_warp_gates.py` | `evidence/2.9.2/warp_gates_20261026.json` (`routes()` stays in `aoa/maps/warp_routes.py`) |
| `compare_client_resources.py` | `evidence/asset-review/client-resources.json` |
| `config_records.py` | `evidence/2.7.1/config_records.{json,txt}`, `evidence/2.9.2/config_records.{json,txt}` |
| `emulate_cipher.py` | `evidence/2.7.1/cipher_emulation.json`, `evidence/2.9.2/cipher_emulation.json` |
| `gun_table.py` | `evidence/2.9.2/gun_table.json` (read by `aoa/host/make_vessel_combat.py`) |
| `inventory.py` | `evidence/2.7.1/installer_inventory.json`, `evidence/2.9.2/installer_inventory.json` |
| `offline_refs.py` | `evidence/2.7.1/offline_refs.json`, `evidence/2.7.1/world_offline_refs.json` |
| `pe_facts.py` | `evidence/2.7.1/pe_facts.json`, `evidence/2.9.2/pe_facts.json` (read by `tests/test_patch_layout.py`) |
| `server_senders.py` | `evidence/2.7.1/server_senders.json` |

## offline_baseline/

The offline rendering experiment, described in
[docs/offline-rendering-baseline.md](../docs/offline-rendering-baseline.md)
and [docs/render-pipeline-audit.md](../docs/render-pipeline-audit.md).

| Script | Frozen output |
|---|---|
| `compare_render_clocks.py` | `evidence/2.9.2/render_clock_comparison.json` |
| `prepare_offline_baseline.py` | none: prepares a local offline client copy |
| `seed_offline_velocity.py` | none: live fixture for a running offline client |
| `test_render_clock_experiment.py`, `test_render_motion.py` | none: suites, run with `python -I tools/test.py --tier all` (need the game) |
