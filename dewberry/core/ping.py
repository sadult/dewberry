"""Latency measurement.

Two kinds of tests, like v2rayN / Throne:
- TCP ping  : plain TCP handshake time to server:port (fast, no core needed).
- URL test  : real delay through the proxy. One temporary Xray instance is
              started with one SOCKS inbound per server, each routed to its
              own outbound, then an HTTP request is timed through each.
"""
from __future__ import annotations

import socket
import time
from concurrent.futures import (ThreadPoolExecutor, as_completed,
                                TimeoutError as FuturesTimeout)

import requests

from ..version import URL_TEST_DEFAULT
from .links import to_outbound

TEST_BASE_PORT = 30500
BATCH = 50  # servers per temporary core instance


# ------------------------------------------------------------- TCP ping

def tcp_ping(host: str, port: int, timeout: float = 4.0):
    """Return TCP connect time in ms, or None on failure."""
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        family, _, _, _, addr = infos[0]
        start = time.perf_counter()
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(addr)
        return int((time.perf_counter() - start) * 1000)
    except OSError:
        return None


def tcp_ping_many(servers: list[dict], on_result, workers: int = 24, should_stop=None):
    """Ping all servers concurrently. Calls on_result(server_id, ms|None)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(tcp_ping, s["address"], s["port"]): s["id"] for s in servers
        }
        for fut in as_completed(futures):
            if should_stop and should_stop():
                break
            on_result(futures[fut], fut.result())


# ------------------------------------------------------------- URL test

def _build_test_config(servers: list[dict], base_port: int) -> dict:
    inbounds, outbounds, rules = [], [], []
    for i, s in enumerate(servers):
        inbounds.append({
            "tag": f"in{i}", "listen": "127.0.0.1", "port": base_port + i,
            "protocol": "socks", "settings": {"udp": False},
        })
        outbounds.append(to_outbound(s, tag=f"out{i}", allow_insecure=True))
        rules.append({"type": "field", "inboundTag": [f"in{i}"], "outboundTag": f"out{i}"})
    return {
        "log": {"loglevel": "none"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {"rules": rules},
    }


def _timed_request(port: int, url: str, timeout: float):
    proxies = {
        "http": f"socks5h://127.0.0.1:{port}",
        "https": f"socks5h://127.0.0.1:{port}",
    }
    try:
        start = time.perf_counter()
        resp = requests.get(url, proxies=proxies, timeout=timeout, stream=True)
        resp.close()
        if resp.status_code < 500:
            return int((time.perf_counter() - start) * 1000)
    except Exception:
        pass
    return None


def url_test_many(xray_core, servers: list[dict], on_result,
                  url: str = URL_TEST_DEFAULT, timeout: float = 8.0,
                  workers: int = 16, should_stop=None):
    """Real-delay test all servers. Calls on_result(server_id, ms|None).

    xray_core: mulberry.core.xray.XrayCore (used to spawn temp instances).
    """
    testable = [s for s in servers if s.get("protocol")]
    for chunk_start in range(0, len(testable), BATCH):
        if should_stop and should_stop():
            return
        chunk = testable[chunk_start:chunk_start + BATCH]
        config = _build_test_config(chunk, TEST_BASE_PORT)
        proc = xray_core.spawn(config, name="urltest")
        try:
            time.sleep(1.2)  # let the core bind its inbounds
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_timed_request, TEST_BASE_PORT + i, url, timeout): s["id"]
                    for i, s in enumerate(chunk)
                }
                try:
                    for fut in as_completed(futures, timeout=timeout + 20):
                        if should_stop and should_stop():
                            break
                        on_result(futures[fut], fut.result())
                except FuturesTimeout:
                    for fut, sid in futures.items():
                        if not fut.done():
                            fut.cancel()
                            on_result(sid, None)
        finally:
            xray_core.kill(proc)


def pick_fastest(servers: list[dict], key: str = "delay_ms"):
    """Return the server with the lowest measured delay (fallback to tcp ping)."""
    def metric(s):
        v = s.get(key)
        if v is None:
            v = s.get("ping_ms")
        return v if v is not None else 10 ** 9
    candidates = [s for s in servers if metric(s) < 10 ** 9]
    return min(candidates, key=metric) if candidates else None
