"""Shade — the native SNI-spoofing subsystem of Dewberry.

This module adapts the original standalone *Shade Engine* into an in-process
subsystem. In the standalone product the engine ran as a **separate process**
(`shade_engine.py --engine`) that the GUI spawned and talked to over stdout.
Inside Dewberry it runs **natively**: no companion executable, no stdout
scraping. The runtime is wrapped in a :class:`SniEngine` object that Dewberry
starts/stops on its own background thread and that streams logs through a
callback, exactly like :class:`mulberry`-derived ``XrayCore`` / ``TunManager``.

The wire-level protocol logic (fake TLS ClientHello construction, the
sequence-number bypass injector, the async relay) is preserved verbatim from
the original engine — only its lifecycle and configuration were re-architected.

Windows-only: packet injection depends on the WinDivert driver via ``pydivert``,
which is imported lazily so the rest of Dewberry (and this file's import) works
on any platform for development and packaging.
"""
from __future__ import annotations

import asyncio
import os
import socket
import struct
import sys
import threading
import time
import traceback
from abc import ABC, abstractmethod

from ..version import ENGINE_VERSION

CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0

DISCONNECTED, CONNECTING, CONNECTED = "disconnected", "connecting", "connected"

DEFAULT_SNI_CONFIG: dict = {
    "LISTEN_HOST": "0.0.0.0",
    "LISTEN_PORT": 40443,
    "FAKE_SNI": "auth.vercel.com",
    "CONNECT_IP": "188.114.98.0",
    "CONNECT_PORT": 443,
}


# ==========================================================================
#  Helpers (from the original network_tools)
# ==========================================================================
def get_default_interface_ipv4(addr: str = "8.8.8.8") -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((addr, 53))
    except OSError:
        return ""
    else:
        return s.getsockname()[0]
    finally:
        s.close()


def _set_keepalive(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except Exception:
        pass
    for opt_name, value in (("TCP_KEEPIDLE", 11), ("TCP_KEEPINTVL", 2),
                            ("TCP_KEEPCNT", 3)):
        opt = getattr(socket, opt_name, None)
        if opt is None:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, opt, value)
        except Exception:
            pass


def validate_sni_config(cfg: dict) -> list[str]:
    """Return a list of human-readable problems ([] means valid)."""
    errors: list[str] = []
    host = str(cfg.get("LISTEN_HOST", "")).strip()
    if not host:
        errors.append("Listen host is required.")
    sni = str(cfg.get("FAKE_SNI", "")).strip()
    if not sni or "." not in sni:
        errors.append("Fake SNI must be a valid hostname.")
    ip = str(cfg.get("CONNECT_IP", "")).strip()
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255
                                  for p in parts):
        errors.append("Destination IP must be a valid IPv4 address.")
    for key, label in (("LISTEN_PORT", "Listen port"),
                       ("CONNECT_PORT", "Destination port")):
        try:
            port = int(cfg.get(key))
            if not (1 <= port <= 65535):
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{label} must be between 1 and 65535.")
    return errors


# ==========================================================================
#  packet_templates (verbatim wire logic)
# ==========================================================================
class ClientHelloMaker:
    tls_ch_template_str = "1603010200010001fc030341d5b549d9cd1adfa7296c8418d157dc7b624c842824ff493b9375bb48d34f2b20bf018bcc90a7c89a230094815ad0c15b736e38c01209d72d282cb5e2105328150024130213031301c02cc030c02bc02fcca9cca8c024c028c023c027009f009e006b006700ff0100018f0000000b00090000066d63692e6972000b000403000102000a00160014001d0017001e0019001801000101010201030104002300000010000e000c02683208687474702f312e310016000000170000000d002a0028040305030603080708080809080a080b080408050806040105010601030303010302040205020602002b00050403040303002d00020101003300260024001d0020435bacc4d05f9d41fef44ab3ad55616c36e0613473e2338770efdaa98693d217001500d5000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    tls_ch_template = bytes.fromhex(tls_ch_template_str)
    template_sni = "mci.ir".encode()
    static1 = tls_ch_template[:11]
    static2 = b"\x20"
    static3 = tls_ch_template[76:120]
    static4 = tls_ch_template[127 + len(template_sni):262 + len(template_sni)]
    static5 = b"\x00\x15"
    tls_change_cipher = b"\x14\x03\x03\x00\x01\x01"
    tls_app_data_header = b"\x17\x03\x03"

    @classmethod
    def get_client_hello_with(cls, rnd: bytes, sess_id: bytes, target_sni: bytes,
                              key_share: bytes) -> bytes:
        server_name_ext = (struct.pack("!H", len(target_sni) + 5)
                           + struct.pack("!H", len(target_sni) + 3) + b"\x00"
                           + struct.pack("!H", len(target_sni)) + target_sni)
        padding_ext = (struct.pack("!H", 219 - len(target_sni))
                       + (b"\x00" * (219 - len(target_sni))))
        return (cls.static1 + rnd + cls.static2 + sess_id + cls.static3
                + server_name_ext + cls.static4 + key_share + cls.static5
                + padding_ext)


