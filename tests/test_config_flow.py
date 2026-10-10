"""Tests for the Sharp NEC cinema projector config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nec_cinema.client import NecConnectionError, NecError, NecNakError
from custom_components.nec_cinema.const import CONF_MACROS, CONF_PROJECTOR_ID, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ENTRY_DATA, HOST, PORT, SERIAL, FakeProjector

pytestmark = pytest.mark.usefixtures("mock_setup_entry")

USER_INPUT = dict(ENTRY_DATA)


async def _start(hass: HomeAssistant) -> dict:
    """Open the user step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    return result


async def test_user_flow(hass: HomeAssistant, projector: FakeProjector) -> None:
    """A manual setup creates an entry named after the model, keyed by serial number."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NC1200C"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == SERIAL


async def test_user_flow_own_name(hass: HomeAssistant, projector: FakeProjector) -> None:
    """A name typed by the user wins over the model name."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_NAME: "Screen 1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Screen 1"


async def test_user_flow_unknown_type(hass: HomeAssistant, projector: FakeProjector) -> None:
    """Without a projector type the name the head reports is used."""
    projector.projector_info = AsyncMock(side_effect=NecError("short setting response"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NC-Series"


async def test_user_flow_without_serial(hass: HomeAssistant, projector: FakeProjector) -> None:
    """A head that does not report a serial number is keyed by its address."""
    projector.serial_number = AsyncMock(side_effect=NecNakError("refused", (0x00, 0x01)))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == f"{HOST}:{PORT}"


@pytest.mark.parametrize(
    ("method", "side_effect", "error"),
    [
        ("model_name", NecConnectionError("no answer"), "cannot_connect"),
        ("model_name", NecNakError("refused", (0x00, 0x00)), "refused"),
        ("model_name", RuntimeError("boom"), "unknown"),
        ("serial_number", NecConnectionError("connection closed"), "cannot_connect"),
        ("projector_info", NecConnectionError("connection closed"), "cannot_connect"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    projector: FakeProjector,
    method: str,
    side_effect: Exception,
    error: str,
) -> None:
    """Errors are shown on the form and the flow recovers afterwards."""
    original = getattr(projector, method)
    setattr(projector, method, AsyncMock(side_effect=side_effect))

    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    setattr(projector, method, original)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured_serial(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """The same projector at another address is not added twice."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, CONF_HOST: "192.0.2.99"}
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_already_configured_host(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """An address that is already set up is refused before contacting it."""
    mock_config_entry.add_to_hass(hass)
    projector.model_name = AsyncMock(side_effect=NecConnectionError("no answer"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    projector.model_name.assert_not_awaited()


async def test_options_flow(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> None:
    """The polling interval and macro names are stored as options."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, CONF_MACROS: "1: Flat, 2: Scope"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {"scan_interval": 30, CONF_MACROS: "1: Flat, 2: Scope"}


async def test_projector_id_is_kept(hass: HomeAssistant, projector: FakeProjector) -> None:
    """A non-zero projector ID ends up in the entry."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_PROJECTOR_ID: 3}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PROJECTOR_ID] == 3
