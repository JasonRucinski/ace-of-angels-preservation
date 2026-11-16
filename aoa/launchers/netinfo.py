"""This PC's IPv4 addresses, each classified, using the standard library only.

kind(): "loopback" (127.x), "home" (the private ranges of a home or office
network), "vpn" (100.64.0.0/10, which Tailscale and similar VPNs use),
"link-local" (169.254.x, no network) or "other" (public or unusual).
The ranges are the server's own (aoa/host/defaults.py), so an address
offered for an audience is one the server accepts for it.

addresses() sends nothing: it reads the host name's addresses and asks the
system which local address would route to a home and a VPN address (a UDP
socket's connect() picks the route without a packet).
"""
import ipaddress
import socket

from aoa.host import defaults

KINDS = ("loopback", "home", "vpn", "link-local", "other")
PRIVATE = tuple(ipaddress.IPv4Network(n) for n in defaults.PRIVATE_NETWORKS)
VPN = tuple(ipaddress.IPv4Network(n) for n in defaults.VPN_NETWORKS)
# Addresses used only to ask the routing table which local address leads there.
PROBES = ("192.168.1.1", "10.0.0.1", "100.100.100.100")


def kind(address):
    ip = ipaddress.IPv4Address(address)
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if any(ip in n for n in VPN):
        return "vpn"
    if any(ip in n for n in PRIVATE):
        return "home"
    return "other"


def _from_hostname():
    try:
        return socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []


def _from_routes(probes=PROBES):
    found = []
    for probe in probes:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9))
                found.append(s.getsockname()[0])
        except OSError:
            continue
    return found


def addresses(sources=(_from_hostname, _from_routes)):
    """[(address, kind)] of this PC, each once, in a stable order (home, vpn, other, loopback)."""
    seen = {}
    for source in sources:
        for address in source():
            try:
                seen.setdefault(str(ipaddress.IPv4Address(address)), None)
            except ValueError:
                continue
    order = {"home": 0, "vpn": 1, "other": 2, "link-local": 3, "loopback": 4}
    return sorted(((a, kind(a)) for a in seen), key=lambda item: (order[item[1]], item[0]))


def for_kind(found, wanted):
    """The addresses of one kind (None: loopback, which every PC has)."""
    if wanted is None:
        return [defaults.LOOPBACK]
    return [address for address, k in found if k == wanted]
