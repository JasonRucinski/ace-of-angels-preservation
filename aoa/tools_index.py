"""Write the tool index of docs/reference/tools.md from the module docstrings.

    python -I tools/run.py aoa.tools_index            print the index
    python -I tools/run.py aoa.tools_index --write    rewrite it in docs/reference/tools.md
    python -I tools/run.py aoa.tools_index --check    exit 1 if docs/reference/tools.md is out of date

The index lists the commands in tools/ (a shim is marked and described by
the module it runs), then every module of aoa/ and archive/ grouped by
package, each with the first line of its docstring. Modules with a command
line (an `if __name__ == "__main__":` block) run through tools/run.py; an
old module name kept only so documented commands work is marked as a shim.
The index sits between two marker comments in docs/reference/tools.md; the
text around it is written by hand, and tools/README.md points to it.
tests/test_tools_index.py fails when the committed index is not current.
Reads source files only; imports nothing it lists.
"""
import ast
import re
import sys

from aoa import cli
from aoa.paths import ROOT

PACKAGES = ("aoa", "archive")
MAIN = re.compile(r"""^if __name__ == ['"]__main__['"]""", re.M)
SHIM_TARGET = re.compile(r"^from ([\w.]+) import (?:main|(\w+) as main)\b", re.M)
OLD_NAME = re.compile(r"^The old name of\b")
PS_SYNOPSIS = re.compile(r"\.SYNOPSIS\s*\n\s*(.+)")
CMD_REM = re.compile(r"^rem (.+)$", re.M | re.I)


def first_sentence(doc):
    """The docstring's first paragraph, up to its first full stop."""
    paragraph = " ".join(doc.strip().split("\n\n")[0].split()) if doc and doc.strip() else ""
    end = paragraph.find(". ")
    return paragraph[:end + 1] if end >= 0 else paragraph


def summary(source, function=None):
    """First sentence of a Python source's docstring (or of one of its functions), or ''."""
    tree = ast.parse(source)
    if function:
        tree = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    return first_sentence(ast.get_docstring(tree) or "")


def cell(text):
    return text.replace("|", "\\|")


def module_name(path):
    return ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")


def module_path(name):
    path = ROOT.joinpath(*name.split(".")).with_suffix(".py")
    return path if path.is_file() else ROOT.joinpath(*name.split(".")) / "__init__.py"


def commands():
    """Rows (name, description) for the files in tools/."""
    rows = []
    for path in sorted((ROOT / "tools").iterdir()):
        if path.suffix == ".py":
            source = path.read_text(encoding="utf-8")
            text = summary(source)
            target = SHIM_TARGET.search(source)
            if text.startswith("Command shim for") and target:
                module, function = target[1], target[2]
                where = f"{module}.{function}" if function else module
                text = f"*shim* for `{where}`: {summary(module_path(module).read_text(encoding='utf-8'), function)}"
        elif path.suffix == ".ps1":
            m = PS_SYNOPSIS.search(path.read_text(encoding="utf-8"))
            text = "PowerShell: " + (m[1].strip() if m else "")
        elif path.suffix == ".cmd":
            m = CMD_REM.search(path.read_text(encoding="utf-8"))
            text = "Windows shortcut: " + (m[1].strip() if m else "")
        else:
            continue
        rows.append((path.name, text))
    return rows


def modules():
    """{package: [(module, runnable, description)]} for aoa/ and archive/."""
    groups = {}
    for package in PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            if "__pycache__" in path.parts or path.name == "__init__.py":
                continue
            source = path.read_text(encoding="utf-8")
            text = summary(source)
            if OLD_NAME.match(text):
                text = "*shim*: " + text
            name = module_name(path)
            groups.setdefault(name.rpartition(".")[0], []).append((name, bool(MAIN.search(source)), text))
    return groups


def render():
    out = ["### Commands in tools/\n", "| File | What it does |", "|---|---|"]
    out += [f"| `{name}` | {cell(text)} |" for name, text in commands()]
    out.append("")
    for package, rows in sorted(modules().items()):
        init = (ROOT.joinpath(*package.split(".")) / "__init__.py")
        heading = summary(init.read_text(encoding="utf-8")) if init.is_file() else ""
        out += [f"### {package}\n"] + ([heading, ""] if heading else [])
        out += ["| Module | Command line | What it is |", "|---|---|---|"]
        for name, runnable, text in rows:
            out.append(f"| `{name}` | {'yes' if runnable else ''} | {cell(text)} |")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


BLOCK = cli.DocBlock("docs/reference/tools.md", "tools index", "aoa.tools_index", render)


def main(argv=None):
    return BLOCK.main(argv, __doc__)


if __name__ == "__main__":
    sys.exit(cli.run(main))
