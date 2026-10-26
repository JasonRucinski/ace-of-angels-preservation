# Ace of Angels — static network/protocol findings (2.7.1 reference, 2.9.2 comparison)

Session date: 2026-10-20. Nothing was executed except (a) Python tooling and
(b) Unicorn emulation of isolated pure codec/cipher routines, with OS/Winsock
imports stubbed. No installer or game process was run. No network traffic was
sent to any historical host.

Labels: **CONFIRMED** = reproduced from bytes or verified by emulation/CRC.
**INFERENCE** = suggested by evidence, limits stated. **HYPOTHESIS** = untested.
All addresses are VAs in the 2.7.1 client (SHA-256 b179c3c2…) unless marked 2.9.2.

## 1. Provenance (CONFIRMED)
* Downloaded per Appendix A; size and SHA-256 matched for the 2.7.1 installer
  (c3f041d0…), the 2.9.2 installer (90c4a47e…), and the 2.7.1 direct client (b179c3c2…).
  Log: `evidence/download_log.jsonl`. Originals are kept read-only in `originals/` (git-ignored).
* Both installers open as ZIP. Member lists match Appendix C exactly (38/41).
  `testzip` is clean. The only PE members are the nine listed in the handoff.
  The 2.7.1 client inside the installer is byte-identical to the Discmaster direct copy.
* Runtime versions were reproduced from the globals passed to every `%d.%d.%d`
  format: 2.7.1 at file 0x2838B8/BC/C0 and 2.9.2 at 0x1D1A10/14/18. Each global has
  13 references and none writes to it. Note: these are 7–8 format call sites, not the
  handoff's "five"; the counting basis differs.
* The four 2.7.1 packet-size diagnostics were reproduced exactly (push VAs 0x476AFE /
  0x476A95 / 0x47708B / 0x476B42; log fn 0x60B0C0; object 0x6A58B8). The full routine
  has 120 entries (`evidence/2.7.1/packet_sizes.txt`). **2.9.2 has no `SPacket` strings
  at all**, so its diagnostic routine is absent.
* The port records were reproduced at the handoff offsets. They are part of a
  384-record `CParams` table (68-byte records, starting at file 0x28AA98, `~` terminator),
  read through `CParams::GetIndexedLookup` (0x521710). The optional overrides file is
  `aoa.cfg` (0x505AE0); if it is missing, the client only logs this.

## 2. Transport and framing (CONFIRMED by emulation)
* Game traffic is UDP: `socket(AF_INET, SOCK_DGRAM)` and `bind(INADDR_ANY, port)` in
  `CComm` (0x60E200). The client binds **port 0** (ephemeral) in `CClientComm::Init`
  and `ConnectToStation`.
* Send path (`CComm::SendPacket`, 0x60DDB0), for a payload under 512 bytes:
  `wire = Encrypt_K( Compress( payload ‖ type:u8 ‖ CRC16-XMODEM(payload):u16le ) )`.
  * Compress is `CCompress` (0x60EB60): a Predictor/RFC-1978-style codec with a
    16-bit hash, up to 3 passes, and a trailer byte `(expand<<4)|passes`; `0x10` means raw.
  * Encrypt is a 2-pass byte-chaining cipher (0x60F5B0 / 0x60F6A0) keyed by 256 bytes.
  * K is loaded from **SCRTY.BIN** (a 256-byte permutation, identical in all builds).
    `CComm` is not marked ready unless that file loads.
* Receive path (0x60DEF0): `recvfrom` (≤0x200 bytes), decrypt, decompress (capped at
  0x200), split off the type and CRC, and accept only if the CRC matches.
* Python implementations in `tools/aoacrypt.py`, `tools/aoapack.py`, and `tools/aoanet.py`
  match the client's own code exactly:
  * cipher: 220/220 cases, for both 2.7.1 and 2.9.2;
  * compressor: byte-identical output, 36/36;
  * the client's real `SendPacket` produces the same wire bytes, 33/33;
  * the client's real `RecvPacket` accepts Python-built datagrams, compressed and raw, 66/66.

  Evidence: `evidence/2.7.1/{cipher,codec,ccomm_framing}_emulation.json`.
* 2.9.2 uses the same pipeline. The codec, cipher, CRC, and archive routines are
  byte-identical once address operands are masked (`evidence/2.9.2/function_matches.json`).
  Only `CComm` member offsets moved.

## 3. Message layer
* Type IDs are the u8 trailer, **not** the size diagnostics (the handoff caution holds).
* There are two receive switches. `CAOAComm` handles type−8 (0x4D1830; 24 types),
  then passes the rest to `CClientComm::ReceiveExtraPacket` (0x45B430; 75 types).
  Packets from unknown senders are dropped (`!!Received [%d] from NO ONE`).
  2.7.1 handles 99 incoming types; 2.9.2 handles 104 (a superset).
  See `docs/message-types.md`.
* There are 116 immediate send sites covering 83 types in 2.7.1, and 58 types in
  2.9.2 (heuristic). Eleven lengths changed between builds.
* **SConnectReq**: type 0x0A, 445 bytes in 2.7.1 and 381 in 2.9.2
  (`CAOAComm::SendConnectRequest`, 0x4D2400). Layout:
  * +1 minor, +5 major, +9 patch (u32 each);
  * +0x0E flag;
  * +0x1F a login-info block of 414 bytes (2.7.1) or 350 bytes (2.9.2).

  It resends every 2 s and times out after 6 s (result 6). The login block starts with
  the handle (20 bytes) and holds the password at +0x14 and again at +0x62. INFERENCE:
  the password is protected only by the static-key cipher.
* **SAckConnect**: type 0x0B (`CClientComm::ReceiveAckConnect`, 0x45BDD0). Payload:
  * +0 ack kind (1 = station ack);
  * +2 u32 identifier;
  * +6 u32 result (0 or 0x0F means success);
  * +0x0D player block;
  * +0x3F status flags (bit 2 = squad leader);
  * +0x45 squad ID.
* Type 0x94 (49 bytes, 0x4D7830) carries a u32, a 32-byte string, and the version.
  It is sent from `CClientComm::CheckEvents`. Its name is unknown (HYPOTHESIS: a
  periodic station ping or keepalive).
* Type 0x1B on receive strips a 5-byte tail (u32 plus inner type) and re-dispatches.
  HYPOTHESIS: a guaranteed-delivery wrapper.
* Several unique-size matches suggest the client also sends designer/admin messages
  (`SLoadPlayer`, `SPacketAddMOTD`, `SPacketLoadScenario`, `SPacketSetParam`).
  These are size hints only.

## 4. Login, servers, ports
* Login dialog 127 has an **editable "Station IP:" combo box** (control 0x3F5,
  `CBS_DROPDOWN`; also present in 2.9.2). Play Online calls `LoginToStation(0)`;
  Offline and Tutorial call `LoginToStation(1)` (Tutorial also sets flag 0x8000 at
  0x6A39B4). The Station address comes from the dialog, or from
  `WSAAsyncGetHostByName("aoahost.com")`, or from a hard-coded fallback.
  The Station port is `STATION_RUNONPORT` (5033).
* Historical hard-coded IPs (evidence only, **not contacted**): 216.99.57.66 (2.7.1),
  66.154.81.18 (2.9.2), and the LAN address 192.168.0.7 (2.7.1 `SendRequestPassword`).
* The client looks up 72 config keys by name. The only ports among them are
  STATION_RUNONPORT (5033) and STATION_TCPJOBPORT (5034). GAMESERVERPORT (5031),
  NAMESERVERPORT (5032), LOCALPORT, and SERVERPORT are never looked up by the client.
  INFERENCE: they belong to the server and Station programs, which shared this header.
  The same table also holds Station settings (`STATION_PINGREGISTEREDSERVERS`,
  `STATION_SERVERREGISTERHOLDOFF`, `MAXLOGINS`=50, …).
* TCP is used for `CClientComm`'s resource and auto-update downloader:
  * `GET http://%s/aoaresource/%s` requests;
  * `execchk.bin` and `resource.txt` checksums;
  * self-update via `AoAClient.ex_` and `renexe.exe`;
  * a 4-byte-header `TCPRead`.

  It is not the gameplay channel.

## 5. Host mode and offline simulation
* No reachable host mode was found. The evidence:
  * `CComm`'s listen/accept wrappers (0x60E0C0 / 0x60E0E0) have no code or data references.
  * The only reachable listen/accept is Xaudio's FTP active-mode data socket
    ("Network Streaming Module 1.4").
  * An incoming SConnectReq (0x0A) is only logged (`connect request from [%s]?!`),
    in both builds.
  * The client never binds a fixed port.

  This holds within static analysis; indirect calls through unseen pointers can't be
  fully excluded.
* Offline mode skips every Station call and runs local resource sync (dialog 157).
  The world offline flag (`CAOAWorld+0xD00B9`) is read in only 4 functions; for
  example, `CollideMissile` resolves hits locally when offline. INFERENCE: flight,
  AI, and collision code runs client-side in both modes. Damage, scoring, and
  sessions were server-authoritative online, which matches the developer's 2001
  forum statement.

## 6. Data archives (CONFIRMED by CRC)
* Every `.aoa` file and `AOAOBJECTS.ODB` is a `CDataHandler` archive, version 0x0402.
  * header: a 256-byte per-archive key, encrypted with the built-in key at VA 0x6A0128
    (also present in 2.9.2);
  * then `count:u16` and `version:u16`;
  * then 280-byte entries: name[256], offset u64, size, compress, cipher mode.
* All **1,178 entries** (430 in 2.7.1, 748 in 2.9.2) decode, and every one passes its
  CRC (`evidence/*/archives.json`; `tools/aoapack.py extract`). Content types: scripts
  (`.scr`, readable), objects (`.gob/.sco/.shs`), TGA/BMP, MP3, SFX, the "Curt3"
  scenario, and `update_interval_*` tables.

## 7. Missing components for a working multiplayer service
Recovered: wire framing, codec, cipher, key file, archive format, the message-ID
inventory, the connect request/ack layouts, and the login flow.

Still missing:
1. **Station server.** It must accept SConnectReq, validate the version and the
   login block, return SAckConnect with a valid player block (layout from +0x0D not yet
   decoded), serve the game-server list (`SPacketGameserverList`, 461 = 1 + 10×46 in
   2.7.1), and answer pings and the type-0x94 message. A minimal stub looks feasible,
   but per-type payload layouts must be decoded handler by handler.
2. **Game server.** It must authoritatively simulate damage, deaths, score,
   scenarios, and missiles, using the client's ~100 incoming and ~80 outgoing types.
   No server program survives, but the 2.7.1 client still contains many of the
   server's send routines (shared `CAOAComm` code) and a few live server-side
   callers: [9.43](#943-the-271-client-keeps-the-servers-send-routines-25-october-2026).
   Behaviour is reconstructed from those senders plus the client handlers.
   This is by far the largest piece of work.
3. **Name server** (port 5032). Its role and protocol are unknown; the client never
   addresses it by name.
4. **Resource/HTTP host** (`/aoaresource/`, `resource.txt`, `execchk.bin`) — optional;
   formats partly known.
5. Account database, player and squad persistence, MOTD — no data was recovered.
6. Unknown: the reliability (0x1B) semantics, sequence and ack rules, the timers in
   `CClientComm::CheckEvents`, and the type names for most IDs.

## 8. Reproduce
```
py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
python -I tools/fetch.py manifest/downloads.json 2.7.1 originals/2.7.1
python -I tools/inventory.py <installer> <ver> docs/history/2026-10-20-research-handoff.txt work/<ver>
python -I tools/version_probe.py | packet_sizes.py | config_records.py | dispatch_table.py | send_sites.py ...
python -I tools/emulate_cipher.py / emulate_codec.py   (see each script's docstring)
```
All outputs are under `evidence/<ver>/`.

## 9. Live confirmation against a local Station stub (2.9.2, 20 Oct 2026)

The patched 2.9.2 client was run on Windows 11 and pointed at
`tools/station_stub.py` on **127.0.0.1 only**, by typing 127.0.0.1 into the
login dialog's Station IP box (Play Online, handle `testpilot`, test
password). No traffic went to any historical host.

**CONFIRMED live:**
* The codec in `tools/aoanet.py` decodes every client datagram with valid CRC
  using SCRTY.BIN as the key.
* **SConnectReq** (0x0A): UDP to port 5033, 381-byte payload, version
  fields 2.9.2, handle at +0x1F, 350-byte login block; resent every 2 s,
  three tries, as predicted statically.
* **SAckConnect** (0x0B), 2.9.2 layout read from
  `CClientComm::ReceiveAckConnect` (0x431630) and accepted by the client:
  * +0 u8 (printed as `me[%d]`);
  * **+1 u8 ack kind: 1 = Station** (reads status flags and squad, logs
    `Got Stationserver ack`), 0 = game-server path. The earlier note that +0
    is the kind was wrong: the branch reads a stack copy of byte +1;
  * +2 u32 player id, +6 u32 result (0 or 0x0F = success);
  * +0x0D 350-byte player block (copied wholesale into the player object;
    `STATUS FLAGS` at +0x3F, squad present at +0x45, squad name at +0x11F).
  Echoing the client's own login block as the player block is accepted.
  The 13-byte header plus 350-byte block (363 bytes) is enough.
* After a Station ack the client:
  * sends reliable (0x1B) messages: payload ‖ u32 sequence ‖ u8 inner type.
    Seen: seq 1 inner 0x6E (352-byte player record, name "Offline" at +2),
    seq 2 inner 0x80 (4 bytes), seq 3 inner 0xAD (4 bytes). Without an ack
    the client resends seq 1 about every 0.86 s;
  * opens the resource-sync dialog and makes a **TCP** connection to the
    Station on **port 5034** (`STATION_TCPJOBPORT`). The request is
    plaintext, 142 bytes. The initial capture had zero-filled leading fields
    and job 14 (file-state request). The later trace in 9.16 corrects the
    initial u32-job interpretation: byte +0x80 is the job, +0x81 a separate
    flag, and +0x3C a player-record-derived u32 correlation field;
  * on connection refused or no reply it proceeds (`Ending Update Dialog`,
    `SendPacketBeginSerialLoad`, `initializing station dialog`), then blocks
    on `waiting for xfer lock` behind a second TCP job (type 5).

**Next for a minimal Station:** the reliable-message ack (which type the
client expects back for 0x1B), the TCP job reply framing (`TCPRead`, 4-byte
header) for job types 14 and 5, then the station-dialog traffic (server list
`SPacketGameserverList`, chat, MOTD).

### 9.1 Reaching the Station screen (CONFIRMED live)

With the stub answering three things, the client completes login and opens
the Station dialog (server list, player list, chat; handle shown as logged in):

* **Reliable-message ack:** reply type **0x0F** whose payload is the u32
  sequence from the 0x1B wrapper. The CAOAComm receive switch (0x4864E2)
  walks the retry list at `CAOAComm+0xF18` and unlinks the entry whose
  sequence (entry+0) equals payload+0; the client then stops resending.
* **TCP job replies (port 5034):** `CClientComm::TCPRead` (0x435930) reads a
  **u32 length** then that many bytes, decompresses them with CCompress
  (0x52A630 = 2.7.1 `CCompress::Decompress`) and dispatches on the job type
  (jump table 0x43664C, types 0..0x24). Length 0 skips the handler and just
  releases the transfer lock.
* **Job 14 (resource file-state list, handler 0x432ED0):** body = 128-byte
  name header + N × 168-byte records, N = (len − 0x80) / 0xA8. A header with
  zero records ("all files current") lets resource sync finish
  (`Ending Update Dialog`), after which the client sends
  `SendPacketBeginSerialLoad`, opens the Station dialog and initialises
  DirectX.
* Jobs then requested and answered with length 0: 11, 5 (handler 0x432760,
  128-byte records), and queued 18 and 6. Other client traffic seen: type
  0x94 (49 bytes), reliable inner types 0x6E, 0x80, 0xAD, and a 1-byte 0x4F.

Not yet supplied: the game-server list, player list, MOTD/chat traffic.

### 9.2 Server list and the Play gate (CONFIRMED live)

* The game-server list is **TCP job 5**, not a UDP packet: handler
  `ReceiveGameserverList` (0x432760), body = N × 128-byte records:
  `+0x00` name, `+0x20` terrain, `+0x40` background (both logged by
  `LoginArena Planning to load ter[%s] back[%s]`), `+0x60` IP string,
  `+0x72` u16 port, `+0x74` u32 players, `+0x78` u8 slot, `+0x7C` u32
  (record passed on only if < 99).
* **Slot 0 is the station total**: the Station dialog's notify (0x4582B0)
  writes its player count to the Logins box. Slots >= 1 become rows of the
  Server list, which is control 0x42B (columns Server / Players / IP;
  control 1000 is the player/notify list). The first row is auto-selected.
  Confirmed: one record in slot 1 shows "Local Arena | 0 | 127.0.0.1".
* `RequestGameserverConnect` (0x42FF20) connects to the row's IP/port.
  The client re-requests job 5 every few seconds while on the Station screen.
* **Play is gated on a pilot handle**: the command path (0x4586D0 →
  0x4563B0 "processing command to enter arena") first shows
  *Access Restriction: "Please select a handle first, with the ADD HANDLE
  button"* when no handle is selected. Handles (aliases) come from the
  Station ("Got aliases!", 0x45DBE0; 0x45DA70 is the preceding handler);
  supplying them is the next step.
* Idle Station traffic: type 0x94 (49 bytes) followed by a 1-byte 0x4F,
  repeating.

### 9.3 Pilot-list reply and initial arena responder

**Recovered statically from the verified 2.9.2 executable:**

* Pilot aliases arrive over **UDP type 0x9A**, not a TCP job. The dispatch
  case at `0x430F5D` passes the payload at `CClientComm+0x364` directly to
  observer method `+8`. The dialog observer vtable starts at `0x5903D0`;
  its `+8` entry is `0x45DBE0` (the function logging "Got aliases!").
* Payload: **ten 32-byte NUL-terminated name slots (320 bytes)**, with no
  count or prefix. The dialog clears combo `0x442`, adds nonempty slots,
  then selects the current name if it appears, otherwise the last nonempty
  name. Empty remaining slots must still be present: the handler always
  traverses all ten. The stub supplies one synthetic pilot, `testpilot`.
  `--pilot NAME` allows 1..19 non-NUL ASCII characters to also fit the
  narrower 20-byte login-name field.
* `SendPacketBeginSerialLoad` (`0x488FC0`) sends reliable inner type
  `0x80`, four bytes. This is a general serial-load request, **not proven
  to be a dedicated alias-list request**. The original server's ordering
  is unknown. As an experimental timing choice, the stub sends aliases
  once per login after the first TCP job 5 reply, when the Station is
  requesting its server list. It does not send them immediately after
  login, before the Station observer has registered.
* The game-server branch of `ReceiveAckConnect` is `0x431986`, selected
  by acknowledgement byte `+1 = 0`. It logs "Got gameserver ack", then
  calls `0x488B30` for indices 0 through 25 to initialize event timers
  (not to send 26 data requests). The Station branch uses
  `+1 = 1`. The optional `--arena` listener binds UDP **127.0.0.1:5031**
  and answers a 381-byte type `0x0A` request with that game-server variant
  of the existing 363-byte type `0x0B` reply. This exchange was subsequently
  confirmed live in section 9.4.

**Verification completed:**

* `tools/emulate_station_aliases.py` executes the actual `0x45DBE0` handler
  in Unicorn, with logging and Windows UI imports intercepted. Four cases
  passed: empty previous name, "Offline", matching previous name, and a
  19-character supplied name. In each, the handler added exactly one item
  and selected it. Evidence: `evidence/2.9.2/station_aliases_emulation.json`.
  This verifies the payload layout and selection calls, not live UI timing.
* `python -I tools/test_station_stub.py`: five passing regression checks,
  including a real subprocess/socket exchange on ephemeral localhost
  Station ports with a synthetic key. Checks cover TCP fragmentation and
  decompression, the subsequent alias datagram, both acknowledgement
  variants, reliable-wrapper dispatch, and malformed/bad-CRC rejection.
  No game client or historical network destination is used by these tests.

Run the local experiment from the repository root:

```powershell
.venv/Scripts/python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/station-pilots.jsonl --tcp 5034 --ack --arena --seconds 900
```

Then manually log in to `127.0.0.1` with test-only credentials and press
Play. UDP records now include `udp_port` to distinguish Station and arena
traffic. The terrain/background names now use bundled assets (section 9.5);
world state is not implemented. This is not a playable multiplayer server.

