"""Config flow for the Sharp NEC cinema projector."""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .client import NecClient, NecConnectionError, NecError, NecNakError, NecProjector
from .const import (
    CONF_MACROS,
    CONF_PROJECTOR_ID,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import resolve_model

_LOGGER = logging.getLogger(__name__)

# Longest text accepted for the hand written preset names in the options.
MAX_MACROS_LENGTH = 2000

# A host name: labels of letters, digits, hyphens and underscores, separated
# by dots. Anything else, such as a scheme, a path or a port, is not one.
_HOSTNAME = re.compile(
    r"(?!-)[A-Za-z0-9_-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9_-]{1,63}(?<!-))*\.?"
)


def clean_host(value: str) -> str | None:
    """Return the address to connect to, or None when the text is not one.

    The field is free text, so it is checked before anything is sent to it:
    surrounding spaces and the brackets of an IPv6 address are dropped, and a
    URL, a path or an address with a port is turned down with a clear message
    instead of a connection error.
    """
    host = value.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not _HOSTNAME.fullmatch(host):
            return None
    return host


USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Optional(CONF_PROJECTOR_ID, default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
    }
)


async def _probe(host: str, port: int, projector_id: int) -> tuple[str | None, str | None]:
    """Return the model name and serial number of the projector."""
    client = NecClient(host, port, projector_id)
    projector = NecProjector(client)
    try:
        reported = await projector.model_name()
        try:
            serial = await projector.serial_number()
        except NecConnectionError:
            raise
        except NecError:
            serial = None
        try:
            projector_type, subtype = await projector.projector_info()
        except NecConnectionError:
            raise
        except NecError:
            projector_type, subtype = None, None
        return resolve_model(projector_type, subtype, reported), serial
    finally:
        await client.close()


class NecCinemaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the user flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the projector."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = clean_host(user_input[CONF_HOST])
            if host is None:
                errors[CONF_HOST] = "invalid_host"
            else:
                user_input = {**user_input, CONF_HOST: host}
                self._async_abort_entries_match({CONF_HOST: host})
                try:
                    model, serial = await _probe(
                        host, user_input[CONF_PORT], user_input[CONF_PROJECTOR_ID]
                    )
                except NecNakError:
                    errors["base"] = "refused"
                except NecError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("unexpected error while contacting the projector")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(serial or f"{host}:{user_input[CONF_PORT]}")
                    self._abort_if_unique_id_configured()
                    title = user_input[CONF_NAME]
                    if title == DEFAULT_NAME and model:
                        title = model
                    return self.async_create_entry(title=title, data=user_input)

        # Keep what was typed when the form comes back with an error.
        schema = self.add_suggested_values_to_schema(USER_SCHEMA, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> NecCinemaOptionsFlow:
        """Return the options flow."""
        return NecCinemaOptionsFlow()


class NecCinemaOptionsFlow(OptionsFlow):
    """Handle the options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling interval and macro names."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    "scan_interval",
                    default=options.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=300)),
                vol.Optional(CONF_MACROS, default=options.get(CONF_MACROS, "")): vol.All(
                    str, vol.Length(max=MAX_MACROS_LENGTH)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