# ==========================================================================
#  monitor_connection
# ==========================================================================
class MonitorConnection:
    def __init__(self, sock: socket.socket, src_ip, dst_ip, src_port, dst_port):
        self.monitor = True
        self.syn_seq = -1
        self.syn_ack_seq = -1
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.src_port = src_port
        self.dst_port = dst_port
        self.id = (self.src_ip, self.src_port, self.dst_ip, self.dst_port)
        self.thread_lock = threading.Lock()
        self.sock = sock


class FakeInjectiveConnection(MonitorConnection):
    def __init__(self, sock, src_ip, dst_ip, src_port, dst_port,
                 fake_data: bytes, bypass_method: str, peer_sock):
        super().__init__(sock, src_ip, dst_ip, src_port, dst_port)
        self.fake_data = fake_data
        self.sch_fake_sent = False
        self.fake_sent = False
        self.t2a_event = asyncio.Event()
        self.t2a_msg = ""
        self.bypass_method = bypass_method
        self.peer_sock = peer_sock
        self.running_loop = asyncio.get_running_loop()


# ==========================================================================
#  SniEngine — the native subsystem
# ==========================================================================
class SniEngine:
    """In-process SNI-spoofing tunnel.

    Lifecycle mirrors the other Dewberry networking cores:
        engine = SniEngine(log=print)
        engine.start(config)   # non-blocking; spins up its own thread
        engine.running         # bool
        engine.stats()         # dict of live health/telemetry
        engine.stop()
    """

    def __init__(self, log=print):
        self.log = log
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mother_sock: socket.socket | None = None
        self._injector = None            # FakeTcpInjector, created in-thread
        self._stop_flag = threading.Event()
        self._running = False
        self._ready = False
        self.started_at: float | None = None
        self.interface_ipv4: str = ""
        self.active_connections = 0
        self.total_accepted = 0
        self.config: dict = {}
        self._connections: dict = {}

    # ------------------------------------------------------------ state
    @property
    def running(self) -> bool:
        return self._running

    @property
    def ready(self) -> bool:
        return self._ready

    def uptime(self) -> float:
        return (time.time() - self.started_at) if self.started_at else 0.0

    def stats(self) -> dict:
        return {
            "running": self._running,
            "ready": self._ready,
            "uptime": self.uptime(),
            "listen": f"{self.config.get('LISTEN_HOST', '')}:"
                      f"{self.config.get('LISTEN_PORT', '')}",
            "fake_sni": self.config.get("FAKE_SNI", ""),
            "connect_ip": self.config.get("CONNECT_IP", ""),
            "connect_port": self.config.get("CONNECT_PORT", ""),
            "interface": self.interface_ipv4,
            "active": self.active_connections,
            "accepted": self.total_accepted,
            "version": ENGINE_VERSION,
        }

    # ------------------------------------------------------------ control
    def start(self, config: dict) -> None:
        if self._running:
            return
        errors = validate_sni_config(config)
        if errors:
            raise ValueError("; ".join(errors))
        self.config = dict(config)
        self._stop_flag.clear()
        self._ready = False
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="shade-engine")
        self._running = True
        self.started_at = time.time()
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag.set()
        self._running = False
        self._ready = False
        # break the WinDivert recv loop
        try:
            if self._injector is not None:
                self._injector.shutdown()
        except Exception:
            pass
        # break the asyncio accept loop
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
        sock = self._mother_sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        self._thread = None
        self._loop = None
        self._mother_sock = None
        self._injector = None
        self.active_connections = 0
        self.started_at = None
        self.log("[shade] engine stopped")

    # ------------------------------------------------------------ runtime
    def _run(self) -> None:
        self.log(f"[shade] Shade Engine v{ENGINE_VERSION}")
        self.log("[shade] initializing native subsystem...")
        cfg = self.config
        listen_host = str(cfg["LISTEN_HOST"]).strip()
        listen_port = int(cfg["LISTEN_PORT"])
        fake_sni = str(cfg["FAKE_SNI"]).strip().encode()
        connect_ip = str(cfg["CONNECT_IP"]).strip()
        connect_port = int(cfg["CONNECT_PORT"])

        interface = get_default_interface_ipv4(connect_ip)
        if not interface:
            self.log("[shade] ERROR: could not determine the local network "
                     "interface. Check your connection and destination IP.")
            self._running = False
            return
        self.interface_ipv4 = interface

        try:
            from pydivert import WinDivert, Packet  # noqa: F401
        except Exception as exc:
            self.log(f"[shade] ERROR: WinDivert/pydivert unavailable ({exc!r}). "
                     "The SNI engine requires Windows + Administrator rights.")
            self._running = False
            return

        w_filter = ("tcp and ("
                    f"(ip.SrcAddr == {interface} and ip.DstAddr == {connect_ip})"
                    " or "
                    f"(ip.SrcAddr == {connect_ip} and ip.DstAddr == {interface})"
                    ")")

        try:
            self._injector = FakeTcpInjector(w_filter, self._connections,
                                             self.log)
        except Exception as exc:
            self.log(f"[shade] ERROR: WinDivert failed to start ({exc!r}). "
                     "Run Dewberry as Administrator and allow the driver.")
            self._running = False
            return
        threading.Thread(target=self._injector.run, daemon=True,
                         name="shade-injector").start()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(self._loop_exception_handler)
        self._loop = loop
        try:
            loop.run_until_complete(self._serve(
                loop, listen_host, listen_port, fake_sni,
                connect_ip, connect_port, interface))
        except OSError as exc:
            self.log(f"[shade] ERROR: could not bind {listen_host}:"
                     f"{listen_port} ({exc}). The port may be in use.")
        except Exception as exc:  # pragma: no cover - defensive
            self.log(f"[shade] ERROR: engine stopped unexpectedly ({exc!r}).")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._running = False
            self._ready = False

    async def _serve(self, loop, listen_host, listen_port, fake_sni,
                     connect_ip, connect_port, interface) -> None:
        mother = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        mother.setblocking(False)
        mother.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        mother.bind((listen_host, listen_port))
        _set_keepalive(mother)
        mother.listen()
        self._mother_sock = mother
        self._ready = True
        self.log(f"[shade] listening on {listen_host}:{listen_port} -> "
                 f"{connect_ip}:{connect_port}")
        self.log(f"[shade] fake SNI: {fake_sni.decode(errors='replace')} | "
                 f"interface: {interface}")
        self.log("[shade] engine ready, waiting for connections")
        while not self._stop_flag.is_set():
            try:
                incoming, addr = await loop.sock_accept(mother)
            except (asyncio.CancelledError, OSError):
                break
            self.total_accepted += 1
            self.log(f"[shade] connection accepted from {addr[0]}:{addr[1]}")
            incoming.setblocking(False)
            _set_keepalive(incoming)
            loop.create_task(self._handle(
                loop, incoming, fake_sni, connect_ip, connect_port, interface))

    async def _handle(self, loop, incoming_sock, fake_sni, connect_ip,
                      connect_port, interface) -> None:
        bypass_method = "wrong_seq"
        try:
            fake_data = ClientHelloMaker.get_client_hello_with(
                os.urandom(32), os.urandom(32), fake_sni, os.urandom(32))
            outgoing = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing.setblocking(False)
            outgoing.bind((interface, 0))
            _set_keepalive(outgoing)
            src_port = outgoing.getsockname()[1]
            conn = FakeInjectiveConnection(
                outgoing, interface, connect_ip, src_port, connect_port,
                fake_data, bypass_method, incoming_sock)
            self._connections[conn.id] = conn
            self.active_connections += 1
            try:
                await loop.sock_connect(outgoing, (connect_ip, connect_port))
            except Exception:
                self._drop(conn, outgoing, incoming_sock)
                return
            try:
                await asyncio.wait_for(conn.t2a_event.wait(), 2)
                if conn.t2a_msg != "fake_data_ack_recv":
                    raise ValueError("unexpected close")
            except Exception:
                self._drop(conn, outgoing, incoming_sock)
                return
            conn.monitor = False
            self._connections.pop(conn.id, None)
            oti = asyncio.create_task(self._relay(
                loop, outgoing, incoming_sock, asyncio.current_task()))
            await self._relay(loop, incoming_sock, outgoing, oti)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if not self._stop_flag.is_set():
                self.log(f"[shade] connection error: {exc!r}")
        finally:
            self.active_connections = max(0, self.active_connections - 1)

    def _drop(self, conn, outgoing, incoming) -> None:
        conn.monitor = False
        self._connections.pop(conn.id, None)
        for s in (outgoing, incoming):
            try:
                s.close()
            except Exception:
                pass

    async def _relay(self, loop, sock_1, sock_2, peer_task) -> None:
        """Copy sock_1 -> sock_2 until EOF or error, then tear down cleanly.

        Every error raised here (EOF, cancellation, a peer closing the socket,
        or the Windows proactor aborting a pending overlapped I/O) is expected
        during a normal connection close, so they are swallowed quietly to
        avoid noisy tracebacks and "Task exception was never retrieved".
        """
        try:
            while not self._stop_flag.is_set():
                try:
                    data = await loop.sock_recv(sock_1, 65575)
                except (asyncio.CancelledError, OSError, ValueError):
                    break
                if not data:
                    break
                try:
                    await loop.sock_sendall(sock_2, data)
                except (asyncio.CancelledError, OSError, ValueError):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            for s in (sock_1, sock_2):
                try:
                    s.close()
                except Exception:
                    pass
            if peer_task is not None and not peer_task.done():
                peer_task.cancel()

    def _loop_exception_handler(self, loop, context) -> None:
        """Silence expected proactor teardown errors on Windows."""
        exc = context.get("exception")
        if isinstance(exc, (asyncio.CancelledError, OSError, ValueError)):
            return
        if self._stop_flag.is_set():
            return
        loop.default_exception_handler(context)