### 9.4 First arena connection accepted; client crashes during initialization

**CONFIRMED live, user-operated run on 20 Oct 2026, 21:11 local time:**

* After the localhost discovery patch, the user reached Station with the
  normal Play Online button. The client logged `Got aliases!` at 21:11:56.703.
* Play passed the handle gate and sent a valid-CRC, 381-byte `SConnectReq`
  (type `0x0A`, version 2.9.2, pilot `testpilot`) to **127.0.0.1:5031**.
* The client accepted the stub's arena reply, logging
  `::ReceiveAckConnect Got gameserver ack me[0]:[0x00000001]`.
* The user observed a flash and crash. The report log ends with
  `Entering On3dGfxInitialized()` at 21:11:59.468; the regular log ends
  with `loading AI flags`. The latter function (`0x486100`) only logs and
  returns, so it is not evidence of a missing AI-file load.
* No matching new crash dump or Windows crash event was found during this
  inspection. The failing instruction and cause are **not yet known**.
  A reproduction under `tools/crashdbg.py` was requested before attempting
  a crash fix. Placeholder terrain/background names and the minimal echoed
  player record remain possible later initialization problems, not proven
  causes of this crash.

Sanitized evidence (no login-block/password bytes):
`evidence/2.9.2/station_arena_live.json`.

### 9.5 Play failure traced to a nonexistent backdrop

**Confirmed in locally operated debugger runs on 20 Oct 2026:**

* `tools/crashdbg.py --trace-exit` now intercepts CRT `exit` and `_exit`
  and records the caller before allowing normal execution. The original
  failure was an intentional `_exit(2)`, returning to `0x43A3A5`, rather
  than an unhandled exception. `On3dGfxInitialized` looked up the backdrop,
  received null, and failed its `pcGfxObj` assertion (AoA_Gfx.cpp line 1414).
* The stub's job 5 record had advertised placeholder backdrop `field40`.
  Its terrain `field20` was also a placeholder. The record now advertises
  `CTF_arena` and `spacebkgd3`: both match the client's defaults and actual
  bundled `.Gob` assets. No executable patch is needed for this fix.
* With these names, the client logs both entry and exit from
  `On3dGfxInitialized`. The final normal-heap run accepted the arena reply
  at 21:28:00.765 and completed graphics initialization at 21:28:01.203.
  Visual inspection reached the in-game Game Info / Briefing panel over
  a black scene. The stub received subsequent arena UDP traffic, including
  type `0x1F`; its payload meaning is not established here.

**Limits:** this fixes the reproduced missing-backdrop exit, not every
remaining client problem. One subsequent normal-heap run ended with
`0xC000041D` after a native heap failure; the corrupting writer is unknown.
A guarded-allocator run reported out-of-bounds reads and eventually exhausted
its non-reusing 768 MB arena, so it is not a stability result. The final
normal-heap run reached its 150-second debugger timeout (exit `0xDEAD`,
deliberately imposed by the harness), but repeatedly logged first-chance
`0x80000001` exceptions. Reaching the briefing does not establish stable
flight or a populated world. Arena world/spawn state is still unimplemented.

The five protocol regression checks pass after the asset-name correction.
All game-server tests used loopback. Raw local logs contain test login data
and remain under ignored `work/`; sanitized findings are recorded here.

### 9.6 Explicit flight entry and experimental two-client relay

20 Oct 2026, localhost only. `--experimental-flight` sends type `0x27`
(`SLoadShip`: vessel[64], database[64], slot byte; 129 bytes) with
`Ym Khtat`, `AoAObjects.odb`, and local slot zero, then type `0x2C`
(four-byte body, unused by this receive handler). A three-second delay after
the arena acknowledgement is an experimental scheduling choice.
`crashdbg.py --trace-arena` confirmed execution at `0x4306C1` and `0x430684`.
The client displayed a ship HUD and space backdrop. This is explicit server
flight entry, unlike the fallback watchdog path at `0x433AC9`.

`--experimental-relay` adds a deliberately incomplete relay experiment:

* Assigns distinct tags `0x80010000 | slot`, with slots 1..49. The client
  stores its own player in local slot zero while retaining the server tag.
* Sends type `0x26` player records, 438 bytes. Recovered fields: vessel[20]
  at +0, database[20] at +20, tag at +0x28, player record at +0x46,
  position at +0x1A4, copy-player-record flag at +0x1B0. All player records
  are synthetic (`LocalPilotN`); credentials are never copied to peers.
* Forwards valid-CRC type `0x1F` position packets to other registered peers
  when the first header's player bit and index match the sender. This is
  **not full payload validation or authoritative simulation**. The incoming
  client handler is `0x4342C0`; payloads can contain multiple updates.
* Catches Windows UDP connection-reset errors when a previous peer exits.
  `--arena-port` allows isolated tests without occupying the game port.

**Live evidence:** two real clients ran from separate ignored local folders.
Client B executed two player loads, a ship load, and explicit flight entry.
`tools/inspect_arena.py` read its active player array: local slot 0 held
`LocalPilot2`, tag `0x80010002`; slot 1 held `LocalPilot1`, tag `0x80010001`.
The UI also announced both pilots entering the scene. Thus remote player
creation is confirmed in this direction, not just packet transmission.

**Failed verification:** on the late join, client A entered the player-load
handler, then crashed with `0xC0000005` reading `0x80010001` in ntdll heap code.
The stack includes a compression allocation at `0x52AA84`, called from
packet receive at `0x529ED1`. This identifies where the corrupt heap was
noticed, not its writer. Two-way movement has **not** been verified. The
surviving client displayed `Server Not Responding`. Both spawn positions
read back as zero; the intended offset in the experimental player record
was not retained. Do not treat this as playable multiplayer.

Other unfinished pieces: reliable server delivery/order, disconnect removal,
peer expiry, concurrent Station login/alias association, current player
counts, terrain population, scoring, weapons/damage, and scenario rules.
The experimental flags remain off by default. Six protocol tests pass,
including two synthetic UDP clients receiving distinct identities and
player loads, plus byte-preserving position forwarding. That transport test
does not replace the failed real-client movement verification.

Map/scenario inventory: `docs/hosting-assets.md` and
`evidence/2.9.2/arena_inventory.json`. Five arena candidates, twelve other
layouts, five backdrops, and one scenario (`Curt3`) are locally available;
none is yet verified as a working hosted multiplayer mode.

### 9.7 Movement decoder crash and bounded relay (20 Oct 2026)

The guarded late-join replay reached an invalid write at `0x49598C`, inside
the position decoder called by `ReceivePositionUpdate` at `0x434449`.
Mask bit `0x80000000` enables optional data; submask bit 0 writes through a
destination that the client receive caller has not initialized. In the
captured fault, that pointer was `0x52AC68`, a code address. Forwarding the
full client-to-server update to another client is therefore unsafe. This
is a concrete crash cause, not proof that every earlier heap failure has
the same cause.

`station_stub.movement_update` now validates the first record's assigned
player slot and retains only mask `0x07FFFFFF` and its correctly sized
kinematic prefix. It preserves the decoder's absolute/delta encoding and
field precedence, rejects a truncated prefix, and drops the entire suffix
(including any further records). Equipment, status, scoring and other
optional blocks are not relayed. This remains an incomplete experiment:
there is no delta recovery after packet loss or authoritative simulation.

Verification:

- Seven protocol tests pass, including actual localhost two-peer transport
  with the unsafe optional block removed, wrong-slot rejection and prefix
  truncation checks.
- `tools/emulate_movement.py` executes original decoder `0x495330` in
  Unicorn. All 229 single-bit/combined/random mask cases consume exactly
  the filtered body length. A nonzero target-position case writes the
  expected coordinates. The deliberately unsupported optional pointer
  reproduces the invalid write at `0x49598C` before filtering. Results:
  `evidence/2.9.2/movement_emulation.json`.
- Live localhost guarded-client replay: a synthetic second endpoint sent
  1,482 updates over 75 seconds, alternating a previously captured update
  containing optional fields and a known `0x40` target-position update.
  Read-only memory inspection confirmed active `LocalPilot2`, tag
  `0x80010002`, with target `(1500, 250, -500)`. Its actual position remained
  `(1000, 0, 0)`. The client remained alive after the replay, without a fatal
  exception or guarded WRITE report. Raw captures stay ignored under
  `work/filtered-*`; no account/login payloads are published.

The live check used `crashdbg.py --guard-heap --guard-continue --guard-reuse`.
Delayed reuse prevents diagnostic allocator exhaustion: blocks are withheld
for 4,096 frees, then reused by page count. Reused addresses cannot detect
old use-after-free pointers, and continuing guard reads changes behavior;
this is diagnostic evidence, not a clean native-heap stability certification.
An initial native-heap attempt entered flight but did not load the late
synthetic peer after the server-not-responding state; it is inconclusive.

Next: recover heartbeat/session state and how target coordinates feed remote
motion, then verify two actual clients exchanging movement. Terrain object
population, teams, scoring, weapon/damage behavior and disconnect cleanup
remain missing. Do not describe the current stub as playable multiplayer.

### 9.8 Arena heartbeat and actual remote motion (20 Oct 2026)

The CAOAComm receive tables at `0x4869B0`/`0x48694C` map type 8 to
`0x48656B` (virtual BouncePing, implemented at `0x486C20`) and type 9
to `0x48655F` (ping-response handler `0x486DC0`). The bounce sends a
12-byte type-9 body. Layout: u32 timestamp, u16 trip time, u8 player,
one reserved byte, two u16 counters. The incoming server request uses
player 0; the client replaces this with its own tag's low byte. Valid
incoming peer traffic refreshes last-heard time through `0x4C1760`.

The experimental flight/relay now sends type-8 pings once per second after
bootstrap. Eight protocol tests pass, including an actual socket check for
the ping and a timestamp-wrap check. The live 2.9.2 client returned type-9
packets and the flight screenshot no longer showed Server Not Responding.
This does not implement peer expiry, disconnect cleanup or latency accounting.

The earlier stationary target result is explained by the physics update's
early return at `0x48AE71` through `0x48AF7A`: with motion flags, velocities
and the other checked motion fields zero, it skips the correction path.
Position correction itself is present at `0x48C23C` onward. A synthetic
peer sent 349 type-0x1F packets over 35 seconds using mask `0x41`, target
`(1500,250,-500)` and velocity `(10,0,0)`. The real client's remote player
actually moved: a read-only snapshot showed position approximately
`(1508.119,249.9997,-499.9995)`, rather than its spawn `(2000,0,0)`.
This confirms actual remote motion from relayed position-plus-velocity;
it does not establish prediction accuracy or recovery from dropped deltas.

Two actual clients then connected as tags `0x80010001` and `0x80010004`
(two synthetic peers had occupied slots 2 and 3). Each loaded the other's
pilot. The first client deferred processing the late join while inactive
and processed it on activation, without the prior fatal exception. Both
clients returned pings. Short `W` key inputs did not produce local motion;
the second client's local max velocity/acceleration were 3250/650, so zero
thrust limits are not the immediate explanation. Held-key input/control
mode and actual two-way player-controlled motion remain to be verified.

These live tests used the diagnostic guarded allocator described in 9.7;
no guarded WRITE or second-chance crash was recorded during the checks.
Client A ended at the requested 300-second debugger timeout (`0xDEAD`),
not a game crash. Local raw logs/snapshots are ignored `work/ping-*` and
`work/motion-probe.txt`. The motion probe's printed count is twice its
actual sends; 349 is the count confirmed from the server capture.

The `code-clues.md` lead was mapped to the 2.9.2 mission-group loader at
`0x4C0030`, server-role byte `world+0xDEEEC`. No role byte was changed.
This is the next static entry point for reconstructing scenario spawning.

### 9.9 Spawn consistency and late-join motion seeds (20 Oct 2026)

The client receive table maps type `0x24` to `0x430881`, which passes three
float coordinates to `0x4BE970` for the local player. That setter writes
both actual and target positions. The relay bootstrap now sends this after
the local ship load and flight entry, using the same distinct spawn
coordinates advertised by SLoadPlayer to observers. Previously the local
ship stayed at zero while observers could place it at `(slot-1)*1000`.

The relay now retains each endpoint's last reported position and velocity.
The encoder at `0x493983` sends absolute position under flag `0x40` when
coordinates change. Decoder `0x495330` consumes that triplet first, then
absolute/short-delta/byte-delta velocity under flags `1/2/4`. The cache
uses those same flags and float32 rounding, rejecting non-finite position
or velocity values. It does not extrapolate coordinates or simulate physics.

Late joiners receive each existing pilot's last reported coordinates in
SLoadPlayer and an absolute `0x41` position/velocity seed. This avoids
starting a moving existing player from its old spawn with an unknown
velocity-delta baseline. Orientation and other delta state are not yet
seeded, and packet-loss recovery and disconnect cleanup remain absent.

Verification: nine protocol tests pass. The real localhost socket test
moves pilot A before pilot C joins, checks C's SLoadPlayer coordinates and
absolute velocity seed, and checks its distinct local-position message.
The original executable in Unicorn independently confirms both delta
formats, the resulting seeds, and the local-position setter. Results are
in `evidence/2.9.2/movement_emulation.json`. See the live follow-up below;
the isolated routines alone did not catch the flight-entry reset.

A separate live run used the normal client heap (no guard allocator).
The heartbeat/filtered-relay code from 9.8 loaded a synthetic second pilot
and applied position-plus-velocity updates: actual remote coordinates
reached approximately `(1506.019,249.9988,-499.9977)` with velocity `(10,0,0)`.
There was no second-chance exception at that observation. Raw evidence is
ignored `work/flight-controls*` and `work/flight-native*`. This is stronger
than the previous guard-allocator motion check, but is still a bounded test.

Keyboard Tab successfully changed the local max velocity from 3250 to
30000, confirming delivery of a persistent keyboard command. Short W taps
still did not move the local ship. The UI API provides key taps, not a
held-key action; a user-held W check was requested to distinguish that test
limitation from a control-mode/game-state issue. No change to thrust limits
or client input code was made on this evidence.
The default numpad-0 match-target-speed tap was also tried with a moving
target; no local position/velocity change was observed. It does not replace
the pending held-thrust check.

Live follow-up: sending `0x24` before EnterFlight did not retain the local
spawn. `SetupFlightMode` (`0x44B5C0`) reloads coordinates from player-info
offsets `+0x14E/+0x152/+0x156`, then calls the position setter at `0x44B694`.
The bootstrap now sends `0x27`, `0x2C`, then `0x24`. A fresh normal-heap
client joined behind a synthetic pilot and retained actual and target
`(1000,0,0)`. Trace confirmed load-player, load-ship, enter-flight, then
set-position. The socket regression now requires this ordering.

Remote motion is still unstable: 38 of 100 read-only snapshots over about
10 seconds contained non-finite remote acceleration, velocity and target
position, while the local spawn stayed finite. Later updates restored finite
remote values. This occurred with the synthetic sender still active, so it
is not solely a disconnect problem. Raw local evidence: ignored
`work/spawn-order-client.txt`, `spawn-order-samples.json`, and
`spawn-order.jsonl`. No fatal exception was observed during that sample.

A concrete next lead is the physics acceleration calculation at
`0x48C200/0x48C208/0x48C214`: velocity differences are divided by a time
step, then written to kinematic `+0x5C/+0x60/+0x64`. The tick difference
comes from `0x48AE43..0x48AE5D`. Unicorn execution of the original
`0x48C1BF..0x48C236` sequence now confirms that unchanged velocity with a
16 ms step produces zero acceleration, while a zero step produces three
NaNs. This is recorded in `movement_emulation.json`; a zero time step
is not yet confirmed at the live call site. The receive path subsequently uses
acceleration at `0x4345F1` even with zero packet trip time; zero multiplied
by NaN remains NaN. No physics patch or speculative server workaround was
applied. `inspect_arena.py` now includes acceleration for this investigation.

### 9.10 Confirmed zero-time physics failure and reversible guard

The normal-heap client was launched with `crashdbg.py --trace-physics`.
A breakpoint immediately before the acceleration division (`0x48C200`)
recorded `dt=0.0` for remote tag `0x80010001` on its first update and
repeatedly afterward. This confirms the missing precondition identified
in 9.9. Breakpoints change timing; the comparison run below omitted this
physics breakpoint. Raw trace: ignored `work/physics-client.txt`.

`tools/physics_timestep.py` adds a reversible guard at `0x48AE71`. After
the original tick bookkeeping, it checks the calculated time step at
`[esp+0x38]`. Zero takes the existing balanced epilogue at `0x48CE9F`;
positive values execute the displaced instruction and original physics.
The cave at `0x58B400` is within the executable padding already mapped by
the logger stability patch. Full normalized SHA-256 checks restrict this
to the known stability-patched 2.9.2 client, and original/localhost hostnames
are preserved. No server packet workaround or invented elapsed time is used.

Verification:

- Original x86 acceleration with zero time reproduces three NaNs; 16 ms
  with unchanged velocity yields zero acceleration.
- Four original-code guard cases verify zero-time stack cleanup and
  unchanged positive-time continuation (1 ms, 16 ms, 1 s).
- Byte-level tests verify exact undo, repeat application, hostname
  preservation, modification limited to two regions, and rejection of
  altered images. Both checks are reproducible via
  `emulate_movement.py` and `test_physics_timestep.py`.
- A fresh normal-heap client with the guard and no physics breakpoint
  retained spawn `(1000,0,0)` and applied remote movement. The first
  300 snapshots (~30 s) and next 200 (~20 s) had no non-finite position,
  target, velocity or acceleration, versus 38/100 in the earlier unguarded
  sample. Another 100 samples after the synthetic sender exited also stayed
  finite. Sanitized counts are in `evidence/2.9.2/physics_timestep_live.json`.
  This is a bounded synthetic-peer comparison, not proof of full
  gameplay or prediction accuracy. Raw evidence is ignored
  `work/physics-fixed*`.

The guard was applied to the test copy and `game/2.9.2/AOACLIENT.EXE`.
Preserved originals are unchanged. Local two-way keyboard-controlled
flight, authoritative simulation, packet loss, disconnect cleanup, and
scenario hosting remain unverified or unimplemented.

User verification, 21 Oct 2026: after reopening the patched local game for
the held-W retry, the user reported "yes all movement is working". This
confirms local player-controlled movement and closes the earlier input-test
uncertainty. It does not establish two-client movement synchronization,
combat, scoring or scenario hosting. The retry used the localhost stand-in;
raw capture is ignored `work/held-w-retry.jsonl`.

### 9.11 Real-player relay and first mission-object spawn (21 Oct 2026)

The user-input capture contains 61 valid movement packets from the first
pilot, with decoded speed reaching about 836.97 and distance from spawn
about 6478.84 game units. A second patched real client joined, received the
first pilot's cached position/velocity, and subsequently sent movement of
its own. On activating the first client, its remote slot for tag
`0x80010002` held coordinates near `(-2145.80,0,18352.06)` and velocity
`(0,0,-131.95)`, matching the second pilot's movement direction and velocity.
The second client's local snapshot was near `(-2145.80,0,18430.43)`.
Snapshots were not simultaneous. Both clients held finite peer movement
state; evidence is `evidence/2.9.2/two_client_motion.json`.

Inactive windows defer processing and remote prediction drifts while
updates stop. This establishes delivery in both directions with real
player input, not accurate continuous synchronization, packet-loss recovery,
or an authoritative shared simulation.

The mission-group loader lead in `code-clues.md` led to type `0x25`, the
191-byte LoadObject message emitted by `0x48A460` and received through
`0x43059D`. `station_stub.scenario_test_object()` constructs one passive
`Ym Khtat` from `AoAObjects.odb`, name `Local mission ship`, tag
`0x40010001`, kind `0x11`, coordinates `(0,0,1500)`. The new opt-in
`--experimental-object` flag sends it after the flight bootstrap. It reserves
regular object slot 1 for this single-object experiment; it is not a
general object allocator or a parser for Curt3.

Nine protocol tests pass, including actual socket delivery of the object
after flight entry and local positioning. A fresh real patched client
loaded an active object with the expected tag, kind and coordinates and
visibly rendered the named ship directly ahead. Before the experiment, the
only active regular object was slot 0; this test did not replace an existing
object. Evidence: `evidence/2.9.2/object_spawn_live.json`, with raw captures
ignored under `work/object-*`. No second-chance exception was observed at
the verification point. `inspect_arena.py --objects` reads the regular
object pool for repeatable checks.

This is verified non-player object creation. AI, firing/damage authority,
teams, score and mission completion are not implemented by the stub.

### 9.12 Arena departure and expiry (21 October 2026)

