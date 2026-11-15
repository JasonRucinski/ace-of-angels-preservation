"""Keep an inactive flying client reading the network (findings 9.24).

Wakeup-timer callback 0x446E70: the `jne` at 0x446EAF skips the frame while
the window is inactive if the graphics layer reports exclusive mode
(+0x24C5). The client always requests exclusive mode, so an inactive flying
client stopped reading UDP. NOPs let the 66 ms timer run the frame. Verified
only with the dgVoodoo windowed wrapper. frame-clock-v1's gate, at the call
right after this site, exists because of it.
"""
from aoa.client.patches.base import Patch, Region

NAME = "background-network-v1"
SITE = 0x446EAF
JNE, NOP = b"\x75\x34", b"\x90\x90"

PATCH = Patch(id=NAME, since=2, policy="always", regions=(Region(SITE, JNE, NOP),))
