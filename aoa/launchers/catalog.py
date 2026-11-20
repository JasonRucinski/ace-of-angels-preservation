"""What the two windows offer, and the words they use for it.

Every fact comes from the engines' tables: maps from aoa/maps/registry.py,
host profiles, ports, backdrops and client feature levels from
aoa/host/defaults.py, client options from the patch registry
(aoa/client/patches/__init__.py). This module only orders them and adds the
player-facing wording: short labels and a longer hover text.
"""
from dataclasses import dataclass

from aoa.client import patches
from aoa.host import defaults
from aoa.maps import registry

PATCH_LEVEL = patches.PATCH_LEVEL
PORTS = dict(defaults.PORTS)
PROFILE_NAMES = {"local-guests": "This PC only", "local-relay": "This PC only",
                 "lan-dogfight": "My home network", "vpn-dogfight": "Friends over a VPN"}


# --- maps ---------------------------------------------------------------------
@dataclass(frozen=True)
class Map:
    name: str
    content: str          # registry.PLAYABLE, COMPONENT or EMPTY
    note: str
    client_file: str = None   # a file every player needs beside the game (JRMAP's terrain)

    @property
    def playable(self):
        return self.content == registry.PLAYABLE

    def describe(self):
        """'Arena1a: 239 objects; main arena'."""
        return f"{self.name}: {self.note}" if self.note else self.name


def _map(entry):
    name, kind, target, _ = entry
    note = registry.NOTES.get(name, "")
    if name == "JRMAP":
        note = "23 objects incl. 5 safe zones; every player needs its terrain file"
    return Map(name, registry.CONTENT[name], note, target if kind == registry.TRN else None)


# Playable maps first, in registry order, then the rest.
MAPS = tuple(sorted((_map(m) for m in registry.MAPS), key=lambda m: not m.playable))
BY_NAME = {m.name: m for m in MAPS}
PLAYABLE_MAPS = tuple(m for m in MAPS if m.playable)


# --- who can join -------------------------------------------------------------
@dataclass(frozen=True)
class Audience:
    key: str
    label: str
    profile: str
    kind: str          # the netinfo address kind this audience binds to (None: loopback)
    sentence: str
    no_address: str    # what to say when this PC has no such address


AUDIENCES = (
    Audience("this-pc", "This PC only", "local-guests", None,
             "Only a game running on this computer can join. Good for trying things out.", ""),
    Audience("home", "My home network", "lan-dogfight", "home",
             "Players on the same home or office network (Wi-Fi or cable) can join.",
             "This PC has no home-network address. Check that it is connected to your router."),
    Audience("vpn", "Friends over a VPN", "vpn-dogfight", "vpn",
             "Friends anywhere can join through a private VPN such as Tailscale. "
             "Never open the game's ports on your router.",
             "No VPN address found. Start your VPN app (for example Tailscale), then choose Refresh."),
)
AUDIENCE = {a.key: a for a in AUDIENCES}
AUDIENCE_OF_PROFILE = {a.profile: a for a in AUDIENCES} | {"local-relay": AUDIENCES[0]}
ALIASES = dict(defaults.ALIASES)

BACKDROPS = tuple((name, f"Starfield {name.removeprefix('spacebkgd') or '1'}") for name in defaults.BACKDROPS)
DEFAULT_BACKDROP = defaults.DEFAULT_BACKDROP

# Map objects the host can add, with what each needs.
OBJECTS = (
    ("navigation_buoys", "Navigation buoys",
     "Markers on the map that players can target. Needs the map objects exported from the game files."),
    ("turret_trial", "Turret trial (Arena1a)",
     "Five Arena1a turrets, with firing turned off. Needs the exported map objects."),
    ("warp_trial", "Warp gates trial (Arena1a)",
     "Nine Arena1a warp gates. This PC only: a gate moves players without a host check."),
)


def object_availability(profile, maps, terrain, export_ready):
    """{object key: '' if it can be used, else one sentence on what is missing}."""
    if not terrain:
        common = "Needs map terrain (Advanced)."
    elif not export_ready:
        common = "Needs the map objects exported from your game files."
    else:
        common = ""
    arena = common or ("" if maps == ["Arena1a"] else "Only on the map Arena1a.")
    return {"navigation_buoys": common,
            "turret_trial": arena,
            "warp_trial": arena or ("" if profile in defaults.OBJECT_PROFILES["warp_trial"]
                                    else "Only when the host is for this PC only.")}


# --- what a host asks of its players' game ---------------------------------------
FEATURES = dict(defaults.CLIENT_PATCH_LEVELS)


def feature_sentence(feature):
    """'Players need patch level 11 or later for map terrain.'"""
    words = {"terrain": "map terrain", "safe zones": "safe zones", "power-ups": "power-ups"}[feature]
    return f"Players need patch level {FEATURES[feature]} or later for {words}."


