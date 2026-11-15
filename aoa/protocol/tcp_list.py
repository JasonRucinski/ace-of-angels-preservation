"""Station TCP replies: the game-server list, the custom-config list and the reply framing."""
from aoa.formats import aoapack


# Uncompressed TCP reply bodies per job type. Job 14 (resource file-state
# list, handler 0x432ED0): a 128-byte name header, then 168-byte records,
# count = (len - 0x80) / 0xA8; zero records = "every file is current".
def server_record(index, name, s20, s40, ip, port, players, status=0):
    """One 128-byte game-server entry for job 5 (ReceiveGameserverList, 0x432760):
    +0x00 str[32], +0x20 str[32], +0x40 str[32], +0x60 str (IP), +0x72 u16,
    +0x74 u32 players, +0x78 u8 slot index, +0x7C u32 (passed on only if < 99).
    Slot 0 is not a server: CAOAStationDlg's notify (0x4582B0) writes its
    player count into the "Logins" box. Slots >= 1 become rows of the Server
    list (control 0x42B: name, players, IP); RequestGameserverConnect
    (0x42FF20) connects to the row's +0x60 IP and +0x72 port."""
    r = bytearray(0x80)
    for off, text, size in ((0x00, name, 32), (0x20, s20, 32), (0x40, s40, 32), (0x60, ip, 18)):
        b = text.encode("latin1")[:size - 1]
        r[off:off + len(b)] = b
    r[0x72:0x74] = port.to_bytes(2, "little")
    r[0x74:0x78] = players.to_bytes(4, "little")
    r[0x78] = index
    r[0x7C:0x80] = status.to_bytes(4, "little")
    return bytes(r)


def ship_config_list():
    """TCP job 4 body: the custom-config list (findings 9.40).

    The handler (0x435CEB -> 0x4AF030) takes 0x68-byte entries; one whose
    +0x20 name is "_all" sets world +0xDF141, so the fighter menu offers a
    "default" config (index 0) for every ship. Without it the menu shows
    "Ship Not Available" and refuses with "Fighter Not Available".
    """
    entry = bytearray(0x68)
    entry[0x20:0x24] = b"_all"
    return bytes(entry)


TCP_JOB_BODIES = {
    4: ship_config_list(),
    14: bytes(0x80),
    5: server_record(0, "station", "", "", "", 0, 1)
       # Bundled terrain and the client's default backdrop (0x4A3045).
       # Unknown backdrop names make On3dGfxInitialized call _exit(2).
       + server_record(1, "Local Arena", "CTF_arena", "spacebkgd3", "127.0.0.1", 5031, 0),
}


def tcp_reply(job, bodies=None):
    """u32 length + CCompress body (CClientComm::TCPRead 0x435930 decompresses
    with the routine matching 2.7.1 CCompress::Decompress). Length 0 skips the
    job handler and only releases the client's transfer lock."""
    body = (TCP_JOB_BODIES if bodies is None else bodies).get(job)
    if body is None:
        return (0).to_bytes(4, "little")
    packed = aoapack.compress(body)
    return len(packed).to_bytes(4, "little") + packed


def server_list_body(population, arena_port=None, mode="Local Arena", available=True, station_population=0,
                     advertised_address="127.0.0.1", terrain="CTF_arena", backdrop="spacebkgd3"):
    """Publish admitted arena population; no arena row when unavailable.

    Existing recovered fields 0x20/0x40 are terrain/backdrop, not mode enums.
    """
    body = server_record(0, "station", "", "", "", 0, station_population)
    if arena_port is not None and available:
        body += server_record(1, mode, terrain, backdrop, advertised_address, arena_port, population)
    return body
