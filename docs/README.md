# Documentation index

Most of these documents are working notes, written as the investigation went.
They are dated, careful to separate what was verified from what was inferred,
and sometimes refer to "the user" (the project owner) who ran live tests.
Newest results are in [findings.md](findings.md) and the status section of
[CONTEXT.md](../CONTEXT.md).

## Playing

| Document | What it covers |
|---|---|
| [play.md](play.md) | **Start here.** From nothing to flying offline, then with friends |
| [lan-dogfight.md](lan-dogfight.md) | Hosting and joining on one home network |
| [vpn-dogfight.md](vpn-dogfight.md) | Playing over the internet through a private VPN, host console, lag testing |
| [linux-host.md](linux-host.md) | Minimal Linux host with a systemd service, LAN checks and a VPN path |
| [host-control.md](host-control.md) | The host window: players, scores, kick/ban, map switching |
| [map-viewer.md](map-viewer.md) | Loading any of the 20 recovered maps in the client |
| [hype-reel.md](hype-reel.md) | Filming scripted shots of the real client and cutting the highlight reel |
| [texture-pack.md](texture-pack.md) | Optional sharper ship and station skins, built from your own copy |
| [running-on-windows-11.md](running-on-windows-11.md) | Why the client crashed on modern Windows and how it was fixed |
| [client-setup.md](client-setup.md) | Every client patch, its address, the undo and the checks |

## History and preservation

| Document | What it covers |
|---|---|
| [CONTEXT.md](../CONTEXT.md) | The research record: recovered builds, the company, the universe, revival evidence, what was searched |
| [../data/magazine-mentions.md](../data/magazine-mentions.md) | 2000–2006 magazine coverage, with archive links |
| [version-assets.md](version-assets.md) | What differs across the six recovered versions |
| [level-data.md](level-data.md) | Maps, scenarios and missions found in the clients |
| [hosting-assets.md](hosting-assets.md) | Inventory of the 2.9.2 maps, backdrops and scenario |
| [assets.md](assets.md) | Extracting models and textures for study (output is never committed) |
| [private-web-archive.md](private-web-archive.md) | Rebuilding the old website and forums from the Wayback Machine |

## How the game works

Reverse-engineering notes. Addresses refer to the hash-verified 2.7.1 or 2.9.2
`AOACLIENT.EXE` named in each document.

| Document | What it covers |
|---|---|
| [findings.md](findings.md) | The main log: network protocol, cipher, packet formats, and every fix (sections 9.x) |
| [local-protocol.md](local-protocol.md) | The protocol subset the stand-in server implements |
| [message-types.md](message-types.md) | Table of message types, senders and receivers |
| [code-clues.md](code-clues.md) | Other recovered code paths and source-path clues |
| [local-server.md](local-server.md) | Server profiles, options and logs |
| [arena1a.md](arena1a.md) | Recovering the Arena1a map |
| [render-pipeline-audit.md](render-pipeline-audit.md) | Rendering bugs found by emulation |
| [asteroid-rendering.md](asteroid-rendering.md) | The asteroid size-popping investigation |
| [offline-rendering-baseline.md](offline-rendering-baseline.md) | Rendering baseline for the offline mission |

## Plans

| Document | What it covers |
|---|---|
| [internet-server-todo.md](internet-server-todo.md) | Roadmap for a real internet server, maps and performance |
| [modernization-todo.md](modernization-todo.md) | Roadmap for client and game modernization |
| [first-playable-release.md](first-playable-release.md) | Specification for an authoritative first release (deferred) |
| [client-extension-gate.md](client-extension-gate.md) | Gate for client changes an authoritative server would need |
