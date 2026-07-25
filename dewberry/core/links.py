"""Parse V2Ray/Xray share links into Mulberry server dicts and Xray outbounds.

Supported schemes: vless://, vmess://, trojan://, ss://, socks://
Supported transports: tcp, ws, grpc, httpupgrade, xhttp, kcp, quic
Supported security: none, tls, reality
"""
from __future__ import annotations

import base64
import json
import uuid as uuidlib
from urllib.parse import parse_qs, unquote, urlparse

SUPPORTED_SCHEMES = ("vless", "vmess", "trojan", "ss", "socks")


def new_id() -> str:
    return uuidlib.uuid4().hex[:12]


def _b64(data: str) -> bytes:
    data = data.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(data + "=" * (-len(data) % 4))


def _q(params: dict, key: str, default: str = "") -> str:
    v = params.get(key)
    return unquote(v[0]) if v else default


def _base(protocol: str, raw: str) -> dict:
    return {
        "id": new_id(),
        "protocol": protocol,
        "raw": raw.strip(),
        "remark": "",
        "address": "",
        "port": 0,
        "network": "tcp",
        "security": "none",
        "sni": "",
        "host": "",
        "path": "",
        "alpn": "",
        "fp": "",
        "flow": "",
        "pbk": "",
        "sid": "",
        "spx": "",
        "header_type": "none",
        "grpc_service": "",
        "grpc_mode": "gun",
        "uuid": "",
        "password": "",
        "method": "",
        "sub_id": None,
        "ping_ms": None,   # TCP handshake time
        "delay_ms": None,  # real URL-test delay through the proxy
    }


# ---------------------------------------------------------------- parsers

def _parse_vmess(link: str) -> dict:
    payload = json.loads(_b64(link[len("vmess://"):]).decode("utf-8", "replace"))
    s = _base("vmess", link)
    s.update(
        remark=str(payload.get("ps") or "") or f"{payload.get('add')}:{payload.get('port')}",
        address=str(payload.get("add") or ""),
        port=int(payload.get("port") or 0),
        uuid=str(payload.get("id") or ""),
        network=str(payload.get("net") or "tcp"),
        security="tls" if str(payload.get("tls") or "") in ("tls", "1", "true") else "none",
        sni=str(payload.get("sni") or ""),
        host=str(payload.get("host") or ""),
        path=str(payload.get("path") or ""),
        alpn=str(payload.get("alpn") or ""),
        fp=str(payload.get("fp") or ""),
        header_type=str(payload.get("type") or "none"),
    )
    s["alter_id"] = int(payload.get("aid") or 0)
    s["vmess_security"] = str(payload.get("scy") or "auto")
    return s


def _parse_uri(link: str, scheme: str) -> dict:
    u = urlparse(link)
    params = parse_qs(u.query)
    s = _base(scheme, link)
    s.update(
        remark=unquote(u.fragment) or f"{u.hostname}:{u.port}",
        address=u.hostname or "",
        port=int(u.port or (443 if scheme != "socks" else 1080)),
        network=_q(params, "type", "tcp"),
        security=_q(params, "security", "tls" if scheme == "trojan" else "none"),
        sni=_q(params, "sni") or _q(params, "peer"),
        host=_q(params, "host"),
        path=_q(params, "path") or _q(params, "serviceName"),
        alpn=_q(params, "alpn"),
        fp=_q(params, "fp"),
        flow=_q(params, "flow"),
        pbk=_q(params, "pbk"),
        sid=_q(params, "sid"),
        spx=_q(params, "spx"),
        header_type=_q(params, "headerType", "none"),
        grpc_service=_q(params, "serviceName"),
        grpc_mode=_q(params, "mode", "gun"),
    )
    if scheme == "vless":
        s["uuid"] = unquote(u.username or "")
    elif scheme == "trojan":
        s["password"] = unquote(u.username or "")
    elif scheme == "socks":
        s["uuid"] = unquote(u.username or "")
        s["password"] = unquote(u.password or "")
    if s["network"] == "grpc" and not s["grpc_service"]:
        s["grpc_service"] = s["path"]
    return s


def _parse_ss(link: str) -> dict:
    body = link[len("ss://"):]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    body = body.split("?", 1)[0]
    if "@" in body:
        creds, hostport = body.rsplit("@", 1)
        try:
            creds = _b64(creds).decode("utf-8")
        except Exception:
            creds = unquote(creds)
        method, password = creds.split(":", 1)
    else:
        decoded = _b64(body).decode("utf-8")
        creds, hostport = decoded.rsplit("@", 1)
        method, password = creds.split(":", 1)
    host, port = hostport.rsplit(":", 1)
    s = _base("ss", link)
    s.update(
        remark=unquote(frag) or f"{host}:{port}",
        address=host.strip("[]"),
        port=int(port),
        method=method,
        password=password,
    )
    return s


