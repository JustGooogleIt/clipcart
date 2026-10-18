"""URL checks for agent-submitted product links (no page fetch).

Rejects non-https, credentials, IP literals and names that are not public,
and (when ``resolve``) hosts that do not resolve only to public addresses.
Canonicalizes by dropping fragments and common tracking parameters.
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".test", ".example", ".invalid", ".onion", ".arpa")
_TRACKING = ("utm_", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "ref_src", "srsltid", "_ga")
AGGREGATOR_DOMAINS = {"solescout.ai"}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dns")


@dataclass(frozen=True)
class UrlCheck:
    ok: bool
    reason: str | None
    canonical: str | None = None
    domain: str | None = None


def _resolves_public(host: str, timeout_s: float) -> bool:
    try:
        infos = _pool.submit(socket.getaddrinfo, host, 443, proto=socket.IPPROTO_TCP).result(timeout=timeout_s)
    except (FutureTimeout, OSError):
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def registrable_domain(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 and len(parts[-1]) == 2 and len(parts[-2]) <= 3 else ".".join(parts[-2:])


def check_url(url: str, *, resolve: bool = True, timeout_s: float = 2.0) -> UrlCheck:
    if not isinstance(url, str) or len(url) > 2048 or any(c.isspace() for c in url.strip()):
        return UrlCheck(False, "not a single URL")
    p = urlparse(url.strip())
    if p.scheme != "https":
        return UrlCheck(False, "not https")
    if p.username or p.password:
        return UrlCheck(False, "URL contains credentials")
    if p.port not in (None, 443):
        return UrlCheck(False, "non-standard port")
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return UrlCheck(False, "no host")
    try:
        ipaddress.ip_address(host)
        return UrlCheck(False, "IP address instead of a retailer domain")
    except ValueError:
        pass
    if "." not in host or host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        return UrlCheck(False, "not a public domain")
    if resolve and not _resolves_public(host, timeout_s):
        return UrlCheck(False, "domain does not resolve to a public address")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not any(k.lower() == t or k.lower().startswith(t) for t in _TRACKING)]
    canonical = urlunparse(("https", host, p.path or "/", "", urlencode(query), ""))
    return UrlCheck(True, None, canonical, registrable_domain(host))
