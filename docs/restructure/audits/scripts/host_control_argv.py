import sys, itertools, io, contextlib
sys.path.insert(0, '/home/user/ace-of-angels-preservation/tools')
from pathlib import Path
import host_control as hc, station_runtime as sr, online_terrain
FAKE = Path(sys.argv[1])
hc.ROOT = FAKE; hc.WORK = FAKE/'work/host'
fails = {}
n=0
for mode, terrain, m, buoys, turret, warp, ts in itertools.product(hc.MODES, (True, False), online_terrain.MAP_NAMES,
        (True, False), (True, False), (True, False), (0, 4, 20)):
    addr = {'This PC only':'127.0.0.1','LAN':'192.168.1.5','VPN (internet)':'100.101.102.103'}[mode]
    s = dict(hc.DEFAULTS, mode=mode, address=addr, terrain=terrain, map=m, navigation_buoys=buoys,
             turret_trial=turret, warp_trial=warp, target_ships=ts, game=str(FAKE/'game/2.9.2'), max_players=8)
    # GUI clears unavailable options
    for k, r in hc.node_availability(s).items():
        if r: s[k] = False
    argv = hc.server_args(s)[1:]
    n+=1
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            sr.parse_args(argv)
    except SystemExit:
        msg = err.getvalue().strip().splitlines()[-1]
        fails.setdefault(msg, []).append((mode, terrain, m, buoys, turret, warp, ts))
print(n, 'combos')
for k, v in fails.items(): print(len(v), k, v[:3])
