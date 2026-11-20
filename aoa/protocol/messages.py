"""Constants every message module shares: the NUL pad byte and the log names of datagram types."""

NUL = bytes(1)
TYPE_NAMES = {0x0A: "SConnectReq", 0x0B: "SAckConnect", 0x94: "type94 (ping/keepalive?)", 0x1B: "wrapper 0x1B"}
