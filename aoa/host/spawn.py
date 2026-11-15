"""Where relay players spawn."""


def spawn_position(slot, axis="x", spacing=1000.0, origin=None):
    """Diagnostic line of spawns. Ships appear to face +z initially, so
    axis z with a short spacing puts each later player ahead of the first.
    `origin` moves the line, e.g. to a map's viewing spawn."""
    offset = (slot - 1) * spacing
    x, y, z = origin or (0.0, 0.0, 0.0)
    return (x + offset, y, z) if axis == "x" else (x, y, z + offset)
