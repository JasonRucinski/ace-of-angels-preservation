# Notice

This is an unofficial, non-commercial preservation and research project. It
is not affiliated with, endorsed by or connected to Flying Rock Enterprises,
L.L.C., its founders or any successor.

*Ace of Angels*, its client, art, models, sounds, music, text and the
"Known Sphere" setting are the work of Flying Rock Enterprises and remain
the property of their respective owners. Names are used here only to identify
the game being studied.

## What this repository does and does not contain

- **No game files.** No installer, executable, texture, model, sound or other
  game asset is stored here. The tools read a copy you obtain yourself,
  from the public archive listings (archive.org, the Wayback Machine,
  Discmaster) recorded in
  [`manifest/downloads.json`](manifest/downloads.json).
- **A few website images.** The README shows 11 promotional screenshots and
  art images from the archived official sites (aceofangels.com and
  flyingrockllc.com), kept in [`docs/images/`](docs/images/SOURCES.md) with
  their sources. They are not taken from the game files.
- **Patches are applied locally.** The client fixes in `tools/` change bytes in
  your own copy of the game executable, with an exact undo. They do not ship
  any part of the original program.
- **The stand-in server is new code.** `tools/station_stub.py` and its helpers
  were written from observing and statically analysing the client. No
  original server software was recovered or used.
- **Research data** under `evidence/` and `data/` records measurements, hashes,
  short identifying strings and citations, for verification and scholarship.

The game's end-user licence agreement forbids redistributing the game without
Flying Rock's written permission. Please do not open issues or pull requests
that add game files, and do not re-host them alongside this project.

If you hold rights in *Ace of Angels* and have a concern about anything here,
please open an issue or contact the repository owner through GitHub, and it
will be addressed promptly.
