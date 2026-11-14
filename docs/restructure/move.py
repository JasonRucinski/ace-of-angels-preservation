"""Phase 1 of the restructure: move tools/ into aoa/, tests/ and archive/.

Reads docs/restructure/file-map.tsv and does the move deterministically, in
two steps that are committed separately so that `git log --follow` sees pure
renames:

  python3 -I docs/restructure/move.py mv        git mv every mapped file
  python3 -I docs/restructure/move.py rewrite   edit the moved files in place
  python3 -I docs/restructure/move.py docs      rewrite paths in the Markdown docs

`rewrite`, run on the tree `mv` left:

1. writes each new package's __init__.py, aoa/paths.py and the tools/ shims
   (rows marked `yes`), and the forwarders for the two moved .cmd files;
2. rewrites imports of moved modules with the ast module: `import
   patch_client` becomes `from aoa.client import base` and every
   `patch_client.X` in that file becomes `base.X`; a new short name that
   collides with another name in the file is imported under a role-qualified
   alias (`from aoa.host import server as host_server`);
3. deletes every sys.path.insert line, and the `import sys` / `Path`
   imports left unused by the edits;
4. replaces repo-root computations from __file__ with aoa.paths.ROOT;
5. turns paths of moved scripts run as child processes (`ROOT /
   "tools/station_stub.py"`, `Path(stub.__file__)`) into
   aoa.paths.entry(name), the tools/ shim.

Edits are made on the source text at the positions the ast reports, so
everything else in a file stays byte for byte. Cases these rules do not cover
are listed in MANUAL as exact text replacements. Nothing here changes what
the code does; hand fixes it cannot express are separate commits.

`docs` rewrites paths of moved files in every tracked *.md outside
evidence/ and docs/restructure/ (the restructure's own records keep the old
paths they describe). Commands of shimmed tools keep their text; other
commands become `tools/run.py aoa.<package>.<module>` (suites: `tools/test.py
<suite>`), and other mentions of a moved file become its new path. Prose is
not reworded.
"""
import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAP = REPO / "docs/restructure/file-map.tsv"

PACKAGES = {
    "aoa": "Ace of Angels preservation and play tools, as one importable package.",
    "aoa/formats": "File formats: archives, cipher, models, scenes, maps and installers (standard library only).",
    "aoa/protocol": "Network protocol: datagram codec, movement and object status messages.",
    "aoa/maps": "Maps: placements, custom maps and objects, export and preview.",
    "aoa/client": "Client preparation: the prepare engine, its base step, texture pack and install.",
    "aoa/client/patches": "Client patches, one module per patch.",
    "aoa/client/experiments": "Superseded offline patch experiments, kept until phase 2 archives them.",
    "aoa/host": "Host: the arena server, its configuration, delivery, operations and headless runner.",
    "aoa/launchers": "Launcher windows for players and hosts.",
    "aoa/research": "Archive.org and Wayback research tools behind one polite HTTP helper.",
    "aoa/analysis": "Disassembly and static-analysis tools for the client executables.",
    "aoa/emulation": "Original-code emulator and the emulation checks of the local gate.",
    "aoa/live": "Windows process readers and live verifiers for a running client.",
    "aoa/reel": "Highlight reel: scripted pilots, recording and editing.",
    "tests": "Every test suite; run them with tools/test.py.",
    "archive": "Frozen one-off scripts kept for reproducibility; nothing in aoa imports them.",
    "archive/analysis": "Frozen one-off analysis scripts; their output is committed under evidence/.",
    "archive/offline_baseline": "Frozen offline-baseline experiment scripts and their tests.",
}

PATHS_MODULE = '''"""Repository paths: ROOT, the ignored WORK folder, and the tools/ command scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"


def entry(name, root=ROOT):
    """tools/<name>.py, the command script that runs a tool as its own process."""
    return Path(root) / "tools" / f"{name}.py"
'''

SHIM = '''"""Command shim for {module}; the code lives there."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
{imports}

if __name__ == "__main__":
    sys.exit({call})
'''

CMD_FORWARDER = '''@echo off
rem Kept so existing shortcuts work: the launcher is now {target} in the repository root.
call "%~dp0..\\{target}" %*
'''