Static inspection of the original 2.9.2 executable establishes these paths:

| Message | Direction / payload | Evidence |
|---|---|---|
| `0x4E` | Client to server, one byte supplied as the quit reason | `SendImQuitting` at `0x4871C0`, identified by its diagnostic strings; `0x48725E` writes the reason, `0x487261` sets length 1, `0x48726B` sets type `0x4E`. The routine sends three copies to the arena and also sends to Station. The reason values' meanings remain unresolved. |
| `0x2D` | Server to client, player slot in payload byte 0 | Dispatch at `0x430710` reads one byte and calls `0x4A6FB0`, whose diagnostics identify `RemovePlayer`. The routine indexes the player array at world `+0xD32AC` with stride `0x3B0`. No generation/tag check precedes removal. The stub sends exactly one byte; a historical sender's full packet size is not independently recovered. |
| `0x09` | Client to server, 12-byte bounced ping | `BouncePing` at `0x486C20` replaces payload byte 6 with the local tag's low byte at `0x486C58`/`0x486C5E`; length/type are set at `0x486CDB`/`0x486CE5`. The timestamp remains in payload bytes 0..3. |

Reproduce the static inspection with `tools/explore.py`, using
`game/2.9.2/AOACLIENT.EXE.orig` and `work/2.9.2/disasm.pkl`: commands
`dis 48724d 110`, `dis 430710 24`, `func 4a6fb0`, and `dis 486c20 65`.
This is client-side evidence, not recovered original server behavior.

The local stub now accepts a one-byte arena quit only from an admitted
endpoint, including inside a single reliable envelope. Its reason cannot
select another player. Duplicate quits are harmless (reliable copies still
receive transport acknowledgments). It clears that endpoint's handshake,
motion, bootstrap timer, ping timer, issued-ping list and expiry deadline.
Loaded observers receive a single best-effort `0x2D`; pending players are
not announced until their bootstrap and are omitted from other snapshots.
Movement from a still-loading peer is ignored until its bootstrap completes.

`--peer-timeout SECONDS` defaults to 30 and must be finite and positive.
Initial flight admission includes the existing three-second bootstrap delay
in its deadline. Valid finite position/velocity updates or a matching ping
reply extend the deadline. At most four issued ping timestamps are retained
per peer; each can be consumed once and the reply must identify that peer's
assigned slot. Handshake retries, unknown packets, malformed movement,
non-finite position/velocity and invalid ping replies do not refresh it.
These checks are bounded local diagnostics, not authenticated transport.

Removed slots and endpoints remain reserved until the process restarts.
This prevents delayed movement or duplicate quit messages from being applied
to a replacement session at that endpoint, and prevents a late slot-only
removal from deleting a replacement player. A fresh endpoint can join with
a fresh slot. The run is limited to 49 lifetime admissions; it does not yet
support sustained churn or same-endpoint reconnect. Server-full remains a
silent refusal pending recovery of a suitable error response. Reliable
removal, safe reuse and general session replay protection remain required.
Station ownership, alias routing, TCP jobs and passive mission objects are
outside this arena-only cleanup change. Inactive/minimized real clients may
expire because their processing pause remains unresolved.

Verification: `python -I tools/test_station_stub.py` exercises real localhost
UDP sockets with a synthetic key; all 12 tests passed in 37.947 seconds.
The lifecycle test verifies cancellation
before bootstrap, one removal for duplicate wrapped quits, malformed quit
rejection, retired-endpoint rejection, stale-movement rejection, valid
heartbeat survival, invalid/replayed heartbeat expiry, stopped pings and
late-join snapshots without departed players. The existing handshake,
movement relay, late-join seed, object and Station/TCP checks remain included.
No real game client was launched for this change; visible despawn and
loss/reordering behavior have not been verified in the renderer.

### 9.13 Reliable removal and the slot-reuse limit (21 October 2026)

This supersedes 9.12's best-effort removal transport. Other bootstrap messages
remain best effort, so the complete session lifecycle exit gate is still open.

The original 2.9.2 receive path at `0x4863A2` recognizes outer type `0x1B`.
After identifying the sender it subtracts five bytes, reads the inner type
and little-endian u32 sequence, sends a four-byte `0x0F` acknowledgment at
`0x486428`–`0x486439`, then calls the duplicate filter at `0x4C2730`.
A rejected duplicate jumps past dispatch at `0x486457`. ACK precedes dispatch;
it is not proof that the game applied the removal successfully.

The peer constructor passes **30** to the history constructor at `0x49D6AE`.
`0x4C26D0` allocates and zero-fills that many sequence IDs. `0x4C2730` scans
them for equality and inserts unseen IDs into a circular buffer. This is
duplicate suppression, not ordered delivery or a permanent replay barrier.
Sequence zero is initially considered a duplicate. After 30 different IDs
have displaced an earlier ID, that old packet can execute again.

`tools/emulate_reliable_history.py` runs the original constructor and filter
in Unicorn with the existing allocator stub; it verifies zero rejection,
acceptance of IDs 1..30, rejection of their duplicates, and acceptance of an
old ID after eviction. Reproduction:

```powershell
.venv\Scripts\python.exe -I tools/emulate_reliable_history.py game/2.9.2/AOACLIENT.EXE.orig evidence/2.9.2/reliable_history_emulation.json
```

The output records the verified original executable hash. This executes
only isolated duplicate-filter code, not the network dispatcher or renderer.

`ReliableRemovals` in `station_stub.py` now sends `0x2D` inside `0x1B` with a
nonzero, process-unique sequence. It sends at most five identical copies,
nominally 0.5 seconds apart, then retires an unacknowledging observer at the
next retry deadline (normally 2.5 seconds after the first send, plus loop
scheduling). No unbounded catch-up sends occur after a stall. Pending entries
are keyed by endpoint and sequence; malformed, unknown, wrong-peer and
duplicate acknowledgments cannot clear another delivery. Peer departure
clears all pending deliveries to that peer.

An observer receives at most 30 distinct reliable removals during its
session, including acknowledged ones. Before a 31st, the server retires it
and tells remaining observers of its departure. This deliberately preserves
every removal ID in the client history. Any future outbound reliable spawn,
load or match events must share this budget or replace this policy; they
cannot be added independently without revisiting duplicate safety. Pending
state is bounded by 49 admitted endpoints and 30 removals per observer.

Slots and retired endpoints still are not reused. A delayed slot-only
movement/removal, an old best-effort load, or a same-endpoint quit cannot be
made generation-safe merely by receiving an ACK or waiting an arbitrary
interval. A maintained client/protocol change or a verified transport that
enforces session generations is needed before claiming replay-safe reuse.
The server's retirement policy removes its state and stops sending; it does
not yet send a verified client-facing disconnect explanation. These are
local diagnostic limits, not a usable sustained-churn internet release.

Tests cover exact retry limits, wrong-peer/malformed/duplicate ACKs, sequence
exhaustion without wrap, the 30-ID budget, and socket delivery with a lost
first ACK. The socket receiver suppresses duplicate application while still
acknowledging retries. A second socket case keeps heartbeats alive while
dropping every removal ACK and verifies retirement after five copies.
Real-client reliable dispatch and visible despawn remain unverified.

Verification result: all 14 tests in `python -I tools/test_station_stub.py`
passed in 43.075 seconds, including complete removal-ACK loss. The original
duplicate-filter emulator also passed; `git diff --check` reported no errors.

### 9.14 Original-client reliable receive-path verification (21 October 2026)

A real-client verification attempt could not launch the game: the Windows
computer-use helper returned `GetCursorPos failed: Access is denied.
(0x80070005)` twice, including a retry after refreshing the window inventory.
No game process opened. The temporary loopback server was stopped. This is
an automation/environment failure, not evidence of a game or protocol crash.

The existing `tools/emulate_reliable_history.py` now also exercises original
machine code beginning at `0x4863C8`, after sender recognition. It supplies
actual packets from `station_stub.ReliableRemovals`, executes the wrapper
unpacking, ACK preparation and duplicate check, and stops at the accepted
dispatch or duplicate branch. For accepted removals it executes the original
`0x2D` case at `0x430710` and inspects the argument at `RemovePlayer` entry.

The verified sequence is an initial slot-2 removal, its server-generated
retry, a new slot-3 removal, a delayed slot-2 duplicate, and a slot-3
duplicate. All **five** packets generate the expected four-byte `0x0F` ACK;
only **two** reach `RemovePlayer`, with slots `[2, 3]`. Feeding the original
client's captured ACK into the server clears its pending retry. The previous
30-entry history and eviction checks also continue to pass.

Evidence is in `evidence/2.9.2/reliable_history_emulation.json` under
`receive_probe`; use the reproduction command in 9.13. The harness verifies
the original executable hash before emulation. Packet initialization/address
setup, Winsock address conversions and ACK transmission are stubbed; it
stops before the `RemovePlayer` body. Wire decoding, sender recognition,
world destruction and rendering are outside this test. No executable bytes
on disk or installed game settings were changed. A successful real-client
test is still required to establish visible despawn and continued play.

### 9.15 Reproducible local runtime and bounded I/O (21 October 2026)

The stand-in now uses validated argument parsing and a named `local-relay`
profile. Its default diagnostic mode remains passive; raw packet logging is
now explicit. See [the local server runbook](local-server.md) for commands,
defaults, overrides and compatibility limits. `station_runtime.py` contains
only the configuration, rotating log writer and legacy TCP list worker;
protocol/gameplay behavior remains in `station_stub.py`.

Default logs allow only metadata and fixed server-generated status fields.
They omit login blocks, handles, addresses and TCP request names. File work
runs off the UDP thread behind a bounded queue, with bounded records and
rotation. The console no longer prints each packet. Tests cover raw opt-in,
redaction, three-file rotation under a 16 KiB test limit, and a blocked log
writer: four records remain queued while 16 excess records are dropped.
This verifies bounded behavior, not a measured throughput improvement.

The TCP listener binds synchronously so startup failures are visible. Its
independent nonblocking loop limits clients to 16, keeps only 142 request
bytes each and applies an absolute three-second request/response deadline.
Tests verify fragmented jobs, truncated jobs, unknown jobs, reset sockets,
capacity rejection/recovery, full notification queues and clean shutdown.
A slow client no longer serializes all other TCP requests.

The runtime publishes immutable server-list snapshots from the arena state.
They report actual admitted population, mode name, fixed map/backdrop and
bound port, and omit unavailable arenas. A live profile test checks population
0 → 1 → 0, unchanged population on duplicate admission, and omission after
49 lifetime admissions. It keeps an incomplete TCP request open during UDP
admissions to verify that channel does not block the relay loop. The Station
login count remained unknown/zero at this stage; 9.16 adds per-client sessions
and active login counts. Account/pilot ownership is still open.

Verification: six runtime tests passed in 5.341 seconds; the 14 existing
protocol tests passed in 43.157 seconds. The original-client reliable receive
emulator also passed after the runtime integration. `git diff --check` passed.
No real-client UI, internet transport, actual file download or simulation
performance validation was performed. No public bind option was added.

### 9.16 Per-client Station sessions and TCP correlation (21 October 2026)

The original `SendRequestTCPData` trace corrects the initial TCP-header
interpretation. The request starts at `CClientComm+0x12E8`; `TCPConnect`
passes length `0x8E` at `0x435894`. String copies target offsets 0 and 64.
Instructions `0x430339..0x430342` copy local player-record offset `0x7B` to
request offset `0x3C`. The job at `0x80` is one byte; `0x4303EB..0x4303F1`
copies a separate record flag at `0x8B` to request byte `0x81`. The original
semantic name of the u32 field is unknown; it is usable for local correlation.

`ReceiveAckConnect` passes the ACK block at payload+13 to `0x49DB20`, which
copies 350 bytes to player+`0x374`. The local player is world+`0xD32AC`, making
that record pointer world+`0xD3620`, the pointer used by TCP request packing.
The stand-in now places a per-session ID at ACK payload+`0x88` (13+`0x7B`).
The header player tag remains 1, independent of this correlation ID.

`tools/emulate_station_request.py` verifies the original executable hash,
executes the original record copy and request-packing instructions, and checks
two distinct u32 IDs plus flag `0xA7`. Both IDs survive unchanged; job 5 remains
5 despite the nonzero flag. Evidence is in
`evidence/2.9.2/station_request_emulation.json`. Allocation/free and post-copy
name/UI propagation are mocked; full ACK dispatch, sockets, rendering and
arena transitions are outside the harness. No executable files are patched.

Station state is now keyed by UDP endpoint. Identical direct/wrapped retries
return the same ID without resetting alias delivery or expiry. A changed
handshake cannot replace an existing session. TCP reads an immutable routing
snapshot and checks the request's ID, source IP and deadline; unknown or expired
IDs receive an empty frame. A successful job 5 queues that ID, rather than a
global notification. The UDP loop rechecks it before delivering the synthetic
pilot list once. It bounds notification processing per loop iteration.

Station sends one-second pings and consumes each matching timestamp at most
once; replies require the known endpoint, 12-byte size and tag 1. Quit/expiry
remove live session state and update the Station login count. TCP traffic and
handshake replay do not refresh the lease. Each session retains only a hash
of its handshake for duplicate comparison. Retired endpoints and IDs are not
reused, with a fixed 64-admission lifetime limit that also bounds retained
retirement state. Capacity/reconnect rejection has no verified UI explanation.

Three session regressions pass, including a real-socket sequence with two
clients on the same IP, distinct IDs, correct alias targets, wrapped retries,
live login counts, unknown IDs, file-state job 14, a nonzero job flag, quit
during a partial TCP request, and one surviving client while another expires.
Deterministic cases cover source-IP mismatch, heartbeat forgery/replay/expiry,
stale notifications, conflicting handshakes and capacity exhaustion. The six
runtime regressions also pass with the corrected header parser.

Final verification: all 23 tests pass (14 protocol in 43.308 seconds, six
runtime in 5.229 seconds, three session tests in 4.294 seconds). Both original
client emulation scripts pass, and `git diff --check` reports no whitespace
errors. The runtime/session suites were repeated after bounding notification
draining; the arena behavior was unchanged by that adjustment.

This is local diagnostic session correlation, not authentication. IDs are
predictable, pilot names are synthetic, and arena admission is not bound to
Station authorization. Alias delivery is best effort. Full original-client
Station heartbeat and return-to-Station behavior remain unverified. Downloads,
pilot ownership, secure transport, reconnect and public hosting remain open.

### 9.17 Bounded ingress, version rejection and capacity (21 October 2026)

Original 2.9.2 `CComm::RecvPacket` pushes `0x200` for `recvfrom` at `0x529E8B`
and for fixed decompression at `0x529ECA`. The Python UDP codec now enforces
both limits and the 509-byte payload bound after reserving type/CRC. Every
predictor pass checks its output before appending beyond 512 bytes. Malformed
compression trailers and optional compression CRC failures raise `ValueError`.
Archive callers retain an explicit separate API/default, so networking cannot
accidentally use the unbounded archive path.

The server handles Windows `WSAEMSGSIZE` without terminating. Its pre-decode
token buckets limit global/per-endpoint work and hold no more than 256 endpoint
entries; the two UDP channels rotate service order. Rate-limit drops are counted
without per-drop disk writes. These are diagnostic bounds, not a public-service
security or throughput claim. See [local-protocol.md](local-protocol.md).

Handshake version fields must match 2.9.2 before admission. The original login
switch at `0x444B8D` maps result 8 to `0x444BAC` (“Incorrect version”), 4 to
`0x444BFC` (capacity refusal), and 5 to `0x444BD4` (invalid login). Failure ACKs
retain the fixed 363-byte layout but zero the player block. Simultaneous arena
admission defaults to eight (`--max-players`, 1..49); rejected attempts consume
no slot. The original lifetime/retirement limits remain.

Six tests cover boundaries, 4,000 seeded malformed/mutated wire cases, expansion
bombs, bad CRCs, rate limits, endpoint-table bounds, and a live socket sending
60 KiB UDP followed by a wrong-version then valid handshake. The server survives,
rejects the version and gives the valid request its first Station ID. Original
2.7.1 compressor comparison remains 36/36 with zero failures after the changes.

### 9.18 Consolidated client preparation (21 October 2026)

`prepare_client.py` composes the existing three fixes/discovery setting rather
than requiring manual undo/reapply ordering. `patch_client.configure` now builds
the known stability image in memory; its hash remains
`87249b8a8ce37684085ad8e62457b6e8f1f9d4a6f5653bcf8dfe11495c1b7f00`.
Preparation accepts only the pristine or normalized known 2.9.2 image. The
hostname field remains 12 bytes, including NUL; no code relocation is invented.
Changing the host preserves the zero-time guard and logger fixes.

The tool records patch version/IDs and exact input, output and backup hashes.
An exclusive first-input backup is never overwritten. Pending metadata plus
same-directory atomic file replacement permit retry or undo after a denied
replacement/interruption. Unrecorded executable drift and corrupt backup data
are rejected. Undo restores the first input even if a wrapper later breaks.
The checked launcher validates setup before starting with the game directory
as cwd; no real launcher execution was performed in this batch.

Ten static dependencies in `config/client-2.9.2.json` were compared to the
hash-pinned original installer and current working copies. The initial whole-
bundle check correctly failed on `SOUNDS.AOA`: the original client expands it
from 1,230,636 to 14,537,627 bytes with decoded WAVs. This is documented runtime
behavior in [assets.md](assets.md), not evidence of corruption. The manifest
therefore labels it mutable and applies presence/size bounds without claiming
runtime hash integrity. Wrapper DLL hashes were independently matched against
the already verified dgVoodoo2 2.87.5 ZIP. The installer/wrapper binaries were
not executed or redistributed.

Seven tests use temporary executable copies for composition, host changes,
idempotence, exact undo, original asset checks, binary/backup/wrapper conflicts,
missing dependencies and interruption recovery. The user's executable and
assets were only read. Setup-script syntax and byte-level tests are distinct
from clean-machine OCX registration, graphics and real UI acceptance, still open.
Commands and limitations: [client-setup.md](client-setup.md).

### 9.19 Complete safe-prefix state tracking and downstream recovery (21 October 2026)

`relay_motion.py` decodes all 16 field groups in the safe prefix consumed by
`0x495330..0x49585F`. It preserves absolute/signed16/signed8 precedence, float32
rounding and the scale at `0x59820C` for the two final vector groups. Unknown
physical meanings are named by destination offsets; no units are invented.
Every float component is checked, not only position/velocity. A malformed or
non-finite update is discarded before changing stored state. An unseen delta
base remains unknown until an absolute sample arrives.

Forwarding and late joins now use absolute observations. One-second snapshots
repair missed downstream updates even when the subject stops sending input.
The `+0xF0` integer scalar also calls `0x4BE950`, which sets a client timer to
current tick+3000; it is therefore forwarded only on incoming updates and
excluded from periodic/late-join refresh. Its gameplay meaning remains unknown.
Expired/departed peers are removed before refresh and cannot leave a cached
state announcement behind.

Original-code emulation compares every destination byte in 300 accumulated
updates and 200 recovery/duplicate absolute refreshes. Five deterministic state
tests and a real UDP test verify truncation/non-finite rejection, unknown bases,
scales, periodic recovery, capacity denial without slot consumption, and
surviving state after invalid input. The first socket-test attempt used a
three-second read timeout, which raced the three-second bootstrap; the corrected
test polls until a five-second deadline. No runtime timing change was needed.

This does **not** recover lost/reordered/duplicated upstream client deltas or
provide authoritative physics. A sequence/generation contract and complete
world state remain necessary. Original renderer behavior under the new refresh
path has not been tested. Evidence: `motion_state_emulation.json`; field table
and bounds: [local-protocol.md](local-protocol.md).

### 9.20 Limited local guest ownership and arena binding (21 October 2026)

The opt-in `local-guests` profile assigns unique pilot names and random nonzero
32-bit tickets. All IDs/endpoints retain the existing process-lifetime nonreuse
rule. The Station ACK and alias list carry the assigned pilot, and arena player
announcements use it instead of a slot-derived name. The legacy diagnostic and
local-relay profiles remain available for isolated direct arena experiments.

The original `RequestGameserverConnect` at `0x42FFA2..0x42FFC5` passes the saved
ACK block (`CClientComm+0xF5C`) to `SendConnectRequest`. The latter copies all
350 bytes to request+31 at `0x486EDF..0x486EEE`, then writes the version fields.
`emulate_station_request.py` now executes that construction in addition to TCP
packing; both test IDs survive unchanged at arena request+`0x9A`. Full ACK/UI/
socket transitions remain outside the isolated harness.

