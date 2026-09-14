"""A fake NEC cinema projector, speaking the real frame format over TCP.

Used by the client tests. It keeps a small amount of state so commands can be
verified by their effect, records every frame it receives, and can be told to
misbehave (drop the connection, stay silent, send an unrelated frame first) so
the error handling can be exercised.
"""

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _loader import protocol


class Nak(Exception):
    """Raised by a handler to make the projector refuse a command."""

    def __init__(self, kind: int, detail: int) -> None:
        super().__init__(f"{kind:02X} {detail:02X}")
        self.code = (kind, detail)


def pad(data: bytes, length: int) -> bytes:
    """Pad a data portion out to the length the real projector returns."""
    return data + bytes(length - len(data))


class FakeProjector:
    """Minimal projector emulation for tests."""

    def __init__(self) -> None:
        """Start with a powered on NC2000C showing the IMB."""
        self.power = True
        self.douser_closed = False
        self.picture_mute = False
        self.port = (0x04, 0x0C)
        self.received: list[bytes] = []
        self.modern_lamp_supported = False
        self.parts_supported = False
        self.silent = False
        self.drop_connection = False
        self.send_stale_frame = False
        self._server: asyncio.Server | None = None

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> int:
        """Listen on an ephemeral port and return it."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Shut the server down."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # -------------------------------------------------------------- helpers

    def commands(self) -> list[tuple[int, int]]:
        """Return the (id1, id2) pairs received so far."""
        return [(frame[0], frame[1]) for frame in self.received]

    def last_payload(self) -> bytes:
        """Return the data portion of the last frame received."""
        frame = self.received[-1]
        return frame[5 : 5 + protocol.data_length(frame)]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                header = await reader.readexactly(5)
                tail = await reader.readexactly(protocol.data_length(header) + 1)
                self.received.append(header + tail)

                if self.drop_connection:
                    self.drop_connection = False
                    writer.close()
                    return
                if self.silent:
                    continue

                id1, id2 = header[0], header[1]
                data = tail[:-1]
                if self.send_stale_frame:
                    self.send_stale_frame = False
                    writer.write(protocol.build_frame(0x20, 0xFF, b"\x00"))

                try:
                    payload = self._dispatch(id1, id2, data)
                except Nak as err:
                    writer.write(
                        protocol.build_frame(id1 | 0xA0, id2, bytes(err.code), 0x01, 0x0C)
                    )
                else:
                    writer.write(
                        protocol.build_frame(id1 | 0x20, id2, payload, 0x01, 0x0C)
                    )
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            if not writer.is_closing():
                writer.close()

    # ------------------------------------------------------------ dispatch

    def _dispatch(self, id1: int, id2: int, data: bytes) -> bytes:
        sub = data[0] if data else None

        if (id1, id2) == (0x02, 0x00):
            self.power = True
            return b""
        if (id1, id2) == (0x02, 0x01):
            self.power = False
            return b""
        if (id1, id2) == (0x02, 0x16):
            self.douser_closed = True
            return b""
        if (id1, id2) == (0x02, 0x17):
            self.douser_closed = False
            return b""
        if (id1, id2) == (0x02, 0x10):
            if self.douser_closed:
                raise Nak(0x02, 0x0E)
            self.picture_mute = True
            return b""
        if (id1, id2) == (0x02, 0x11):
            self.picture_mute = False
            return b""
        if (id1, id2) == (0x02, 0x03):
            if data[0] == 0x05 and data[1] not in (0x1A, 0x1B, 0x38, 0x3B):
                return bytes([0xFF])
            return bytes([0x00])
        if (id1, id2) == (0x02, 0x18):
            return b""

        if (id1, id2) == (0x00, 0x85):
            return self._status(sub)

        if (id1, id2) == (0x00, 0x86):
            return pad(bytes([0x08]) + b"02A1234EB\x00", 16)
        if (id1, id2) == (0x00, 0xC1):
            ports = bytes([0x1A, 0x1B, 0x38, 0x3B])
            return bytes([len(ports)]) + ports
        if (id1, id2) == (0x02, 0xBC):
            return bytes([0x00, 0x02, 0x2A, 0x00, 0x2B, 0x00])
        if (id1, id2) == (0x02, 0xBD):
            code = protocol.u16le(data, 1)
            text = {0x2A: b"Douser error", 0x2B: b"Fan 3 stopped"}[code]
            return bytes([0x00]) + code.to_bytes(2, "little") + bytes([len(text)]) + text + b"\x00"
        if (id1, id2) == (0x03, 0x2F) and sub == 0x1E:
            if not self.modern_lamp_supported:
                raise Nak(0x00, 0x01)
            return bytes([0x1E]) + (1234).to_bytes(2, "little")
        if (id1, id2) == (0x03, 0x2F) and sub == 0x1C:
            return bytes([0x1C, 0x00, 0x00, 0x00]) + (875).to_bytes(2, "little")
        if (id1, id2) == (0x03, 0x94):
            return (7200).to_bytes(4, "little") + b"\x00"
        if (id1, id2) == (0x00, 0xD6):
            if not self.parts_supported:
                raise Nak(0x00, 0x01)
            if sub == 0x00:
                return bytes([0x00, 0x03, 0x02])
            name = b"DMD"
            return pad(bytes([0x01, 0x03, data[2]]), 16) + bytes([len(name)]) + name
        if (id1, id2) == (0x00, 0xD3):
            return bytes([0x20, 0x03, data[2]]) + (312).to_bytes(2, "little", signed=True)

        raise Nak(0x00, 0x00)

    def _status(self, sub: int | None) -> bytes:
        if sub == 0x00:  # SETTING REQUEST, projector type NC2000C
            return pad(bytes([0x0C, 0x08, 0x0A]), 32)
        if sub == 0x01:  # RUNNING STATUS
            data = bytearray(16)
            data[2] = 0x01 if self.power else 0x00
            data[5] = 0x04 if self.power else 0x00
            data[9] = 0x01 if self.power else 0x00
            data[12:14] = (300).to_bytes(2, "little")
            return bytes(data)
        if sub == 0x02:  # INPUT STATUS
            data = bytearray(16)
            data[2], data[3] = self.port
            return bytes(data)
        if sub == 0x03:  # MUTE STATUS
            data = bytearray(16)
            if self.douser_closed:
                data[0] = 0x81
            elif self.picture_mute:
                data[0] = 0x01
            return bytes(data)
        if sub == 0x04:  # MODEL NAME
            return pad(b"NC2000C\x00", 32)
        if sub == 0xE4:  # TEMPERATURE STATUS 3
            data = bytearray([0xE4]) + bytearray(32)
            data[1:3] = (245).to_bytes(2, "little", signed=True)
            data[3:5] = (0x7FFF).to_bytes(2, "little")
            data[5:7] = (-55).to_bytes(2, "little", signed=True)
            return bytes(data)
        if sub == 0xE6:  # CURRENT TITLE
            name = b"SCOPE 2D"
            return bytes([0xE6, 5, 1, len(name)]) + name + b"\x00"
        raise Nak(0x00, 0x00)
