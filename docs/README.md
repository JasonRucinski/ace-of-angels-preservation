# Documentation index

Most of these documents are working notes, written as the investigation went.
They are dated, careful to separate what was verified from what was inferred,
and sometimes refer to "the user" (the project owner) who ran live tests.
Newest results are in [findings.md](research/findings.md) and the status section of
[CONTEXT.md](../CONTEXT.md).

## Playing

| Document | What it covers |
|---|---|
| [play.md](play/README.md) | **Start here.** From nothing to flying offline, then with friends |
| [STATUS.md](STATUS.md) | What works and how it was checked, what is untested, what does not exist |
| [lan-dogfight.md](host/lan.md) | Hosting and joining on one home network |
| [vpn-dogfight.md](host/vpn.md) | Playing over the internet through a private VPN, host console, lag testing |
| [linux-host.md](host/linux.md) | Minimal Linux host with a systemd service, LAN checks and a VPN path |
| [host-control.md](host/host-window.md) | The host window: players, scores, kick/ban, map switching |
| [map-viewer.md](play/map-viewer.md) | Loading any of the 20 recovered map layouts in the client |
| [custom-maps.md](create/custom-maps.md) | Building new maps from a JSON spec; the first one, Crucible |
| [custom-objects.md](create/custom-objects.md) | Adding new objects from glTF models; the first one, NASA's Bennu |
| [hype-reel.md](create/hype-reel.md) | Filming scripted shots of the real client and cutting the highlight reel |
| [texture-pack.md](play/texture-pack.md) | Optional sharper ship and station skins, built from your own copy |
| [running-on-windows-11.md](research/windows-11.md) | Why the client crashed on modern Windows and how it was fixed |
| [client-setup.md](reference/client-patches.md) | Every client patch, its address, the undo and the checks |

## History and preservation

| Document | What it covers |
|---|---|
| [CONTEXT.md](../CONTEXT.md) | The research record: recovered builds, the company, the universe, revival evidence, what was searched |
| [../data/magazine-mentions.md](../data/magazine-mentions.md) | 2000–2006 magazine coverage, with archive links |
| [version-assets.md](reference/versions.md) | What differs across the six recovered versions |
| [level-data.md](research/level-data.md) | Maps, scenarios and missions found in the clients |
| [hosting-assets.md](reference/maps.md) | Inventory of the 2.9.2 maps, backdrops and scenario |
| [assets.md](reference/asset-formats.md) | Extracting models and textures for study (output is never committed) |
| [private-web-archive.md](archive/web-archive.md) | Rebuilding the old website and forums from the Wayback Machine |

## How the game works

Reverse-engineering notes. Addresses refer to the hash-verified 2.7.1 or 2.9.2
`AOACLIENT.EXE` named in each document.

| Document | What it covers |
|---|---|
| [findings.md](research/findings.md) | The main log: network protocol, cipher, packet formats, and every fix (sections 9.x) |
| [local-protocol.md](reference/protocol.md) | The protocol subset the stand-in server implements |
| [message-types.md](reference/message-types.md) | Table of message types, senders and receivers |
| [code-clues.md](research/code-clues.md) | Other recovered code paths and source-path clues |
| [local-server.md](host/server-reference.md) | Server profiles, options and logs |
| [arena1a.md](research/arena1a.md) | Recovering the Arena1a map |
| [arena1a-rebuild.md](research/arena1a-trials.md) | Arena1a navigation buoys, turret and warp gate trials (26–27 October 2026) |
| [render-pipeline-audit.md](research/rendering/pipeline-audit.md) | Rendering bugs found by emulation |
| [asteroid-rendering.md](research/rendering/asteroids.md) | The asteroid size-popping investigation |
| [offline-rendering-baseline.md](research/rendering/offline-baseline.md) | Rendering baseline for the offline mission |

## Plans

| Document | What it covers |
|---|---|
| [internet-server-todo.md](roadmap/internet-server.md) | Roadmap for a real internet server, maps and performance |
| [modernization-todo.md](roadmap/modernization.md) | Roadmap for client and game modernization |
| [first-playable-release.md](roadmap/authoritative-server.md) | Specification for an authoritative first release (deferred) |
| [client-extension-gate.md](client-extension-gate.md) | Gate for client changes an authoritative server would need |
