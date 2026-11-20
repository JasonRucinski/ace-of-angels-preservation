# Ace of Angels (Flying Rock Enterprises): research context

Everything found so far about *Ace of Angels*, Flying Rock Enterprises' online
3D space-combat sim (2000–2006). The work was done in a cloud Claude Code
session on 2026-10-20; this file carries it to a local project.

Items marked *verified* were checked directly: downloaded, hashed, parsed,
read in OCR text, or read from a registry. Items marked *(snippet)* came from
a search-engine summary only.

## 1. The asks

1. Download links for every release, demo, beta and alpha.
2. A link to the website with the game's universe and lore.
3. Any sign that the project is coming back.

## 2. Status

The development work that followed this research (client fixes, the
stand-in host, maps and tools) is logged by date in
[docs/research/log.md](docs/research/log.md), which holds what this section
recorded from 20 to 27 October 2026. What works today, and what is untested:
[docs/STATUS.md](docs/STATUS.md). The status of the three asks:

| Ask | Status |
|---|---|
| Builds | **Six recovered client versions, verified locally:** full installers 2.0.0, 2.7.1, 2.8.0, 2.8.2, 2.9.2, plus replacement client 2.3.1 (no complete asset bundle). See `manifest/downloads.json` for sources/hashes and `docs/reference/versions.md` for the cross-version inspection. The older source table below is historical and incomplete. |
| Universe site | **aceofangels.com**; before that, **flyingrockllc.com** (2000–01 magazines). Both are offline. **Restored** from the Wayback Machine on 21 Oct 2026: 2,894 archived pages, including 949 forum pages. Kept private because it copies third-party pages; rebuild it with `tools/restore_web_archive.py` ([docs/archive/web-archive.md](docs/archive/web-archive.md)). |
| Revival | **No public sign.** A March 2006 release was scheduled, then nothing. The domains are still renewed (to 2027), registrant hidden. |

## 3. Builds and media

**Local asset review, 20 October 2026:** the six-version manifest supersedes
the original three-build search below. Missing packages were downloaded into
`builds/asset-review/`; previously retained 2.7.1 and 2.9.2 originals were
reverified. Static extraction and comparisons live under `work/asset-review/`
and `evidence/asset-review/`. See `docs/reference/versions.md` for useful recovered
geometry, older arena markers, limitations, and reproduction commands.

| What | Version | Date | Size | MD5 / SHA-256 | Where (live 2026-10-20) | Status |
|---|---|---|---|---|---|---|
| Client installer `aoa-current.exe`, from the **CD-Action 06/2002** cover CD (PL) | **v2.8.2** | file 2002-03-28; © 1997–2001 | 28,083,710 B | `96c852b07a7d55c7894dbdda624fa3db` / `9edcb5376d875188a6986067a3fd05952fb25086db0c456f01bfdfd84e840052` | https://archive.org/download/cda_20260908/CDA%2006-2002.iso/%23dema%2Face%20of%20angels%2Faoa-current.exe | **verified**; every packed file passes CRC |
| Beta v2.8.0 on FilePlanet | v2.8.0 | 2002-06-04 | ~26.6 MB | MD5 `7401dd3d2a54256e60c1bb3e5b35f752` (as listed) | https://www.fileplanet.com/56934/download/Ace-of-Angels-Beta-v2.8.0 | **not verified**: Cloudflare 403 even in headless Chromium |
| ″, Archive Team's 2012 FilePlanet rescue (ID 56934) | ″ | | | | https://archive.org/details/FileplanetFiles_50000-559999 (IDs 55000–59999, 24 GB tar) | **restricted** (401/403) |
| Client installer `aoa-current.exe`, from *Family Game Pack 3* (HU, Woodstone, MMH 269) | **v2.9.2** | file 2004-07-20; © 1997–2004 | 35,461,120 B | `ddb6a3217a0987bdf0eedef7c19767af` / `90c4a47e5df320171667209288edbe9899f957a397cb982bc459f17c785cbe38` | https://archive.org/download/family-game-pack-3-mmh-269/Family%20GamePack%203%20MMH269.iso/Games%2FAce%20of%20Angels%2Faoa-current.exe and the mirror https://archive.org/download/family_game_pack32004/family_game_pack3%282004%29.iso/Games%2FAce%20of%20Angels%2Faoa-current.exe | **verified**; both copies byte-identical |
| Trailer `ace of angels.wmv`, from the **PC Zone 118 cover DVD**, Aug 2002 (UK), "Best of E3" | – | 2002 | 2,978,383 B | `cc14e4e112e7ad64644d64fbbe51e8cc` / `b4e1fd1ad82dbceeaa1b17e278144757ee56e07db79a51c5f8df36fa8eaf399d` | kept locally, not in this repository; on archive.org only inside the 3.96 GB https://archive.org/details/dppcz-0802-dvd.-7z | **verified** (valid ASF) |
| Demo (early 2001) | ? | early 2001 | ? | – | Mega Game 03/2001 reviewed it, "downloaded from Flying Rock's site" | **not found** (not on Mega Game 02–05/2001 discs) |
| Intro video (< 3 MB) on the CD-Action 01/2003 cover CD, Bonus section | – | 2002–03 | < 3 MB | – | That CD isn't on archive.org; maybe in `cd-action-bonus-2003` (`2003.zpaq`, 866 MB) | not checked; probably the same as the trailer |
| Gamers Workshop #37 disc (BG, Apr 2002) | ? | 2002-04 | ? | – | The magazine lists Ace of Angels in its disc contents; the disc isn't on archive.org | **not found** |