# Exact text replacements for cases the rules below do not cover, applied to
# the moved file before the ast pass. `__AOA_PATHS__` stands for the module
# name the rewrite binds aoa.paths to in that file.
MANUAL = {
    # Only used to put tools/ on sys.path.
    "aoa/reel/bot.py": [("TOOLS = Path(__file__).resolve().parents[1]\n", "")],
    "aoa/reel/record.py": [("HERE = Path(__file__).resolve().parent\nROOT = HERE.parents[1]\n",
                            "from aoa.paths import ROOT\n")],
    "aoa/reel/scout.py": [("HERE = Path(__file__).resolve().parent\n", "")],
    # The script to start is chosen by name.
    "tests/test_dedicated_host.py": [
        ('tool = "dedicated_host.py" if controller else "station_stub.py"',
         'tool = "dedicated_host" if controller else "station_stub"'),
        ("str(Path(__file__).with_name(tool))", "str(__AOA_PATHS__.entry(tool))")],
}

ROOT_EXPRS = {"Path(__file__).resolve().parents[1]", "Path(__file__).resolve().parent.parent"}
REEL_ROOT_EXPRS = {"Path(__file__).resolve().parents[2]"}
PLACEHOLDER = "__AOA_PATHS__"


def git(*args, capture=False):
    result = subprocess.run(["git", *args], cwd=REPO, check=True, text=True,
                            capture_output=capture)
    return result.stdout if capture else None


def folder(old, new):
    """{old path: new path} for every tracked file of a moved folder, before or after the move."""
    before = git("ls-files", old, capture=True).split()
    if before:
        return {path: new + path[len(old):] for path in before}
    return {old + path[len(new):]: path for path in git("ls-files", new, capture=True).split()}


def read_map():
    """(moves {old path: new path}, shimmed {old module name})."""
    moves, shimmed = {}, set()
    for line in MAP.read_text(encoding="utf-8").splitlines()[1:]:
        old, new, keep, _ = line.split("\t")
        if old.endswith("/"):
            moves.update(folder(old, new))
        elif old != new:
            moves[old] = new
        if keep == "yes":
            shimmed.add(Path(old).stem)
    moves.update(folder("tools/snapshots/", "tests/snapshots/"))
    return moves, shimmed


def modules(moves):
    """{old module name: new dotted name} for tools/ and for tools/reel/."""
    top, reel = {}, {}
    for old, new in moves.items():
        if not old.endswith(".py"):
            continue
        dotted = new[:-3].replace("/", ".")
        (reel if old.startswith("tools/reel/") else top)[Path(old).stem] = dotted
    assert not set(top) & set(reel)
    return top, reel


def do_mv(moves):
    status = git("status", "--porcelain", capture=True)
    if status.strip():
        sys.exit("move.py mv needs a clean tree")
    for old, new in sorted(moves.items()):
        (REPO / new).parent.mkdir(parents=True, exist_ok=True)
        git("mv", old, new)
    print(f"moved {len(moves)} files")


