"""Native UI configuration with reviewed semantic discovery and stable identities."""

from copy import deepcopy
from uuid import uuid4
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import DOMAIN, NAME
from .vehicle import FIELDS, discover


def entity(domain=None):
    return (
        selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
        if domain
        else selector.EntitySelector()
    )


def defaults():
    return {
        "vehicles": [],
        "chargers": [],
        "sites": [],
        "brain_enabled": True,
        "optimizer_enabled": True,
        "stale_seconds": 900,
        "snapshot_skew_seconds": 120,
        "command_budget": 100,
    }


class Editor:
    async def async_step_menu(self, user_input=None):
        self.editing = None
        self.editing_provider = False
        return self.async_show_menu(
            step_id="menu",
            menu_options=[
                "modules",
                "vehicle",
                "provider",
                "site",
                "charger",
                "edit",
                "remove",
                "finish",
            ],
        )

    def _is_editing(self, group, key):
        return getattr(self, "editing", None) == (group, key)

    def _save_item(self, group, data):
        editing = getattr(self, "editing", None)
        if editing and editing[0] == group:
            old = next(i for i in self.config[group] if i["id"] == editing[1])
            data["id"] = old["id"]
            if group == "vehicles":
                data["providers"] = old["providers"]
            self.config[group] = [data if i["id"] == old["id"] else i for i in self.config[group]]
        else:
            self.config[group].append(data)

    def _show_item(self, *, step_id, data_schema, errors=None):
        editing = getattr(self, "editing", None)
        if editing:
            group, key = editing
            item = next(i for i in self.config[group] if i["id"] == key)
            values = dict(item)
            if group == "sites":
                values.update(item.get("tariff", {}))
                values["price_basis"] = values.pop("mode", "all_in")
            schema = {}
            for marker, validator in data_schema.schema.items():
                name = str(marker)
                if name in values:
                    marker = type(marker)(name, default=values[name])
                schema[marker] = validator
            data_schema = vol.Schema(schema)
        return self.async_show_form(step_id=step_id, data_schema=data_schema, errors=errors or {})

    async def async_step_edit(self, user_input=None):
        choices = {
            f"{g}:{i['id']}": i.get("name", i["id"])
            for g in ("vehicles", "sites", "chargers")
            for i in self.config[g]
        }
        choices.update(
            {
                f"providers:{v['id']}:{p['id']}": v["name"] + " / " + p["id"]
                for v in self.config["vehicles"]
                for p in v["providers"]
            }
        )
        if user_input:
            parts = user_input["item"].split(":", 2)
            if parts[0] == "providers":
                vehicle = next(v for v in self.config["vehicles"] if v["id"] == parts[1])
                provider = next(p for p in vehicle["providers"] if p["id"] == parts[2])
                self.provider = {
                    **provider,
                    "vehicle": vehicle["id"],
                    "primary": vehicle["providers"][0]["id"] == provider["id"],
                }
                self.suggestions = dict(provider["fields"])
                self.editing_provider = True
                return await self.async_step_fields()
            self.editing = (parts[0], parts[1])
            return await {
                "vehicles": self.async_step_vehicle,
                "sites": self.async_step_site,
                "chargers": self.async_step_charger,
            }[parts[0]]()
        return self.async_show_form(
            step_id="edit", data_schema=vol.Schema({vol.Required("item"): vol.In(choices)})
        )

    async def async_step_modules(self, user_input=None):
        if user_input is not None:
            self.config.update(user_input)
            return await self.async_step_menu()
        return self._show_item(
            step_id="modules",
            data_schema=vol.Schema(
                {
                    vol.Required("brain_enabled", default=self.config["brain_enabled"]): bool,
                    vol.Required(
                        "optimizer_enabled", default=self.config["optimizer_enabled"]
                    ): bool,
                    vol.Required("stale_seconds", default=self.config["stale_seconds"]): vol.All(
                        vol.Coerce(int), vol.Range(min=30, max=86400)
                    ),
                    vol.Required(
                        "snapshot_skew_seconds",
                        default=self.config.get("snapshot_skew_seconds", 120),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=86400)),
                    vol.Required("command_budget", default=self.config["command_budget"]): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10000)
                    ),
                }
            ),
        )

    async def async_step_vehicle(self, user_input=None):
        if user_input:
            self._save_item("vehicles", {"id": uuid4().hex, "providers": [], **user_input})
            return await self.async_step_menu()
        return self._show_item(
            step_id="vehicle",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required("capacity_kwh", default=75): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=500)
                    ),
                    vol.Required("max_kw", default=11): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=350)
                    ),
                    vol.Required("efficiency", default=0.9): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=1)
                    ),
                }
            ),
        )

    async def async_step_provider(self, user_input=None):
        choices = {v["id"]: v["name"] for v in self.config["vehicles"]}
        if not choices:
            return self.async_abort(reason="no_vehicles")
        if user_input:
            self.provider = user_input
            self.suggestions = discover(self.hass, user_input["device"])
            return await self.async_step_fields()
        return self._show_item(
            step_id="provider",
            data_schema=vol.Schema(
                {
                    vol.Required("vehicle"): vol.In(choices),
                    vol.Required("device"): selector.DeviceSelector(),
                    vol.Required("id"): str,
                    vol.Required("primary", default=False): bool,
                }
            ),
        )

    async def async_step_fields(self, user_input=None):
        errors = {}
        if user_input:
            reg = er.async_get(self.hass)
            if any(
                (e := reg.async_get(eid)) is None or e.device_id != self.provider["device"]
                for eid in user_input.values()
            ):
                errors["base"] = "invalid_mapping"
            else:
                vehicle = next(
                    v for v in self.config["vehicles"] if v["id"] == self.provider["vehicle"]
                )
                if any(
                    p["device"] == self.provider["device"]
                    and not (
                        v["id"] == self.provider["vehicle"]
                        and p["id"] == self.provider["id"]
                        and getattr(self, "editing_provider", False)
                    )
                    for v in self.config["vehicles"]
                    for p in v["providers"]
                ):
                    errors["base"] = "duplicate_device"
                elif any(
                    p["id"] == self.provider["id"] for p in vehicle["providers"]
                ) and not getattr(self, "editing_provider", False):
                    errors["base"] = "invalid_mapping"
                else:
                    provider = {
                        "id": self.provider["id"],
                        "device": self.provider["device"],
                        "fields": dict(user_input),
                        "entity_refs": {
                            field: reg.async_get(eid).id for field, eid in user_input.items()
                        },
                    }
                    if getattr(self, "editing_provider", False):
                        vehicle["providers"] = [
                            p for p in vehicle["providers"] if p["id"] != self.provider["id"]
                        ]
                    vehicle["providers"].insert(
                        0 if self.provider["primary"] else len(vehicle["providers"]), provider
                    )
                    return await self.async_step_menu()
        return self._show_item(
            step_id="fields",
            data_schema=vol.Schema(
                {
                    (
                        vol.Optional(f, default=self.suggestions[f])
                        if f in self.suggestions
                        else vol.Optional(f)
                    ): entity()
                    for f in sorted(FIELDS)
                }
            ),
            errors=errors,
        )

    async def async_step_site(self, user_input=None):
        errors = {}
        if user_input:
            try:
                ZoneInfo(user_input["timezone"])
                if user_input["id"] in {
                    s["id"] for s in self.config["sites"] if not self._is_editing("sites", s["id"])
                } or user_input["zone_state"] in {
                    s["zone_state"]
                    for s in self.config["sites"]
                    if not self._is_editing("sites", s["id"])
                }:
                    raise ValueError("Duplicate site or zone")
                if bool(user_input.get("nordpool_entry")) == bool(user_input.get("price_entity")):
                    raise ValueError("Select exactly one price source")
                if user_input.get("nordpool_entry") and user_input["price_basis"] != "spot_ex_vat":
                    raise ValueError("Official prices are spot ex VAT")
                tariff = {
                    "mode": user_input["price_basis"],
                    **{k: user_input[k] for k in ("grid", "tax", "supplier", "vat")},
                }
                from .prices import all_in

                all_in([], tariff)
                self._save_item("sites", {**user_input, "tariff": tariff, "currency": "DKK"})
                return await self.async_step_menu()
            except ValueError, KeyError:
                errors["base"] = "invalid_mapping"
        return self._show_item(
            step_id="site",
            data_schema=vol.Schema(
                {
                    vol.Required("id"): vol.Match(r"^[a-z0-9_]+$"),
                    vol.Required("name"): str,
                    vol.Required("zone_state", default="home"): str,
                    vol.Required("timezone", default="Europe/Copenhagen"): str,
                    vol.Required("grid_kw", default=17.94): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=1000)
                    ),
                    vol.Optional("nordpool_entry"): selector.ConfigEntrySelector(
                        selector.ConfigEntrySelectorConfig(integration="nordpool")
                    ),
                    vol.Optional("price_entity"): entity("sensor"),
                    vol.Optional("grid_tariff_entity"): entity("sensor"),
                    vol.Optional("guest_power_entity"): entity("sensor"),
                    vol.Required("price_attribute", default="slots"): str,
                    vol.Required("price_multiplier", default=1): vol.All(
                        vol.Coerce(float), vol.Range(min=0.000001)
                    ),
                    vol.Required("area", default="DK2"): vol.In(["DK1", "DK2"]),
                    vol.Required("price_basis", default="spot_ex_vat"): vol.In(
                        ["all_in", "spot_ex_vat"]
                    ),
                    **{
                        vol.Required(k, default=(0.25 if k == "vat" else 0)): vol.All(
                            vol.Coerce(float), vol.Range(min=0, max=100)
                        )
                        for k in ("grid", "tax", "supplier", "vat")
                    },
                }
            ),
            errors=errors,
        )

    async def async_step_charger(self, user_input=None):
        errors = {}
        if user_input:
            source = er.async_get(self.hass).async_get(user_input["status"])
            if (
                not source
                or source.device_id != user_input["device"]
                or user_input["id"]
                in {
                    c["id"]
                    for c in self.config["chargers"]
                    if not self._is_editing("chargers", c["id"])
                }
            ):
                errors["base"] = "invalid_mapping"
            else:
                self._save_item("chargers", user_input)
                return await self.async_step_menu()
        return self._show_item(
            step_id="charger",
            data_schema=vol.Schema(
                {
                    vol.Required("id"): vol.Match(r"^[a-z0-9_]+$"),
                    vol.Required("name"): str,
                    vol.Required("device"): selector.DeviceSelector(),
                    vol.Required("status"): entity("sensor"),
                    vol.Required("zone_state", default="home"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_remove(self, user_input=None):
        choices = {
            f"{g}:{i['id']}": i.get("name", i["id"])
            for g in ("vehicles", "sites", "chargers")
            for i in self.config[g]
        }
        if user_input:
            group, key = user_input["item"].split(":")
            self.config[group] = [i for i in self.config[group] if i["id"] != key]
            return await self.async_step_menu()
        return self._show_item(
            step_id="remove", data_schema=vol.Schema({vol.Required("item"): vol.In(choices)})
        )

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title=NAME, data=self.config)


class ConfigFlow(Editor, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        self.config = defaults()
        return await self.async_step_menu()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(Editor, config_entries.OptionsFlow):
    def __init__(self, entry):
        self.config = deepcopy({**entry.data, **entry.options})

    async def async_step_init(self, user_input=None):
        return await self.async_step_menu()
