from typing import Any
import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN


class AguacatecConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Paso inicial cuando el usuario añade la integración desde la UI."""
        errors = {}

        if user_input is not None:
            app_name = user_input["user_telegram"]
            return self.async_create_entry(title=app_name, data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required("id_aguacatec"): cv.string,
                vol.Required("user_telegram"): cv.string,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ):
        """Paso de reconfiguración para cambiar el Google Sheet ID."""
        errors = {}

        if user_input is not None:
            if not user_input.get("id_aguacatec", "").strip():
                errors["id_aguacatec"] = "invalid_id"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data_updates={"id_aguacatec": user_input["id_aguacatec"].strip()},
                )

        entry = self._get_reconfigure_entry()
        current_id = entry.data.get("id_aguacatec", "")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required("id_aguacatec", default=current_id): cv.string,
            }),
            errors=errors,
        )