`tools/fetch_known_builds.py builds/` downloads both verified builds and
checks their MD5s (tested).

### What's in the builds (inspected without running them)

- Both are Wise installers holding the full client: AOACLIENT.EXE,
  TEXTURES/SOUNDS/HUD/DATA/IMAGES/FX/SCENARIOS/SCRIPTS `.AOA` packs,
  AOAOBJECTS.ODB, MUSIC.MP3, KEYMAP.PDF, a tutorial, notes and the EULA.
- **Versions come from compiled-in globals** (`tools/aoa_version.py`). The
  bundled AOANOTES.TXT says "v2.3.0" in both builds; it was never updated.
- There is an **offline training mission**: waves of 6 enemies, with 3 AI
  wingmen you command. CD-Action's disc text says "offline mission and
  tutorial available". **Online play is dead**: the server address is
  hard-coded to 66.154.81.18 (Cyber Wurx, Atlanta colocation).
- The client contains the string "Ace of Angels is not supported on Windows
  NT", though Windows 2000 was supported (likely an NT4 check). Needs DirectX
  7. (20 Oct 2026 note; since then 2.9.2 runs on Windows 10/11 with the
  project's fixes: [docs/play/README.md](docs/play/README.md).)
- The EULA forbids redistribution without Flying Rock's written permission.
  Linking to archive.org copies is fine; re-hosting is a separate decision.

## 4. The game and the company

- **Timeline from magazines** (`data/magazine-mentions.md`):
  - in development "since 1996", by a team of five over four years
  - previews from 2000 onward, aimed at "mid-2000", then Q1 2001, then Q1 2002
  - a demo and arena betas in 2001
  - IGF 2002 finalist, then **Technical Excellence winner** (Mar 2002)
  - Milia 2002, Cannes
  - free client downloads and cover-CD betas in 2002, "still without a
    publisher" in Nov 2002 and Oct 2003
  - "online-only, never in shops" (CD-Action, Apr 2003)
  - a new beta "expected soon" (GameStar HU, Jan 2004); v2.9.2 dates from 2004
  - **scheduled release 20 Mar 2006** (Come to Game #2, 2006); nothing after
- **Flying Rock Enterprises, L.L.C.**: Georgia company no. K822302 (previously
  1072437), administratively dissolved 26 Aug 2011 (OpenCorporates). In the
  game files: 488 Kennesaw Ave NW, Marietta GA 30060, support@aceofangels.com.
- People: Bryan G. Stephens spoke for Flying Rock in a Feb 2002 interview
  (Shacknews, quoting homelanfed.com). Founders were "Linda, Jamey, and Curt
  and me", plus Ahmed *(snippet, GameDev.net)*. Curt Hartung designed the
  flight model *(snippet)*. An artist did concept art for "Flying Rock
  Productions" in 1998–99 (Dragon Con 2007 program).
- Trademarks (USPTO and the Official Gazette):
  - ACE OF ANGELS, SN 75-840,543, reg. 2,395,790; first use 1998-10-28;
    cancelled 2007
  - ACE OF ANGELS AND DESIGN, reg. 2,486,838; expired 2008
  - FLYING ROCK ENTERPRISES, LLC, expired 2007
  - The only later filing found is a 2023 "ACE OF ANGELS" mark for clothing
    (SN 97903051); its owner wasn't checked and it is probably unrelated.

### Universe (for the lore search)

- Early 26th century, **"The Known Sphere"** (about a quarter of the Milky
  Way), **8 races and 10 nations**, each with its own culture and military
  philosophy (Worthplaying 2002).
- 40+ fighters, about 50 flagship classes, 200 players per server *(Gamepressure)*.
- 20 ships in the 2002 beta. The first arena, the Battlezone Area, ran from
  Earth to the Moon.
- Players climb from recruit to general and take part in their nation's
  politics. Downed pilots eject; if their side loses, they are taken prisoner
  and can be ransomed or escape (CD-Action 04/2003).
- Strings in the client (*verified*): ship names **Naroch, Mkulat, Vermok,
  Vasa Chovo**; "Please select a Race / Nation"; "Alliance", "Republican".
- Old-site URLs from the client:
  - `http://www.aceofangels.com/manual/manualframes.html`
  - `http://www.aceofangels.com/cgi-local/wrapit_nolinks.pl?file='players/signup.html'`
  - the menu path "Player Links → Information → General Player Rules of Conduct"

## 5. Revival evidence (RDAP and HTTP, 2026-10-20)

| Domain | Registered | Expires | DNS | Live state |
|---|---|---|---|---|
| aceofangels.com | 1998-10-21 | 2027-10-20 | GoDaddy / Domains By Proxy; NS67/68.WORLDNIC.COM | does not resolve |
| flyingrockllc.com (the site named in 2000–01 magazines) | **1998-10-21, same day** | 2027-10-20 | GoDaddy; DOMAINCONTROL; A 66.118.69.159 (CityNet) | resolves; HTTP 503/timeout from the cloud |
| flyingrock.com | 1997-09-11 | 2027-09-10 | Network Solutions; JOMAX | "Site Under Construction", Last-Modified 2021-07-02. **Not confirmed to be Flying Rock's.** |

LeadIQ (an aggregator, low weight) lists "Flying Rock Enterprises", about 2
employees, website flyingrockllc.com, LinkedIn
`linkedin.com/company/flying-rock-enterprises`.

## 6. Already searched (don't repeat)

- **archive.org disc images:** 142 items, logged in `data/disc_search.tsv`.
  74 were really searched; 64 could not be (raw `.bin`/`.img`, or images
  wrapped in RAR/7z/ZIP); 4 found something.
- **archive.org full-text search** of scanned magazines: 83 files, 29
  relevant (`data/magazine-mentions.md`). The search found nothing for
  `aceofangels.com` or `flyingrockllc` as single tokens.
- archive.org catalog under several spellings; Game Patches Archive "A"; the
  Yahoo Groups `aceofangels` WARC (restricted).
- Download portals and abandonware sites: nothing. FTP indexes (Mamont):
  nothing named `aoa-current.exe`, `aoaclient`, `aceofangels` or `flyingrock`.
- Steam, itch.io, IndieDB, ModDB, Reddit, Discord, YouTube: nothing.
- **Blocked from the cloud** (worth retrying locally):
  - web.archive.org (network policy)
  - Discmaster and Common Crawl (connection reset)
  - Arquivo.pt (403 on its index and search APIs)
  - Library of Congress web archive and archive.today (CAPTCHA)
  - FilePlanet, GameSpot and GameFAQs (Cloudflare)
- **Search noise:** "Ace of Angels" is also the K-pop group AOA. Pair the name
  with "Flying Rock" or "space".

## 7. Next steps (in order)

1. **Wayback Machine**, for the universe site and any builds it hosted:
   - `python3 -I tools/wayback_builds.py --out wb/`, then `--download`
   - read `wb/all_urls.tsv` for lore, manual, news and download pages
   - check `flyingrockllc.com` (the 2000–01 site) as well as aceofangels.com
   - by hand: https://web.archive.org/web/*/aceofangels.com*
2. **Discmaster** (https://discmaster.textfiles.com): search `aoa-current.exe`,
   `aoaclient.exe`, `flyingrockeula.txt`, `aoanotes.txt`. It indexes files
   inside archive.org's CD images, including the 64 unsearched ones.
3. **The unsearched discs** in `data/disc_search.tsv`, most promising first:
   - Joystick #134 (02/2002) and #136 (04/2002): raw `.img`
   - Czech GameStar #36–#40 (01–05/2002): `.bin`. Try the small
     `*_dic-files.zip` logs first; the `_volDesc`/`_mainInfo` text lists
     directory records. Skip the large `*_cd1.zip` files.
   - the PC Guru 2001 CD collection (`PCGURUCD`)
   - Hungarian GameStar and PC Guru 2003–04 zips
   - the CD-Action Bonus 2002/2003 `.zpaq` archives
   - The method: download, then
     `python3 -I tools/run.py aoa.research.disc_image rar …` or
     `7z e -so … | python3 -I tools/run.py aoa.research.disc_image iso …`.
4. **FilePlanet in a real browser**: does the v2.8.0 file download? Check its
   MD5 against `7401dd3d…f752`.
5. **Revival follow-ups**:
   - open flyingrockllc.com in a browser
   - the LinkedIn company page
   - a USPTO search for new "ACE OF ANGELS" or "FLYING ROCK" filings
   - a Georgia Secretary of State search for a successor entity
   - an X or Facebook search for "Ace of Angels" with "Flying Rock"
6. **Every new build** gets the same treatment: `tools/run.py aoa.formats.wise`,
   then `tools/aoa_version.py`, then hashes. Add a row to the table in section 3.

## 8. Tools

Every command and module, with what it does, is indexed in
[docs/reference/tools.md](docs/reference/tools.md) (generated from the module
docstrings). The table that stood here on 20 October 2026, with what each
tool had been tested on, is kept in the
[research log](docs/research/log.md#archive-research-tools-from-contextmd).

Debian's `7zip` package can *list* RAR archives but can't decompress them;
use libarchive (`tools/run.py aoa.research.disc_image rar`) or a 7-Zip build
with the RAR codec.

## 9. Safety

- **Never run an installer on your own machine.** Use a throwaway Windows
  98/XP VM.
- One new, empty directory per download. Keep scripts elsewhere and run them
  with `python3 -I`.
- Pace requests to the archives. Every archive.org and Wayback request in
  `tools/` goes through `aoa/research/http.py`, which waits between requests
  to the same host and backs off on HTTP 429 and 5xx (13 Nov 2026).

## 10. Sources

- Magazine scans: `data/magazine-mentions.md`, with links.
- French Wikipedia: https://fr.wikipedia.org/wiki/Ace_of_Angels_(jeu_vid%C3%A9o)
- Worthplaying, 17 Jan 2002: https://worthplaying.com/article/2002/1/17/news/1925-ace-of-angels-to-be-at-the-milia-2002/
- IGF 2002 winners: https://www.writerswrite.com/winners-announced-at-independent-games-3282002788
- Shacknews interview, 23 Feb 2002: https://www.shacknews.com/article/18846/ace-of-angels-interview
- GameDev.net interview: https://gamedev.net/tutorials/industry/interviews/flying-rock-enterprises-r1776
- GameSpot first look: https://www.gamespot.com/articles/first-look-ace-of-angels/1100-2833623/
- Gamepressure: https://www.gamepressure.com/games/ace-of-angels/zdaf6
- games.cz: https://games.tiscali.cz/ace-of-angels-2398
- OpenCorporates: https://opencorporates.com/companies/us_ga/K822302
- LeadIQ: https://leadiq.com/c/flying-rock-enterprises/5a1dd0fe2300005c00d9790b
- Justia, 2023 filing: https://trademarks.justia.com/979/03/ace-of-97903051.html
- RDAP: `https://rdap.verisign.com/com/v1/domain/<domain>`, then the registrar link
