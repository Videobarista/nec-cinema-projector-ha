"""Config flow for the Sharp NEC cinema projector."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .client import NecClient, NecError, NecNakError, NecProjector
from .const import (
    CONF_MACROS,
    CONF_PROJECTOR_ID,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

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


async def _probe(host: str, port: int, projector_id: int) -> tuple[str, str | None]:
    """Return the model name and serial number of the projector."""
    client = NecClient(host, port, projector_id)
    projector = NecProjector(client)
    try:
        model = await projector.model_name()
        try:
            serial = await projector.serial_number()
        except (NecError, NecNakError):
            serial = None
        return model, serial
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
            try:
                model, serial = await _probe(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_PROJECTOR_ID],
                )
            except NecNakError:
                errors["base"] = "refused"
            except NecError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    serial or f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                title = user_input[CONF_NAME]
                if title == DEFAULT_NAME and model:
                    title = model
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

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
                vol.Optional(
                    CONF_MACROS, default=options.get(CONF_MACROS, "")
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
