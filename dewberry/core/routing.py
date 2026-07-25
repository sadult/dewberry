"""Xray routing & DNS builder.

Highlights:
- "Bypass Iranian websites" sends geosite Iran categories, *.ir domains and
  Iranian IP ranges (geoip:ir) straight to the `direct` outbound, so local
  banking / government / shop sites keep working while connected.
- Ad & malware blocking through geosite categories.
- Custom user rules (direct / proxy / block domain lists).

Geo files: use the Iran-aware bundles from `scripts/get_assets.py`
(chocolate4u/Iran-v2ray-rules) which include `geosite:ir` and `geoip:ir`.
"""
from __future__ import annotations

IR_DOMAINS = ["geosite:ir", "regexp:.+\\.ir$"]
ADS_DOMAINS = ["geosite:category-ads-all"]
MALWARE_DOMAINS = ["geosite:malware", "geosite:phishing", "geosite:cryptominers"]


def build_routing(settings: dict) -> dict:
    rules: list[dict] = []

    # Always keep the api tag local if present.
    rules.append({"type": "field", "inboundTag": ["api"], "outboundTag": "api"})

    block_domains = list(settings.get("custom_block") or [])
    if settings.get("block_ads", True):
        block_domains += ADS_DOMAINS
    if settings.get("block_malware", True):
        block_domains += MALWARE_DOMAINS
    if block_domains:
        rules.append({"type": "field", "outboundTag": "block", "domain": block_domains})

    proxy_domains = list(settings.get("custom_proxy") or [])
    if proxy_domains:
        rules.append({"type": "field", "outboundTag": "proxy", "domain": proxy_domains})

    direct_domains = list(settings.get("custom_direct") or [])
    if settings.get("bypass_iran", True):
        direct_domains += IR_DOMAINS
    if direct_domains:
        rules.append({"type": "field", "outboundTag": "direct", "domain": direct_domains})

    direct_ips = []
    if settings.get("bypass_iran", True):
        direct_ips.append("geoip:ir")
    if settings.get("bypass_lan", True):
        direct_ips.append("geoip:private")
    if direct_ips:
        rules.append({"type": "field", "outboundTag": "direct", "ip": direct_ips})

    return {"domainStrategy": "IPIfNonMatch", "rules": rules}


def build_dns(settings: dict) -> dict:
    """Plain resolvers with fallbacks; Iranian resolver pinned to .ir.

    DoH-only DNS made every non-matching domain hang when the DoH endpoint
    was blocked (IPIfNonMatch resolves domains to test the geoip:ir rule).
    Plain UDP resolvers + localhost fallback keep resolution instant.
    """
    servers: list = []
    if settings.get("bypass_iran", True):
        servers.append({
            "address": settings.get("dns_iran") or "78.157.42.100",
            "domains": IR_DOMAINS,
            "skipFallback": True,
        })
    remote = settings.get("dns_remote") or "8.8.8.8"
    if remote.startswith("https://"):  # migrate old default
        remote = "8.8.8.8"
    servers.append(remote)
    for fallback in ("1.1.1.1", "localhost"):
        if fallback != remote:
            servers.append(fallback)
    return {"servers": servers, "queryStrategy": "UseIPv4", "tag": "dns"}