def parse_link(link: str):
    link = link.strip()
    if "://" not in link:
        return None
    scheme = link.split("://", 1)[0].lower()
    try:
        if scheme == "vmess":
            return _parse_vmess(link)
        if scheme in ("vless", "trojan"):
            return _parse_uri(link, scheme)
        if scheme == "ss":
            return _parse_ss(link)
        if scheme in ("socks", "socks5"):
            return _parse_uri(link, "socks")
    except Exception:
        return None
    return None


def parse_links(text: str) -> list[dict]:
    """Parse many links (newline separated, optionally base64-wrapped)."""
    text = text.strip()
    if text and "://" not in text.split("\n", 1)[0]:
        try:
            text = _b64(text).decode("utf-8", "replace")
        except Exception:
            pass
    out = []
    for line in text.replace("\r", "\n").split("\n"):
        s = parse_link(line)
        if s:
            out.append(s)
    return out


# ---------------------------------------------------------------- outbound

def _stream_settings(s: dict, allow_insecure: bool) -> dict:
    net = s["network"] or "tcp"
    st: dict = {"network": net, "security": s["security"] or "none"}

    if net == "ws":
        ws: dict = {"path": s["path"] or "/"}
        if s["host"]:
            ws["host"] = s["host"]
            ws["headers"] = {"Host": s["host"]}
        st["wsSettings"] = ws
    elif net == "grpc":
        st["grpcSettings"] = {"serviceName": s["grpc_service"] or "",
                              "multiMode": s.get("grpc_mode") == "multi"}
    elif net == "httpupgrade":
        st["httpupgradeSettings"] = {"path": s["path"] or "/", "host": s["host"] or ""}
    elif net in ("xhttp", "splithttp"):
        st["network"] = "xhttp"
        st["xhttpSettings"] = {"path": s["path"] or "/", "host": s["host"] or ""}
    elif net == "kcp":
        st["kcpSettings"] = {"header": {"type": s["header_type"] or "none"},
                             "seed": s["path"] or None}
    elif net == "quic":
        st["quicSettings"] = {"security": s["host"] or "none", "key": s["path"] or "",
                              "header": {"type": s["header_type"] or "none"}}
    elif net == "tcp" and (s["header_type"] or "none") == "http":
        st["tcpSettings"] = {"header": {"type": "http", "request": {
            "path": [s["path"] or "/"],
            "headers": {"Host": [h for h in (s["host"] or "").split(",") if h]},
        }}}

    if st["security"] == "tls":
        tls = {"serverName": s["sni"] or s["host"] or s["address"],
               "allowInsecure": bool(allow_insecure)}
        if s["alpn"]:
            tls["alpn"] = [a for a in s["alpn"].split(",") if a]
        if s["fp"]:
            tls["fingerprint"] = s["fp"]
        st["tlsSettings"] = tls
    elif st["security"] == "reality":
        st["realitySettings"] = {
            "serverName": s["sni"] or "",
            "fingerprint": s["fp"] or "chrome",
            "publicKey": s["pbk"] or "",
            "shortId": s["sid"] or "",
            "spiderX": s["spx"] or "",
        }
    return st


def to_outbound(s: dict, tag: str = "proxy", allow_insecure: bool = False,
                mux: bool = False, mux_concurrency: int = 8) -> dict:
    """Convert a Mulberry server dict into an Xray outbound object."""
    proto = s["protocol"]
    ob: dict = {"tag": tag}

    if proto == "vless":
        ob["protocol"] = "vless"
        user = {"id": s["uuid"], "encryption": "none"}
        if s["flow"]:
            user["flow"] = s["flow"]
        ob["settings"] = {"vnext": [{"address": s["address"], "port": s["port"],
                                     "users": [user]}]}
    elif proto == "vmess":
        ob["protocol"] = "vmess"
        ob["settings"] = {"vnext": [{"address": s["address"], "port": s["port"],
                                     "users": [{"id": s["uuid"],
                                                "alterId": s.get("alter_id", 0),
                                                "security": s.get("vmess_security", "auto")}]}]}
    elif proto == "trojan":
        ob["protocol"] = "trojan"
        ob["settings"] = {"servers": [{"address": s["address"], "port": s["port"],
                                       "password": s["password"]}]}
    elif proto == "ss":
        ob["protocol"] = "shadowsocks"
        ob["settings"] = {"servers": [{"address": s["address"], "port": s["port"],
                                       "method": s["method"], "password": s["password"]}]}
    elif proto == "socks":
        ob["protocol"] = "socks"
        server = {"address": s["address"], "port": s["port"]}
        if s["uuid"]:
            server["users"] = [{"user": s["uuid"], "pass": s["password"]}]
        ob["settings"] = {"servers": [server]}
    else:
        raise ValueError(f"Unsupported protocol: {proto}")

    ob["streamSettings"] = _stream_settings(s, allow_insecure)
    if mux and proto in ("vless", "vmess", "trojan", "ss"):
        ob["mux"] = {"enabled": True, "concurrency": int(mux_concurrency)}
    return ob
