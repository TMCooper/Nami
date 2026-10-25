import os
import time
import socket
import asyncio
import ipaddress
from collections import OrderedDict
from typing import Optional
from urllib.parse import urlparse

_DNS_CACHE_TTL = 300.0
_DNS_CACHE_MAX = 2048
_dns_cache: "OrderedDict[str, tuple]" = OrderedDict()
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class UnsafeUrlError(ValueError):
    pass


def is_public_ip(ip_str: str) -> bool:
    """True only for globally routable unicast addresses (embedded IPv4 in IPv6 is unwrapped first)."""
    try:
        ip = ipaddress.ip_address(str(ip_str).split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour:
            ip = ip.sixtofour
        elif ip.teredo:
            ip = ip.teredo[1]
        elif ip in _NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        elif ip.is_site_local:
            return False
    return ip.is_global and not ip.is_multicast


def peer_is_public(response) -> bool:
    """Checks the address the connection actually reached (defeats DNS rebinding between check and connect)."""
    stream = response.extensions.get("network_stream") if hasattr(response, "extensions") else None
    if stream is None:
        return False
    addr = stream.get_extra_info("server_addr")
    return bool(addr) and is_public_ip(addr[0])


async def assert_public_http_url(url: str):
    """Rejects non-http(s) URLs and hosts resolving to non-public addresses (first SSRF filter).

    The address really connected to is checked again with peer_is_public once the response arrives.
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise UnsafeUrlError("URL invalide")
    if parsed.scheme not in ("http", "https") or not host:
        raise UnsafeUrlError("URL non supportée")

    now = time.monotonic()
    cached = _dns_cache.get(host)
    if cached and cached[0] > now:
        _dns_cache.move_to_end(host)
        is_public = cached[1]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError, ValueError):
            raise UnsafeUrlError("Hôte introuvable")
        addresses = {info[4][0] for info in infos}
        is_public = bool(addresses) and all(is_public_ip(a) for a in addresses)
        _dns_cache[host] = (now + _DNS_CACHE_TTL, is_public)
        _dns_cache.move_to_end(host)
        while len(_dns_cache) > _DNS_CACHE_MAX:
            _dns_cache.popitem(last=False)

    if not is_public:
        raise UnsafeUrlError("Hôte non autorisé")


def media_root(root_folder: str) -> str:
    return os.path.realpath(os.path.join(root_folder, "nami"))


def resolve_media_path(path: str, root_folder: str) -> Optional[str]:
    """Returns the real path if it lies inside {root_folder}/nami, else None (blocks arbitrary file access)."""
    if not path:
        return None
    base = os.path.normcase(media_root(root_folder))
    real = os.path.realpath(path)
    try:
        if os.path.commonpath([os.path.normcase(real), base]) != base:
            return None
    except ValueError:
        # Different drives on Windows
        return None
    return real
