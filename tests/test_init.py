"""Tests for setting up and unloading the Sharp NEC cinema projector integration."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nec_cinema.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import SERIAL, FakeDualLampProjector, FakeProjector


def _entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Look an entity up by its unique ID, independent of its name."""
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{key}")
    assert entity_id is not None, f"{platform} {key} was not created"
    return entity_id


def _state(hass: HomeAssistant, platform: str, key: str) -> str:
    """Return the state of an entity looked up by its unique ID."""
    state = hass.states.get(_entity_id(hass, platform, key))
    assert state is not None
    return state.state


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up the entry."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """The entry loads, creates the device and its entities, and unloads cleanly."""
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SERIAL), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.model == "NC1200C"
    assert device.serial_number == SERIAL

    assert _state(hass, "media_player", "projector") == STATE_ON
    assert _state(hass, "sensor", "process_status") == "running_light_on"
    assert _state(hass, "binary_sensor", "connectivity") == STATE_ON
    assert float(_state(hass, "sensor", "lamp_watt")) == 1700.0

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_never_reached_waits(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """A projector that has never answered keeps the entry waiting."""
    projector.online = False
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_offline_setup_from_memory(
    hass: HomeAssistant,
    projector: FakeProjector,
    mock_config_entry: MockConfigEntry,
    stored_device: dict[str, Any],
) -> None:
    """A projector that answered before is set up while off and shown as off."""
    projector.online = False
    await _setup(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, SERIAL), mock_config_entry.entry_id
    )
    assert device is not None
    assert device.model == "NC1200C"

    assert _state(hass, "media_player", "projector") == STATE_OFF
    assert _state(hass, "binary_sensor", "connectivity") == STATE_OFF
    assert _state(hass, "sensor", "process_status") == STATE_UNAVAILABLE
    # The entities match what the projector reported before.
    _entity_id(hass, "sensor", "lamp_watt")
    _entity_id(hass, "sensor", "temperature_0")

    projector.online = True
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert not mock_config_entry.runtime_data.set_up_offline
    assert _state(hass, "media_player", "projector") == STATE_ON
    assert _state(hass, "binary_sensor", "connectivity") == STATE_ON
    assert _state(hass, "sensor", "process_status") == "running_light_on"


async def test_goes_offline_while_running(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """Losing the projector shows it as off instead of failing."""
    await _setup(hass, mock_config_entry)
    projector.online = False
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "media_player", "projector") == STATE_OFF
    assert _state(hass, "binary_sensor", "connectivity") == STATE_OFF
    assert _state(hass, "sensor", "process_status") == STATE_UNAVAILABLE


async def test_actions(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """The actions are registered once and reach the projector."""
    await _setup(hass, mock_config_entry)
    media_player = _entity_id(hass, "media_player", "projector")

    for action in ("select_title", "select_macro", "lens_control", "picture_mute"):
        assert hass.services.has_service(DOMAIN, action)

    await hass.services.async_call(
        DOMAIN, "select_macro", {"entity_id": media_player, "macro": 3}, blocking=True
    )
    projector.select_macro.assert_awaited_once_with(3)

    await hass.services.async_call(
        DOMAIN, "select_title", {"entity_id": media_player, "title": 12}, blocking=True
    )
    projector.select_title.assert_awaited_once_with(12)

    await hass.services.async_call(
        DOMAIN,
        "lens_control",
        {"entity_id": media_player, "axis": "zoom", "direction": "minus", "duration": 0.5},
        blocking=True,
    )
    projector.lens_control.assert_awaited_once_with("zoom", 0xFE)

    await hass.services.async_call(
        DOMAIN, "picture_mute", {"entity_id": media_player, "enabled": True}, blocking=True
    )
    projector.picture_mute_on.assert_awaited_once()


async def test_douser_cover(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """Closing the douser cover sends the douser command."""
    await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        "cover",
        "close_cover",
        {"entity_id": _entity_id(hass, "cover", "douser")},
        blocking=True,
    )
    projector.douser_close.assert_awaited_once()


async def test_retired_entity_removed(
    hass: HomeAssistant, projector: FakeProjector, mock_config_entry: MockConfigEntry
) -> None:
    """The light control mode select of earlier versions is cleaned up."""
    mock_config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "select", DOMAIN, f"{SERIAL}_light_mode", config_entry=mock_config_entry
    )

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("select", DOMAIN, f"{SERIAL}_light_mode") is None


@pytest.mark.parametrize("light", [True, False])
async def test_light_source_switch(
    hass: HomeAssistant,
    projector: FakeProjector,
    mock_config_entry: MockConfigEntry,
    light: bool,
) -> None:
    """The Light source switch sets the light control mode."""
    await _setup(hass, mock_config_entry)
    await hass.services.async_call(
        "switch",
        "turn_on" if light else "turn_off",
        {"entity_id": _entity_id(hass, "switch", "light")},
        blocking=True,
    )
    assert projector.mode == (0x01 if light else 0x02)


async def test_lamp_mode_with_lamp_off(
    hass: HomeAssistant,
    dual_projector: FakeDualLampProjector,
    mock_config_entry: MockConfigEntry,
) -> None:
    """With the lamp off the lamp mode is sent to the projector."""
    dual_projector.status = 0x0C
    dual_projector.light = False
    await _setup(hass, mock_config_entry)
    lamp_mode = _entity_id(hass, "select", "lamp_mode")
    assert hass.states.get(lamp_mode).state == "dual"

    await hass.services.async_call(
        "select", "select_option", {"entity_id": lamp_mode, "option": "lamp2"}, blocking=True
    )
    dual_projector.set_lamp_mode.assert_awaited_once_with(0x02)


async def test_lamp_mode_with_lamp_lit(
    hass: HomeAssistant,
    dual_projector: FakeDualLampProjector,
    mock_config_entry: MockConfigEntry,
) -> None:
    """With a lamp lit the change is refused before asking the projector."""
    await _setup(hass, mock_config_entry)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": _entity_id(hass, "select", "lamp_mode"), "option": "lamp1"},
            blocking=True,
        )
    assert err.value.translation_key == "lamp_mode_lamp_on"
    dual_projector.set_lamp_mode.assert_not_awaited()
