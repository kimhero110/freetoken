"""SSRF protection for WitKit Bench."""

import ipaddress
import socket
import os
from urllib.parse import urlparse


def ssrf_guard(base_url: str) -> None:
    """Reject private/loopback/link-local/CGNAT/resolved targets unless
    env ALLOW_PRIVATE_TARGETS=1 is set (for trusted internal use)."""
    if os.environ.get("ALLOW_PRIVATE_TARGETS", "0") == "1":
        return
    try:
        u = urlparse(base_url)
    except Exception:
        raise ValueError("invalid base_url")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("base_url must be http/https with a hostname")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except Exception:
        raise ValueError("DNS resolution failed: " + str(u.hostname))
    for info in infos:
        raw = info[4][0].split('%')[0]
        ip = ipaddress.ip_address(raw)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ValueError("target address is in a private/reserved range, blocked by SSRF protection")
        if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
            raise ValueError("target address is in a private/reserved range, blocked by SSRF protection")
