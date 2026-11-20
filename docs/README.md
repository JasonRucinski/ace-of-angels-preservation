# Documentation

Every document, once, by who it is for. The kind says how to read it:

- **guide**: how to do something; kept current.
- **reference**: facts to look up. Tables marked *generated* are written from
  the code and a CI test fails when one is stale.
- **log**: a dated research record, kept as it was written; later results
  are new entries that link back (see [Research records](#research-records)).
- **roadmap**: proposed work, not a claim that it is done.

What works today and what is untested is stated in one place only:
[STATUS.md](STATUS.md) (reference). How to contribute, the house rules and
where each kind of doc goes: [CONTRIBUTING.md](../CONTRIBUTING.md).

## Players

| Document | Kind | What it covers |
|---|---|---|
| [play/README.md](play/README.md) | guide | **Start here.** From nothing to flying offline on Windows 10/11, then joining friends |
| [play/launcher.md](play/launcher.md) | guide | The player window's Options: what each group does, Apply, undo, the texture pack switch |
| [play/troubleshooting.md](play/troubleshooting.md) | guide | Symptoms and fixes; what `setup_game.ps1` does by hand |
| [play/texture-pack.md](play/texture-pack.md) | guide | Optional sharper ship and station skins, built from your own copy |
| [play/map-viewer.md](play/map-viewer.md) | guide | Flying around any of the 20 recovered map layouts |

## Hosts

| Document | Kind | What it covers |
|---|---|---|
| [host/README.md](host/README.md) | guide, generated defaults | **Start here.** This PC, home network, VPN or Linux; ports, firewall, the hosts name; each player's steps; the defaults tables |
| [host/host-window.md](host/host-window.md) | guide | The host window: who can join, start, share, players, change map |
| [host/lan.md](host/lan.md) | guide | Hosting on a home network by hand, and LAN acceptance |
| [host/vpn.md](host/vpn.md) | guide | Friends on other connections through a private VPN |
| [host/linux.md](host/linux.md) | guide | The unattended Linux service: setup, rotation, recovery |
| [host/console.md](host/console.md) | guide | Console commands, the status file, crash restarts, lag testing |
| [host/server-reference.md](host/server-reference.md) | reference, generated flags | Server profiles, every server flag, logs, sessions and limits |

## Map makers and video

| Document | Kind | What it covers |
|---|---|---|
| [create/custom-maps.md](create/custom-maps.md) | guide | Building new maps from a JSON spec; the first one, Crucible |
| [create/custom-objects.md](create/custom-objects.md) | guide | Adding new objects from glTF models; the first one, NASA's Bennu |
| [create/hype-reel.md](create/hype-reel.md) | guide | Filming scripted shots of the real client and cutting the highlight reel |

## Contributors

Reverse-engineering references. Addresses refer to the hash-verified 2.7.1 or
2.9.2 `AOACLIENT.EXE` named in each document.

| Document | Kind | What it covers |
|---|---|---|
| [reference/client-patches.md](reference/client-patches.md) | reference, generated patch table | Every client patch, its addresses, the undo and the checks |
| [reference/protocol.md](reference/protocol.md) | reference | The protocol subset the stand-in server implements |
| [reference/message-types.md](reference/message-types.md) | reference, generated | Message types, senders and receivers (by `aoa.analysis.message_table`) |
| [reference/maps.md](reference/maps.md) | reference, generated map table | The 20 loadable maps, how the client loads one, the 2.9.2 map and scenario assets |
| [reference/asset-formats.md](reference/asset-formats.md) | reference | The `.Gob` and `.Sco` formats; extracting models and textures for study |
| [reference/versions.md](reference/versions.md) | reference | What differs across the six recovered versions |
| [reference/tools.md](reference/tools.md) | reference, generated index | Every command and module |
| [restructure/README.md](restructure/README.md) | log | The November 2026 restructure: plan, briefs, audits, what still needs Windows |

## Researchers

| Document | Kind | What it covers |
|---|---|---|
| [../CONTEXT.md](../CONTEXT.md) | log | The archive research record: builds, the company, the universe, revival, what was searched, next steps |
| [../data/magazine-mentions.md](../data/magazine-mentions.md) | reference | 2000–2006 magazine coverage, with archive links |
| [archive/web-archive.md](archive/web-archive.md) | guide | Rebuilding the old website and forums from the Wayback Machine |
| [images/SOURCES.md](images/SOURCES.md) | reference | Where each README image came from, with hashes |

### Research records

| Document | Kind | What it covers |
|---|---|---|
| [research/README.md](research/README.md) | guide | How the records are kept and added to |
| [research/log.md](research/log.md) | log | The development log by date, newest first |
| [research/findings.md](research/findings.md) | log | Static protocol findings (sections 1–8) and every live investigation and client fix (9.1–9.48) |
| [research/windows-11.md](research/windows-11.md) | log | Why the client crashed on modern Windows and how it was fixed (20 October 2026) |
| [research/level-data.md](research/level-data.md) | log | Maps, scenarios and missions found in the clients (22 October 2026) |
| [research/code-clues.md](research/code-clues.md) | log | Other recovered code paths and source-path clues |
| [research/arena1a.md](research/arena1a.md) | log | Recovering the Arena1a map |
| [research/arena1a-trials.md](research/arena1a-trials.md) | log | Arena1a navigation buoys, turret and warp gate trials (26–27 October 2026) |
| [research/rendering/pipeline-audit.md](research/rendering/pipeline-audit.md) | log | Rendering bugs found by emulation |
| [research/rendering/asteroids.md](research/rendering/asteroids.md) | log | The asteroid size-popping investigation and the rendering patches |
| [research/rendering/offline-baseline.md](research/rendering/offline-baseline.md) | log | Rendering baseline for the offline mission |

## Plans

| Document | Kind | What it covers |
|---|---|---|
| [roadmap/internet-server.md](roadmap/internet-server.md) | roadmap | A real internet server, maps and performance |
| [roadmap/modernization.md](roadmap/modernization.md) | roadmap | Client and game modernization |
| [roadmap/authoritative-server.md](roadmap/authoritative-server.md) | roadmap | The deferred authoritative server: first release specification and client-extension gate |

The pages at the old `docs/*.md` paths are stubs that say where each one
moved.