Before assigning a player tag, guest admission checks ticket, source IP,
assigned name, expiry and any existing arena endpoint binding. A second socket
cannot replace an already bound ticket. Valid arena heartbeat/movement extends
the owning Station lease; redundant Station pings stop while bound. Station
quit/expiry revokes the arena admission, including pending bootstrap. Arena
departure releases the binding and restarts Station inactivity. Retired arena
endpoints still cannot reconnect; full return-to-Station behavior is not claimed.

The socket regression verifies unaffiliated rejection, two distinct guest
names/tickets, correct aliases, wrong-name rejection, takeover rejection,
duplicate admission, Station revocation before bootstrap, the surviving
player's assigned name and lease renewal beyond the original Station deadline.
Deterministic tests cover ticket collision/zero avoidance, stale IDs and lease
binding/release. This is limited local guest ownership, **not modern account
authentication**: tickets are only 32 bits and unencrypted, and a captured unused
ticket can be impersonated. Public ingress remains unsupported.

Final expanded local gate: **44 tests in eight suites and five original-code
emulators passed**, with no skipped tests. The independent codec comparison
also passed 36/36 cases, PowerShell setup syntax parsed without execution,
Python compilation passed, and `git diff --check` found no whitespace errors.
`evidence/2.9.2/local_gate_20261021.json` records check durations, exclusions and
implementation source hashes. This evidence does not complete the internet
roadmap: ordered world loading, reuse/reconnect, authoritative combat, collision,
content delivery, hosting and real-client/external acceptance gates remain open.

### 9.21 Inbound reliable duplicate suppression (21 October 2026)

Before this step, every inbound `0x1B` copy was ACKed **and** its inner
message dispatched. The current handlers happened to be idempotent: a
handshake repeats its reply, quit is a no-op once departed, a heartbeat tick
is consumed once, and wrapped movement is ignored. That was a property of
each handler, not of the transport, and would not hold for future combat or
award messages.

`InboundReliable` in `tools/station_stub.py` now keeps the last 64 sequence
IDs per (listening port, endpoint), for at most 512 endpoints (LRU). Every
copy is still acknowledged, because the sender may have lost the earlier
ACK. A repeated ID is dispatched only for `0x0A`: the handshake path is
idempotent and must answer again if the first `SAckConnect` was lost. Other
repeats are dropped and logged as `reliable_duplicate`. The shutdown line
reports the count. History is kept after departure, because endpoints are
never reused within a run. The window mirrors the client's own fixed-count
receive history (30 IDs, [9.14](#914-original-client-reliable-receive-path-verification-21-october-2026)).
Sequence zero is not pre-filled, because the client's send-side counter
origin has not been recovered.

Tests: a unit test covers channel/endpoint isolation, zero, window eviction
and the endpoint bound. A live Station socket test sends three copies of a
wrapped quit from one endpoint and one copy with the same ID from another.
It verifies four ACKs, two departures and exactly two counted duplicates.
The existing wrapped-handshake retry test still receives repeated
`SAckConnect` replies without restarting flight. Gate: 46 tests in eight
suites and five original-code emulators passed
(`evidence/2.9.2/local_gate_20261021_dedup.json`).

Limits: replays older than 64 newer IDs, or from an endpoint evicted from
the table, are treated as new, so handlers must stay idempotent. The
original client's reliable send path was not exercised, and no real-client
retry was observed. This does not implement outbound reliable delivery
beyond removals, or slot reuse/reconnect.

### 9.22 Server hang-up (`0x3E`), client grace timers and shutdown (21 October 2026)

Static analysis of the 2.9.2 client only (`tools/explore.py`); nothing here
was observed in a running client. It answers whether a server can tell a
client to disconnect cleanly before shutdown.

**`0x3E` is a silent "stop talking" command, not a disconnect notice.** The
receive case at `0x430A03` logs `being commanded to hang up. doing it` and
clears one byte, global `+0xD3628`. It does not read the payload (the 2.7.1
send site uses four bytes). That byte is field `+0x37C` of the server peer
object at global `+0xD32AC`. Vtable `0x598258` slot `+0x10` (`0x49D750`)
returns it, and the client calls that slot as its "server alive" test before
23 send/UI paths (for example `0x4857B0`, `0x4858B0`, `0x48A460`; dialog
controls `0x485`/`0x473` at `0x458C2F`). Only three instructions write it:

- `0x430A1E` (`0x3E` received): set to 0, with no UI message.
- `0x4315E8` (`GetWhoSentServer`): any later datagram from the server
  endpoint sets it to 1, logs `Back from the dead` and hides the
  not-responding indicator (`0x452A50`).
- `0x433B98` (client timer case at `0x433B3E`): if the server is alive and
  silent longer than its grace value, set to 0 and show
  `Server Not Responding` (`0x452A20`, string resource `0x23`).

After `0x3E` and silence, the client therefore stops sending and never shows
`Server Not Responding`, because the timer only fires while the flag is set.
The player gets no explanation. **Do not send `0x3E` on shutdown.** It might
quiet a client during maintenance, but any later packet revives the peer.

**Client grace timers.** The comm constructor (`0x42EB30`) defaults
`+0x11CC` to 1000 and `+0x11D0` to 7000. `0x42F0E0` then reads named
parameters `CLIENTWATCHDOG` and `CLIENTGRACE` from a compiled table at
`0x5D8110` (128 entries of a 64-byte name plus a float at `+0x40`, read by
`0x4C1400`). The table gives `CLIENTWATCHDOG` 1000 and `CLIENTGRACE` 16000.
The grace is compared with the time since the server peer's last receive
(`+0x5A4`) against time global `0x5E8E5C`. Milliseconds are likely but
unverified, because that time source was not traced. The ~16-second figure
below carries the same caveat. Other entries include `WATCHDOGTIMEOUT` 1000,
`STATIONTIMEOUTWATCHDOG` 15000, `WATCHDOGGRACE` 40000,
`FLIGHTLOOPWATCHDOGTIMEOUT` 10000 and `ArenaUnloadTimeout` 300000.

At startup `0x4A2770` loads `params.aoa` from the working directory through
`0x4C11F0`. That parser reads `NAME value` lines, skips `#` comments and
stores the `atof` value into the table (`0x4C1329`). The 2.9.2 install does
not ship this file. It is a plausible client-side way to lengthen internet
grace periods, but it is untested and should not be distributed until a real
client confirms it. Server `0x6D SetParam` (`0x4A8010`) accepts only
`launchcount`, `minlaunchdist` and `turretocv`, and logs other names as
`NOT UNDERSTOOD`, so a server cannot change these timers.

**Resulting shutdown definition.** There is no recovered message that
returns a 2.9.2 client from flight to Station. The honest current behavior
is: the server closes its sockets, and each client shows
`Server Not Responding` after about 16 seconds of silence. The stub already
does this. `SetupWorldMode` (`0x44B900`) is entered from the Station
dialog's arena login (`0x4563B0`). It is not an exit path. A
server-initiated return to Station, or an end-of-match transition, needs
further client analysis or the maintained protocol change in
[first-playable-release.md](first-playable-release.md).

### 9.23 Real-client check (21 October 2026)

Real, prepared 2.9.2 clients on one Windows 11 PC were run against the local
stub (`local-relay`). Scratch copies of `game/2.9.2` were used, recorded with
`prepare_client.py prepare`. Login, Station Play and Alt+Q were driven through
window messages; the user flew the earlier rounds. Derived results are in
`evidence/2.9.2/real_client_check_20261021.json`. Raw captures stay in
ignored `work/realcheck-20261021/`.

**Regression found and fixed: TCP close hangs the client.** The bounded TCP
worker from 9.15 closed each data connection after its reply. The 2.9.2 client
reuses that connection for its next job ("already connected"). When the server
closes it, `ShutdownTCPBySocket` (`0x4366F0`) sets the TCP queue mutex
`0x5E6700` to 1 and never clears it. Job requests (`0x4300F0`) spin on that
mutex only while a transfer is in progress. Station-dialog setup queued a job
while the server-list job was in flight, so the UI thread spun on
`waiting for xfer lock` forever. The in-flight job's connect notification was
never serviced, and no Station screen appeared. The earlier server held each
connection about a second, so the client reused it and never reached this
path. That is why older runs worked and the synthetic tests could not catch
it. `StationTCPServer` now keeps a connection open across jobs while the
Station session its requests resolved to is alive. Afterwards one connection
served jobs 14, 5, 18, 6 and 11 in order, and every later login reached Station.

**One UDP socket for Station and arena.** Each client sends to Station 5033
and arena 5031 from the same source port. After arena entry, its Station
heartbeat replies carry the arena slot (for example 2) instead of 1. The
Station tag check therefore expired live sessions after the peer timeout.
Station now validates only the single-use issued tick.

**Background-window stalls.** When the user switched between two clients, the
inactive one stopped servicing UDP and later drained its queue. Heartbeat
replies arrived 9–37 s late (about 38 s inactive) and 35–63 s late (about
64 s inactive), so the 30 s timeout expired both. Clients driven only by
posted messages did *not* stall while not foreground. The triggering
condition is unresolved (user focus changes and dgVoodoo mouse capture are
candidates). Reliable removal retries now back off from 0.5 s to 4 s until
the peer timeout. Previously they sent five copies in 2.5 s, which retired an
observer for a stall it would otherwise survive. The modernization item on
inactive/minimized clients stands.

**Reliable messages from the real client.** The Station/arena sequence starts at 1
(observed inner types `0x80`, `0xAD`, `0x6E`, `0x1D`, `0x6E`, `0x3C`). No
duplicate copies were seen, so the 9.21 deduplication was exercised only by
synthetic tests.

**Quit, despawn and relaunch.** Alt+Q in flight is key command 91 (`Quit
Game (no prompt)`, handler `0x4506D0`, jump table `0x4508A4`). It sends `0x4E`
three times to each of Station and arena within 41 ms. The server logged
`client quit` for both. The remaining observer acknowledged the reliable
removal (`0x0F`, sequence 4) 39 ms later, and its active player table no
longer held the departed slot. Visible rendering was not captured, because
PrintWindow returns black for the DirectX surface. The quitting client then
started `AoAClient.exe autologin` through a helper (the quit path names
`renexe.exe` and `AoAClient.ex_`) and logged back into Station by itself.
This corrects 9.22: the client's return to Station after an arena is a
restart with auto-login, not a server message. Closing the window from the
taskbar sends no quit; the server notices only through the timeout.

**Grace timer measured.** With the server killed, the server-alive byte
(`+0xD3628`, 9.22) cleared **16.2 s** later in a default client and
**5.8 s** later in a client whose folder held `params.aoa` with
`CLIENTGRACE 4000`. `CLIENTGRACE` is therefore milliseconds, and
`params.aoa` overrides it. The remainder is time since the last 1 s ping plus
the 1 s `CLIENTWATCHDOG` tick. A background client still timed out on
schedule.

**Unexplained crash.** A user-launched client sharing `game/2.9.2` with a
hung second client crashed (`0xC0000005`, `ntdll+0x4FC65`) about 0.2 s after
its arena ACK, before any other server message. Later the same day a
patched client in its own folder crashed the same way (`0xC0000005`,
`ntdll+0x5019E`) about 0.3 s after `On3dGfxInitialized`, as the second
client to join. That is 2 crashes in about 12 arena joins, so the shared
folder was not the cause. This intermittent heap corruption on arena join is
open and needs a debugger trace (`tools/crashdbg.py`). One client per folder
is still advisable.

**Windowing.** dgVoodoo's DirectX `Resolution = 640x480` with windowed output
gives a 640×480 window. A DPI-unaware query at 125% scaling reports 512×384.
`CaptureMouse = false` lets two windows sit side by side.

Gate after these changes: 47 tests and five original-code emulators passed
(`evidence/2.9.2/local_gate_20261021_realclient.json`).

### 9.24 Background-client network stall and fix (21 October 2026)

This explains the 38–64 s stalls in 9.23. Static analysis of the 2.9.2 client:

- In flight, UDP is read only from the per-frame path. The comm update
  `0x433990` calls the receive loop `0x486300`. `SetupFlightMode` ends the
  1-second Station wakeup timer and installs the flight loop `0x44AFD0`.
- The idle loop `0x407F50` runs a frame (`0x44AD60`) only while the
  "app active" byte `0x5E6E28` is set. The window procedure `0x4450D0` sets it
  from `WM_ACTIVATEAPP` (`0x1C`).
- On `WM_ACTIVATE` with WA_INACTIVE, the same procedure starts the wakeup
  timer (`SetTimer` ID `0x23434`, interval `0x42` = 66 ms, callback
  `0x446E70`). Its handler, `0x4529C0`, ends that timer on reactivation.
- The callback runs the frame only if the graphics object's exclusive-mode
  byte (`+0x24C5`, set by `0x552B60`, "IntiD3D for exclusive mode") is clear.
  Otherwise it only calls `0x4857B0`. The client always initializes exclusive
  mode; dgVoodoo presents it in a window, but the flag stays set.

So a deactivated flying client stops reading UDP until it is activated again.
Clients driven only by posted messages had never been activated, so they never
received a deactivation. That is why they kept working in 9.23.

**Reproduction without changing the user's focus.** Sending a flying client
`WM_ACTIVATE(WA_INACTIVE)` and `WM_ACTIVATEAPP(FALSE)` for 15 s stopped
its arena heartbeat replies for 16.1 s. They then arrived up to 15.1 s late.
The other client's maximum gap stayed at 1.08 s.

**Fix.** Patch `background-network-v1` replaces the callback's `jne` at
`0x446EAF` (`75 34`) with two NOPs. The 66 ms timer then runs the normal
frame while the window is inactive. Under the same 15 s deactivation, the
patched client's maximum heartbeat gap was 1.3 s and its maximum lag 0.33 s.
It stayed responsive and kept both players in its table. `prepare_client.py`
now applies it (patch version 2) and `check` requires it. The tested binary
is the prepared localhost output,
`506a5c47cf67b2b8f09100c319776b5f6d3fbadc350cd544c85df4fb7fbb8e0e`.

Limits: tested only under dgVoodoo windowed output, with simulated activation
messages and one 15 s window. A real focus change by the user, minimizing,
long inactivity and native exclusive fullscreen (where surfaces can be lost)
were not tested. While inactive the client renders at about 15 Hz, which
costs some CPU/GPU.

### 9.25 Combat protocol survey and gun table (21 October 2026)

Static analysis of the 2.9.2 client, plus one live attempt. This is the
recovery groundwork for damage modelling; nothing here is implemented in the
server yet.

**Firing guns is player state, not a message.** Key command 1 (`Fire primary
weapons`, Space or a mouse button; registered at `0x441363`) runs `0x4B0690`.
That function sets the weapon-group mask `0x5E7C98` and status bit `0x40` in
player `+0xF4` (`0x20000` on another branch), then requests comm updates
(`0x488B30`, reasons 3 and `0x15`). Correction from 9.26: the status flags
were already relayed (they are the mask `0x400` field). The per-gun fire
levels travel in the `0x10000000` block, which the relay dropped until 9.26.
Command 2 (`Fire Missle`, `M`) requires a locked target and sends
`SendFireMissile` (`0x2A`, 146 bytes).

**Combat messages and contracts recovered.** The client's own log strings give
the names:

| Type | Direction | Contract |
|---|---|---|
| `0x2A` | client ↔ server | `SendFireMissile` 146 bytes / `OnReceiveMissileLaunch` (`0x4B16B0`) |
| `0x30` | client ↔ server | `SendImpactMissile` 21 bytes / `ReceiveMissileImpact` (`0x433FC0`) |
| `0xB2` | client → server | `SendFireTorpedo` |
| `0x48` | client → server → target | Ship collision impulse: u32 source tag, u32 target tag, float3 (20 bytes, unreliable; sent from collision routine `0x4B4340`). On receipt the target tag **must equal the local player's tag or the client calls `_exit(2)`** (`0x431EA0`). Forward only to that target. |
| `0x3A` | server → client | 16 bytes: u32 tag hit, float3. The client logs `I hit [%s] (now {x,y,z})`, sets its own position to the float3 and processes the hit (`0x4AD220`). A server-authoritative collision correction. |
| `0x41` | server → client | `SetGunDamage`, 10 bytes: u16 gun level, f32 damage (stored as u16), u32 second value. Overwrites the static gun table below. |
| `0x3D` | server → client | `ReceiveWYSIWIGDamage`, 3 bytes: u8 player slot, u8 count, u8 value; applies to that player's gun systems (`0x431B10`). Semantics only partly read. |
| `0x37`, `0x49`, `0x52`, `0x56`, `0x3B` | various | `SendIHaveDied`; `Send/ReceiveDisableObject`; `ProcessHitFlag`; `ShiftScore`; "Server commanding a ship reset" (`0x4A42E0`) |

`0x34` (3 bytes) is not combat. The position-update receiver sends it to ask
for an unknown object.

**Static gun table.** `tools/gun_table.py` decodes it to
`evidence/2.9.2/gun_table.json` (original EXE hash checked). Reader
`0x4DA990`: level *i* has a 36-byte record at `0x5D62CC + 36·i`. Field +6 is
per-shot damage, the field `SetGunDamage` overwrites. The level-to-id switch
at `0x4DAAC2` gives ids that match the `.Sco` gun names:

| Level | Id | Damage |
|---|---|---|
| 1 | 250 | 7 |
| 2 | 280 | 14 |
| 3 | 310 | 21 |
| 4 | 360 | 28 |
| 5 | 410 | 35 |
| 6 | 460 | 42 |
| 7 | 550 | 70 |
| 8 | 650 | 90 |
| 9 | 750 | 110 |
| 10 | 850 | 130 |

The Ym Khtat's four `Gun310` therefore deal 21 per shot and its two `Gun-360`
deal 28, against the system hit points from the `.Sco` configs
([assets](assets.md)): Hull 40, Engine 30, Power Plant 30. The other eleven
fields are kept raw with their weapon-object destinations. Their meanings
(for example energy, range, projectile speed, refire) are not established.

**Live attempt.** Space and `M` posted to a flying client changed no message
types. This is consistent with gunfire living in `0x1F` status bits and with
missiles needing a lock. Live aimed fire with real input was not captured.

**What a damage model needs next.**
1. Decode the `0x1F` status block safely enough to relay firing state
   (done in 9.26).
2. Find who decides gun hits online (9.26: the victim's client). The client resolves `CollideMissile`
   locally only when offline (section 5), and nothing in the send list
   reports a gun hit, so the server likely computed hits from fire state and
   positions.
3. Name the remaining gun fields and the `.Sco` system parameters.
4. Capture real aimed fire between two clients to confirm 1–2.

### 9.26 Victim-side damage, gun-state relay and death report (21 October 2026)

Live test: two real prepared clients on one PC, firing triggered by a posted
Space key, effects read from client memory. Derived results are in
`evidence/2.9.2/combat_live_20261021.json`. This corrects 9.25 on how firing
travels.

**Firing replication.** `SendPositionUpdate` (`0x434730`) passes `player+4`
as the decoder's kinematic base. So the mask `0x400`/`0x800` field that
`local-protocol.md` called the "`+0xF0` control scalar" is **player `+0xF4`,
the status flags**: bit `0x40` is set while guns fire. The safe prefix
already relayed it. Each gun's fire level travels in a second block, mask
`0x10000000`, directly after the prefix (decoder `0x49585F`). Its layout is
a u8 header (low 7 bits count, high bit to player `+0x1A4`), then count ×
(u16 system index, u8 value). The receiver stores value × 0.1 in that gun's
`+0xFC` (`0x4DACF0`). In the live capture, guns 2–7 report 15 while firing
and 0 otherwise.

The decoder also increments its own 5000-entry counter array (decoder
object `[ptr, count]` at comm `+0xF8C`) at the packet's index, with no
bounds check. `relay_motion` now relays this block only when it is well
formed and every index is below 128; otherwise only the block is dropped.
`tools/emulate_movement.py` runs the original decoder against a 128-entry
array followed by guard bytes. A relayed block for guns 2–7 plus index 127
is consumed to the exact length, only those counters change, the guard
survives, and the header flag lands at player `+0x1A4`. During a live burst,
the other client read the shooter's guns at `+0xFC` = 1.5.

**Damage is computed by the victim's client.** With spawns 300 units apart
along +z (`--spawn-axis z --spawn-spacing 300`), B fired at A for 5 s. A's
own systems (current HP at system `+0x88`) fell:

| System | Before | After |
|---|---|---|
| shield (10) | 107 | 0.32 |
| Hull (12) | 40 | 0 |
| Engine (11) | 30 | 27.03 |
| ECM (8) | 5 | 3.03 |
| Scanner (9) | 5 | 4.02 |
| two guns | 2 | ~1.0 |

Internal Hull (13) stayed at 12. B's view of A's HP did not change, and no
damage message was sent. During a further 10 s burst, A sent **`0x37
SendIHaveDied`** once. Its 4-byte payload is the killer's tag (`0x80010002`,
the shooter), sent unreliably from `0x486AD0` (caller `0x4A5440`). A then
reset its systems to full by itself. B sent nine `0x48` collision impulses at
A during that burst; the stub ignores them.

This matches the WYSIWYG ("what you see is what you get") message names. The
original design trusts each victim's view of incoming fire. A server
therefore relays fire state, receives death reports with the killer's tag,
and owns scoring, death broadcast and respawn policy. It does not run
hit-scan itself. This is a fairness and cheating limitation of the original
protocol, to be weighed against the authoritative-combat goal in
[first-playable-release.md](first-playable-release.md).

**Not yet handled by the server.** `0x37` (no score, no death broadcast or
`0x38`/`0x56`/`0x42` updates), forwarding of `0x48` to its target, missile
messages, and respawn position policy. Whether the victim's ship explodes on
other clients without a server message was not observed.

**Stability.** Another client crashed on arena join (`0xC0000005`,
`ntdll+0x4E1EA`) while it was the first player in the arena. That is the
third such crash today; see 9.23.

### 9.27 Death relay, kill count and respawn position (21 October 2026)

The stub now acts on the combat messages from 9.26 (`--experimental-relay`
only). Tested with two real prepared clients; still diagnostic, not
authoritative combat.

- **`0x37` death report** (victim → arena, u32 killer tag). `DeathLedger`
  accepts one report per victim per 2 s, because `0x37` is unreliable and
  could arrive as a duplicate. A killer that is not another loaded player
  (self, unknown, object tag) is recorded as 0. The ledger counts kills and
  deaths; the totals print at shutdown and each death is logged as
  `player_died`.
- **`0x38` death notice** (killed tag, killer tag) goes to every *other*
  loaded player. In the client it runs `DoHaveDiedTrivia` → `0x4A5440`
  (`0x4A51C0`). It is never sent to the victim, because `0x4A5440` on the
  local player sends `SendIHaveDied` again (branch at `0x4A5544`).
- **Respawn position.** After dying, the victim resets its systems and
  places itself at the origin. The stub immediately sends the victim `0x24`
  with its assigned spawn point, as at flight entry.
- **`0x48` collision impulse** is forwarded only to its target, and only when
  the source tag is the sender's own, the target is another loaded player,
  the payload is 20 bytes and the vector is finite. `collision_target`
  enforces this, because a client `_exit(2)`s on a mistargeted impulse.

Live result (`--spawn-axis z --spawn-spacing 300`): B fired at A. A died
about 8 s into the burst, the server logged it with a valid killer, and A
was back at its spawn (z=300) at the next sample. After 30 s of continuous
fire B's guns did no lethal damage. A recharge pause and a fresh 15 s burst
killed A again at about 9 s, and A respawned at z=300 again. The likely
cause is gun energy, which is unconfirmed. Both clients stayed responsive.
B's player table kept A active throughout. Whether the observer shows an
explosion was not checked: PrintWindow is black and the client writes no
log while flying.

Unit tests cover collision validation (forged source, size, self/unloaded/
object target, non-finite vector) and the ledger (repeat suppression,
invalid killers, counts).

Not done: score display to clients (`0x56` ShiftScore, `0x42` player
record), match end, spawn protection, the five-second respawn delay proposed
in the release specification, and reliable delivery of `0x38`.

### 9.28 Station pings during arena entry (21 October 2026)

**Status when written: the arena-join crash was not fixed and its cause was unknown. Resolved in [9.29](#929-arena-join-crash-unterminated-archive-text-21-october-2026).**
About one join in five crashed today with an access violation inside `ntdll`
heap code, a fraction of a second after `On3dGfxInitialized`, before any
server flight message. The fault offsets were `0x4FC65`, `0x5019E`, `0x4E1EA`
and `0x50806`. It happened to first and second joiners alike, and to clients
in their own folders.

What was ruled out or tried:

- **Guard heap** (`crashdbg.py --guard-heap --guard-continue --guard-reuse`).
  One debugged join reached flight without any guarded write or
  use-after-free. It reported only reads just past block ends: the TCP
  `<in>data[...]` log line at `0x435B80` prints 12 bytes of every reply,
  including 8-byte ones, and graphics code at `0x558697`/`0x558C67` reads
  past texture buffers. Reads cannot corrupt the heap. The crash did not
  occur in that run, so this is no proof either way.
- **The 5-second TCP keepalive** (`KeepAliveThread`, job 4). Two crashed
  joins had no TCP job within −1.5 to +3 s, so it is not the trigger.
- **Station pings on the shared socket.** The real client uses one UDP
  socket for Station and arena, and `BouncePing` (`0x486C20`) writes ping
  history into the record of the player it identifies as the sender, while
  the local player record is re-allocated at the arena ACK. The stub now
  **binds a Station session to an arena endpoint with the same address**:
  Station stops pinging that socket, the Station lease follows arena
  activity, and quit or expiry on either side ends both. This is reasonable
  behaviour on its own merits, and `test_shared_socket_binds_station_to_arena`
  covers it. In an automated series of 15 single-client joins
  (`work/realcheck-20261021/trials4/`), 13 reached the arena and **1
  crashed** (offset `0x50806`). One never left Station because Play was
  pressed before its server list arrived. That compares with about 4 crashes
  in 17 joins earlier, which is not a statistically meaningful improvement,
  and the crash still occurs. The ping hypothesis does not explain it.

Next: catch the second-chance exception under `crashdbg.py` *without* the
guard heap across a trial series, to get the `AOACLIENT` caller of the heap
operation that fails. Alternatively enable WER LocalDumps on a scratch copy;
that is a machine setting the user must approve. Then trace the corrupting
write from that allocation.

### 9.29 Arena-join crash: unterminated archive text (21 October 2026)

This resolves the intermittent arena-join crash left open in 9.28. The bug is
in the original 2.9.2 client and is now fixed by a versioned client patch.

**Capture.** Joins were driven with each client under `tools/crashdbg.py`,
without the guard heap. Three of twelve crashed, all identically:

1. On arena entry, the target-window loader `0x502B80` reads `tgtwin2.cfg`
   from `hud.aoa` (archive read `0x5290E0`) and passes it to a tokenizer
   (`0x527860`). The tokenizer splits on `" :,\t\n\r"` and copies the input
   as a C string (`0x526FA0`).
2. The archive data comes from `CCompress::Decompress` (`0x52A630`). Its
   final step allocates **exactly** the decompressed size (`0x52A6E8`),
   copies the data and returns it with **no terminating NUL**.
3. When the heap byte after the 681-byte block is non-zero, the copy and the
   tokenizer run into neighbouring heap data. The token array is sized from
   the result (`0x527D29`), so MFC `operator new` fails and throws
   `CMemoryException`.
4. Unwinding `0x502B80` calls a destructor (`0x505F7E`) that frees a
   "pointer" consisting of config text. `esi = 0x69777467` is "gtwi" from
   "tgtwin". The access violation in `ntdll` heap code
   (`ntdll+0x50806` here; other offsets earlier) follows.

The earlier guard-heap run (9.28) had flagged step 2 as a one-byte read past
a 0x2A9-byte block at `AOACLIENT+0x126FD3`, allocated at `0x52A6ED`. It was
misfiled as harmless. That explains the intermittency: the crash depends
only on what happens to follow the block in the heap.

**Fix: client patch `archive-terminator-v1`** (`tools/archive_terminator.py`,
composed by `prepare_client.py`, patch version 3). The 10 bytes at
`0x52A6E3` (`mov ecx,[esp+10]; push ecx; call new`) jump to a 24-byte cave
at `0x58B440`. The cave allocates size + 1, stores a NUL after the data and
resumes at `0x52A6ED`. Binary callers ignore the extra byte. `check` requires
the patch. The prepared localhost image is
`782d1825e944d564e55034e34d52968ae5fc1e2ee22148a54c17c8d4cf2c1b95`.

**Verification.**
- `tools/emulate_archive_terminator.py` runs the original and the patched
  decompressor on a config-sized body compressed by `aoapack`, with the heap
  after each block pre-filled with `0xAA`. Both return identical data. The
  byte after it is `0xAA` originally and `0x00` patched
  (`evidence/2.9.2/archive_terminator_emulation.json`). It is part of
  `verify_local.py`.
- Preparation tests cover composition, upgrade from version 2, and rejection
  of altered site or cave bytes.
- **25 of 25 real arena joins succeeded with patched clients** (fresh
  copies g–j; `work/realcheck-20261021/trials5/`). Before the fix, 7 of
  about 40 joins crashed today. At the old rate, 25 clean joins happen by
  chance less than 0.1% of the time.

Other callers of `0x52A630` (TCP job bodies, other archive reads) also get
terminated buffers now. Uncompressed archive entries go through a different
path and were not changed. The Station/arena socket binding from 9.28
remains, as ordinary behaviour.

### 9.30 Scoreboard, match limits, and why missiles need teams (21 October 2026)

Static analysis of the 2.9.2 client plus live tests with two real patched
clients (posted keys, memory reads).

**Scoreboard: done and verified.** The HUD shows a player's record fields
`+0x7F`/`+0x83` as "kills/deaths" (`0x47B020`, format `%d/%d`) and `+0x4E`
as score. The record is player `+0x374`. The client never increments its own
kills, so the server supplies them:

- **Own record: `0x42`** (handler `0x4AFC00` → `0x49DB20`). It replaces the
  local player's 350-byte record with payload+4. The stub sends the killer
  and the victim their own handshake record with the server's kills and
  deaths and the client's last reported score. A record is never sent to
  anyone else, because it is the client's login block.
- **Other players: stats inside `0x1F`.** Mask `0x80000000`, submask
  `0x100`: 12 bytes (i16 kills, i16 deaths, i16 rating to player `+0x328`,
  u16 unused, i32 score), applied by SetStats `0x493670`. A position update
  about the receiver itself is rejected ("receive pos update for myself"),
  which is why own stats need `0x42`. The other submask parts write through
  pointers the receiver leaves unset. The relay therefore never forwards a
  client's block; it emits submask `0x100` alone in every snapshot.
  `emulate_movement.py` runs the original decoder on such a block: exact
  length consumed, kills/deaths/score in the stats struct, valid flag set,
  rating at ctx `+0x2E`.
- Real clients report their own stats in submask `0x200` (30 bytes: rating
  at +4, score at +26). `relay_motion.client_stats` reads rating and score
  from it (or from `0x100`). Kills and deaths stay server-owned
  (`DeathLedger`).
- `0x56` ShiftScore (u32 tag, i32 delta to `+0x4E`, base dispatch) exists;
  the stub does not use it.

Live: after B killed A, **B's HUD record showed 1/0 and A's 0/1, and each
client showed the other correctly**. Rating relayed (A saw B at 1.0). Scores
stayed 0: the client's own accrual (`CGunshot::DoFromSelfTrivia`, governed by
`MINTARGETBOUNTYBEFORESCOREACCUM` etc.) did not trigger in these tests.

**Match limits: done and verified.** `Match` with `--kill-limit` (default
20) and `--time-limit` (default 600 s, 0 disables either). A match starts
when the first player is loaded and resets when the arena is empty. At a
limit the server sends every loaded player an arena text (`0x21`, 294 bytes,
u16 kind 3 at +3, text at `+0x25`; receiver `0x4348E0` → `0x446E50`) with the
winner or a tie. It then resets kills/deaths, sends fresh own records and
announces the next match. Live with `--kill-limit 1`, the first kill ended
the match 3 ms later. Both clients' scoreboards returned to 0/0 and both
stayed responsive. The on-screen text was not captured (PrintWindow is black).
These limits are the release specification's proposed rules, not recovered
ones. No recovered server message sends clients back to Station (9.22, 9.23).

**Spawn protection and respawn delay: not implemented.** The client's
invulnerability is a *toggle*: base type `0x81` (`ToggleNodam`, handler
`0x4AE4E0`) flips player `+0x240` and prints "you are invulnerable" / "you
are no longer invulnerable". Sent unreliably, one lost packet inverts the
state for the rest of the life. Sent reliably, it spends two of each
observer's 30 duplicate-history IDs per death (9.13). The victim also
respawns itself immediately, and no hold-dead message was found. Both
therefore wait on the reliable-delivery decision.

**Missiles: blocked on teams.** Key commands are `0x1A` Target nearest (G),
`0xA1` Target nearest Hostile (J), and 2 Fire Missile (M). The Ym Khtat
carries racks IIB a/b and IIIB a/b (systems 14–17). The missile handler
needs the lock state at `world+0xD3440` to have `+0x108` set. Neither G nor
J produced a lock in 8 s with the target 300 units ahead, and no `0x2A` or
`0x30` was sent. Hostility comes from teams. Both `0x50` ObjectToTeam
(46 bytes: tag, team id, u32, team name at +`0x0C`, flags at +`0x2C`/`0x2D`)
and the `0x26` player load (team id at +`0x40`, name at +`0x2C`) feed
`0x4AD590` → `CGameRuleHdlr::AddToTeam`. A trial giving every player its
own ad-hoc team crashed the joining client in `MSVCRT+0x7E6DE` about 3 s
after its arena ACK, when the team data arrived. It was reverted.
Teams evidently need definitions from scenario or game-rule setup
(`CGameRuleHdlr::AddTeam`, `0x4B6380`), which is the next thing to recover.
Missile relay (`0x2A` launch 146 bytes, `0x30` impact 21 bytes) is not
implemented.

### 9.31 Teams fixed (opt-in); missiles need a loadout (21 October 2026)

**Team crash explained and fixed.** A joining client running under
`crashdbg.py` faulted in `msvcrt` formatting `%s` from address `0x244`, the
name field of a null player. The caller is the `0x50` ObjectToTeam handler
(`0x432100`, return `0x432207`). For the local player it treats payload+8 as
the **team leader's tag**, stores that player as the team's leader (team
`+0x30`) and prints "Wingleader: <leader name>". The 9.30 trial sent 0
there, so the leader was null. `object_to_team` now sends the player's own
tag as leader (free-for-all: everyone leads their own team).
The first joiner survived the earlier trial only by luck of message order.

**Teams, opt-in.** `--experimental-teams` (relay only; off by default) puts
team id/name in every `0x26` player load (+`0x40`/+`0x2C`) and sends each
joining player its own `0x50`. Team records live in a list at `world+0xDEF40`
(32-byte name, id at +`0x20`, next at +`0x2C`). Live with two fresh patched
clients, **both joined without crashing**. Each saw two teams: the other
player's (named from the player load) and its own, which showed the default
name "bot" because `0x50` does not apply its name. This is only two joins,
hence opt-in. Unit tests check the leader field and that teams change
nothing else in the player load.

**Targeting works; missile launch does not yet.**
- With teams, "Target nearest Hostile" (J) selects the other player. The
  target manager (`world+0xDF088`) holds the tag `0x80010002`.
- Key commands: rack activation is keypad 1–9 (`0xB8`–`0xC0`, keypad 0 for
  rack 10); `.`/`,` cycle missiles; mouse-flight right button and key M
  launch. M (command 2) runs two handlers. `0x441C90` fires a torpedo when
  one is armed: `world+0xD3440` is the local player's system container
  (player `+0x194`), and its `+0x108` is the "Torpedo ARMED" flag set by a
  world command (`0x4ACA0F`). Otherwise `0x44224B` calls
  `CAOAWorld::LaunchActiveMissiles` (`0x4B0E00`), which is also the only
  caller of `SendFireMissile` (`0x489020`, `0x2A`).
- J, keypad 1, M with the target 300 units ahead sent no `0x2A`. The Ym
  Khtat's rack systems (indexes 14–17) read 0 at `+0x88`, the field holding
  HP for its other systems. So the racks probably start empty. The loadout
  likely comes from the ship's custom configuration
  (`SendRequestCustomConfig` `0xA0`/`0xA4`), which the stub never answers.
  That is the next thing to recover. Missile relay (`0x2A`, `0x30`) remains
  unimplemented until a real launch can be captured.

**Superseded by 9.32:** the racks were full; the launch was refused because
the stub marked every player Friendly.

### 9.32 Missiles work: hostile relations, launch echo and impact relay (21 October 2026)

**9.31's loadout conclusion was wrong.** Rack HP is 0 in the ship file
itself (`sco.json`: every Ym Khtat rack has `hp` 0.0). The missiles are
attachments on the rack (system `+0xE4` list, kind `0x5003`; count `+0x50`,
capacity `+0x48`). A live memory read showed all four racks full: two
Type II 1.1 and two Type III 1.1 missiles, two per rack. Rack IIB a starts
active. Keypad 1 *toggles* a rack, so the 9.31 test switched the only active
rack off. The custom config (`0x99`, applied by `ChangeObjectVesselCustom`
`0x4A7BC0`) is not needed.

**The in-flight log is off by design.** Right after `loading AI flags` the
client clears its main logger's enabled byte (`mov byte [0x5E7E44], 0` at
`0x431A0E`). Every arena-time warning is therefore silent. For diagnosis
only, a scratch copy with those 7 bytes (`C6 05 44 7E 5E 00 00`) NOPed logs
in flight. `tools/crashdbg.py --trace VA,...` (new) logs the registers each
time a listed instruction runs; both were used to walk
`LaunchActiveMissiles` (`0x4B0E00`).

**Launch gates, in order** (all silent except through HUD text):
1. The target's relation (player `+0x1CC`) must not be 1 or 5
   (`0x4B0F01`, "Cannot launch at Friendly/Allied"). The "Set target to …"
   commands use 1 Friendly, 2 Unfriendly, 3 Neutral, 4 Hostile and 5 Allied
   (`0x442376`–`0x442541`).
2. The target's render object must be on screen (`+0x153`, set by the
   visibility test at `0x543000`).
