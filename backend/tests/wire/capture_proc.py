"""
The receiving end of the wire, in a process of its own.

Usage: python capture_proc.py <udp_port>

Binds 127.0.0.1:<port>, stamps every datagram with its arrival time and writes
``<double t><uint16 length><datagram>`` records to stdout. It does nothing else, and
that is the point: stamped inside the harness process, a packet's arrival time also
measures how long the harness held the interpreter lock for audio streaming and
analysis, and those stalls read as frame gaps the backend never produced.

A zero-length record is written when the port has been quiet for a second, so the
process notices a closed pipe and exits when its parent has gone. Stdlib only.
"""
import socket
import struct
import sys
import time


def main(port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    sock.bind(("127.0.0.1", port))
    sock.settimeout(1.0)
    out = sys.stdout.buffer
    out.write(b"READY\n")
    out.flush()
    while True:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            data = b""
        except OSError:
            # Windows raises WSAECONNRESET on a UDP socket after an ICMP
            # port-unreachable; nothing to do with us.
            continue
        t = time.perf_counter()
        try:
            out.write(struct.pack("<dH", t, len(data)) + data)
            out.flush()
        except (BrokenPipeError, OSError, ValueError):
            return


if __name__ == "__main__":
    main(int(sys.argv[1]))
