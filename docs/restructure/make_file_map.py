"""Author the canonical file map (architect's decisions) and check it covers tools/ exactly."""
import os, sys
root = sys.argv[1]
M = {}
def put(dest, *names):
    for n in names:
        src, _, new = n.partition('=')
        assert src not in M, src
        M[src] = dest.rstrip('/') + '/' + (new or src) + '.py' if not dest.endswith('.py') else dest
F = 'aoa/formats'
put(F, 'aoapack', 'aoacrypt', 'gob2obj=gob', 'scene2obj=scene', 'sco_dump=sco', 'decode_trn=trn',
    'decode_scenario=scenario', 'decode_legacy_layout=legacy_layout', 'wise_extract=wise')
put('aoa/protocol', 'aoanet=codec', 'relay_motion=motion', 'turret_groups')
put('aoa/maps', 'navigation_buoys=navigation', 'make_map', 'make_object', 'map_viewer', 'export_assets',
    'export_legacy_models', 'render_obj', 'render_map_previews', 'audit_object_lod=lod',
    'audit_turret_groups=turret_hierarchy', 'audit_warp_gates=warp_routes', 'audit_arena1a=arena1a_audit',
    'check_arena_geometry=arena_geometry')
put('aoa/client', 'prepare_client=prepare', 'patch_client=base', 'texture_pack', 'build_texture_pack',
    'make_install', 'install_wrapper')
put('aoa/client/patches', 'archive_terminator', 'asteroid_render', 'cursor_warp', 'explicit_protection',
    'frame_clock', 'local_station=station_host', 'menu_aspect', 'object_persistence', 'online_terrain',
    'own_ship_menu', 'own_ship_model', 'physics_timestep', 'powerup_pickup', 'solid_world_render',
    'station_detail', 'texture32', 'third_person', 'visibility_fix', 'world_detail')
put('aoa/host', 'station_stub=server', 'station_runtime=runtime', 'reliable_window=delivery', 'host_ops=ops',
    'net_impair', 'vessel_combat', 'make_vessel_combat', 'turret_trial', 'warp_trial', 'dedicated_host=dedicated')
put('aoa/launchers', 'host_control', 'client_launcher')
put('aoa/research', 'fetch', 'fetch_known_builds', 'ia_disc_find', 'ia_fulltext_search', 'ia_fulltext_context',
    'iso_stream_extract', 'rar_img2iso', 'wayback_builds', 'restore_web_archive', 'aoa_version=version',
    'version_probe', 'compare_version_assets')
put('aoa/analysis', 'pe_util', 'explore', 'match_funcs', 'dispatch_table', 'message_table', 'packet_sizes',
    'send_sites', 'dialogs')
put('aoa/emulation', 'emulate_codec=emu', 'emulate_archive_terminator=check_archive_terminator',
    'emulate_client_extensions=check_client_extensions', 'emulate_motion_state=check_motion_state',
    'emulate_movement=check_movement', 'emulate_ordered_events=check_ordered_events',
    'emulate_reliable_history=check_reliable_history', 'emulate_station_aliases=check_station_aliases',
    'emulate_station_request=check_station_request', 'emulate_terrain_nodes=check_terrain_nodes',
    'emulate_warp_trial=warp_trial', 'audit_render_pipeline=render_pipeline')
put('aoa/live', 'inspect_arena=arena', 'measure_frame_pacing=frame_pacing', 'sample_rendering', 'crashdbg',
    'verify_navigation_buoys', 'verify_turret_trial', 'verify_warp_trial')
put('archive/analysis', 'pe_facts', 'server_senders', 'offline_refs', 'config_records', 'gun_table', 'inventory',
    'emulate_cipher', 'audit_arena1a_rebuild', 'audit_level_data', 'audit_map_nodes', 'arena_inventory',
    'compare_client_resources')
put('archive/offline_baseline', 'prepare_offline_baseline', 'seed_offline_velocity', 'compare_render_clocks',
    'test_render_clock_experiment', 'test_render_motion')
put('aoa/client/experiments', 'render_clock_experiment', 'render_culling_experiment')
put('tools', 'verify_local')
put('aoa', 'cli_util=cli')
put('aoa/research', 'polite_http=http')
have = sorted(f[:-3] for f in os.listdir(root + '/tools') if f.endswith('.py'))
for t in have:
    if t.startswith('test_') and t not in M:
        M[t] = 'tests/' + t + '.py'