3. The rack must have recycled (`+0xF8`/`+0xFC` against the clock).
4. The target must be at least the missile's minimum launch distance from
   the shooter. That is 5000 units for Type II (missile system `+0xE8`),
   measured to the target's hull (radius `+0x164`, 116 for the Ym Khtat). A
   scenario `minlaunchdist` overrides it.
5. Then `SendFireMissile` (`0x489020`) sends `0x2A`.

**Relation fix.** The `0x26` player load carries the receiver's relation to
that player at `+0x44` (same team) and `+0x45` (other team), as value − 1
(`0x4A6498` → player `+0x31C`/`+0x320` → `0x49CA40`). The stub sent 0
(Friendly). It now sends 3 (Hostile) in both bytes, because free-for-all has
no teammates; this works with and without `--experimental-teams`.

**Launch protocol.** Online, the shooter does not create its missile: when
connected it only sends `0x2A` and skips the local `OnReceiveMissileLaunch`
call (`0x4B14F7`–`0x4B1520`). `0x2A` is 146 bytes and arrives reliable:

| Offset | Field |
|---|---|
| +0 | f32 lock (100.0 seen) |
| +4 | target tag |
| +8 | shooter tag |
| +0xC | launch count |
| +0x10 | 16 × u32 missile tags, **zeroed by the client** |
| +0x50 | missile name (32 bytes) |
| +0x70 | rack name (32 bytes) |
| +0x90 | u16 targeted system |

Uninitialised stack bytes follow each name's NUL.
`OnReceiveMissileLaunch` (`0x4B16B0`) creates one missile per tag through
`AllocNewObject(3, -1, tag)` (`0x4A5960`). A nonzero tag is used as given;
its low word is the object index, below 1000. So the server must assign
tags, as the original evidently did, so that every client agrees on the
missile's identity.

**Impact protocol.** In flight, only the client whose ship is the missile's
target or shooter checks for collisions. Online it sends `0x30` and applies
nothing itself (`0x4B3BAE`–`0x4B3BD4`). `0x30` is 21 bytes: missile tag,
hit tag (0 for no object), float3 position, and a direct-hit byte
(`0x485960`). `ReceiveMissileImpact` (`0x433FC0`) finds the missile and
calls `DoMissileImpact` (`0x49B9F0`), which damages the hit ship.