class Rewriter:
    """Text edits on one moved file, positioned by its ast."""

    def __init__(self, rel, source, namespace, shimmed, old_rel):
        self.rel, self.namespace, self.shimmed = rel, namespace, shimmed
        self.reel = old_rel.startswith("tools/reel/")
        self.src = source.encode("utf-8")
        self.tree = ast.parse(source)
        self.lines = [0]
        for line in self.src.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.edits = []
        self.need_root = self.need_paths = False
        self.script_only = set()  # module names whose __file__ was only used to start them
        self.parents = {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[child] = node

    # -- positions -------------------------------------------------------
    def span(self, node):
        return (self.lines[node.lineno - 1] + node.col_offset,
                self.lines[node.end_lineno - 1] + node.end_col_offset)

    def text(self, node):
        start, end = self.span(node)
        return self.src[start:end].decode("utf-8")

    def indent(self, node):
        start = self.lines[node.lineno - 1]
        return self.src[start:start + node.col_offset].decode("utf-8")

    def replace(self, node, text):
        self.edits.append((*self.span(node), text))

    def delete_lines(self, node):
        start, end = self.lines[node.lineno - 1], self.lines[node.end_lineno]
        line = self.src[start:end].decode("utf-8")
        body = self.text(node)
        assert line.strip() == body.strip(), f"{self.rel}:{node.lineno}: not alone on its lines"
        self.edits.append((start, end, ""))

    # -- names -----------------------------------------------------------
    def names(self):
        """Every identifier bound or used in the file."""
        found = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.arg):
                found.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.add(node.name)
            elif isinstance(node, ast.alias):
                found.add((node.asname or node.name).split(".")[0])
            elif isinstance(node, ast.ExceptHandler) and node.name:
                found.add(node.name)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                found.update(node.names)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
                found.add(node.name)
        found.discard(PLACEHOLDER)
        return found

    def stored(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and node.id == name and not isinstance(node.ctx, ast.Load):
                return True
            if isinstance(node, ast.arg) and node.arg == name:
                return True
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
                return True
        return False

    # -- passes ----------------------------------------------------------
    def run(self):
        used = self.names()
        bindings = {}     # name bound in the file before -> old module name
        renames = {}      # old module name used as a name -> new name
        plain = []        # (node, alias) for `import X`
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.namespace:
                        bindings[alias.asname or alias.name] = alias.name
                        plain.append((node, alias))
        # Decide the new name for every `import X` without alias.
        taken = set(used) - {a.name for _, a in plain if not a.asname}
        planned = {}
        for node, alias in plain:
            if alias.asname or alias.name in planned:
                continue
            dotted = self.namespace[alias.name]
            package, short = dotted.rsplit(".", 1)
            if short == alias.name:
                planned[alias.name] = short
                continue
            assert not self.stored(alias.name), f"{self.rel}: {alias.name} is also assigned"
            if short in taken or short in planned.values():
                short = package.rsplit(".", 1)[-1] + "_" + short
                assert short not in taken and short not in planned.values(), (self.rel, short)
            planned[alias.name] = short
            renames[alias.name] = short
        old_names = set(self.namespace)
        # Rewrite the import statements.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import) and any(a.name in self.namespace for a in node.names):
                parts = []
                for alias in node.names:
                    if alias.name not in self.namespace:
                        parts.append(f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
                        continue
                    package, short = self.namespace[alias.name].rsplit(".", 1)
                    name = alias.asname or planned[alias.name]
                    assert name == short or name not in old_names, f"{self.rel}: alias {name} is an old module name"
                    parts.append(f"from {package} import {short}" + (f" as {name}" if name != short else ""))
                self.replace(node, ("\n" + self.indent(node)).join(parts))
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module in self.namespace:
                start, _ = self.span(node)
                head = re.match(rb"from\s+(" + re.escape(node.module.encode()) + rb")\b", self.src[start:])
                assert head, (self.rel, node.lineno)
                self.edits.append((start + head.start(1), start + head.end(1), self.namespace[node.module]))
        # Names that referred to a renamed module.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and node.id in renames:
                self.replace(node, renames[node.id])
        # sys.path edits.
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = ast.unparse(node.value)
                if call.startswith(("sys.path.insert(", "sys.path.append(")) or "sys.path.remove" in call:
                    self.delete_lines(node)
        # Repo root from __file__.
        exprs = REEL_ROOT_EXPRS if self.reel else ROOT_EXPRS
        root_bound = False
        for node in ast.walk(self.tree):
            if isinstance(node, ast.expr) and ast.unparse(node) in exprs:
                parent = self.parents[node]
                if (isinstance(parent, ast.Assign) and parent.value is node and len(parent.targets) == 1
                        and isinstance(parent.targets[0], ast.Name) and parent.targets[0].id == "ROOT"
                        and parent in self.tree.body):
                    self.replace(parent, "from aoa.paths import ROOT")
                    root_bound = True
                else:
                    self.replace(node, "ROOT")
                    self.need_root = True
        if self.need_root and not root_bound:
            for node in self.tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ROOT" for t in node.targets):
                    raise AssertionError(f"{self.rel}: ROOT is bound to something else")
        else:
            self.need_root = False
        # Scripts run as child processes.
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Attribute) and node.attr == "__file__" and isinstance(node.value, ast.Name)
                    and node.value.id in bindings):
                old = bindings[node.value.id]
                assert old in self.shimmed, f"{self.rel}: {old} runs as a script but has no shim"
                self.script_only.add(renames.get(node.value.id, node.value.id))
                parent = self.parents[node]
                if isinstance(parent, ast.Call) and ast.unparse(parent.func) == "Path" and parent.args == [node]:
                    self.replace(parent, f'{PLACEHOLDER}.entry("{old}")')
                else:
                    self.replace(node, f'str({PLACEHOLDER}.entry("{old}"))')
                self.need_paths = True
            elif (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.left, ast.Name)
                  and node.left.id == "ROOT" and isinstance(node.right, ast.Constant)
                  and isinstance(node.right.value, str) and node.right.value.startswith("tools/")):
                target = node.right.value
                if target.endswith(".py"):
                    old = target[len("tools/"):-3]
                    assert old in self.shimmed, f"{self.rel}: {target} has no shim"
                    self.replace(node, f'{PLACEHOLDER}.entry("{old}", ROOT)')
                    self.need_paths = True
                elif target in MOVED_FILES:
                    self.replace(node.right, f'"{MOVED_FILES[target]}"')
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "with_name":
                base = ast.unparse(node.func.value)
                if base in ("Path(__file__)", "Path(__file__).resolve()") and isinstance(node.args[0], ast.Constant):
                    old = node.args[0].value[:-3]
                    if old in self.shimmed:
                        self.replace(node, f'{PLACEHOLDER}.entry("{old}")')
                        self.need_paths = True
                    else:
                        assert old in self.siblings, f"{self.rel}: {old} is no longer beside it"
        if PLACEHOLDER.encode() in self.src:
            self.need_paths = True
        return used

    def apply(self, used):
        edits = sorted(self.edits, key=lambda e: (e[0], -e[1]))
        kept, end = [], -1
        for edit in edits:
            if edit[0] < end:
                assert edit[1] <= end, (self.rel, edit)  # inside an earlier replacement
                continue
            kept.append(edit)
            end = edit[1]
        out = bytearray(self.src)
        for start, stop, text in reversed(kept):
            out[start:stop] = text.encode("utf-8")
        source = out.decode("utf-8")
        paths_name = "aoa_paths" if "paths" in used else "paths"
        source = source.replace(PLACEHOLDER, paths_name)
        new = []
        if self.need_root:
            new.append("from aoa.paths import ROOT")
        if self.need_paths:
            new.append(f"from aoa import paths as {paths_name}" if paths_name != "paths" else "from aoa import paths")
        if new:
            source = insert_imports(source, new)
        return drop_unused(source, self.src.decode("utf-8"), self.script_only)


