"""Config flow for Tap Electric (refresh-token based, with reauth)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TapApiError, TapAuthError, TapElectricClient
from .const import (
    CONF_IDLE_SCAN_INTERVAL,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_TARGETS,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    DEFAULT_IDLE_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_REFRESH_TOKEN): str})


async def _validate_token(hass, token: str) -> TapElectricClient:
    client = TapElectricClient(async_get_clientsession(hass), refresh_token=token.strip())
    await client.async_validate()
    return client


class TapConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Tap Electric config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                client = await _validate_token(self.hass, user_input[CONF_REFRESH_TOKEN])
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
        return self.async_show_form(
            step_id="user", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if user_input is not None:
            try:
                client = await _validate_token(self.hass, user_input[CONF_REFRESH_TOKEN])
            except TapAuthError:
                errors["base"] = "invalid_token"
            except TapApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Tap Electric reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={**reauth_entry.data, CONF_REFRESH_TOKEN: client.refresh_token},
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_TOKEN_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "TapOptionsFlow":
        return TapOptionsFlow()


class TapOptionsFlow(config_entries.OptionsFlow):
    """Poll intervals + Android charging notifications."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        notify_services = sorted(
            self.hass.services.async_services().get("notify", {}).keys()
        )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=15, max=3600)),
                vol.Optional(
                    CONF_IDLE_SCAN_INTERVAL,
                    default=opts.get(CONF_IDLE_SCAN_INTERVAL, DEFAULT_IDLE_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=60, max=3600)),
                vol.Optional(
                    CONF_NOTIFY_ENABLED,
                    default=opts.get(CONF_NOTIFY_ENABLED, False),
                ): bool,
                vol.Optional(
                    CONF_NOTIFY_TARGETS,
                    default=opts.get(CONF_NOTIFY_TARGETS, []),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=notify_services,
                        multiple=True,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
