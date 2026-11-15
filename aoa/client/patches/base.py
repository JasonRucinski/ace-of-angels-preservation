"""A client patch as data, and the generic code that reads and writes one.

Every patch module exports `PATCH` (or `PATCHES`): a `Patch` whose regions
list each byte range it writes, as original and patched bytes. `state()` and
`apply()` below are the only code that reads or writes those ranges;
aoa/client/prepare.py composes them over the registry in
aoa/client/patches/__init__.py.

Addresses are virtual addresses of the 2.9.2 client (image base 0x400000).
`va_to_offset()` maps them to file offsets; `check_mapping()` proves once
per section table that the mapping holds for every registered region.
"""
import hashlib
from dataclasses import dataclass

from aoa.formats import pe

IMAGE_BASE = 0x400000
KINDS = ("site", "cave", "const")    # rewritten code, new code in the .text padding, a data constant
POLICIES = ("base", "always", "option")
GROUPS = ("fixes", "visual", "experimental")


@dataclass(frozen=True)
class Region:
    va: int
    old: bytes
    new: bytes
    kind: str = "site"

    def __post_init__(self):
        if len(self.old) != len(self.new) or not self.old or self.old == self.new:
            raise ValueError(f"region {self.va:#x}: original and patched bytes must differ, at equal length")
        if self.kind not in KINDS:
            raise ValueError(f"region {self.va:#x}: kind {self.kind!r} is not one of {KINDS}")

    @property
    def end(self):
        return self.va + len(self.old)


@dataclass(frozen=True)
class Patch:
    """One client patch.

    since:     the patch version it arrived in (None: between 4 and 10, not recorded).
    policy:    "base" (the stability fixes every supported client carries; applied
               once to the pristine client and never removed), "always" (applied
               by every prepare) or "option" (on or off by choice).
    option:    the option name (prepare's keyword, --[no-]<option> on the command
               line, the launcher's key). None for an option patch that follows
               the patch it `requires`.
    label:     launcher checkbox text (None: no checkbox).
    group:     launcher section: fixes, visual or experimental.
    default:   the setting for a client never prepared before.
    requires:  patch IDs this one is applied with (and removed with).
    conflicts: patch IDs it cannot be on together with (they share code).
    reads:     constant VAs its code reads; another patch may rewrite them only
               if the interaction is declared and tested (test_patch_layout).
    data:      runtime .data reservations (start, size), from aoa/client/layout.py.
    regions:   the current variant's byte ranges.
    legacy:    ((variant ID, regions), ...) of older variants still recognized,
               so prepare can upgrade them in place.
    """
    id: str
    since: int | None
    policy: str
    regions: tuple
    option: str | None = None
    label: str | None = None
    group: str | None = None
    default: bool = False
    requires: tuple = ()
    conflicts: tuple = ()
    reads: tuple = ()
    data: tuple = ()
    legacy: tuple = ()

    def __post_init__(self):
        if self.policy not in POLICIES:
            raise ValueError(f"{self.id}: policy {self.policy!r} is not one of {POLICIES}")
        if self.group is not None and self.group not in GROUPS:
            raise ValueError(f"{self.id}: group {self.group!r} is not one of {GROUPS}")
        if (self.option or self.label) and self.policy != "option":
            raise ValueError(f"{self.id}: only an option patch has an option or label")
        if not self.regions:
            raise ValueError(f"{self.id}: no regions")

    @property
    def variants(self):
        """((variant ID, regions), ...), the current one first."""
        return ((self.id, self.regions), *self.legacy)


def va_to_offset(va):
    """File offset of a patch VA. Holds for every section of the 2.9.2 client
    (raw offset == RVA); check_mapping() verifies it against an image."""
    return va - IMAGE_BASE


_mapped = set()


def check_mapping(image, patches):
    """Raise unless every region of these patches lies in one section's file
    data at offset va_to_offset(va). Checked once per section table."""
    key = hashlib.sha256(bytes(image[:0x400]) + repr([p.id for p in patches]).encode()).digest()
    if key in _mapped:
        return
    pe_image = pe.Image(bytes(image[:0x1000]) if len(image) > 0x1000 else image)
    for patch in patches:
        for _, regions in patch.variants:
            for r in regions:
                first, last = pe_image.section_of_va(r.va), pe_image.section_of_va(r.end - 1)
                if (first is None or first is not last or r.end - first["va"] > first["raw_size"]
                        or first["raw_off"] != first["va"] - pe_image.base or pe_image.base != IMAGE_BASE
                        or va_to_offset(r.end) > len(image)):
                    raise ValueError(f"{patch.id}: region {r.va:#x} is not file-backed at VA - image base")
    _mapped.add(key)


def _matches(regions, image):
    """True/False if every region holds its patched/original bytes, else None."""
    found = set()
    for r in regions:
        at = va_to_offset(r.va)
        actual = image[at:at + len(r.old)]
        if actual == r.old:
            found.add(False)
        elif actual == r.new:
            found.add(True)
        else:
            return None
    return found.pop() if len(found) == 1 else None


def state(patch, image):
    """The installed variant's ID, or None if the patch is absent.

    Raises ValueError on a partial patch or on unknown bytes at its sites.
    """
    for variant, regions in patch.variants:
        found = _matches(regions, image)
        if found is not None:
            return variant if found else None
    raise ValueError(f"unexpected or partial {patch.id} patch")


def apply(patch, image, on):
    """The image with this patch on or off; an older variant is removed first."""
    installed = state(patch, image)
    out = bytearray(image)
    for variant, regions in patch.legacy:
        if variant == installed:
            for r in regions:
                out[va_to_offset(r.va):va_to_offset(r.end)] = r.old
    for r in patch.regions:
        out[va_to_offset(r.va):va_to_offset(r.end)] = r.new if on else r.old
    return bytes(out)