MOVED_FILES = {}


def insert_imports(source, lines):
    """Put new import lines after the module's opening block of imports."""
    tree = ast.parse(source)
    last = None
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last = node
        elif not (index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
            break
    assert last is not None
    text = source.splitlines(keepends=True)
    at = last.end_lineno
    return "".join(text[:at] + [line + "\n" for line in lines] + text[at:])


def loads(tree):
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
        {ast.unparse(n).split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def drop_unused(source, original, script_only=()):
    """Remove top-level imports the edits left unused.

    That is `sys`, `os` and `Path` once used only for sys.path or __file__,
    and a moved module imported only to find its file for a child process.
    """
    before, tree = loads(ast.parse(original)), ast.parse(source)
    after = loads(tree)
    candidates = {"sys", "Path", "os"} & before | set(script_only)
    text = source.splitlines(keepends=True)
    for node in reversed(tree.body):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        dead = [a for a in node.names if (a.asname or a.name) in candidates and (a.asname or a.name) not in after]
        if not dead:
            continue
        rest = [a for a in node.names if a not in dead]
        line = text[node.lineno - 1]
        if rest:
            assert node.lineno == node.end_lineno
            keep = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in rest)
            head = f"from {node.module} import " if isinstance(node, ast.ImportFrom) else "import "
            text[node.lineno - 1] = line[:node.col_offset] + head + keep + line[node.end_col_offset:]
        else:
            del text[node.lineno - 1:node.end_lineno]
    return "".join(text)


def main_form(source):
    """How the module's __main__ block calls main(): via cli_util.run or directly."""
    block = source[source.rindex('if __name__ == "__main__":'):] if 'if __name__ == "__main__":' in source else ""
    return "cli" if "cli_util.run(main)" in block else "plain"


def do_rewrite(moves, shimmed):
    top, reel = modules(moves)
    MOVED_FILES.update({old: new for old, new in moves.items() if not old.endswith(".py")})
    # The scripts that stay in tools/ (verify_local.py) are rewritten by hand.
    for rel, doc in PACKAGES.items():
        init = REPO / rel / "__init__.py"
        assert not init.exists(), init
        init.write_text(f'"""{doc}"""\n', encoding="utf-8")
    (REPO / "aoa/paths.py").write_text(PATHS_MODULE, encoding="utf-8")
    changed = 0
    for old, new in sorted(moves.items()):
        if not new.endswith(".py"):
            continue
        path = REPO / new
        source = path.read_text(encoding="utf-8")
        form = main_form(source)
        for before, after in MANUAL.get(new, ()):
            assert source.count(before) == 1, (new, before)
            source = source.replace(before, after)
        namespace = {**top, **reel} if old.startswith("tools/reel/") or old == "tools/test_reel.py" else top
        rewriter = Rewriter(new, source, namespace, shimmed, old)
        rewriter.siblings = {Path(o).stem for o, n in moves.items() if Path(n).parent == Path(new).parent}
        used = rewriter.run()
        result = rewriter.apply(used)
        compile(result, new, "exec")
        if result != path.read_text(encoding="utf-8"):
            path.write_text(result, encoding="utf-8")
            changed += 1
        stem = Path(old).stem
        if stem in shimmed:
            module = top[stem]
            assert re.search(r"^def main\(", result, re.M), f"{new} has no main()"
            imports = [f"from {module} import main  # noqa: E402"]
            call = "main()"
            if form == "cli":
                imports.insert(0, "from aoa import cli  # noqa: E402")
                call = "cli.run(main)"
            shim = SHIM.format(module=module, imports="\n".join(imports), call=call)
            (REPO / old).write_text(shim, encoding="utf-8")
    for old, new in moves.items():
        if old.endswith(".cmd"):
            text = (REPO / new).read_text(encoding="utf-8")
            assert text.count('cd /d "%~dp0.."') == 1, new
            (REPO / new).write_text(text.replace('cd /d "%~dp0.."', 'cd /d "%~dp0"'), encoding="utf-8")
            (REPO / old).write_text(CMD_FORWARDER.format(target=new), encoding="utf-8")
    print(f"rewrote {changed} modules, wrote {len(shimmed)} shims")


COMMAND = r"((?:python3?(?:\.exe)?|\bpy)(?:\s+-{1,2}[\w.-]+)*\s+)"


def doc_rule(moves, shimmed):
    """A re.sub callback for one tools/ path in a Markdown line."""
    by_old = {old[len("tools/"):]: new for old, new in moves.items()}

    def replace(m):
        command, prefix, sep, name, rest = m["command"] or "", m["prefix"] or "", m["sep"], m["name"], m["rest"]
        new = by_old.get(name.replace("\\", "/"))
        stem = Path(name.replace("\\", "/")).stem
        if new is None or (name.endswith(".py") and stem in shimmed) or name == "README.md":
            return m[0]
        if name.endswith(".py") and command and not prefix:
            if Path(new).name.startswith("test_"):
                suite = stem if new.startswith("tests/") else new[:-3].replace("/", ".")
                tail = " --" if re.match(r"\s+-", rest) else ""
                return f"{command}tools{sep}test.py {suite}{tail}{rest}"
            return f"{command}tools{sep}run.py {new[:-3].replace('/', '.')}{rest}"
        return f"{command}{prefix}{new.replace('/', sep)}{rest}"
    return replace


def relink(text, old_dir, new_dir):
    """Relative Markdown link targets of a moved doc, re-pointed from its new folder."""
    def fix(m):
        target = m[2]
        if re.match(r"[a-z]+:|#|/", target):
            return m[0]
        path, _, anchor = target.partition("#")
        moved = os.path.relpath(os.path.normpath(os.path.join(old_dir, path)), new_dir)
        return f"{m[1]}({Path(moved).as_posix()}{'#' + anchor if anchor else ''})"
    return re.sub(r"(\]\s?)\(([^)\s]+)\)", fix, text)


def do_docs(moves, shimmed):
    names = sorted((old[len("tools/"):] for old in moves), key=len, reverse=True)
    alternatives = "|".join(re.escape(n).replace("/", r"[/\\]") for n in names)
    pattern = re.compile(r"(?P<command>" + COMMAND[1:-1] + r")?(?P<prefix>(?:\.\./)*)"
                         r"(?:(?<=\.\./)|(?<![\w/\\.-]))tools(?P<sep>[/\\])(?P<name>" + alternatives + r")"
                         r"(?!\w)(?P<rest>\s+-|)")
    rule = doc_rule(moves, shimmed)
    changed = []
    for rel in git("ls-files", "*.md", capture=True).split():
        if rel.startswith(("evidence/", "docs/restructure/")):
            continue
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        new = pattern.sub(rule, text)
        if rel in moves.values():
            old = next(o for o, n in moves.items() if n == rel)
            new = relink(new, os.path.dirname(old), os.path.dirname(rel))
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(rel)
    print(f"rewrote paths in {len(changed)} docs")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("mv", "rewrite", "docs"))
    args = ap.parse_args(argv)
    moves, shimmed = read_map()
    if args.step == "mv":
        do_mv(moves)
    elif args.step == "rewrite":
        do_rewrite(moves, shimmed)
    else:
        do_docs(moves, shimmed)


if __name__ == "__main__":
    main()