missing = [h for h in have if h not in M]
extra = [m for m in M if m not in have]
assert not missing and not extra, (missing, extra)
dests = list(M.values()); assert len(dests) == len(set(dests))
NOTES = {
 'station_stub': 'Phase 2: becomes ArenaServer class, then splits (sessions, combat, match, objects, protocol builders)',
 'station_runtime': 'Phase 2: HostConfig + defaults table; eventlog/transport split',
 'online_terrain': 'Phase 2: MAPS registry moves to aoa/maps/registry.py; cave stays here',
 'emulate_codec': 'Phase 2: Emu library stays; 2.7.1-only CLI goes to archive/',
 'audit_turret_groups': 'used by the server (hierarchy); Phase 2 drops its audit CLI to archive/',
 'audit_warp_gates': 'used by the server (routes); Phase 2 drops its audit CLI to archive/ and breaks the import cycle',
 'audit_arena1a': 'kept only because check_terrain_nodes imports it',
 'audit_render_pipeline': 'library for test_render_culling/test_visibility_fix; Phase 2 removes its dependency on the archived culling experiment',
 'audit_object_lod': 'library for four patch tests',
 'patch_client': 'Phase 2: base step + asm helpers; PRISTINE hash moves to aoa/builds.py',
 'prepare_client': 'Phase 2: registry-driven engine',
 'local_station': 'Phase 2: constants only; legacy CLI removed',
 'host_control': 'Phase 3: replaced by aoa/launchers/host_app.py on the shared core',
 'client_launcher': 'Phase 3: replaced by aoa/launchers/play_app.py on the shared core',
 'dedicated_host': 'Phase 2/3: thin front-end on the shared supervisor',
 'fetch_known_builds': 'Phase 2: merged into manifest-driven fetch',
 'version_probe': 'Phase 2: merged into version',
 'pe_util': 'Phase 2: stdlib PE mapper split to aoa/formats/pe.py',
 'test_render_culling': 'Phase 2: visibility parts merge into test_visibility_fix, rest archived',
 'render_culling_experiment': 'superseded by visibility_fix; Phase 2 removes its importers (render_pipeline, test_visibility_fix, test_render_culling) and archives it',
 'render_clock_experiment': 'byte-identical to frame_clock; Phase 2 repoints its importers (test_frame_clock, test_render_culling) and archives it',
}
SHIM = set('''prepare_client station_stub host_control client_launcher dedicated_host map_viewer make_map make_object
build_texture_pack texture_pack install_wrapper make_install fetch_known_builds fetch aoapack export_assets gob2obj
scene2obj render_obj aoa_version restore_web_archive wayback_builds ia_disc_find'''.split())
with open(sys.argv[2], 'w') as f:
    f.write('old_path\tnew_path\tkeeps_tools_shim\tnote\n')
    for k in sorted(M, key=lambda k: (M[k], k)):
        f.write(f"tools/{k}.py\t{M[k]}\t{'yes' if k in SHIM else ''}\t{NOTES.get(k, '')}\n")
    for old, new, note in [
        ('tools/reel/', 'aoa/reel/', 'whole folder, incl. shots.json and edit.json'),
        ('tools/setup_game.ps1', 'tools/setup_game.ps1', 'stays; Phase 3 wizard supersedes it (kept as fallback)'),
        ('tools/register_activeskin.ps1', 'tools/register_activeskin.ps1', 'stays; called by the wizard'),
        ('tools/client_login.ps1', 'tools/dev/client_login.ps1', 'test/reel driver, not player-facing'),
        ('tools/start_lan_dogfight.ps1', 'tools/start_lan_dogfight.ps1', 'Phase 3: becomes a two-line wrapper around the headless host'),
        ('tools/client_launcher.cmd', 'Play.cmd', 'Phase 3: root-level double-click stub; old path kept as a forwarder'),
        ('tools/host_control.cmd', 'Host.cmd', 'Phase 3: root-level double-click stub; old path kept as a forwarder'),
        ('tools/README.md', 'docs/reference/tools.md', 'Phase 4: generated index')]:
        f.write(f'{old}\t{new}\t\t{note}\n')
print(len(M), 'python files mapped;', sum(1 for v in M.values() if v.startswith('archive/')), 'archived;', sum(1 for v in M.values() if v.startswith('tests/')), 'tests;', len(SHIM), 'shims')
