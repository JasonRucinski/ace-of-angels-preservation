"""The generated tables in the docs are current, and cover what they generate from; game-free.

Each table sits between marker comments and is written by a module with
--write and --check (aoa.cli.DocBlock). When a test here fails, regenerate:

    python -I tools/run.py aoa.client.patchdoc --write     docs/reference/client-patches.md

The server flag table (aoa.host.flagdoc) is checked by test_host_data and
the tools index (aoa.tools_index) by test_tools_index.

    python -I tools/test.py test_doc_tables
"""
import importlib
import re
import unittest

from aoa import cli

GENERATORS = ("aoa.client.patchdoc", "aoa.host.flagdoc", "aoa.tools_index")


def block_text(block):
    text = block.committed()
    return text[text.index(block.begin):text.index(block.end)]


class GeneratedTables(unittest.TestCase):
    def test_committed_tables_are_current(self):
        for name in GENERATORS:
            block = importlib.import_module(name).BLOCK
            with self.subTest(table=block.doc):
                self.assertEqual(block.committed(), block.current(),
                                 f"{block.doc} is out of date: python -I tools/run.py {name} --write")

    def test_each_doc_has_one_block_and_hand_text_around_it(self):
        for name in GENERATORS:
            block = importlib.import_module(name).BLOCK
            with self.subTest(table=block.doc):
                text = block.committed()
                self.assertEqual((text.count(block.begin), text.count(block.end)), (1, 1))
                self.assertTrue(text.startswith("# "), "the doc keeps its hand-written title")

    def test_splice_replaces_only_the_block(self):
        block = cli.DocBlock("docs/STATUS.md", "example", "aoa.example", lambda: "new\n")
        text = f"# T\n\nbefore\n\n{block.begin}\n\nold\n\n{block.end}\n\nafter\n"
        self.assertEqual(block.splice(text), f"# T\n\nbefore\n\n{block.begin}\n\nnew\n\n{block.end}\n\nafter\n")
        with self.assertRaises(SystemExit):
            block.splice("# no markers\n")

    def test_patch_table_lists_every_patch_and_flag(self):
        from aoa.client import patchdoc, prepare
        from aoa.client.patches import REGISTRY
        text = block_text(patchdoc.BLOCK)
        for p in REGISTRY:
            with self.subTest(patch=p.id):
                self.assertRegex(text, rf"\| `{re.escape(p.id)}` \|")
                if p.option:
                    self.assertIn(f"`{prepare.flag(p.option)}`", text)
        for option, alias in prepare.FLAG_ALIASES.items():
            self.assertIn(f"`{alias}`", text)


if __name__ == "__main__":
    unittest.main()