**Server (`MissileLedger`, local relay).**
- **Launch:** validates the shooter tag (it must be the sender's) and that
  the target is another loaded player. It also checks the count (1–16), the
  lock (0–100), that the tags are zero, that both names are printable and
  NUL-terminated, and that the system id is at most `0x1000`.
- **Echo:** scrubs the stack bytes after the names and assigns `0x40CCIIII`
  tags, with index IIII in 500–999 (above the test object). It allows at
  most 16 live missiles per shooter, then echoes `0x2A` to every loaded
  player, shooter included.
- **Impact:** accepts `0x30` only from that missile's shooter or target and
  only for a loaded player (or 0). The position must be finite. Only the
  first report counts, and it is relayed to every loaded player.
- **Lifetime:** entries expire after 60 s or when their shooter or target
  leaves.
- **Delivery:** both relays are best effort, like the other combat relays;
  the reliable-ID budget (9.13) stays reserved for removals.

**Live result** (`evidence/2.9.2/missile_live_20261021.json`). Two patched
clients ran with the ships 6000 apart (`--spawn-spacing 6000`). Six launches
gave six impacts, all reported by the shooter. They carried the server's tags
(`0x400101F4`, …) and the target client applied every one: shield 107.0 →
97.2 → 64.7 → 41.0 after 1, 4 and 6 hits (Type II about 10, Type III about
12). When rack IIB a ran empty, the client moved to IIB b, then to IIIB a.
One key press in each burst did not fire, probably the recycle gate.

**Not done.** Missile kills were not observed (no kill in this test; a
missile death would go through the existing `0x37` path). Missiles hitting
non-player objects are dropped by the impact check. Rearming (powerups, base
docking at player `+0x332`) is not served. The default 1000-unit spawn
spacing is inside the 5000-unit minimum, so players must fly apart first.

### 9.33 Sustained reliable delivery without a client patch (22 October 2026)

**Problem.** 9.13 limited every player to 30 reliable server messages per
session. The client's duplicate filter (`0x4C2730`) remembers only the last
30 IDs, so a 31st distinct ID could evict an old one and let a late copy of
it execute again. That budget made despawns, and any reliable combat, run out
in a long session. It was the reason LAN players had to restart everything
after a dropout.

**Observation.** Eviction needs 30 newer distinct IDs to reach the client
*before* the stale copy. On a path that does not hold a datagram more than
`margin` seconds behind later ones (the same assumption as TCP's maximum
segment lifetime), a copy sent at `t` cannot arrive after anything sent at
`t + margin`. So an ID only needs protection while it is unacknowledged,
and for `margin` seconds after its last transmission. The budget can be a
sliding window instead of a lifetime count.

**Implementation** (`tools/reliable_window.py`, `--sustained-delivery`,
default on for `vpn-dogfight`):
- The server first-sends a new ID to a player only if fewer than 30 IDs have
  been sent since the oldest live ID, inclusive.
- Delivery is stop-and-wait per player. That keeps launch → impact →
  death order, and the window is never held by more than one in-flight ID.
- Despawns are *essential*: if undelivered by the peer timeout, the
  observer is retired, as before. Combat events, the score record and match
  text are *droppable*: they are abandoned after 5 s and later messages
  continue.
- The margin defaults to 3 s (`--reorder-margin`, 0.5–30).

**Any message can be wrapped.** Disassembly of the receive loop shows the
plain path (`0x48645F`) and the unwrapped `0x1B` path both reach `0x486464`
with the inner type already written to `+0x7E8` and the length reduced by
five. Sustained mode therefore also wraps the join sequence (`0x26` loads,
`0x27`, `0x2C`, `0x24`) and the respawn `0x24`, `0x42` and `0x21`, so a single
lost datagram can no longer leave a joiner outside flight. These types are
proven unwrapped on real clients; wrapped, they are proven only by this code
path. Real-client confirmation is an acceptance item.

**Rejoin.** Slots are still never reused (generation safety, 9.13). A
crashed player now rejoins from a new endpoint and gets a new slot. In
sustained mode, a new Station login from the IP of an arena player silent for
≥5 s removes that player at once ("replaced by rejoin"). An active second
client on the same IP is left alone. The limits are 49 arena joins and 64
Station logins per host run.

**Verification** (`tools/test_internet_play.py`, 8 tests):
- A virtual-time model of the client's 30-entry filter, over 30/80/150 ms RTT
  × 0/1/3% loss × two seeds: 400 events each (13× the old budget) with 5% of
  copies delayed up to 90% of the margin. Every event applied exactly once
  and in order.
- A self-check shows that the same model *does* re-execute an evicted ID.
- A live loopback `vpn-dogfight` session under 60 ms RTT, 20 ms jitter, 3% loss
  and 1% duplication. Two synthetic clients that model the receive path
  joined through a lossy handshake and applied exactly one `0x27`/`0x2C`. Each
  then received 25 launch/impact pairs plus the join, death, respawn and match
  messages (over 80 reliable IDs each), with no duplicate application. A
  silent client was replaced on rejoin, and a console `kick` despawned a third.

Throughput is one reliable message per round trip per player: about 6/s at
150 ms. A real internet session has not been run.

### 9.34 Dragged panels stick to the lower-right corner (23 October 2026)

**Symptom (user report).** Clicking a movable in-game panel to drag it threw
the mouse and the panel into the lower-right corner of the screen, where they
stayed.

**Cause.** The client keeps its own mouse object (`app+0x180`). `WM_MOUSEMOVE`
client coordinates go to `+0x10/+0x14` (`0x4EACA0`). The warp `0x4EACE0`
stores a new position and calls `SetCursorPos(x + [+0x28], y + [+0x2C])`.
That origin comes only from `WM_MOVE` (`0x4451D0`), split with `and 0xFFFF` /
`shr 0x10`, so a negative coordinate becomes about 65535. Window dragging
(`0x51DE40`) records a grab offset, moves the panel by the mouse delta each
frame, and then warps the cursor to panel + grab offset (`0x51E072`).
With a bad origin, that warp lands at the bottom-right edge. The next
`WM_MOUSEMOVE` reports a large delta, the panel follows until clamped, and
the loop repeats.

**Live evidence.** Two launches of the dgVoodoo-windowed map-viewer client
(1920×1080 window at 0,0, DPI-aware manifest) were read with
`ReadProcessMemory`. Both had a cached origin of **65535,65535** and a mouse
position of 1918,1078. The window's real origin was 0,0. The
hwnd global `0x5E6DE8` held the game window. Which `WM_MOVE` delivered −1,−1
was not traced.

**Fix: `cursor-warp-origin-v1` (patch version 12).** `0x4EAD16` (18 bytes)
jumps to a 60-byte cave at `0x58B300`. The cave calls
`ScreenToClient(hwnd, {0,0})` through the existing import, and then
`SetCursorPos(x − pt.x, y − pt.y)`. If `ScreenToClient` fails, it falls back
to the cached origin. `ECX` (this) and the stack frame are preserved; the
cave resumes at the original `pop esi; ret 8`. `tools/cursor_warp.py` holds
the patch, and `prepare_client.py` applies it and requires it in `check`.

**Verification.** `tools/test_cursor_warp.py` (4 tests, unicorn) runs the
client's own `0x4EACE0` from the prepared image. Unpatched, a stale origin
gives `SetCursorPos(960+65535, 540+65535)`. Patched, four window layouts
(0,0; −1920,100; −8,−31; 100,200) give the exact screen point. The fallback
keeps the old result, callee-saved registers and `ret 8` are intact, and
corrupted sites are rejected. The prepare/menu/terrain/rendering suites still
pass. `game/2.9.2` and `work/map-viewer-client` were re-prepared (`check`
ready, SHA-256 `6d0c3fc3…7e71`). **Not yet confirmed by
dragging a panel in the real client.**

### 9.35 Frame pacing: a millisecond game clock and the timer-frame gate (23 October 2026)

Measured live with `tools/measure_frame_pacing.py`, a read-only probe that
polls the client every ~3 µs. It timestamps the frame counter incremented
just before each present (app `[0x5E6E58]+0x38`, at `0x44AF94`) and reads
the game clock (`0x5E8E5C`), the main camera (graphics `+0x2510`) and the
app-active flag (`0x5E6E28`) for every frame. Test PC: 1920×1080 at 60 Hz,
AMD Radeon integrated graphics, on battery, dgVoodoo 2.87.5 windowed. The
ship coasted at 500 units/s in a scratch client.

**How the client paces frames** (static, confirmed by tracing):
- **Main loop:** `0x407F50` spins on `PeekMessage` and runs a frame only when
  QPC shows at least 16 ms since the previous frame start (`freq*16/1000`),
  so the cap is 62.5 fps.
- **Present:** `Flip(DDFLIP_WAIT)` asks for vsync, but the windowed wrapper
  does not block. Visible windows are held to the 60 Hz refresh by the
  compositor (measured 60.0 fps). On a locked desktop the client issued
  62.5 fps.
- **Game clock:** game time is `GetTickCount` (~15.6 ms resolution). The
  frame function `0x44AD60` stores the clock step at app `+0x34` (in
  `0x4497E0`) and skips the frame entirely when the step is 0.
- **Background:** with the window inactive the main loop stops (`0x5E6E28`
  clear) and a ref-counted ~66 ms wakeup timer (`0x446E70`, started by
  `0x452930`, ended by `0x4529C0` on activation) renders instead, measured
  at 78 ms per frame. That is the background-network-v1 path (9.24).

**Stock result, window in focus at 60 Hz:** game-time steps are 15/16 ms,
with a 31/32 ms double tick about every tenth frame. That is 57 of 587
frames off the 16.67 ms display interval by more than 4 ms, RMS 4.7 ms.
Camera motion error was 0.23–0.27 of a frame. On a locked desktop at
62.5 fps the double ticks came about twice a second.

**Why Codex's QPC clock alone was not enough.** Codex's QPC clock (verified
earlier offline) removes the coarse steps. But in a window that was never
activated after login the wakeup timer stays on beside the main loop, and
with a millisecond clock its frames no longer have a 0 ms step. They render
and present, splitting the cadence: 75 fps, with intervals like 4+12 or
8+8 ms. Traced: 381 presents = 315 main-loop + 66 timer frames in 5 s. With
`GetTickCount` almost all of these frames were silently skipped.

**frame-clock-v1** (`tools/frame_clock.py`, now applied by
`prepare_client.py prepare` by default; `--no-frame-clock` opts out;
patch version 13):
- **Clock:** Codex's verified clock cave (byte-identical) at `0x58B600`
  replaces both game-clock reads (`0x5296C4`, `0x529700`). The logger and
  `srand` keep `GetTickCount`; those are the only other two callers.
- **Gate:** a cave at `0x58B680`, called from the timer at `0x446EB1`, runs
  a timer frame only when at least 50 ms have passed since the last frame's
  clock (app `+0x30`). It is unsigned and safe across clock wrap.
- **Tests:** `tools/test_frame_clock.py` emulates the gate (skip below
  50 ms, run at 50 ms, wrap, balanced stack, app pointer intact) and checks
  exact undo and that preparation is idempotent.

**Result, window in focus at 60 Hz:** game-time steps alternate 16/17 ms,
which is 16.67 ms correctly rounded. Only 10–17 of 600 frames were off by
more than 4 ms (single system stalls), RMS 1.5–2.0 ms, roughly two to three
times smoother. In the background it still renders at 78 ms from the timer
(12.8 fps), same as stock, and the focused client beside it held 59.9 fps.

**Other checks:**
- **Forced vsync:** setting dgVoodoo's DirectX `ForceVerticalSync = true`
  made no measurable difference, because the compositor already paces the
  window. Left unchanged.
- **Frame build time:** frame start to present measures ~16 ms because
  rendering blocks on the previous vsync. That is latency, not CPU cost.
- **Unexplained slow run:** one earlier run issued only 28.5 fps (35 ms)
  while on battery with the desktop visible. It did not recur in later runs
  in the same power state, so it was likely a transient GPU/power state; not
  investigated further.

**Not covered:**
- Frame rates above 60 Hz. The 16 ms cap will pace a 120/144 Hz display
  unevenly.
- Codex's culling numeric fix is still offline-only.
- Sound and network timing under the new clock beyond the existing tests;
  the heartbeat compares only the client's own ticks.
- Raw runs are in `work/render-pacing/`; the summary is in
  `evidence/2.9.2/frame_pacing_20261023.json`.

### 9.36 Visibility math promoted; the player's own ship must stay hidden (23 October 2026)

Codex's offline culling correction (`render-pipeline-audit.md`) is now a
supported patch, `visibility-math-v1` (`tools/visibility_fix.py`), applied by
`prepare_client.py prepare` by default (`--no-visibility-math` opts out;
patch version 14). Two things changed on the way.

**The exact-centre change was dropped.** The experiment also patched
`0x543077` so that a node at distance 0 from the camera became visible
(at the highest detail level). Live reads in flight show the player's own
ship node at distance exactly 0.0000 on every frame. Each read gave
visible = 0, size 232 (2 × radius 116) and direction NaN from the 0/0
normalisation, both at spawn and while coasting 2,000+ units and turning.
The original zero-distance branch (`0x543126`) is what keeps your own hull
from being drawn at the camera, and it never reaches `acos`/`asin`, so
there is no trig domain error to fix there. Promoting that change would have
drawn the player's ship around the cockpit view. The synthetic emulator
fixtures could not reveal that.

**What remains** is one hook at `0x5431A1` (replacing `fld [esi+0x174]`)
into a 91-byte cave at `0x58B700`. It is byte-identical to the experiment's
angle cave when built at the experiment's address. The experiment's caves
at `0x58B700`/`0x58B800` had since been overlapped by online terrain
(`0x58B800`–`0x58BA00`), so it could no longer be applied to a prepared
client.
- **Dot clamp:** the dot is clamped to [−1, 1] before the original
  `_CIacos` call. A NaN dot is treated as 1, which keeps the original visible
  result.
- **Inside the sphere** (camera at distance ≤ radius, but not 0): the node
  is visible with a finite angular bound of 1.0, skipping `_CIasin`. That is
  the original result without the NaN.

**Verification:**
- **Emulation:** `tools/test_visibility_fix.py` runs the original routine
  with the patch in Unicorn (`audit_render_pipeline.run(..., patch=...)`,
  which now honours `CENTER_VISIBLE`). Across 480 moving/turning cases at
  three FPU precisions it found no out-of-domain trig inputs and no NaN-made
  visibility. Previously valid results and every projected size are
  unchanged, and all 48 inside-sphere cases are visible and finite. Distance
  0 matches the original exactly (hidden, no trig), and the small-object
  cutoff is unchanged. Exact undo, partial/corrupt rejection and coexistence
  with the asteroid/solid-world hook (`0x543222`) are checked too.
- **Codex's experiment test:** `tools/test_render_culling.py` was already
  failing on current preparation and now passes. It tests the experiment on
  an image without online terrain and the promoted patches. Both suites are
  in the local gate.
- **Live:** a copy of the real client folder, re-prepared to patch version
  14, flew with the own-ship node still hidden. The other player's node was
  visible with a finite bound. Frame rate with and without the patch was
  within run-to-run noise (23.75 vs 25.2 fps in one pair).

**Unexplained slowdown during this check:** every build, including the
older copy measured at 60 fps earlier the same day, ran at only 23–26 fps.
The battery was at 90% and discharging, the system otherwise idle, and the
display reported 1024 px wide instead of 1920. It is a machine/display
state, not a patch effect, and is not yet investigated.

### 9.37 A dormant chase camera, revived on F2 (23 October 2026)

The 2.9.2 renderer already contains a third-person camera that nothing turns
on. The main render function `0x43B1D0` tests the byte `0x5E6879` at
`0x43B35A`. When it is set, the eye moves to *position − 420 × forward +
100 × up* (constants `0x59015C`, `0x5900BC`; rows of the main camera matrix
at graphics `+0x2510`), and the player's node is enabled with `0x542A90(1)`.
Otherwise the node is disabled with `0x542A90(0)`. That is the byte's only
reference: no code writes it, and the default key map has no view key.

**Why setting the byte alone is not enough.** Culling happens earlier in
the frame. In flight the camera *is* the player's render node: `0x449900`
hands the node's matrix to `0x553810` at `0x44A092`. It then disables the
node at `0x44A097`, and `0x49BC90` culls every object against the camera
record `[player+0x19C]+0x2C`. Drawing (`0x542990`) needs three bytes:
visible `+0x151`, enabled `+0x150` and `+0x152`. So the own ship is hidden
twice, by the enabled flag and by the zero-distance cull that 9.36 described.
9.36 named only the zero-distance branch. Live reads now show the enabled
flag is the first gate.

**third-person-camera-v1** (`tools/third_person.py`, patch version 15, on by
default; `--no-third-person` opts out):
- **Cave A** at `0x58BC00`, from `0x44A091`. It reads F2's toggle bit with
  `GetKeyState` (already imported; the client has no DirectInput) and
  stores it to `0x5E6879`. When the bit is on, it copies the camera record
  (0xE0 bytes) to `0x60D300` in the zero-filled `.data` tail. It moves the
  copy's position to the renderer's chase eye, using the same constants,
  and enables the node for culling in place of the original `0x542A90(0)`.
  The main camera matrix is unchanged; the renderer applies the offset.
- **Cave B**, from `0x49BCB8`. It passes that copy to the culling routine
  as the camera record. This happens only for the node cave A used, in the
  same game tick (`0x5E8E5C`), so spectate frames and other camera objects
  are unaffected.
- F2 is unbound in the default key map. The toggle bit flips on every press,
  so no state is kept beyond the key state itself.

**Verification:**
- **Emulation:** `tools/test_third_person.py` runs both caves in Unicorn on
  the prepared image. Off, the original call order, pointer and tick are
  kept, the flag is cleared and culling gets the real record. On, the eye
  matches the renderer's formula at three orientations, and the node is
  enabled. Cave B returns the copy only for the same node and tick (other
  objects, a null node and a later tick keep `+0x2C`). The suite also checks
  stack and register balance, exact undo, rejection of partial or corrupt
  patches, coexistence with every optional rendering patch, and that the
  `.data` state words are unreferenced.
- **Live** (scratch copy of the prepared client, Arena1a relay, ship facing
  +z at (2000, 0, 0)):
  - **Off:** render eye at the ship; node enabled/visible 0/0.
  - **On:** render eye (2000, 100, −420), equal to the culling copy. The
    node stayed enabled and visible (1/1) in all 134,701 samples over 3 s,
    at distance 431.7.
  - **Off again:** back to the stock state.
  - The toggle was driven by a real F2 press once, and later by setting the
    key state through attached thread input while the desktop was locked.
- **Not verified:** nobody has looked at the rendered picture yet; in-flight
  captures come back black on this PC. Aiming, HUD target brackets and the
  F7 spectate view with the chase camera on are also untested. Because the
  flag is only refreshed in flight frames, a spectate view with F2 on is
  probably pulled back by the same offset.

A first attempt moved the main camera itself and enabled the node only for
culling. Live reads showed `0x43B1D0` disabling the node again before
drawing (visible 1, enabled 0), which led to the dormant branch.

### 9.38 Why only players can be targeted (23 October 2026)

User report: in flight, the cycle key only reaches other players. Static
analysis of the 2.9.2 client explains it. Nothing was patched and nothing
was tested live.

**The keys.** Registered at `0x441598`–`0x441686` (command, key):
`0x1A` Target nearest (G), `0xA1` nearest Hostile (J), `0x21`/`0x22` Cycle
through targets forward/reverse (T, Shift+T), the per-relation cycles
beside them (`0x1D`/`0x1E` Friendly on F, `0x1F`/`0x20` Allied on L,
`0x23` on Unfriendly U, then Neutral and Hostile), and
`0x82` Target Under Reticle (Y). The flight switch `0x442140` sends T to
`0x4A0B30(1, 0, 0xFF)` on the target manager (`world+0xDF088`). That calls
`0x4A1530` (forward) or `0x4A1970` (reverse), then `0x4A1380` to set the
target.

**What the scans cover.** `0x4A1530`, `0x4A1970` and the nearest scan
`0x4A0550` walk only two arrays:
- players: `world+0xD32AC`, stride 0x3B0, count byte `world+0xDEF58`;
- world objects: `world+0x4C`, stride 0x360, count u16 `world+0xDEF5A`.

Tag lookups also know two more classes, by tag bit (`0x4A01D0`,
`0x4A1210`): `0x20000000` terrain objects (linked list from the terrain
controller `world+0xDF03C`, next at `+0x180`; the tag counter starts at
`0x20000000`, `0x495C6E`) and `0x10000000` target-only objects
(`world+0xDEEC8`, count `world+0xDEEBC`). **No scan walks the terrain
list**, so map objects are never cycle or nearest candidates, although a
terrain tag is a valid target once it is set.

**Candidate filter** `0x4A10F0` (and `0x4B0810`), relation 0 = any. It
rejects an object when any of these hold:
- `+0x243` or `+0x2F7` is clear;
- `+0x188`, `+0x189` or `+0x20E` is set;
- its zone `+0x1C4` differs from the world's (`world+0xD3470`);
- it is the local player;
- render distance `+0x168` exceeds 5,000,000 (2,000,000 when vtable `+0xC`
  is false);
- `+0x20C` is set and its type `+0x1F4` is not 4 (from 0..6).

**Consequence for our server.** Arena1a's 239 terrain objects (stations,
capital ships, asteroids; [map-viewer.md](map-viewer.md)) are all in the
terrain list. The relay spawns no world objects unless
`--experimental-object` is given, and the host control window never passes
it. So the cycle list holds only players. In the original game, AI ships,
turrets and flags would have been server-spawned world objects.

