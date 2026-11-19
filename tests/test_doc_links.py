"""Every relative link and anchor in the Markdown resolves; game-free.

Checks each tracked .md file outside docs/restructure/audits/ (a frozen
record of the audit): every relative link, image and reference definition,
and every href/src attribute, names a file or folder that exists, and every
#anchor exists in the Markdown file it points at (GitHub's heading ids, plus
explicit <a id="..."> anchors). A link may not point into the ignored
builds/, game/, originals/, wb/ or work/ folders, or outside the
repository, and may not land on a stub: the three-line page left at a doc's
old path that says where it moved. The GitHub links of the issue templates
are held to the same rules.

    python -I tools/test.py test_doc_links
"""
import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import unquote

from aoa.paths import ROOT

EXEMPT = ("docs/restructure/audits/",)
IGNORED = {"builds", "game", "originals", "wb", "work"}
FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1")
LINK = re.compile(r'\]\(([^)\s]+)(?:\s+"[^"]*")?\)|^\s*\[[^\]]+\]:\s*(\S+)|(?:href|src)="([^"]+)"', re.M)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EXPLICIT = re.compile(r'<a\s+(?:id|name)="([^"]+)"')
STUB = re.compile(r"\A# [^\n]+\n\nMoved to [^\n]*\]\([^)\n]+\)[^\n]*\n\Z")
ISSUE_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/blob/main/([^\s#\"']+)(?:#([\w-]+))?")


def tracked(*patterns):
    """Tracked (and new, not ignored) files matching the patterns, repo-relative."""
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "--", *patterns], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        return sorted({p for p in out.splitlines() if (ROOT / p).is_file()})
    except (OSError, subprocess.CalledProcessError):
        found = set()
        for pattern in patterns:
            for path in ROOT.glob(pattern if "/" in pattern else f"**/{pattern}"):
                parts = path.relative_to(ROOT).parts
                if path.is_file() and not (set(parts[:1]) & IGNORED or ".git" in parts):
                    found.add(path.relative_to(ROOT).as_posix())
        return sorted(found)


def prose_lines(text):
    """(line number, line) outside fenced code blocks, with inline code spans removed."""
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, CODE_SPAN.sub("", line)


def slug(heading):
    """GitHub's id for a heading's text."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)   # links and images keep their text
    text = re.sub(r"<[^>]+>", "", text).replace("`", "")
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


_anchors = {}


def anchors(path):
    """Every id a link may name in this Markdown file."""
    if path not in _anchors:
        found, counts, fenced = set(), {}, False
        for line in path.read_text(encoding="utf-8").splitlines():
            if FENCE.match(line):
                fenced = not fenced
                continue
            if fenced:
                continue
            found.update(EXPLICIT.findall(line))
            m = HEADING.match(line)
            if m:
                base = slug(m[2])
                n = counts.get(base, 0)
                counts[base] = n + 1
                found.add(base if n == 0 else f"{base}-{n}")
        _anchors[path] = found
    return _anchors[path]


def is_stub(path):
    return path.suffix == ".md" and path.is_file() and bool(STUB.match(path.read_text(encoding="utf-8")))


def check_target(source, target):
    """The problem with one link from `source` (a repo-relative path), or None."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return None
    path, _, anchor = target.partition("#")
    if path:
        resolved = (ROOT / source).parent.joinpath(unquote(path)).resolve()
    else:
        resolved = (ROOT / source).resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        return f"{target}: outside the repository"
    if relative.parts and relative.parts[0] in IGNORED:
        return f"{target}: into the ignored {relative.parts[0]}/ folder"
    if not resolved.exists():
        return f"{target}: {relative.as_posix()} does not exist"
    if path and is_stub(resolved):
        return f"{target}: lands on a stub (link the page it moved to)"
    if anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
        return f"{target}: no #{anchor} in {relative.as_posix()}"
    return None


def problems():
    found = []
    for source in tracked("*.md"):
        if source.startswith(EXEMPT):
            continue
        for number, line in prose_lines((ROOT / source).read_text(encoding="utf-8")):
            for m in LINK.finditer(line):
                problem = check_target(source, next(g for g in m.groups() if g))
                if problem:
                    found.append(f"{source}:{number}: {problem}")
    for source in tracked(".github/ISSUE_TEMPLATE/*"):
        for number, line in enumerate((ROOT / source).read_text(encoding="utf-8").splitlines(), 1):
            for m in ISSUE_URL.finditer(line):
                problem = check_target("README.md", m[1] + (f"#{m[2]}" if m[2] else ""))
                if problem:
                    found.append(f"{source}:{number}: {problem}")
    return found


class DocLinks(unittest.TestCase):
    def test_every_link_resolves(self):
        found = problems()
        self.assertEqual(found, [], "broken doc links:\n" + "\n".join(found))

    def test_stubs_point_at_a_page(self):
        stubs = [p for p in tracked("*.md") if is_stub(ROOT / p)]
        self.assertTrue(stubs, "no stubs found: the stub pattern no longer matches")
        for stub in stubs:
            with self.subTest(stub=stub):
                target = LINK.search((ROOT / stub).read_text(encoding="utf-8"))
                self.assertIsNone(check_target(stub, next(g for g in target.groups() if g)))

    def test_the_checker_catches_what_it_should(self):
        # Guards the parser: each of these must be reported.
        for target in ("docs/no-such-page.md", "docs/STATUS.md#no-such-heading", "work/x.png",
                       "../outside.md", "docs/play.md"):
            with self.subTest(target=target):
                self.assertIsNotNone(check_target("README.md", target))
        self.assertIsNone(check_target("README.md", "docs/STATUS.md#maps"))
        self.assertEqual(slug("9.47 An orbit camera on F4; F2 was never unbound (26–27 October 2026)"),
                         "947-an-orbit-camera-on-f4-f2-was-never-unbound-2627-october-2026")
        self.assertEqual(slug("🚀 The game"), "-the-game")


if __name__ == "__main__":
    unittest.main()
