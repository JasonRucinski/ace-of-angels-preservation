"""Which suites run where: the CI list, the local gate list and the emulation checks.

Suites are named by module: a bare name is tests/<name>.py, a dotted name is
that module (the archived offline-baseline suites).
"""
# Game-free: protocol, server, relay and host checks against synthetic
# clients on loopback, the golden snapshots of client patch bytes and server
# command lines, --help of every command, the import and layering rules.
CI = (
    "test_network_bounds", "test_relay_motion", "test_relay_recovery",
    "test_station_runtime", "test_station_sessions", "test_station_stub",
    "test_guest_admission", "test_combat_delivery", "test_client_extensions",
    "test_lan_dogfight", "test_internet_play", "test_powerups",
    "test_target_ships", "test_host_control", "test_prepare_client", "test_dedicated_host",
    "test_client_launcher", "test_make_map", "test_make_object",
    "test_patch_layout", "test_prepare_outputs", "test_host_argv", "test_reel",
    "test_cli_help", "test_polite_http", "test_install_wrapper", "test_make_vessel_combat",
    "test_imports", "test_layering", "test_builds", "test_pe", "test_map_registry", "test_host_data",
    "test_host_config", "test_supervisor", "test_arena_server", "test_launcher_logic",
    "test_launcher_windows",
    "test_research", "test_installer", "test_emulation", "test_procmem", "test_evidence_index",
    "test_tools_index", "test_site", "test_doc_links", "test_doc_tables",
    "test_doc_commands",
    # Client suites with game-free halves: cave emulation and code checks (unicorn).
    "test_frame_clock", "test_menu_aspect", "test_visibility_fix",
)
# The texture pack builder is a Windows player tool that needs Pillow from
# requirements-texture.txt, which only the Windows CI job installs.
CI_WINDOWS = ("test_build_texture_pack",)

# The local gate (tools/verify_local.py): needs the user's original 2.9.2
# executable and assets, requirements-research.txt and requirements-texture.txt.
# A skip fails the gate.
LOCAL = (
    "test_network_bounds", "test_relay_motion", "test_prepare_client",
    "test_client_launcher",
    "test_station_runtime", "test_station_sessions", "test_guest_admission",
    "test_relay_recovery", "test_station_stub", "test_combat_delivery",
    "test_client_extensions", "test_lan_dogfight", "test_scene_nodes",
    "test_online_terrain", "test_host_control", "test_asteroid_render", "test_solid_world_render",
    "test_station_detail", "test_world_detail", "test_object_persistence",
    "test_object_persistence_pipeline", "test_internet_play", "test_cursor_warp",
    "test_texture32", "test_aoapack_write", "test_frame_clock",
    "test_visibility_fix", "test_third_person", "test_powerups",
    "test_powerup_pickup", "test_target_ships", "test_build_texture_pack",
    # Suites that ran nowhere before phase 1; they need the game or its export.
    "test_menu_aspect", "test_navigation_buoys", "test_object_lod", "test_physics_timestep",
    "test_turret_groups", "test_turret_trial", "test_warp_headless", "test_warp_trial",
)

# Suites of the archived offline-baseline experiment; only `--tier all` runs them.
ARCHIVED = (
    "archive.offline_baseline.test_render_clock_experiment",
    "archive.offline_baseline.test_render_culling",
    "archive.offline_baseline.test_render_motion",
)

# Original-code emulation checks of the local gate: each takes CLIENT.EXE.orig and OUT.json.
EMULATION = (
    "aoa.emulation.check_station_request", "aoa.emulation.check_station_aliases",
    "aoa.emulation.check_reliable_history", "aoa.emulation.check_movement",
    "aoa.emulation.check_motion_state", "aoa.emulation.check_archive_terminator",
    "aoa.emulation.check_client_extensions", "aoa.emulation.check_ordered_events",
    "aoa.emulation.check_terrain_nodes",
)
