"""A local HTTP/3 (QUIC) endpoint for the topology MCP server, for testing only.

Cloudflare terminates HTTP/3 at its edge, so a deployed Worker never sees QUIC
and this file is not part of the deployment. It exists so the agent's HTTP/3
transport can be exercised end to end on one machine:

  python h3_dev_server.py --port 4433        # self-signed certificate, made on start
  python agent_client.py https://127.0.0.1:4433/mcp --insecure

Requests go through server.handle_http, the same Streamable HTTP rules the
HTTP/1.1 mode uses. Needs: pip install aioquic
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import ipaddress
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from aioquic.asyncio import serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ProtocolNegotiated
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from server import TopologyServer, handle_http


def self_signed(directory: Path, host: str) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                       critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path


def make_protocol(server: TopologyServer, allowed_origins: set[str]) -> type[QuicConnectionProtocol]:
    class H3Server(QuicConnectionProtocol):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.http: H3Connection | None = None
            self.streams: dict[int, list[Any]] = {}

        def quic_event_received(self, event: Any) -> None:
            if isinstance(event, ProtocolNegotiated) and event.alpn_protocol in H3_ALPN:
                self.http = H3Connection(self._quic)
            if self.http is None:
                return
            for ev in self.http.handle_event(event):
                if isinstance(ev, HeadersReceived):
                    self.streams[ev.stream_id] = [{k.decode(): v.decode() for k, v in ev.headers}, b""]
                elif isinstance(ev, DataReceived) and ev.stream_id in self.streams:
                    self.streams[ev.stream_id][1] += ev.data
                if getattr(ev, "stream_ended", False) and ev.stream_id in self.streams:
                    self.respond(ev.stream_id, *self.streams.pop(ev.stream_id))

        def respond(self, stream: int, headers: dict[str, str], body: bytes) -> None:
            assert self.http is not None
            status, payload, extra = handle_http(
                server, headers.get(":method", ""), headers.get(":path", ""),
                lambda name: headers.get(name.lower()), body, allowed_origins,
            )
            data = b"" if payload is None else json.dumps(payload).encode()
            out = [(b":status", str(status).encode())]
            if payload is not None:
                out.append((b"content-type", b"application/json"))
            out += [(k.lower().encode(), v.encode()) for k, v in extra.items()]
            self.http.send_headers(stream, out)
            self.http.send_data(stream, data, end_stream=True)
            self.transmit()

    return H3Server


async def run(host: str, port: int, ready: asyncio.Event | None = None, stop: asyncio.Event | None = None) -> None:
    server = TopologyServer(caller="h3-dev-client")
    with tempfile.TemporaryDirectory() as tmp:
        cert, key = self_signed(Path(tmp), host)
        config = QuicConfiguration(is_client=False, alpn_protocols=H3_ALPN)
        config.load_cert_chain(cert, key)
        allowed = {f"https://{host}:{port}", f"https://localhost:{port}", f"https://127.0.0.1:{port}"}
        quic = await serve(host, port, configuration=config, create_protocol=make_protocol(server, allowed))
        print(f"MCP over HTTP/3 on https://{host}:{port}/mcp (self-signed)", file=sys.stderr, flush=True)
        if ready:
            ready.set()
        try:
            await (stop.wait() if stop else asyncio.Future())
        finally:
            quic.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4433)
    args = ap.parse_args()
    asyncio.run(run(args.host, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
