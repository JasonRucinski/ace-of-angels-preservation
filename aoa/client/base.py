"""Former home of the logger patches (now aoa/client/patches/logger.py).

Kept only for the names aoa.emulation imports from it; new code imports
aoa.client.asm.
"""
from aoa.client.asm import Asm, d32, jmp_patch

__all__ = ["Asm", "d32", "jmp_patch"]
