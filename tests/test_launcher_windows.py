"""Smoke test of the two launcher windows: each --demo state builds, shows its widgets
inside the window and changes nothing. Needs tkinter and a display (Linux CI has
neither: the suite skips with the reason); run it under Xvfb with a Python that has
tkinter, for example:

    xvfb-run /usr/bin/python3.12 -I tools/test.py test_launcher_windows

The windows' layout on Windows 10 and 11 is not covered: see docs/STATUS.md.
"""
import os
import sys
import unittest

try:
    import tkinter
    tkinter.Tk().destroy()
    REASON = None
except Exception as error:  # noqa: BLE001 - no tkinter, or no display
    REASON = f"needs tkinter and a display ({type(error).__name__})"


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


@unittest.skipIf(REASON, REASON)
class WindowTests(unittest.TestCase):
    def check_inside(self, root):
        root.update()
        right, bottom = root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height()
        for widget in widgets(root):
            if not widget.winfo_ismapped() or widget.winfo_toplevel() is not root:
                continue
            with self.subTest(widget=str(widget)):
                self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right + 1)
                self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom + 1)

    def test_player_window_every_state(self):
        from aoa.launchers import play_app
        for state in play_app.DEMOS:
            with self.subTest(state=state):
                root, window = play_app.build(state)
                try:
                    self.check_inside(root)
                    texts = {w.cget("text") for w in widgets(root) if w.winfo_class() == "TButton"}
                    if state == "checklist":
                        self.assertIn("Apply the fixes", texts)
                        self.assertFalse(window.tabs.winfo_ismapped())
                    else:
                        self.assertIn("Play", texts)
                        self.assertFalse(window.play_button.instate(["disabled"]))
                    if state == "join":
                        self.assertTrue(window.hosts_box.winfo_ismapped())
                        self.assertFalse(window.join_button.instate(["disabled"]))
                    if state == "options":
                        self.assertFalse(window.option_vars["experimental_asteroids"].get())
                        self.assertIn("was turned off", window.option_note.get())
                    if state == "error":
                        self.assertEqual(len(root.winfo_children()) - len(
                            [w for w in root.winfo_children() if w.winfo_class() != "Toplevel"]), 1)
                finally:
                    root.destroy()

    def test_host_window_every_state(self):
        from aoa.launchers import host_app
        for state in host_app.DEMOS:
            with self.subTest(state=state):
                root, window = host_app.build(state)
                try:
                    self.check_inside(root)
                    if state == "running":
                        self.assertEqual(len(window.table.get_children()), 3)
                        self.assertIn("Ace of Angels server", window.share.get())
                    if state == "setup":
                        self.assertFalse(window.start_button.instate(["disabled"]))
                finally:
                    root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
