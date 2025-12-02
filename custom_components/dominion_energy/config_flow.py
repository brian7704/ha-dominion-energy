"""Config flow for Dominion Energy integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from dompower import (
    DompowerClient,
    InvalidAuthError,
    CannotConnectError,
    TokenExpiredError,
    ApiError,
    LOGIN_URL,
    AccountInfo,
    MeterDevice,
)
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_NUMBER,
    CONF_COST_MODE,
    CONF_FIXED_RATE,
    CONF_METER_NUMBER,
    CONF_OFF_PEAK_RATE,
    CONF_PEAK_END_HOUR,
    CONF_PEAK_RATE,
    CONF_PEAK_START_HOUR,
    CONF_REFRESH_TOKEN,
    CONF_SERVICE_ADDRESS,
    COST_MODE_API,
    COST_MODE_FIXED,
    COST_MODE_TOU,
    DEFAULT_FIXED_RATE,
    DEFAULT_OFF_PEAK_RATE,
    DEFAULT_PEAK_END_HOUR,
    DEFAULT_PEAK_RATE,
    DEFAULT_PEAK_START_HOUR,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# Initial step only requires tokens - account/meter discovered automatically
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_REFRESH_TOKEN): str,
    }
)


async def _validate_tokens(
    hass, access_token: str, refresh_token: str
) -> bool:
    """Validate that the tokens work by attempting a refresh."""
    session = async_get_clientsession(hass)
    client = DompowerClient(
        session,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    await client.async_refresh_tokens()
    return True


class DominionEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dominion Energy."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._account_meter_options: dict[str, tuple[AccountInfo, MeterDevice]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DominionEnergyOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - collect and validate tokens."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_tokens(
                    self.hass,
                    user_input[CONF_ACCESS_TOKEN],
                    user_input[CONF_REFRESH_TOKEN],
                )
                # Store tokens for later steps
                self._access_token = user_input[CONF_ACCESS_TOKEN]
                self._refresh_token = user_input[CONF_REFRESH_TOKEN]

                # Proceed to account discovery
                return await self.async_step_discover_accounts()

            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except TokenExpiredError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"login_url": LOGIN_URL},
        )

    async def async_step_discover_accounts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Discover accounts and meters from the API."""
        errors: dict[str, str] = {}

        try:
            session = async_get_clientsession(self.hass)
            client = DompowerClient(
                session,
                access_token=self._access_token,
                refresh_token=self._refresh_token,
            )

            # Fetch customer info with all accounts
            customer_info = await client.async_get_customer_info()

            # Build selection options: "account_number|meter_id" -> (AccountInfo, MeterDevice)
            self._account_meter_options = {}
            for account in customer_info.active_accounts:
                for meter in account.meters:
                    if meter.is_active and meter.has_ami:
                        key = f"{account.account_number}|{meter.device_id}"
                        self._account_meter_options[key] = (account, meter)

            if not self._account_meter_options:
                errors["base"] = "no_meters_found"
                return self.async_show_form(
                    step_id="user",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=errors,
                    description_placeholders={"login_url": LOGIN_URL},
                )

            # Auto-select if only one option
            if len(self._account_meter_options) == 1:
                key = next(iter(self._account_meter_options))
                return await self._create_entry_from_selection(key)

            # Multiple options - show selection UI
            return await self.async_step_select_meter()

        except (InvalidAuthError, TokenExpiredError):
            errors["base"] = "invalid_auth"
        except CannotConnectError:
            errors["base"] = "cannot_connect"
        except ApiError as err:
            _LOGGER.error("API error discovering accounts: %s", err)
            errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception during account discovery")
            errors["base"] = "unknown"

        # On error, return to user step
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"login_url": LOGIN_URL},
        )

    async def async_step_select_meter(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle meter selection when multiple accounts/meters exist."""
        if user_input is not None:
            selected_key = user_input["meter_selection"]
            return await self._create_entry_from_selection(selected_key)

        # Build display options with service address context
        options: dict[str, str] = {}
        for key, (account, meter) in self._account_meter_options.items():
            # Format: "123 Main St - Account: 123456789 - Meter: ...117800"
            address = str(account.service_address)
            meter_suffix = meter.device_id[-8:] if len(meter.device_id) > 8 else meter.device_id
            label = f"{address} - Meter: ...{meter_suffix}"
            options[key] = label

        return self.async_show_form(
            step_id="select_meter",
            data_schema=vol.Schema(
                {
                    vol.Required("meter_selection"): vol.In(options),
                }
            ),
        )

    async def _create_entry_from_selection(
        self, selection_key: str
    ) -> ConfigFlowResult:
        """Create config entry from the selected account/meter."""
        account, meter = self._account_meter_options[selection_key]

        # Check for duplicate
        await self.async_set_unique_id(account.account_number)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Dominion Energy ({account.account_number})",
            data={
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_REFRESH_TOKEN: self._refresh_token,
                CONF_ACCOUNT_NUMBER: account.account_number,
                CONF_METER_NUMBER: meter.device_id,
                CONF_SERVICE_ADDRESS: str(account.service_address),
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth when tokens expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await _validate_tokens(
                    self.hass,
                    user_input[CONF_ACCESS_TOKEN],
                    user_input[CONF_REFRESH_TOKEN],
                )
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except TokenExpiredError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                new_data = {
                    **reauth_entry.data,
                    CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                    CONF_REFRESH_TOKEN: user_input[CONF_REFRESH_TOKEN],
                }
                return self.async_update_reload_and_abort(
                    reauth_entry, data=new_data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "name": reauth_entry.title,
                "login_url": LOGIN_URL,
            },
        )


class DominionEnergyOptionsFlow(OptionsFlow):
    """Handle options flow for Dominion Energy."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_COST_MODE,
                        default=current_options.get(CONF_COST_MODE, COST_MODE_API),
                    ): vol.In(
                        {
                            COST_MODE_API: "API Estimate (from bill)",
                            COST_MODE_FIXED: "Fixed Rate",
                            COST_MODE_TOU: "Time-of-Use",
                        }
                    ),
                    vol.Optional(
                        CONF_FIXED_RATE,
                        default=current_options.get(CONF_FIXED_RATE, DEFAULT_FIXED_RATE),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_PEAK_RATE,
                        default=current_options.get(CONF_PEAK_RATE, DEFAULT_PEAK_RATE),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_OFF_PEAK_RATE,
                        default=current_options.get(CONF_OFF_PEAK_RATE, DEFAULT_OFF_PEAK_RATE),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_PEAK_START_HOUR,
                        default=current_options.get(CONF_PEAK_START_HOUR, DEFAULT_PEAK_START_HOUR),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                    vol.Optional(
                        CONF_PEAK_END_HOUR,
                        default=current_options.get(CONF_PEAK_END_HOUR, DEFAULT_PEAK_END_HOUR),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=23)),
                }
            ),
        )
