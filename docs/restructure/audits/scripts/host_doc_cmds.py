import sys, io, contextlib, shlex
sys.path.insert(0, '/home/user/ace-of-angels-preservation/tools')
import station_runtime as sr
K='game/2.9.2/SCRTY.BIN'
cmds = {
 'local-server.md:17': f'{K} work/local-relay.jsonl --profile local-relay',
 'local-server.md:30': f'{K} work/local-guests.jsonl --profile local-guests',
 'local-server.md:41': f'{K} work/local-relay.jsonl --profile local-relay --print-config',
 'local-server.md:56': f'{K} work/observe.jsonl --seconds 60',
 'local-server.md:57': f'{K} work/flight.jsonl --ack --arena --tcp 5034 --experimental-flight --seconds 120',
 'lan-dogfight.md:69': f'{K} work/lan-dogfight.jsonl --profile lan-dogfight --bind-address 192.168.0.61 --max-players 2',
 'local-server.md:67 missile': f'{K} l --profile local-relay --spawn-axis z --spawn-spacing 6000',
 'local-server.md:70 probe': f'{K} l --ack --arena --experimental-flight --max-players 1 --experimental-protection-probe',
 'local-server.md:68 teams': f'{K} l --profile local-relay --experimental-teams',
 'local-server.md:69 relcombat': f'{K} l --profile local-relay --experimental-reliable-combat',
 'ps1 LAN default': f'{K} work/lan-dogfight.jsonl --profile lan-dogfight --bind-address 192.168.0.61 --max-players 2 --map CTF_arena --backdrop spacebkgd3 --console --status-file work/lan-dogfight-status.json',
 'ps1 VPN -MaxPlayers 4': f'{K} work/vpn-dogfight.jsonl --profile vpn-dogfight --bind-address 100.101.102.103 --max-players 4 --map CTF_arena --backdrop spacebkgd3 --console --status-file s.json',
 'ps1 Arena1a -Terrain': f'{K} w --profile lan-dogfight --bind-address 192.168.0.61 --map Arena1a --experimental-terrain --console --status-file s.json',
 'ps1 impair': f'{K} w --profile lan-dogfight --bind-address 192.168.0.61 --impair-rtt-ms 80 --impair-jitter-ms 0 --impair-loss 1',
 'map_viewer serve CTF_arena': f'{K} w --profile local-relay --map CTF_arena --backdrop spacebkgd3 --experimental-terrain',
 'map_viewer serve JRMAP spawn': f'{K} w --profile local-relay --map JRMAP --backdrop spacebkgd3 --experimental-terrain --spawn-at 1 2 3 --seconds 5',
 'lan-dogfight kill-limit 2 (148)': f'{K} w --profile lan-dogfight --bind-address 192.168.0.61 --kill-limit 2',
 'lan sustained (132)': f'{K} w --profile lan-dogfight --bind-address 192.168.0.61 --sustained-delivery',
 'diagnostic + console': f'{K} w --console --status-file s.json',
 'dedicated default bind': f'{K} w --profile vpn-dogfight --bind-address 127.0.0.1',
}
for name, c in cmds.items():
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            a = sr.parse_args(shlex.split(c))
        print('OK  ', name, f"ack={a.ack} arena={a.arena} relay={a.experimental_relay} tcp={a.tcp} sustained={a.sustained_delivery} guests={a.guest_sessions}")
    except SystemExit:
        print('FAIL', name, '->', err.getvalue().strip().splitlines()[-1])
