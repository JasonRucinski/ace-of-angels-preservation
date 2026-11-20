"""Every command the docs show names a real tool, and every flag it uses is in that tool's --help; game-free.

Reads each tracked .md file outside docs/restructure/ (the programme's
records quote commands as they were), stubs excepted. A command is a
`tools/<name>.py`, `.ps1` or `.cmd` in a fenced code block (with `\\`, `` ` ``
and `^` continuations joined) or in an inline code span. Each named
`tools/<name>.py` must exist and have a `main`; `tools/run.py MODULE` must
name a module of aoa/ or archive/ that exists and has a `main` (a
placeholder such as `MODULE` or `aoa.client.patches.<name>` is not
checked), and `tools/test.py` must name suites that exist. For each command
line, every `--flag` before a `--` separator must appear in that command's
`--help` (its subcommand's, when the first argument is one). The help text
is obtained only through the sandbox of tests/test_cli_help.py: a
throw-away copy of the repository, an empty working directory, network and
child processes blocked. A tool whose --help needs an optional package that
is not installed is skipped with its name.

    python -I tools/test.py test_doc_commands
"""
import re
import shlex
import unittest

from aoa.paths import ROOT
from tests import test_cli_help as cli_help
from tests.test_doc_links import FENCE, is_stub, tracked

SKIP = ("docs/restructure/",)
CONTINUED = re.compile(r"(?:\\|`|\^)\s*$")
TOOL = re.compile(r"(?<![\w.-])(?:\.[\\/])?tools[\\/]([\w-]+)\.(py|ps1|cmd)\b")
SPAN = re.compile(r"(?<!`)`([^`]+)`(?!`)")
STOP = {"|", "||", "&&", ";", ">", ">>", "<", "2>&1", "#"}
FLAG = re.compile(r"^[\[(]*(--[A-Za-z0-9][\w-]*)")
MODULE = re.compile(r"^(aoa|archive)(\.\w+)+$")
MAIN = re.compile(r"^def main\b|\bimport (?:\w+ as )?main\b|^main = ", re.M)


def code_lines(text):
    """(line number, text) of every code fragment: fenced lines joined, and inline spans."""
    fenced, pending, start = False, "", 0
    prose = []
    for number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            if not pending:
                start = number
            if CONTINUED.search(line):
                pending += CONTINUED.sub(" ", line)
                continue
            yield start, pending + line
            pending = ""
        else:
            prose.append((number, line))
    # Inline spans may wrap onto the next line.
    joined = "\n".join(line for _, line in prose)
    offsets = [n for n, _ in prose]
    for m in SPAN.finditer(joined):
        yield offsets[joined.count("\n", 0, m.start())], m[1].replace("\n", " ")


def commands(text):
    """(line, tool file, words after it) for every tool invocation in a doc."""
    for number, line in code_lines(text):
        for m in TOOL.finditer(line):
            rest = line[m.end():]
            try:
                words = shlex.split(rest, posix=False)
            except ValueError:
                words = rest.split()
            args = []
            for word in words:
                if word in STOP or word.startswith("#") or TOOL.match(word):
                    break
                args.append(word)
            yield number, f"tools/{m[1]}.{m[2]}", args


def documented():
    """Every command in the docs: [(doc, line, tool, args)]."""
    found = []
    for doc in tracked("*.md"):
        if doc.startswith(SKIP) or is_stub(ROOT / doc):
            continue
        for number, tool, args in commands((ROOT / doc).read_text(encoding="utf-8")):
            found.append((doc, number, tool, args))
    return found


def template(word):
    """A placeholder in a documented command: `MODULE`, `aoa.client.patches.<name>`."""
    return "<" in word or bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", word))


def module_file(name):
    path = ROOT.joinpath(*name.split(".")).with_suffix(".py")
    return path if path.is_file() else None


def suites(args):
    """The suite names of a tools/test.py command line (before `--`)."""
    out = []
    for word in args:
        if word == "--":
            break
        if not word.startswith("-") and re.match(r"^[\w.]+$", word) and word not in ("ci", "local", "all"):
            out.append(word)
    return out


def suite_file(name):
    """tests/<name>.py for a bare suite name, else the dotted module's file (as tests/runner.py runs it)."""
    return ROOT.joinpath(*name.split(".")).with_suffix(".py") if "." in name else ROOT / "tests" / f"{name}.py"


def flags(args):
    out = []
    for word in args:
        if word == "--":
            break
        m = FLAG.match(word)
        if m and m[1] != "--help":
            out.append(m[1])
    return out


def subcommands(help_text):
    """Words that may be subcommands: {a,b} choices and the indented names under positional arguments."""
    names = set()
    for group in re.findall(r"\{([\w,-]+)\}", help_text):
        names.update(group.split(","))
    section = re.search(r"^positional arguments:\n(.*?)(?:\n\S|\Z)", help_text, re.S | re.M)
    if section:
        names.update(re.findall(r"^ {4,}([a-z][\w-]*)\b", section[1], re.M))
    return names


class DocCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commands = documented()
        cls.sandbox = None
        cls.helps = {}

    @classmethod
    def tearDownClass(cls):
        if cls.sandbox is not None:
            cli_help.CliHelp.tearDownClass()

    def help_text(self, target, *sub):
        """--help of a tools/ script or a module (through tools/run.py), from the sandbox only."""
        key = (target, *sub)
        if key not in self.helps:
            if type(self).sandbox is None:
                cli_help.CliHelp.setUpClass()
                type(self).sandbox = cli_help.CliHelp("check")
            proc = type(self).sandbox.sandboxed(target, *sub, "--help")
            if proc.returncode != 0:
                package = cli_help.missing_optional(proc.stderr)
                self.helps[key] = ("skip", package) if package else ("fail", proc.stderr[-1500:])
            else:
                self.helps[key] = ("ok", proc.stdout)
        return self.helps[key]

    def test_docs_show_commands(self):
        # Guards the extraction: the guides show dozens of commands.
        tools = {tool for _, _, tool, _ in self.commands}
        self.assertGreater(len(self.commands), 100)
        self.assertTrue({"tools/prepare_client.py", "tools/station_stub.py", "tools/run.py"} <= tools)

    def test_every_named_tool_exists_and_has_a_main(self):
        for doc, number, tool, args in self.commands:
            with self.subTest(where=f"{doc}:{number}", tool=tool):
                path = ROOT / tool
                self.assertTrue(path.is_file(), f"{doc}:{number}: {tool} does not exist")
                if tool.endswith(".py"):
                    self.assertTrue(MAIN.search(path.read_text(encoding="utf-8")), f"{tool} has no main")
                if tool == "tools/run.py" and args and not args[0].startswith("-") and not template(args[0]):
                    module = args[0]
                    self.assertRegex(module, MODULE, f"{doc}:{number}: run.py {module} is not a module name")
                    source = module_file(module)
                    self.assertIsNotNone(source, f"{doc}:{number}: module {module} does not exist")
                    self.assertTrue(MAIN.search(source.read_text(encoding="utf-8")), f"{module} has no main")
                if tool == "tools/test.py":
                    for suite in suites(args):
                        self.assertTrue(suite_file(suite).is_file(), f"{doc}:{number}: no test suite {suite}")

    def test_every_documented_flag_is_in_the_help(self):
        for doc, number, tool, args in self.commands:
            used = flags(args)
            if not tool.endswith(".py") or not used or (tool == "tools/run.py" and args and template(args[0])):
                continue
            target, rest = tool, args
            if tool == "tools/run.py" and args and MODULE.match(args[0]):
                target, rest = args[0], args[1:]
            with self.subTest(where=f"{doc}:{number}", command=" ".join([tool, *args])):
                state, text = self.help_text(target)
                if state == "skip":
                    self.skipTest(f"{target} --help needs {text}, not installed")
                self.assertEqual(state, "ok", f"{target} --help failed:\n{text}")
                first = next((w for w in rest if not w.startswith("-")), None)
                if first and first in subcommands(text):
                    state, sub = self.help_text(target, first)
                    if state == "ok":
                        text += sub
                for flag in used:
                    found = re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text)
                    self.assertTrue(found, f"{doc}:{number}: {flag} is not in the --help of {target} {first or ''}")

    def test_the_parser_reads_what_it_should(self):
        text = ("Run:\n\n```powershell\n.venv\\Scripts\\python.exe -I tools\\prepare_client.py prepare `\n"
                "  game\\2.9.2\\AOACLIENT.EXE --station aoalan\n```\n\n"
                "Inline `python -I tools/run.py aoa.formats.trn --help` and a wrapped `tools/test.py\n"
                "test_cli_help -- -k fetch`.\n")
        found = list(commands(text))
        self.assertEqual([(t, a) for _, t, a in found],
                         [("tools/prepare_client.py", ["prepare", "game\\2.9.2\\AOACLIENT.EXE", "--station", "aoalan"]),
                          ("tools/run.py", ["aoa.formats.trn", "--help"]),
                          ("tools/test.py", ["test_cli_help", "--", "-k", "fetch"])])
        self.assertEqual(flags(found[0][2]), ["--station"])
        self.assertEqual(flags(found[2][2]), [])
        self.assertEqual(suites(found[2][2]), ["test_cli_help"])
        self.assertEqual(suites(["--tier", "ci"]), [])
        self.assertTrue(template("MODULE") and template("aoa.client.patches.<name>"))
        self.assertFalse(template("aoa.formats.trn"))
        self.assertEqual(subcommands("usage: x {prepare,check}\n\npositional arguments:\n  ACTION\n"
                                     "    undo     restore\n\noptions:\n"), {"prepare", "check", "undo"})


if __name__ == "__main__":
    unittest.main()
