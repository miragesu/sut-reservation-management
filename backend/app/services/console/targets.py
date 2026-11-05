"""Pure target classification + local interface/route deny discovery; no probes/DNS."""

from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
import socket
import struct

from fastapi import HTTPException

PRIVATE = tuple(IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def local_denials():
    try:
        import fcntl
    except ImportError:
        # Disabled Console must not break existing non-Linux development imports.
        raise HTTPException(503, "Console network safety discovery requires a supported host") from None
    denied = set()
    # ioctl reads local interface configuration; no TCP, target probe or DNS request.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
        for _, name in socket.if_nameindex():
            for request in (0x8915, 0x8919):  # SIOCGIFADDR / SIOCGIFBRDADDR
                try:
                    data = fcntl.ioctl(handle, request, struct.pack("256s", name.encode()[:15]))
                    denied.add(str(IPv4Address(data[20:24])))
                except OSError:
                    continue
    try:
        for line in Path("/proc/net/route").read_text().splitlines()[1:]:
            fields = line.split()
            if fields[2] != "00000000":
                denied.add(str(IPv4Address(bytes.fromhex(fields[2])[::-1])))
    except (OSError, ValueError, IndexError):
        # Classification must not silently discard self protection on unsupported hosts.
        raise HTTPException(503, "Console local network safety discovery unavailable") from None
    return denied


def validate_ipv4(value, *, bmc=False, sensitive=(), local=None):
    try:
        address = IPv4Address(value)
        if str(address) != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Console target requires canonical dotted-quad IPv4") from None
    denied = (local_denials() if local is None else set(local)) | set(sensitive)
    if (
        not address.is_global
        and not any(address in network for network in PRIVATE)
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or str(address) in denied
    ):
        raise HTTPException(422, "Console target is sensitive, local or non-unicast")
    if bmc and (
        not any(address in network for network in PRIVATE)
        or any(address in (n.network_address, n.broadcast_address) for n in PRIVATE)
    ):
        raise HTTPException(422, "BMC requires non-sensitive RFC1918 private IPv4")
    return str(address)
