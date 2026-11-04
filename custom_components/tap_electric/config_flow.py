"""Config flow for Tap Electric (refresh-token based)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TapApiError, TapAuthError, TapElectricClient
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class TapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Tap Electric config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = TapElectricClient(
                session, refresh_token=user_input[CONF_REFRESH_TOKEN].strip()
            )
            try:
                await client.async_validate()
            except TapAuthError:
                errors["base"] = "invalid_token"
            except TapApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Tap Electric setup")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    client.profile_id or "tap_electric_account"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=client.account_label or "Tap Electric",
                    data={CONF_REFRESH_TOKEN: client.refresh_token},
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        schema = vol.Schema({vol.Required(CONF_REFRESH_TOKEN): str})
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TapOptionsFlow:
        return TapOptionsFlow()


class TapOptionsFlow(config_entries.OptionsFlow):
    """Allow changing the poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=15, max=3600)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
