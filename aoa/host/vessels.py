"""The fighters a host offers, and the arena messages that name one.

Data and checks only; imports nothing from the server. The protocol builders
(aoa/protocol/arena.py) accept any name that fits its field; these refuse a
vessel the in-flight menu does not offer.
"""
from aoa.host.spawn import spawn_position
from aoa.protocol import arena

DEFAULT_VESSEL = "Ym Khtat"
# Every .Sco object in the 2.9.2 AoAObjects.odb with an engine, pods
# excluded (work/2.9.2/sco.json): the fighters the in-flight menu offers.
SELECTABLE_VESSELS = frozenset((
    "AlphaFighter", "Dafusha", "Dasibaz", "Eagle", "Etat'Illraku", "Foushar", "Grathven", "Hartra",
    "IBCH", "Janha Vari", "Kafic", "MBB", "Meskvak Su", "Mkulat", "N'Goc", "Naroch", "Natak'Illraku",
    "Rchat", "Rhino", "Saksatar", "Shrike", "Tekan", "Test Missile Boat", "Tholfus", "Ummra Viazyem",
    "Vagym", "Vasa Chovo", "Vermok", "Vrak Stat", "Yagari", "Ym Khtat", "Zkole"))


def ship_request(payload):
    """The vessel of a valid fighter request (arena.ship_request) if the host offers it, else None."""
    name = arena.ship_request(payload)
    return name if name in SELECTABLE_VESSELS else None


def load_ship(vessel=DEFAULT_VESSEL, slot=0):
    if vessel not in SELECTABLE_VESSELS:
        raise ValueError("unknown vessel or slot")
    return arena.load_ship(vessel, slot)


def flight_bootstrap(position=None, terrain=None, vessel=DEFAULT_VESSEL):
    if vessel not in SELECTABLE_VESSELS:
        raise ValueError("unknown vessel or slot")
    return arena.flight_bootstrap(vessel, position, terrain)


def load_player(slot, position=None, name=None, team=None, vessel=DEFAULT_VESSEL, station_id=None):
    """arena.load_player for an offered vessel; the position defaults to the slot's spawn."""
    if not 1 <= slot < 50:
        raise ValueError("player slot must be 1..49")
    if vessel not in SELECTABLE_VESSELS:
        raise ValueError("unknown vessel")
    return arena.load_player(slot, position if position is not None else spawn_position(slot), vessel,
                             name, team, station_id)
