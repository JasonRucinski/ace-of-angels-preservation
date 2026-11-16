"""Join a friend's server: read what the host shared, decide how the game reaches it, check it.

The host window shares one line, for example

    Ace of Angels server 192.168.1.5 (name aoalan) - paste this into Play.cmd, Join a friend

parse() also takes a bare address ("192.168.1.5", "100.101.102.103"), a
name ("aoalan") or "aoa://100.101.102.103?name=aoavpn".

The game keeps its server address in an 11-character field. An address
that fits is used as it is. A longer one (most VPN addresses) goes through
a short name that the Windows hosts file points at the address; plan()
says which, and checks() reports three plain results: the address fits,
the name leads to the address, and the host answers on its list port. The
launcher never edits the hosts file: it shows the line to add.
"""
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from aoa.client import prepare
from aoa.host import defaults

FIELD = 11
LIST_PORT = defaults.PORTS["tcp"]
DEFAULT_ALIAS = defaults.ALIASES["vpn-dogfight"]
HOSTS_FILE = r"C:\Windows\System32\drivers\etc\hosts"
SHARE = re.compile(r"(?P<address>\d{1,3}(?:\.\d{1,3}){3})(?:\s*\(name\s+(?P<alias>[A-Za-z0-9-]{1,11})\))?")


@dataclass(frozen=True)
class Target:
    address: str          # IPv4 text, or a name when the host shared only a name
    alias: str = None     # the short name the host suggested

    @property
    def is_ip(self):
        try:
            ipaddress.IPv4Address(self.address)
            return True
        except ValueError:
            return False


def share_line(address, alias):
    """The line the host window gives its players (parse() reads it back)."""
    return f"Ace of Angels server {address} (name {alias}) - paste this into Play.cmd, Join a friend"


def parse(text):
    """A Target from what the host shared; ValueError with a plain sentence when it holds no address."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Paste the line or the address your host sent you.")
    if text.lower().startswith("aoa://"):
        parts = urlsplit(text)
        alias = (parse_qs(parts.query).get("name") or parse_qs(parts.query).get("alias") or [None])[0]
        return _target(parts.hostname or "", alias)
    match = SHARE.search(text)
    if match:
        return _target(match["address"], match["alias"])
    word = text.split()[0] if len(text.split()) == 1 else ""
    if word and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", word):
        return _target(word, None)
    raise ValueError("No server address found. It looks like 192.168.1.5 or 100.101.102.103.")


def _target(address, alias):
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        if re.fullmatch(r"[\d.]+", address or ""):
            raise ValueError(f"{address} is not a valid address. Ask your host to copy it again.") from None
        ip = None
    if ip is not None and (ip.is_unspecified or ip.is_multicast):
        raise ValueError(f"{address} cannot be a server address. Ask your host to copy it again.")
    if alias is not None:
        try:
            prepare.host_field(alias)
        except ValueError:
            alias = None
    return Target(address, alias)


@dataclass(frozen=True)
class Plan:
    target: Target
    server: str            # what the game is set to
    hosts_line: str = ""   # the line the hosts file needs, or "" when none is needed

    @property
    def needs_hosts(self):
        return bool(self.hosts_line)


def plan(target):
    """How the game reaches this target: directly, or through a hosts-file name."""
    if len(target.address) <= FIELD:
        prepare.host_field(target.address)
        return Plan(target, target.address)
    if not target.is_ip:
        raise ValueError(f"The name {target.address} is longer than the game allows ({FIELD} characters). "
                         "Ask your host for the address instead.")
    alias = target.alias or DEFAULT_ALIAS
    return Plan(target, alias, f"{target.address} {alias}")


@dataclass(frozen=True)
class Check:
    title: str
    ok: bool               # True, False, or None (not checked)
    text: str


def check_fits(p):
    if not p.needs_hosts:
        return Check("Address", True, f"The game can use {p.server} directly. No other setup is needed.")
    return Check("Address", True, f"{p.target.address} is longer than the game's {FIELD} characters, "
                                  f"so the game will use the name {p.server} for it.")


def check_name(p, resolve=socket.gethostbyname):
    """Whether the server name leads to the host's address (only when a name is used)."""
    if p.target.is_ip and not p.needs_hosts:
        return Check("Name", True, "Not needed: the address is used directly.")
    try:
        found = resolve(p.server)
    except (OSError, UnicodeError):
        found = None
    if p.target.is_ip and found == p.target.address:
        return Check("Name", True, f"{p.server} leads to {p.target.address}.")
    if not p.target.is_ip:
        if found:
            return Check("Name", True, f"{p.server} leads to {found}.")
        return Check("Name", False, f"This PC cannot find {p.server}. Ask your host for the address instead.")
    where = f"leads to {found}" if found else "is not known to this PC yet"
    return Check("Name", False, f"{p.server} {where}. Add this line to the hosts file, then check again:")


def check_answers(p, connect=socket.create_connection, timeout=3.0):
    """Whether the host's server list answers (TCP list port)."""
    address = p.target.address
    try:
        connection = connect((address, LIST_PORT), timeout)
    except socket.timeout:
        return Check("Host", False, f"No answer from {address} within {timeout:g} s. Check that the host is "
                                    "running, that you are on the same network or VPN, and the host's firewall.")
    except OSError as error:
        reason = "refused the connection: the server is not running there" \
            if isinstance(error, ConnectionRefusedError) else "could not be reached"
        return Check("Host", False, f"{address} {reason}. Ask your host to check that the server is started "
                                    "and the firewall allows it.")
    try:
        connection.close()
    except OSError:
        pass
    return Check("Host", True, f"The host at {address} answers.")


def checks(p, resolve=socket.gethostbyname, connect=socket.create_connection, timeout=3.0):
    return [check_fits(p), check_name(p, resolve), check_answers(p, connect, timeout)]


def open_hosts_command():
    """The command the "Open Notepad as administrator" button runs (Windows asks for permission)."""
    return ["powershell", "-NoProfile", "-Command",
            f"Start-Process notepad.exe -Verb RunAs -ArgumentList '{HOSTS_FILE}'"]


def apply(exe, server):
    """Point the game at `server`; every other option keeps its installed state.

    The protection probe works only with a server on this PC, so it is
    switched off for any other (the one option this may change).
    """
    options = {}
    if server not in prepare.LOOPBACK:
        options["experimental_protection"] = False
    return prepare.prepare(exe, options, station=server)