**Ways to fix (not done):**
1. A client patch appending a terrain-list walk to `0x4A1530`/`0x4A1970`.
   The tag plumbing already supports terrain targets. Whether terrain
   objects pass `0x4A10F0` (`+0x2F7`, `+0x20C`/type) needs a live read.
   Missiles at terrain would be dropped by `MissileLedger`.
2. Server-spawned world objects (the 9.11 type-0x25 object path) for the
   things that should be targetable.

Y (`0x452547` → `0x43D150` → `0x4A1210`) picks a ship system under the
reticle and was not traced further.

### 9.39 The own ship had no model; F2 now shows it (23 October 2026)

User report: F2 gave no third-person view. A read-only watcher showed the
chase flag and the render eye switching in that session, so the camera had
moved 420 back and 100 up. On hy_winga there is nothing near the spawn,
so the only visible change would have been your own ship, and it was not
drawn. 9.37's live check had looked only at the top node's flags. Two more
gates hide the hull:

- **No model.** World object creation (`0x4A36F5`) calls the app's
  handler `0x44C0A0(object, is_self)`, with is_self = (tag `+0x178` ==
  local tag `world+0xD3424`). The handler attaches meshes (`0x43DF70`)
  only when is_self is 0. Live, another player's nodes carried `0x51870007`
  mesh links and yours had none.
- **Hidden level-of-detail children.** The main view's mesh pass
  (`0x43CEBE` → `0x56ECC0`) draws each instance node that passes
  `0x542990` (visible `+0x151`, enabled `+0x150`, LOD `+0x152`). Every
  frame, after rendering, `0x48F730` sets all of your ship's children
  visible, does its own work, then forces them back to 0 (`0x48FAE5`). So
  at the next render they were hidden. Found with an attach-only hardware
  write breakpoint on a child's `+0x151`. A 64-bit debugger must set DR0/DR7
  through the native thread context; the WoW64 context did not arm them.

**own-ship-model-v1** (`tools/own_ship_model.py`, patch version 16, applied
with the third-person camera; `--no-third-person` removes both):
- NOPs the `jne` at `0x44C0C5`, so your ship gets meshes like any other.
- Replaces the store at `0x48FAE5` with a cave at `0x58BE00` that writes
  the chase flag (`0x5E6879`) instead of 0.
- In cockpit view nothing new is drawn, because the mesh pass needs the top
  node enabled, and the frame and renderer clear that flag unless the chase
  camera is on.

**Verification:**
- **Emulation:** `tools/test_third_person.py` now also runs `0x44C0A0` with
  is_self 0 and 1, before and after the patch. It runs the child store with
  the flag 0 and 1, and checks in-place upgrade from a v15 client and
  rejection of partial patches. The local gate passes (146 tests).
- **Live:** two scratch clients on an Arena1a relay with `--spawn-axis z`.
  The chase client was prepared from a copy of `game/2.9.2` at v15. With F2
  on, your ship's top node and high-detail child were drawable (1/1/1), with
  `0x51870007` links. An execute breakpoint on the part draw `0x56D9F0`
  caught the main pass drawing your high-detail child 30 times in 2.5 s
  with F2 on, and not with F2 off (one call on the switching frame).
- **Not verified:** the picture itself (the desktop was locked), effect
  parts such as engine glows (their nodes still lack mesh links), aiming
  and the HUD, and the F7 spectate view.

`game/2.9.2` was re-prepared to patch version 16 (`c07daec9…d22d`, the
build tested live).

### 9.40 Changing ships in flight: the relay never answered the fighter menu (24 October 2026)

User report: Esc → fighter select in flight did not change the ship. The
client was fine; the relay ignored both halves of the online exchange.

**How the 2.9.2 fighter menu works online** (`FighterSelectWin.cpp`):
- The ship list is local: every fighter in `AoAObjects.odb` (`0x464748`).
  The *configuration* list comes from the server. On opening a ship,
  `0x465C70` asks the world for its custom configs. If world `+0xDF141` is
  set, it offers one "default" entry (index 0). If no config matches, it
  shows "Ship Not Available" (index −1); offline it says "Custom Configs
  Not Available Offline".
- `+0xDF141` is set only by `0x4AF030`, the handler for **TCP job 4**
  (`CClientComm::TCPRead` `0x435930`, jump table `0x43664C`). The body is
  a list of 0x68-byte entries. An entry whose `+0x20` name is `_all` sets
  the flag ("every ship, default config"). The client polls job 4 all
  session; the relay answered with length 0 (274 times in one log).
- Confirm (`0x466990`): offline it calls `ChangeObjectVessel`
  (`0x4A7F90`) directly ("Fighter changed"). Online, an index of −1 shows
  "Fighter Not Available". Otherwise it calls `SendRequestCustomConfig`
  (`0x48A030`, **type `0xA0`, 37 bytes**: u32 config index, vessel[32],
  zero byte), shows "Requesting fighter..." and waits. The relay dropped
  `0xA0`.
- Server replies the client understands: `0x27` ReceiveLoadShip (vessel,
  database, slot) calls `ChangeObjectVessel` for that slot. `0x47` (vessel
  name) and `0x99` (slot, vessel, database, then 128 × {u16 item, u8
  system} for `ChangeObjectVesselCustom` `0x4A7BC0`) both first run
  `0x4A4310`. Outside a safe zone, that moves the ship to a random point
  and zeroes its velocity. If the ship was hit in the last 15 s, it then
  calls `0x4A5440` with the last attacker; otherwise it bumps the pilot
  record's `+0x83` (deaths). So the original server treated a swap in open
  space as a death. (`0x4A5440` was not traced; "death credit to the last
  attacker" is inferred.)
- A receiver's world index for a remote player is the tag's low word
  (`AllocNewPlayer` `0x4A5DE0`; its own ship is 0). So `0x27` with slot N
  changes player N's hull for every observer. Re-sending `0x26` does not:
  the same tag and name hit "multiple load for player" and return.

**Fix (relay only, no client patch):** `tools/station_stub.py`
- TCP job 4 returns one `_all` entry (`ship_config_list`), on every profile.
- `0xA0` from a loaded relay player (plain or `0x1B`-wrapped) is checked
  by `ship_request`: exact size, NUL-terminated name, and one of the 32
  engine-fitted `.Sco` objects, pods excluded (`SELECTABLE_VESSELS`). The
  pilot then gets `0x27` slot 0, every loaded observer gets `0x27` with the
  pilot's slot, and the pilot gets `0x24` back to its spawn. That replaces
  the random move, so a swap is not a free escape or repair. Deaths are
  not counted. Late joiners get the vessel in the `0x26` record, which has
  only a 20-byte vessel field; the longest name is 13. Each request is
  logged as `ship_change` with the vessel or `rejected` in `status`.
- Custom loadouts (`0x99`) and safe zones are not implemented.

**Verification:**
- `test_ship_selection_messages` covers the job 4 body, request
  validation, and the `0x27`/`0x26` vessel fields.
- `test_ship_change_relay` runs a real relay with three synthetic clients.
  An unknown ship is rejected; a wrapped Vermok request is ACKed. A and B
  then load Vermok in the right slots, A returns to spawn, and late joiner
  C gets A's record as Vermok.
- **Live** (user, `game/2.9.2` at patch version 16, host control,
  `local-relay` on hy_winga): Esc → fighter select offered "default", and
  Commit changed the ship. The relay logged `ship_change` Naroch, then
  Vermok, and the user confirmed flying the new ship. Before the fix, the
  same menu said "Fighter Not Available".
- **Not verified:** what a second player sees (only one client was
  connected), and the self-reported deaths (`0x37`, no killer) every few
  seconds in the same runs, which began before any ship change.

**Second cause: the join erased the Station ID.** After that success,
"Fighter Not Available" came back on new hosts (hy_winga again, then
JRMAP). Each failing run polled job 4 every 5 s from flight entry and got
length 0 every time. The one working run had died twice before its first
job 4 poll. The job body was not the problem: the relay was refusing the
requests. TCP requests carry player record `+0x7B` at offset `0x3C` (9.16).
The bootstrap's `0x26` for the joiner's own slot has the copy-record flag
(`+0x1B0`): the tag resolves to the local ship (`0x4A64FE` → `0x4A5DE0`,
index 0), and `0x4A641C` copies the synthetic, mostly blank record over the
client's. That zeroes the Station ID, so `StationSessions.resolve` refuses
every later TCP job. A death fixed it by accident: the relay then sends `0x42`,
the client's own login block, restoring `+0x7B`. This also explains the
"not explained" 16:24 run. **Fix:** the self-load `0x26` now carries the
client's own Station ID at record `+0x7B`, copied from its arena login
block. Only the owner's record gets it. `test_ship_change_relay` checks
that the joiner's own record has the ID, other players' records have none,
and no `0x42` arrives during flight setup.
Earlier sessions' 274 empty job-4 replies were the same refusal.

**Verified live after the second fix** (17:00, user's host, no death first):
job 4 at 10 s after login returned 22 bytes. A read-only memory read showed
world `+0xDF141` change 0 → 1, and the relay accepted `ship_change` Naroch
18 s later.

**Menu timing:** the client first asks for job 4 about 10 s after
login (≈5 s into flight), on a timer, and stops once it has the list.
`0x465C70` fills the config box when a ship is clicked. A ship shown
before the list arrived keeps "Ship Not Available" until it is clicked
again. The world reset that clears `+0xDF141` (`0x4A2770`) runs only once,
at startup (`0x445756`).

**Ghost HUD panels from a first attempt.** The first version of the
Station ID fix sent `0x42` (the client's own record) right after `0x2C`.
The user then saw large copies of HUD panels on the background, in
cockpit and F2 views. A full-resolution capture showed a sideways
missile-rack panel and two target-gauge clusters beside the real ones.
`0x42` is not a plain copy: `0x49DB20` calls `0x4A60D0`, which notifies
the world's listeners that the player record changed (event 6). The self
`0x26` does the same before flight entry; repeating it after the HUD
exists left the ghosts. With the ID carried in the self-load instead, the
user confirmed the ghosts were gone (17:12, ship change to Zkole in the
same session).
- **Open:** a death still makes the relay send `0x42` mid-flight (9.30
  scoreboard). That may leave the same ghosts after dying; not checked.
- Screen captures of the dgVoodoo window must be DPI-aware: the game
  draws 1920×1080 into a window Windows reports as 1536×864 at 125 %.
  `PrintWindow` without `SetProcessDPIAware` crops to the top left.

### 9.41 F2 showed no hull after a fighter-menu switch (25 October 2026)

User report: the chase camera showed the Ym Khtat, but after switching
ships in flight (Esc → fighter select, 9.40) F2 pulled the view back with
no hull. A Zkole loaded at spawn was drawn: the game's own capture showed it
(below). The difference is the fighter menu's 3D preview.

**Cause.** `FighterSelectWin` gets the previewed model's renderer by name
through `0x569380` (`0x465EAB`). That is the same shared renderer real ships
of that model attach to. It then calls `0x5686A0(0)`, which sets renderer
`+0x31` and every part's `+0x244` to 0 so the preview stays out of the main
view. It also clears each part's `+0x245` (`0x466033`, `0x4660C9`). Nothing
sets them back: every other caller of `0x5686A0` also passes 0. After the
switch, your new hull attaches to those parts:
- The main mesh pass (`0x43CEBE` → `0x56ECC0`) skips a part whose `+0x244`
  is 0. A read-only watcher of the user's run showed the Zkole parts at
  `+0x244..+0x247` = `00 00 01 01` and the Ym Khtat's at `01 01 01 01`.
  Each Zkole part also listed two instances: your LOD child and the
  preview's node.
- Past that check, the single-instance draw (`0x56D9F0`) sets the
  instance's world transform only when `+0x245` is set (`0x56DD72`). With
  it clear, the hull would be drawn with the previous object's transform.
  The first fix let the part through but missed this, and the user's retest
  still showed nothing. The menu's own draw (`0x568DE0`) re-sets `+0x245`
  from renderer `+0x33` each time it draws (`0x568F7D`).

**own-ship-menu-model-v1** (`tools/own_ship_menu.py`, patch version 17,
applied with the third-person camera; caves at `0x58BF00`, state byte
`0x60D3EC`):
- **Part check** (`0x56ECDC`): records the part's `+0x244`. A part with it
  clear is still walked when the chase flag is on.
- **Instance check** (`0x56ED01`): after the original `0x542990` test, a
  restricted part draws only instances whose parent (`+0x144`) is your top
  node (`[world+0xD3448]`). For those it sets the part's `+0x245` back to 1.
  The preview's node is never drawn in the main view. With F2 off, and for
  parts the menu never touched, nothing changes.
- `state()` also recognises the first cave (without the `+0x245` restore),
  so a client prepared with it upgrades in place.

**Verification:**
- **Emulation** (`tools/test_third_person.py`): the original skips cleared
  parts. Patched, a cleared part draws your instance with `+0x245` restored,
  and does not draw the preview's instance. Cockpit view and untouched parts
  are unchanged. The suite also checks upgrades and partial-patch rejection.
  The local gate passes (152 tests).
- **Live, user:** `game/2.9.2` at patch version 17 (`15be31ba…d5db`).
  Ym Khtat → Esc → fighter select → Zkole → F2 now shows the Zkole hull.
- **Live, scratch:** with the hull loaded at spawn, execute breakpoints on
  `0x56D9F0` counted the same entry, world-transform and draw calls for
  Zkole as for the Ym Khtat, at the ship's position. This came before the
  menu was identified.

**Not fixed:** other players flying a model you have previewed probably stay
hidden in your main view for the rest of the session. The parts are shared,
and the restore is limited to your own ship. Not tested.

**Seeing the 3D view.** GDI and `PrintWindow` captures of the flying client
are black or stale here. The client's own capture works: plain **F5** in
flight (command `0xB4`, "Screen capture to file", registered at `0x44F552`)
writes `Capture Images\AoAImgN.tga` in the game folder. In the user's own
client F5 saved nothing; their keymap may bind it differently.

### 9.42 Safe-zone cubes never drew on server-loaded maps (25 October 2026)

User report: spawning inside a safe zone should show a translucent blue
cube; nothing was drawn. The archived forums agree on the original look
(players asked for "safe zones with other colors rather than blue" and
proposed a duel arena "transparent like a safe zone").

**Where safe zones are.** Layout category 7 (`CreateTerrainFromGfxInfo`
`0x4963E4`, object `Cube`) and `.TRN` kind 2 both reach `AddTerrainObject`
(`0x4971F0`) kind 2 (`0x497333`). That path makes a model-less terrain
object and calls `AddSafeZone` (`0x4928E0`) on the zone handler
(`world+0xDF06C`) with centre ± half-size (layout: gfx info `+0x114`;
`.TRN`: record `+0x104`). It returns 0, so `Cube1.Gob` (a 390-unit box
textured `GALogo.tga`) is never used for zones. `ProcessZones`
(`0x4927C0`) sets the ship's `+0x2F8` in-safe-zone byte.

| Map | Safe zones | Half-size | Spawn inside one |
|---|---|---:|---|
| Arena1a, newterrain | 4: `SafeZone Z` (origin), `0` (84, 200047, 660390), `1` (−45336, 95404, −122072), `2` (45007, 95404, −122072) | 5,137 | yes (origin) |
| outerchange, irrosa01 | 1: `SafeZone Z` (origin) | 5,137 | yes |
| hy_base_test | 1: `Home` (origin) | 5,137 | yes |
| CTF_arena_b | 1: `SafeZone Z` (10, 0, 0) | 5,137 | no: the viewing spawn is ~97 km away |
| JRMAP | 5: (500, 0, 1634), (281731, 7, −24696), (60340, 13032, −43856), (74479, 15430, 52602), (5000000, 0, 0) | 2,500, 2,000, then 5,000 | no |
| the other 13 | none | | |

**The visual.** `0x43E030` (flight view, `this` = `[0x5E6E58]+0x138`)
copies a zone box into the view's array (`+0x2674` count, `+0x2680`,
stride `0x548`), skipping exact duplicates, and builds a `CDxWaveCube`
(`0x507AE0`, "InitWavy"); option bit 10 of `[0x5E72C4]` picks a plain
`0xFF0000FF` box instead (`0x55E750`). `0x43E190` draws them with the
texture-stage alpha taken from the vertex colour, gated by `+0x266C` (set
by `0x43E030`) and `+0x266D` (set in the constructor). `0x438D47` culls
per entry (`+0x545`). Nothing reads the terrain object's `+0x1FC` zone
byte; the view array is the only renderer.

**Cause.** Only two places feed `0x43E030`: the login-time interface setup
(`0x449433`) and `SetupFlightMode` (`0x44B5C0`, walk at `0x44B7AB`). The
original server sent terrain before flight entry. `online-terrain-v2`
loads the map at `0x4306AF`, right *after* `SetupFlightMode` returns, so
the safe list was empty when both walks ran and no cube was ever built.

**Fix: `online-terrain-v3`** (`tools/online_terrain.py`, patch version 18).
After a successful layout load or `ReadInTerrain`, the cave repeats
`SetupFlightMode`'s walk: each safe-list node's box (`[node]`, next at
`+8`) goes to `0x43E030` on the flight view. Null handler, flight mode or
view skip it. The map table moved from `+0xA0` to `+0xC0` to make room;
`prepare` recognises v2 (byte-identical to the old cave) and v1 and
upgrades them in place.

**JRMAP.** Its five kind-2 records carry empty database and object names.
`AddTerrainObject` looks the object up (`0x4CDA80`) before its kind switch,
so they were dropped. `decode_trn.convert_292` now names them
`AoAObjects.odb` / `Cube`, as the layout path does. Re-run
`map_viewer.py install`; the converted file is now `60b09731…6779`.

**Verification:**
- **Emulation** (`tools/test_online_terrain.py`): every map entry walks a
  three-node safe list after loading and passes each box with `ecx` = view;
  no walk without a load, a handler or a view; v2 bytes upgrade to v3 in
  both `online_terrain` and `prepare_client`. The local gate passes
  (154 tests).
- **Live, scratch copy of `game/2.9.2` at patch version 18**
  (`53910b7c…7e7b`, the same bytes now in `game/2.9.2`), loopback relay,
  memory read after flight entry
  ([safe_zones_20261025.json](../evidence/2.9.2/safe_zones_20261025.json)):
  every map's zone-visual count equals its safe-zone count (Arena1a 4,
  newterrain 4, outerchange 1, irrosa01 1, hy_base_test 1, CTF_arena_b 1,
  JRMAP 5, CTF_arena 0). JRMAP's terrain list grew from 18 to 23 objects.
- **On screen (F5 captures, by Claude):** spawned in Arena1a's `SafeZone Z`,
  the whole view is tinted by the translucent blue wave pattern with the
  asteroids visible through it. From (0, 2000, −17000) the zone is a blue
  translucent cube with bright edges. irrosa01 shows the same tint;
  CTF_arena (no zone) shows none.
- **Live, user:** `game/2.9.2` at patch version 18: confirmed on screen.

**Not done:** safe-zone *rules* (no damage, "Entering Safe Zone" text,
launch restrictions) are client/server behaviour that was not tested.
CTF_arena_b and JRMAP do not spawn inside their zones.

### 9.43 The 2.7.1 client keeps the server's send routines (25 October 2026)

Static analysis only; nothing was patched or run. Reproduce with
`python -I tools/server_senders.py work/2.7.1/members/15_AOACLIENT.EXE
work/2.7.1/disasm.pkl evidence/2.7.1/send_sites.json
game/offline-baseline-2.9.2/AOACLIENT.EXE evidence/2.7.1/server_senders.json`
([evidence](../evidence/2.7.1/server_senders.json)).

**What survives.** Client and server were built from one `CAOAComm` class.
2.7.1 still links the server half; 2.9.2 drops it. Twenty `Send…` routine
names appear in 2.7.1's strings and not in 2.9.2's, and 32 packet types have
a 2.7.1 send site but none in 2.9.2. Each named routine is tied to its
function by the warning string its code references, and to its packet by
the immediate type/length stores (`send_sites.json`):

| Routine (2.7.1) | Function | Sends | 2.9.2 receiver |
|---|---|---|---|
| `SendLoadPlayer` ("had no team") | `0x4D85B0` | `0x26`, 498 B | yes |
| `SendChangePCShip` | `0x4D6920` | `0x27` 129 B and `0x47` 40 B | yes |
| `SendEnterFlightLoop` | `0x4D7350` | `0x2C`, 4 B | yes |
| `SendYouHaveMadeAKill` | `0x4D6700` | `0x42`, 418 B | yes |
| `SendGainScore` | `0x4D6DA0` | `0x56`, 8 B | yes |
| `SendRestart` | `0x4D6E80` | `0x12`, 192 B | yes |
| `SendHangup` | `0x4D6520` | `0x3E`, 4 B | yes (9.22) |
| `SendToggleSNM` | `0x4D6880` | `0x46`, 0 B | yes |
| `SendWYSIWIGDamage` | `0x4D6450` | `0x3D`, 3 B | yes |
| `SendSetModSpec` | `0x4D5CE0` | `0x83`, 5 B | yes |
| `SendSetupTFCGame` | `0x4D55F0` | `0xA9`, 320 B | yes |
| `SendMovePowerupTo` | `0x4D6CB0` | `0x53`, 14 B | yes |
| `SendPacketShipConfiguration` | `0x4D7420` | `0x99`, 577 B | yes |
| `SendConnectToOtherServer` | `0x4D77A0` | `0xA8`, 422 B | no |

Unnamed server senders with a unique size match include `SpawnPowerUp`
(`0x43`, 17 B, `0x4D67E0`), `TurretGroupStatus` (`0x70`, 236 B, `0x4D4F00`),
`SetParam` (`0x6D`, 68 B, `0x4D8820`), `LoadScenario` (`0x64`, 71 B,
`0x4D5F70`) and `UpdateStoredPlayer` (`0x6E`, 416 B, `0x4D70E0`). The
`SendRequestHTTP…` routines are client stubs that only log `PANIC … CALLED!!`.

**Dead and live code.** Most senders are reached only through their
incremental-link thunk, and nothing calls those thunks. The exceptions are
server logic that still runs in the client build, and are the best leads:

| Sender | Called from |
|---|---|
| `TurretGroupStatus` `0x70` | `0x4EA6A0`, `0x4EA9C0` (turret group code) |
| `SetParam` `0x6D` | `0x4612E0` |
| `LoadObject` `0x25` | `0x5074D0` |
| `ObjectToTeam` `0x50` | `0x502220` |
| `LoadScenario` `0x64` | `0x50B3F0` |
| `UpdateStoredPlayer` `0x6E` | `0x45F9A0`, `0x507B60` |
| `SetModSpec` `0x83` | `0x4FDC30`, `0x509AE0` |
| `0x8D` (400 B) | `0x507750`, `0x508590` |
| `0x40` (5 B) | `0x509970`, `0x509AE0` |

**How to use it.** For a server feature, the 2.9.2 receiver gives the
layout and the client's reaction; the 2.7.1 sender shows which fields the
original server filled and from what arguments. Payloads start at packet
object `+0x14` in both builds (type at `+0x498`, length at `+0x494`).
Power-ups are the first feature rebuilt this way (9.44). Names in this
table are confirmed by strings; the size-hint names of unnamed senders are
not. Whether a dead sender's arguments were real server values still needs
its server-side caller, which no surviving build has.

### 9.44 Power-ups: decoded, hosted, and blocked by two 2.9.2 client changes (25 October 2026)

Power-ups are the first server feature rebuilt from the 2.7.1 senders (9.43).

**Messages.**

| Type | Size | Direction | Layout | Code |
|---|---|---|---|---|
| `0x43` SpawnPowerUp | 17 B | server → client | i32 x, y, z; u8 type 0–4; u32 tag (nonzero) | 2.7.1 sender `0x4D67E0`; 2.9.2 receiver `0x431D30` |
| `0x44` HitPowerup | 4 B | client → server | u32 tag; sent in a reliable `0x1B` envelope | `SendHitPowerup` `0x485DB0` |
| `0x53` MovePowerupTo | 14 B | server → client | u16 world-object index; f32 x, y, z | `SendMovePowerupTo` `0x4D6CB0`; receiver `0x430B2B` |

The receiver makes a `PowerUp1` world object (`AllocNewObject` `0x4A5960`
with the tag, so index = tag & 0xFFFF), names it from a five-entry table and
sets object type 6, `+0x210` = 1 and `+0x211` = type. The types are 0
Missile Power Up, 1 Shield Power +5, 2 +10, 3 +20, and 4 Repair Power Up
(`0x5D249C`/`0x5D24B4`/`0x5D24CC`, identical in 2.7.1).

**The effect is the client's.** `CollideWithPowerup` (`0x4B4D60`) hides the
object (`0x49CD70(0)`), plays a sound, sends `0x44`, then applies:
- type 0: one missile per rack ("Missile Added");
- types 1–3: shield +5/+10/+20, capped at its maximum;
- type 4: up to two damaged systems restored ("Systems Repaired").

On `0x53` every client hides the object, sets a 5,000 ms countdown
(`+0x338`) and moves it. The object update `0x49ABD0` sets it shown again
(`+0x2F7`) when the countdown ends. Nothing in the client chooses where a
power-up goes: that was the server.

**Where they go: power-up zones.** Terrain kind 6 in `AddTerrainObject`
(`0x4971F0`, jump table `0x497878`) calls `CAOAZoneHandler::AddPowerupZone`
(`0x492C10`). It passes the record's centre, its half-size (`.TRN` 2.9.2
`+0x104`) and the power-up type (`+0x194`), and builds a box of centre ±
half-size. It sizes a per-zone maximum as `int(… × MAXPOWERUPSPERUNITDENSITY
× half / POWERUPUNITDENSITY) + 1`. Both keys are server settings no build
ships. **JRMAP's 11 "unnamed kind-6 markers" (level-data.md) are power-up
zones**, all with valid types: three stacks near the flags, with half-sizes
1,000–5,000. No layout category seen in `CreateTerrainFromGfxInfo` makes a
kind-6 zone, so the 19 layout maps have none.