def host_needs(config):
    """The client features this host's settings rely on."""
    needs = []
    if config.terrain:
        needs.append("terrain")
        if config.objects.get("powerups") and any(BY_NAME[m].client_file for m in config.maps):
            needs.append("power-ups")
    return needs


# --- client options -----------------------------------------------------------
GROUPS = (("fixes", "Fixes (recommended)"), ("visual", "Visual extras"), ("experimental", "Experimental"))
# Player wording; the registry's label stays the command line's help text.
LABELS = {
    "menu_framing": "Widescreen ship-selection screen",
    "smooth_frame_clock": "Smoother frame timing",
    "bounded_visibility": "Fix objects popping in and out",
    "powerup_pickups": "Power-up pickups",
    "distant_objects": "See objects further away",
    "chase_camera": "Chase camera and orbit view (F2, F4)",
    "experimental_asteroids": "Smoother asteroids at a distance",
    "experimental_solids": "Smoother world models at a distance",
    "experimental_station_detail": "Full detail on stations",
    "experimental_world_detail": "Full detail on everything",
    "experimental_texture32": "32-bit textures",
    "experimental_protection": "Protection probe (this PC only)",
}
HELP = {
    "menu_framing": "Keeps the ship on the selection screen in proportion on a widescreen monitor.",
    "smooth_frame_clock": "Times frames with a precise clock, so flight is even on fast PCs.",
    "bounded_visibility": "Corrects a calculation that made distant objects flicker or vanish.",
    "powerup_pickups": "Lets you pick up power-ups on maps whose host places them.",
    "distant_objects": "Draws ships and objects at a longer distance than the original game.",
    "chase_camera": "F2 switches to a camera behind your ship, F4 to a camera that circles it. "
                    "Your own ship is drawn in both.",
    "experimental_asteroids": "Keeps asteroid shapes steady at a distance. Not together with the next option.",
    "experimental_solids": "Keeps every world model's shape steady at a distance. "
                           "Not together with \"Smoother asteroids\".",
    "experimental_station_detail": "Draws stations at full detail at every distance. "
                                   "Not together with \"Full detail on everything\".",
    "experimental_world_detail": "Draws every world model and texture at full detail. "
                                 "Not together with \"Full detail on stations\".",
    "experimental_texture32": "Loads textures with full color and transparency. "
                              "Needed for a replacement texture pack's larger images.",
    "experimental_protection": "A test of the game's own protection code. Works only when you play on this PC.",
}


@dataclass(frozen=True)
class Option:
    key: str
    group: str
    label: str
    help: str
    default: bool
    conflicts: tuple   # option keys it cannot be on with


def _options():
    out = []
    for p in patches.REGISTRY:
        if not p.option:
            continue
        others = tuple(patches.BY_ID[c].option for c in p.conflicts)
        out.append(Option(p.option, p.group, LABELS[p.option], HELP[p.option], p.default, others))
    return tuple(out)


OPTIONS = _options()
OPTION = {o.key: o for o in OPTIONS}


def grouped_options():
    """[(group title, [Option])] in the order the Options tab shows them."""
    return [(title, [o for o in OPTIONS if o.group == key]) for key, title in GROUPS]


def recommended():
    """{option: on} as a never-prepared client gets them (the registry defaults)."""
    return {o.key: o.default for o in OPTIONS}


def original_visuals():
    """Recommended fixes kept on; every visual and experimental option off."""
    return {o.key: o.default if o.group == "fixes" else False for o in OPTIONS}


def conflict_sentence(key, other):
    return f"\"{OPTION[key].label}\" and \"{OPTION[other].label}\" change the same code, so only one can be on."


# Graphics quality (the dgVoodoo wrapper's dgVoodoo.conf [DirectX] keys).
# key, label, hover, DirectX key, enabled value, original value
QUALITY = (
    ("antialiasing", "Smooth edges (8x anti-aliasing)", "Removes jagged edges on ships and stations.",
     "Antialiasing", "8x", "appdriven"),
    ("filtering", "Sharper textures at an angle (16x)", "Anisotropic filtering: surfaces seen at a "
     "steep angle stay sharp.", "Filtering", "16", "appdriven"),
    ("point_filter", "Keep pixel-art textures crisp", "Textures the game draws unfiltered stay unfiltered "
     "when the options above are on.", "KeepFilterIfPointSampled", "true", "false"),
    ("mipmaps", "Less texture shimmer", "Generated mipmaps: distant textures stop sparkling.",
     "Mipmapping", "autogen_bilinear", "appdriven"),
    ("phong", "Smoother lighting", "Per-pixel lighting where the game allows it.",
     "PhongShadingWhenPossible", "true", "false"),
)

WRAPPER_PAGE = "https://github.com/dege-diosg/dgVoodoo2/releases/tag/v2.87.5"
WRAPPER_ZIP = "dgVoodoo2_87_5.zip"
WRAPPER_LOSS = ("Without it the game runs full screen in its original 2004 mode: Alt+Tab may not work, "
                "and the Graphics quality options stay off.")
