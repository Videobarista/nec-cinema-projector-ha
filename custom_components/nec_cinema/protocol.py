"""Frame handling for the NEC cinema projector control protocol.

Reference: "Control Commands for Cinema Projector Series 2", rev. 15.0
(Sharp NEC Display Solutions, document LDC0001), chapter 4 "Communication Frame".

Frame layout::

    byte 0  ID1
    byte 1  ID2
    byte 2  Projector ID
    byte 3  model code (upper 4 bits) | data length (upper 4 bits)
    byte 4  data length (lower 8 bits)
    byte 5+ data portion (0 .. 4095 bytes)
    last    checksum (lower 8 bits of the sum of all preceding bytes)

A response repeats ID2 and sets bit 5 (0x20) of ID1. Bit 7 (0x80) marks a NAK,
in which case the data portion holds a two byte error code.
"""

from __future__ import annotations

from dataclasses import dataclass

HEADER_LENGTH = 5

MODEL_CODE_BROADCAST = 0x00
MODEL_CODE_NC = 0x0C
MODEL_CODE_MM = 0x0B

ACK_BIT = 0x20
NAK_BIT = 0x80

# Data portion of a NAK response, table "Data portion of response" (chapter 4.2).
NAK_ERRORS: dict[tuple[int, int], str] = {
    (0x00, 0x00): "unknown command",
    (0x00, 0x01): "this model does not support the function",
    (0x01, 0x00): "invalid value specified",
    (0x01, 0x01): "terminal unavailable or not selectable",
    (0x01, 0x02): "selected language is not available",
    (0x01, 0x03): "terminal is not installed",
    (0x02, 0x00): "memory reservation error",
    (0x02, 0x01): "GPIO control enabled",
    (0x02, 0x02): "operating memory",
    (0x02, 0x03): "setting not possible (metadata may be enabled)",
    (0x02, 0x04): "forced on-screen mute mode",
    (0x02, 0x06): "displaying a signal other than PC Viewer",
    (0x02, 0x07): "no signal",
    (0x02, 0x08): "displaying a test pattern or file screen",
    (0x02, 0x09): "no PC card inserted",
    (0x02, 0x0A): "memory operation failed",
    (0x02, 0x0C): "displaying the entry list",
    (0x02, 0x0D): "power off inhibited",
    (0x02, 0x0E): "execution error",
    (0x02, 0x0F): "no operation authority",
    (0x03, 0x00): "wrong gain number",
    (0x03, 0x01): "selected gain is not available",
    (0x03, 0x02): "adjustment failed",
    (0x06, 0x00): "media server not linked",
    (0x06, 0x01): "media server not connected",
    (0x06, 0x02): "media server send error",
    (0x06, 0x03): "media server receive timeout",
    (0x06, 0x04): "media server command invalid while projector is in standby",
    (0x07, 0x00): "projector is not ready",
}


def checksum(payload: bytes) -> int:
    """Return the lower 8 bits of the sum of all bytes."""
    return sum(payload) & 0xFF


def build_frame(
    id1: int,
    id2: int,
    data: bytes = b"",
    projector_id: int = 0x00,
    model_code: int = MODEL_CODE_BROADCAST,
) -> bytes:
    """Build a command frame."""
    length = len(data)
    if length > 0x0FFF:
        raise ValueError("data portion too long")
    header = bytes(
        (
            id1 & 0xFF,
            id2 & 0xFF,
            projector_id & 0xFF,
            ((model_code & 0x0F) << 4) | ((length >> 8) & 0x0F),
            length & 0xFF,
        )
    )
    body = header + data
    return body + bytes((checksum(body),))


def data_length(header: bytes) -> int:
    """Return the announced data length from a five byte header."""
    return ((header[3] & 0x0F) << 8) | header[4]


@dataclass(slots=True)
class Response:
    """A parsed response frame."""

    id1: int
    id2: int
    projector_id: int
    model_code: int
    data: bytes

    @property
    def is_nak(self) -> bool:
        """Whether the projector refused the command."""
        return bool(self.id1 & NAK_BIT)

    @property
    def error_code(self) -> tuple[int, int] | None:
        """Return the NAK error code, if any."""
        if self.is_nak and len(self.data) >= 2:
            return (self.data[0], self.data[1])
        return None

    @property
    def error_text(self) -> str:
        """Human readable reason for a refused command."""
        code = self.error_code
        if code is None:
            return "unknown error"
        return NAK_ERRORS.get(code, f"error {code[0]:02X}H {code[1]:02X}H")


def parse_frame(header: bytes, tail: bytes) -> Response:
    """Parse a response from its header and the remaining bytes.

    ``tail`` must hold the data portion plus the trailing checksum byte.
    """
    if len(header) != HEADER_LENGTH:
        raise ValueError("bad header length")
    length = data_length(header)
    if len(tail) != length + 1:
        raise ValueError("bad frame length")
    body = header + tail[:-1]
    if checksum(body) != tail[-1]:
        raise ValueError("checksum mismatch")
    return Response(
        id1=header[0],
        id2=header[1],
        projector_id=header[2],
        model_code=(header[3] >> 4) & 0x0F,
        data=tail[:-1],
    )


def u16le(data: bytes, offset: int) -> int:
    """Read an unsigned little endian 16 bit value."""
    return int.from_bytes(data[offset : offset + 2], "little", signed=False)


def s16le(data: bytes, offset: int) -> int:
    """Read a signed little endian 16 bit value."""
    return int.from_bytes(data[offset : offset + 2], "little", signed=True)


def u32le(data: bytes, offset: int) -> int:
    """Read an unsigned little endian 32 bit value."""
    return int.from_bytes(data[offset : offset + 4], "little", signed=False)


def cstring(data: bytes, offset: int = 0, length: int | None = None) -> str:
    """Decode a NUL terminated ASCII string."""
    chunk = data[offset:] if length is None else data[offset : offset + length]
    return chunk.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