# ==========================================================================
#  injecter — WinDivert bridge (pydivert imported lazily, in-thread)
# ==========================================================================
class FakeTcpInjector:
    """Owns the WinDivert handle and performs the wrong-seq fake injection."""

    def __init__(self, w_filter: str, connections: dict, log=print):
        from pydivert import WinDivert  # lazy, engine-thread only
        self.w = WinDivert(w_filter)
        self.connections = connections
        self.log = log
        self._closed = False
        self.w.open()

    def shutdown(self) -> None:
        self._closed = True
        try:
            self.w.close()
        except Exception:
            pass

    def run(self) -> None:
        try:
            while not self._closed:
                try:
                    packet = self.w.recv()
                except Exception:
                    if self._closed:
                        return
                    raise
                self.inject(packet)
        except Exception as exc:  # pragma: no cover
            if not self._closed:
                self.log(f"[shade] injector stopped: {exc!r}")

    # ---- injection state machine (verbatim from the original engine) ----
    def _fake_send_thread(self, packet, connection) -> None:
        time.sleep(0.001)
        with connection.thread_lock:
            if not connection.monitor:
                return
            packet.tcp.psh = True
            packet.ip.packet_len = packet.ip.packet_len + len(connection.fake_data)
            packet.tcp.payload = connection.fake_data
            if packet.ipv4:
                packet.ipv4.ident = (packet.ipv4.ident + 1) & 0xffff
            if connection.bypass_method == "wrong_seq":
                packet.tcp.seq_num = (
                    connection.syn_seq + 1 - len(packet.tcp.payload)) & 0xffffffff
                connection.fake_sent = True
                self.w.send(packet, True)

    def _unexpected(self, packet, connection, msg: str) -> None:
        connection.sock.close()
        connection.peer_sock.close()
        connection.monitor = False
        connection.t2a_msg = "unexpected_close"
        connection.running_loop.call_soon_threadsafe(connection.t2a_event.set)
        self.w.send(packet, False)

    def _on_inbound(self, packet, connection) -> None:
        if connection.syn_seq == -1:
            self._unexpected(packet, connection, "no syn sent")
            return
        if (packet.tcp.ack and packet.tcp.syn and not packet.tcp.rst
                and not packet.tcp.fin and len(packet.tcp.payload) == 0):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if connection.syn_ack_seq != -1 and connection.syn_ack_seq != seq_num:
                self._unexpected(packet, connection, "syn-ack seq change")
                return
            if ack_num != ((connection.syn_seq + 1) & 0xffffffff):
                self._unexpected(packet, connection, "syn-ack ack mismatch")
                return
            connection.syn_ack_seq = seq_num
            self.w.send(packet, False)
            return
        if (packet.tcp.ack and not packet.tcp.syn and not packet.tcp.rst
                and not packet.tcp.fin and len(packet.tcp.payload) == 0
                and connection.fake_sent):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if (connection.syn_ack_seq == -1
                    or ((connection.syn_ack_seq + 1) & 0xffffffff) != seq_num):
                self._unexpected(packet, connection, "ack seq mismatch")
                return
            if ack_num != ((connection.syn_seq + 1) & 0xffffffff):
                self._unexpected(packet, connection, "ack ack mismatch")
                return
            connection.monitor = False
            connection.t2a_msg = "fake_data_ack_recv"
            connection.running_loop.call_soon_threadsafe(connection.t2a_event.set)
            return
        self._unexpected(packet, connection, "unexpected inbound")

    def _on_outbound(self, packet, connection) -> None:
        if connection.sch_fake_sent:
            self._unexpected(packet, connection, "packet after fake sent")
            return
        if (packet.tcp.syn and not packet.tcp.ack and not packet.tcp.rst
                and not packet.tcp.fin and len(packet.tcp.payload) == 0):
            if packet.tcp.ack_num != 0:
                self._unexpected(packet, connection, "syn ack_num not zero")
                return
            if connection.syn_seq != -1 and connection.syn_seq != packet.tcp.seq_num:
                self._unexpected(packet, connection, "syn seq mismatch")
                return
            connection.syn_seq = packet.tcp.seq_num
            self.w.send(packet, False)
            return
        if (packet.tcp.ack and not packet.tcp.syn and not packet.tcp.rst
                and not packet.tcp.fin and len(packet.tcp.payload) == 0):
            seq_num = packet.tcp.seq_num
            ack_num = packet.tcp.ack_num
            if (connection.syn_seq == -1
                    or ((connection.syn_seq + 1) & 0xffffffff) != seq_num):
                self._unexpected(packet, connection, "out ack seq mismatch")
                return
            if (connection.syn_ack_seq == -1
                    or ack_num != ((connection.syn_ack_seq + 1) & 0xffffffff)):
                self._unexpected(packet, connection, "out ack ack mismatch")
                return
            self.w.send(packet, False)
            connection.sch_fake_sent = True
            threading.Thread(target=self._fake_send_thread,
                             args=(packet, connection), daemon=True).start()
            return
        self._unexpected(packet, connection, "unexpected outbound")

    def inject(self, packet) -> None:
        if packet.is_inbound:
            c_id = (packet.ip.dst_addr, packet.tcp.dst_port,
                    packet.ip.src_addr, packet.tcp.src_port)
            connection = self.connections.get(c_id)
            if connection is None:
                self.w.send(packet, False)
                return
            with connection.thread_lock:
                if not connection.monitor:
                    self.w.send(packet, False)
                    return
                self._on_inbound(packet, connection)
        elif packet.is_outbound:
            c_id = (packet.ip.src_addr, packet.tcp.src_port,
                    packet.ip.dst_addr, packet.tcp.dst_port)
            connection = self.connections.get(c_id)
            if connection is None:
                self.w.send(packet, False)
                return
            with connection.thread_lock:
                if not connection.monitor:
                    self.w.send(packet, False)
                    return
                self._on_outbound(packet, connection)
