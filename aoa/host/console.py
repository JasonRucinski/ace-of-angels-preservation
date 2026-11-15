"""The host's operator side: the player table, the status file contents and console commands.

Each function takes the running ArenaServer; aoa/host/ops.py holds the
status file writer and the console reader they use.
"""
import math
import os
import time

from aoa.host import ops, warp_trial
from aoa.host.defaults import ARENA_JOINS
from aoa.protocol import codec
from aoa.protocol.arena import arena_message


def player_rows(server, now):
    players = []
    for peer, slot in sorted(server.arena_players.items(), key=lambda item: item[1]):
        entry = server.meter.endpoints.get(peer, {"rx_bytes": 0, "tx_bytes": 0})
        then, rx, tx = server.traffic_mark.get(peer, (server.started, 0, 0))
        elapsed = max(now - then, 1e-3)
        kills, died, _, _ = server.player_stats(peer)
        players.append({"slot": slot, "pilot": server.arena_pilots.get(peer) or f"LocalPilot{slot}",
                        "loaded": peer in server.ping_due, "kills": kills, "deaths": died,
                        "ping_ms": round(server.arena_rtt[peer]) if peer in server.arena_rtt else None,
                        "in_kbps": round((entry["rx_bytes"] - rx) * 8 / elapsed / 1000, 1),
                        "out_kbps": round((entry["tx_bytes"] - tx) * 8 / elapsed / 1000, 1),
                        "idle_s": round(now - server.arena_heard.get(peer, now), 1)})
    return players


def status(server, now):
    players = player_rows(server, now)
    for peer in server.arena_players:
        entry = server.meter.endpoints.get(peer, {"rx_bytes": 0, "tx_bytes": 0})
        server.traffic_mark[peer] = (now, entry["rx_bytes"], entry["tx_bytes"])
    return {"schema": 1, "pid": os.getpid(), "profile": server.args.profile, "mode": server.mode, "map": server.args.map,
            "uptime_s": round(now - server.started),
            "match": server.match.number, "players": players, "max_players": server.args.max_players,
            "arena_joins_used": server.next_player_slot - 1, "arena_joins_limit": ARENA_JOINS,
            "station_sessions": len(server.station.peers), "station_admissions_used": server.station.next_id - 1,
            "station_admissions_limit": server.station.CAPACITY, "banned_ips": len(server.banned_ips),
            "sustained_delivery": server.args.sustained_delivery,
            "navigation_buoys": len(server.buoys),
            "warp_trial": {"objects": len(server.warp),
                           "routes": [{"gate": g['name'], "destination_node": g['destination_node'],
                                       "tag": hex(warp_trial.tag(g))} for g in server.warp_gates],
                           "model": "WarpGate / WarpA",
                           "orientation_restored": False, "host_authorized_transit": False} if server.warp else None,
            "turret_trial": {"objects": len(server.trial) // 2, "enabled": False,
                             "model_assignment": "provisional TurretA", "orientation_restored": False} if server.trial else None,
            "powerups": None if server.powerups is None else {"placed": len(server.powerups.items), "taken": server.powerups.taken},
            "target_ships": None if server.targets is None else {"placed": len(server.targets.ships),
                                                          "destroyed": server.targets.destroyed},
            "reliable_pending": len(server.removals.pending), "events_expired": getattr(server.removals, "expired", 0),
            "traffic": dict(server.meter.totals(), dropped_in=server.meter.dropped_in, dropped_out=server.meter.dropped_out),
            "impairment": server.impair_out.describe() if server.impair_out.active else None,
            "lifecycle": {"managed": server.args.managed_session, "next_map": server.args.next_map,
                          "kill_limit": server.args.kill_limit, "time_limit_s": server.args.time_limit,
                          "match_elapsed_s": None if server.match.started is None else round(now - server.match.started),
                          "restart_reason": server.restart_reason,
                          "restart_in_s": None if server.restart_due is None else max(0, math.ceil(server.restart_due - now))}}


def remove(server, slot, ban):
    peer = next((peer for peer, taken in server.arena_players.items() if taken == slot), None)
    if peer is None:
        return f"no arena player in slot {slot}"
    server.arena.sendto(codec.encode(*arena_message("You were removed by the host"), server.key), peer)
    if ban:
        server.banned_ips.add(peer[0])
    server.depart(peer, "banned by host" if ban else "kicked by host")
    server.station_depart(peer, "banned by host" if ban else "kicked by host")
    server.log({"t": round(time.time(), 3), "event": "host_" + ("ban" if ban else "kick"), "slot": slot})
    return f"{'banned' if ban else 'kicked'} slot {slot}"


def command(server, line, now):
    command, value = ops.parse_command(line)
    if command is None:
        return value
    if command == "help":
        return ops.HELP
    if command == "status":
        return ops.player_table(player_rows(server, now))
    if command == "end":
        if not server.arena_players or server.match.started is None:
            return "no match in progress"
        server.end_match("ended by host", now)
        return "match ended"
    if command in ("say", "quit"):
        text = value if command == "say" else "Host is shutting down"
        for peer in list(server.arena_players) if server.args.arena else []:
            server.arena.sendto(codec.encode(*arena_message(text), server.key), peer)
        server.log({"t": round(time.time(), 3), "event": "host_" + command})
        return ops.QUIT if command == "quit" else f"said to {len(server.arena_players)} player(s)"
    return remove(server, value, command == "ban")