**Relay** (`--powerup-zones TRN`, `PowerUps` in `station_stub.py`):
- Reads the kind-6 records (`decode_trn.powerup_zones_292`) and places one
  power-up per zone (the `+1` floor of the original count) at a random point
  in its box. Indices are 100–499 (tags `0x400000xx`), between the test
  object and missiles.
- Sends every `0x43` to a player after flight entry (reliable with sustained
  delivery).
- On a valid `0x44` it picks a new point in the same zone and sends `0x53`
  to every loaded player, the picker included, so all copies hide, move and
  reappear together. It ignores repeats for the 5 s hidden window and
  unknown tags.
- The host window passes the map's own `.trn` automatically for TRN maps
  (JRMAP). `tools/test_powerups.py` adds 7 tests (zone reader, layouts,
  pickup rules, a loopback socket test with a late joiner); the local gate
  passes (161).

**Live, one real client** ([evidence](../evidence/2.9.2/powerups_live_20261025.json)):
the test used a scratch copy of the patch-version-18 client, prepared for
Station 127.0.0.2 so the user's running host was left alone. The relay
served JRMAP's 11 zones plus a synthetic Shield +5 zone of half-size 0
placed 150 units ahead of the spawn.
- **Spawn works:** all 12 objects appeared with the sent tags, types, names
  and positions (memory read).
- **Pickup does not, in unmodified 2.9.2.** The ship overlapped the test
  power-up and nothing happened. 2.9.2's `SetTerrainType` (`0x49A560`) puts
  type 6 in the case that clears the collidable byte `+0x2FB`, and the
  collision pass (`0x4B2E90`) skips such objects (`0x4B3013`). 2.7.1's
  `SetTerrainType` (`0x4EE130`) marks type 6 collidable.
- **Setting `+0x2FB` in memory:** the client picked it up at once and sent
  `0x44`; the relay logged "Shield Power +5" and broadcast `0x53`.
- **It never came back.** After 5 s, `+0x2F7` was 1 again, but the model's
  enabled byte `[+0x19C]+0x150`, cleared by the hide (`0x49CD70` →
  `0x542A90`), stayed 0. The countdown never re-enables it (2.7.1's
  countdown at `0x4EE462` is the same), so the power-up stayed invisible and
  untouchable. Setting that byte too gave a second pickup immediately.
- Collision also needs the object to be drawn this frame
  (`[+0x19C]+0x151`, `0x542990`). A power-up exactly at the camera is culled
  and cannot be touched; the test zone was moved 150 units ahead for this
  reason.

**Fix: `powerup-pickup-v1`** (`tools/powerup_pickup.py`, patch version 19,
on by default; `--no-powerup-pickup` opts out):
- **Collidable on the `0x43` path.** The receiver's store
  `mov dword [edi+0x200], 4` at `0x431E19` jumps to a 22-byte cave at
  `0x58B2C0`. This is free padding between `patch_client`'s logger cave
  (ends `0x58B286`) and `cursor_warp` (`0x58B300`). The cave repeats the
  store, sets `+0x2FB` = 1 and returns to `0x431E23`. Terrain power-up zones
  (also type 6) are untouched.
- **Shown again on expiry.** In place at `0x49ACC2`, the 17 bytes
  `mov byte [esi+0x2F7], 1; mov dword [esi+0x338], 0` become
  `push 1; mov ecx, esi; call 0x49CD70; and dword [esi+0x338], 0; nop`.
  The countdown's only nonzero writer is the `0x53` receiver (`0x430B77`),
  which itself calls `0x49CD70(0)` and so needs the model pointer. The call
  therefore never meets a null model. Both callers of `0x49ABD0` ignore its
  return value.

**Verification:**
- **Emulation** (`tools/test_powerup_pickup.py`, 5 tests): the client's own
  `ReceiveSpawnPowerup` runs with allocation, model, name, position and log
  stubbed, and real `SetTerrainType`.
  - Unpatched it leaves `+0x2FB` = 0; patched it sets 1.
  - Type, `+0x200` = 4, `+0x210`/`+0x211`, the tag passed to
    `AllocNewObject` and the integer-to-float position are unchanged.
  - The real countdown and show/hide, after a real hide, expire to shown
    without the model unpatched, and shown with the model patched.
  - Running and idle countdowns behave identically; the patch is reversible
    and rejects corruption at each site.
  - The local gate passes (166).
- **Live, real client** (scratch copy prepared at version 19,
  `f2f0c457…31da`, Station 127.0.0.2; same host and zones as above), with
  no memory writes:
  - All 12 power-ups are collidable. The test power-up was picked up 22
    times in a row, every 5.00–5.05 s: pickup, `0x44`, relay `0x53`, hide,
    move to the same point, reappear, touch.
  - The relay rejected none.
  - An in-game F5 capture 0.3 s after a logged pickup shows the client's own
    yellow **"Shield +5"** HUD message.

- **Live, user:** `game/2.9.2` prepared at patch version 19 (`88ffd5f7…78bc`),
  JRMAP hosted from the host window with its own zones: tested and confirmed
  working (25 October 2026).

**Not verified:** a second client watching another player's pickup, and
which of the other effects (missile reload, larger shields, repair) the
user's test covered. Rules that may have lived on
the server, such as whether a picker had to be near the power-up, are
unknown. The relay trusts the client's report, as the client trusts itself
for the effect.

### 9.45 Server-spawned target ships (25 October 2026)

This follows up 9.38. The user chose server-spawned world objects over a
client patch to the target scans.

**LoadObject `0x25`** (191 bytes, receiver `0x4A66A0`), fields read from
the receiver:

| Offset | Field |
|---|---|
| +0x00 | vessel name (`.Sco` in the database) |
| +0x20 | database (`AoAObjects.odb`) |
| +0x40 | display name |
| +0x60 | tag. An existing live object with that tag is left alone, so resends are harmless |
| +0x64 | kind, passed to `SetTerrainType` (`0x49A560`) |
| +0x68 | to `0x49C6F0` |
| +0x6C | team name |
| +0x8C | team id. With 0 the client makes a team of its own for the object (`0x4AD4B0`, names from 8000) |
| +0x90 / +0x91 | same-team / other-team relation, in the player load's encoding (9.32) |
| +0x92 | float3 position |
| +0x9E | float3 target position (kind 0xD only) |
| +0xAA | tag stored at `+0x2E0` |
| +0xBA | nonzero: put the object in a target window (`0x4A0F90`) |
| +0xBB | zone; 0 means the world's |

**SetTerrainType kinds.** Kind 3 is the only collidable non-terrain kind.
Kind 0x11 clears `+0x20C` and keeps `+0x2FB`. Kinds 0–2 and 4–15 set
`+0x20C`, which the candidate filter `0x4A10F0` rejects unless the type is 4.
So kind 0x11, which the 9.11 test object uses, is targetable.

**`TargetShips`** (`station_stub.py`, `--target-ships N`, 1–98; needs the
relay):
- Places N passive ships on a 60° arc 12,000 units ahead of the first spawn
  (ships face +z), cycling Ym Khtat, Vermok, Shrike, Rhino, Tholfus and Eagle.
- Names are "Target 1…N", tags `0x40010002`… (indexes 2–99, between the test
  object and power-ups), kind 0x11, relation 3/3 (Hostile).
- Every player gets them after flight entry, like power-ups (reliable with
  sustained delivery).
- `MissileLedger` takes their tags: a launch at one is echoed, and only the
  shooter's impact report is accepted.
- The host window passes "Target ships" (default 4).

**Live, one real client** ([evidence](../evidence/2.9.2/target_ships_live_20261025.json);
scratch copy at patch version 19, Station 127.0.0.2, Arena1a with terrain):
- All ships loaded as world objects with the sent tags, type 0x11,
  `+0x20C` 0 and relation 4.
- The client filled its three target windows with them unprompted.
- **T reached every ship in turn and J picked one.**
- At a 110° arc the outer ships were off screen at spawn, so the arc is 60°.
- **Missiles from the spawn are refused by design.** The Arena1a spawn lies in
  a safe zone (9.42). While the ship's `+0x2F8` (`world+0xD35A4`) is set,
  `0x44AFD0` holds every lock at 0, and `LaunchActiveMissiles` stops at
  `0x4B0E47`. Ships at 6,000 units would be inside 5,000 + hull once the
  player left the 5,137-unit zone, hence 12,000.
- Spawned at (0, 0, −30000), clear of the zone, M at the ship dead ahead:
  - the relay logged the launch and, 4.7 s later, the impact;
  - the ship was knocked into a spin.

**They cannot be destroyed.** `DoMissileImpact` (`0x49B9F0`) applies damage
(`0x49BCE0`) only when the hit object is the local player (`0x49BADC`); other
objects get the effect and sound only. After the impact, the ship's shield
(92) and hull (34) still held the ship file's full values. Gun damage is also
victim-side (9.26), so no client damages a server object. Making them
destructible needs the server to own their damage, and no message for that
is recovered yet. The spin is applied only by the shooter's own collision
code, so other clients may show a different orientation.

**Not verified:** gunfire at a target ship, a second client, maps other than
Arena1a, and the user's own copy of the client.

**Superseded by 9.46:** the messages were found, and the ships are now
destroyed by the server.

### 9.46 Target ships take damage and blow up: the original server's channels (25 October 2026)

Static analysis of the 2.9.2 client and three live runs ([evidence](../evidence/2.9.2/target_ships_damage_live_20261025.json)).
No client patch is needed.

**The server owned object damage.** `world+0xDEEEC` is an is-server flag.
Two paths that involve it:
- `DoDamage` (`0x49BCE0`) does nothing to an object in a safe zone
  (`+0x2F8`) or flagged `+0x240`. With simple damage on (`+0x1F0`) it calls
  `DoSimpleDamage` (`0x49BFA0`): HP `+0x1E8` −= damage × 0.8 × 0.5 (× 10
  for type 1).
- At 0 HP the HP is refilled from `+0x1EC`, and the object's category
  `+0x200` decides the rest:

| `+0x200` | At 0 HP | Server branch |
|---|---|---|
| 0 | "%s destroyed"; the caller kills it | sends `SendRemoveObject` to every player |
| 1 | "%s respawned" ±2,000 units away | |
| 2 | "%s disabled" (`0x4A6270`) | |
| 3 | "%s disabled timed", `+0x1DC` = 60,000 | sends `SendDisableObject` (`0x49`, 60,000 ms) |
| 4 | nothing; not dead | |

LoadObject sets `+0x200` = 4 (9.45). So a client never destroys a
server-loaded object, and the shooter's own copy just loses HP and refills.
Missile impacts damage only the local player (9.45), and ships have their
simple damage turned off online on the first hit (`0x49BD03`). So for
anything server-owned, the server keeps the score.

**How hits reach the server: perceived damage in `0x1F`.**
- When a gunshot hits an object, `0x48F730` calls
  `CPerceivedDamage::AddEntry` (`0x493480`) on the list at `world+0xDF034`.
  It does so only for the local player's own shots (gunshot `+0x60`, set at
  `0x48F163` when the shooter tag is the local player's) and for targets
  with `+0x1D4` set. A loaded ship has `+0x1D4` = 1.
- The entry is (victim tag, gunshot `+0x68`, count). `+0x68` is the gun
  system's index `+0xA4` (`0x48F180`); repeat hits raise the count.
- `SendPositionUpdate` (`0x434730` → encoder `0x49494A`) writes the list as
  submask 2 of the `0x80000000` block: u8 count, then count × (u32 tag, u8
  gun index, u8 hits). It then clears the list (`0x493460`). The decoder
  reads the same layout at `0x495A38`.
- Live, the client's uploads carried entries `(0x40010002, 2–7, 1)` while
  its six guns hit Target 1: ten uploads in 3 s. The gun index is the
  system's `.Sco` position + 1.

**How the server ended an object.**
- `SendRemoveObject` (`0x488ED0`) is type `0x45`, 3 bytes: u16 world-object
  index, u8 1 = blow up.
- Receiver `0x430728` → `RemoveObject` (`0x4A71A0`) logs "Removing [%s]
  blowing up[%s]", plays the view event, and takes the object out.
- `0x38` ObjectHasDied (`0x4A51C0`) does resolve object tags, but its kill
  routine (`0x4A5440`) treats a non-local object as follows:
  - with `+0x1DC` ≠ −1, it goes dormant (model off, target windows move on);
  - otherwise only a ship that is the local player is moved to the origin.
  - For a loaded ship (`+0x1DC` = −1) it only refills the shields. That was
    live run 2: no change.

**Server** (`TargetShips` in `station_stub.py`; table in `tools/vessel_combat.py`,
generated by `tools/make_vessel_combat.py` from the `.Sco` export and the gun
table):
- **HP:** each ship has the vessel's Shield value as simple HP, matching
  the live client (Ym Khtat 107).
- **Gun hits:** the relay reads each shooter's submask-2 entries
  (`relay_motion.perceived_damage`) and keeps only those for live target
  ships. Each hit costs gun-table damage × 0.4, looked up from the
  shooter's vessel and gun index. Unknown guns, players and counts above 16
  per entry are ignored.
- **Missile hits:** an accepted `0x30` on a ship costs 10 (Type II) or 12
  (Type III). These are the shield drops measured on players (9.32), not a
  recovered rule.
- **Destruction:** at 0 HP every loaded player gets `0x45` (index, 1). After
  15 s every player gets the `0x25` load again at full HP. Late joiners get
  only live ships, and the status file counts destructions.

**Live** (one ship 1,500 units ahead, 4 s of gunfire):
- The client's own copy fell 107 → 98.6 → … → 6.2 in steps of 8.4 (Gun310)
  and 11.2 (Gun-360), the server's formula exactly.
- At 4.44 s the server's count reached 0 and the `0x45` arrived. The object
  went away (`+0x243` 0, tag 0) and the target window emptied.
- At 19.53 s it was back at its spot with 107 HP and targeted again.

**Not verified:**
- the explosion on screen (in-flight captures are black);
- missile kills;
- a second client;
- maps other than Arena1a;
- the user's own copy of the client.

A second client simulates the shooter's gunshots from the relayed fire state
and so damages its own copy too. That copy is never destroyed either, and it
is removed and reloaded with everyone else's.
