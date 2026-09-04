"""Servidor TCP efêmero para provar o adapter RAW TCP real da F9-E."""

from __future__ import annotations

import os
import socket
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("F9E_PRINT_PORT", "19100"))
OUTPUT = Path(os.environ.get("F9E_PRINT_CAPTURE", "/tmp/f9e-print-capture.txt"))


def main() -> None:
    OUTPUT.write_bytes(b"")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(8)
        print(f"F9-E TCP capture listening on {HOST}:{PORT}", flush=True)
        while True:
            conn, _ = server.accept()
            with conn:
                chunks: list[bytes] = []
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                payload = b"".join(chunks)
                with OUTPUT.open("ab") as handle:
                    handle.write(payload)
                    handle.write(b"\n---F9E---\n")


if __name__ == "__main__":
    main()
