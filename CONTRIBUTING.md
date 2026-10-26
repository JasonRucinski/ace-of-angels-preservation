# Contributing

Thanks for helping keep *Ace of Angels* alive. Four kinds of help matter most.

## Leads and old material

The project is still missing builds and history. Especially wanted:

- **Discs**: magazine cover CDs/DVDs from 2001–2004 with an Ace of Angels demo
  or beta, such as Joystick #134/#136 (FR), GameStar CZ #36–#40, Gamers
  Workshop #37 (BG), the CD-Action 01/2003 Bonus section (PL), PC Guru (HU).
- **Builds**: the early-2001 demo, any arena beta, or any version not in
  [`manifest/downloads.json`](manifest/downloads.json).
- **The universe**: manuals, lore pages, forum posts, screenshots or videos.
- **The people**: anything from former Flying Rock staff or players, and any
  sign of the 2009–2010 OGRE or 2020 Unreal Engine 4 revival attempts.

Open a **Lead** issue with what you have and where it came from. Please do not
upload game files to this repository; a description, a hash and a public
archive link are enough. [CONTEXT.md](CONTEXT.md) section 6 lists what has
already been searched.

## Play reports

Multiplayer between separate PCs has not been recorded yet, so any session is
valuable. Open a **Play report** issue with your Windows version, GPU, whether
you used the dgVoodoo wrapper, LAN or VPN, the player count, and what did or
didn't work. The client log in `game\2.9.2\Logs\` helps with crashes.

## Code and reverse engineering

Setup is in [docs/play.md](docs/play.md); the tool map is in
[tools/README.md](tools/README.md); the notes are indexed in
[docs/README.md](docs/README.md).

House rules, from how the project has worked so far:

- **Evidence over claims.** Say what was verified and how: a test, an
  emulation run, a live client check. Keep "untested" visible. Machine-readable
  results go in `evidence/`.
- **Client patches are reversible and hash-checked.** A new patch accepts only
  known images, records its undo, and gets a `test_*.py` that checks it, often
  by running the original code in Unicorn.
- **No game files in commits.** Extracted assets and renders go to the ignored
  `work\` folder.
- **Untrusted downloads stay contained.** Each download goes in its own new,
  empty folder under `builds\` or `wb\`. Run Python on it with `-I`, from
  outside that folder.
- **Be gentle with archive.org and the Wayback Machine**: pause between
  requests and back off on HTTP 429.

Before opening a pull request, run the tests that cover your change, and the
full gate if you have the game set up:

```powershell
.venv\Scripts\python.exe -I tools\verify_local.py
```

The tests that need no game files also run in CI on every pull request.

## Searching tips

"Ace of Angels" is also the K-pop group AOA. Pair searches with
"Flying Rock" or "space". Anything taken only from a search-engine summary is
marked *(snippet)* in the notes until the source itself is read.
