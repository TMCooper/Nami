import os
import asyncio

import pytest

from backend.services.net_safety import assert_public_http_url, resolve_media_path, is_public_ip, peer_is_public, UnsafeUrlError


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5000/api/getAllAnime",
    "http://localhost:8000/catalog",
    "http://10.0.0.5/admin",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://example.com/x.jpg",
    "http://[::1",
    "http://" + "a" * 70 + ".test/x.jpg",
])
def test_private_and_non_http_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        asyncio.run(assert_public_http_url(url))


def test_public_ip_literal_is_accepted():
    asyncio.run(assert_public_http_url("https://8.8.8.8/image.jpg"))


def test_media_path_must_stay_inside_root_nami(tmp_path):
    root = tmp_path / "downloads"
    episode = root / "nami" / "anime" / "Frieren" / "Saison_1" / "Episode_01.mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"x")
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")

    assert resolve_media_path(str(episode), str(root)) == os.path.realpath(str(episode))
    assert resolve_media_path(str(outside), str(root)) is None
    traversal = str(root / "nami" / ".." / ".." / "secret.txt")
    assert resolve_media_path(traversal, str(root)) is None
    assert resolve_media_path("", str(root)) is None


@pytest.mark.parametrize("ip", [
    "100.64.0.1", "100.100.100.200",   # CGNAT / Tailscale, cloud metadata
    "2002:7f00:1::",                    # 6to4 wrapping 127.0.0.1
    "::ffff:10.0.0.1",                  # IPv4-mapped private
    "fec0::1",                          # deprecated site-local
    "224.0.0.1", "0.0.0.0", "fe80::1",
])
def test_non_global_addresses_are_not_public(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "2001:4860:4860::8888"])
def test_global_addresses_are_public(ip):
    assert is_public_ip(ip)


class _Stream:
    def __init__(self, addr):
        self.addr = addr

    def get_extra_info(self, name):
        return self.addr if name == "server_addr" else None


class _Response:
    def __init__(self, addr):
        self.extensions = {"network_stream": _Stream(addr)} if addr else {}


def test_peer_check_uses_the_address_actually_connected_to():
    # DNS rebinding: the name looked public during the check, the connection reached loopback
    assert not peer_is_public(_Response(("127.0.0.1", 80)))
    assert peer_is_public(_Response(("8.8.8.8", 443)))
    assert not peer_is_public(_Response(None))
