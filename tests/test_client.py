"""Tests for the projector protocol client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.nec_cinema.client import NecNakError, NecProjector
from custom_components.nec_cinema.protocol import HEADER_LENGTH, Response, parse_frame


def _response(id1: int, id2: int, data: bytes) -> Response:
    """Build a parsed response frame as the projector would send it."""
    body = bytes((id1, id2, 0x00, 0xC0, len(data))) + data
    frame = body + bytes((sum(body) & 0xFF,))
    return parse_frame(frame[:HEADER_LENGTH], frame[HEADER_LENGTH:])


def _projector(response: Response) -> tuple[NecProjector, AsyncMock]:
    """Return a projector whose client answers every request with ``response``."""
    client = MagicMock()
    client.request = AsyncMock(return_value=response)
    return NecProjector(client), client.request


async def test_lamp_mode_request() -> None:
    """LAMP MODE REQUEST goes out as 03H B0H and reports the current mode."""
    projector, request = _projector(_response(0x23, 0xB0, bytes((0xD8, 0x01))))
    assert await projector.lamp_mode() == 0x01
    request.assert_awaited_once_with(0x03, 0xB0, bytes((0xD8,)))


async def test_lamp_mode_set_uses_setting_command() -> None:
    """LAMP MODE SET goes out as 03H B1H.

    The protocol document prints 03H B0H, which is the request: a head sent
    that only reports its current mode and changes nothing.
    """
    projector, request = _projector(_response(0x23, 0xB1, bytes((0xD8, 0x00))))
    await projector.set_lamp_mode(0x02)
    request.assert_awaited_once_with(0x03, 0xB1, bytes((0xD8, 0x02)))


@pytest.mark.parametrize(
    ("result", "message"),
    [(0x01, "reported an error"), (0x02, "cannot change the lamp mode right now")],
)
async def test_lamp_mode_set_refused(result: int, message: str) -> None:
    """A result other than success is raised as a refusal."""
    projector, _request = _projector(_response(0x23, 0xB1, bytes((0xD8, result))))
    with pytest.raises(NecNakError, match=message):
        await projector.set_lamp_mode(0x00)
