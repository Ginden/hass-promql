# Linking entities to config subentries

## The problem

When a config entry uses subentries (`integration_type: "hub"`), HA's integration UI
groups devices and entities by which subentry they belong to. If entities are added
via `async_add_entities` without specifying a subentry, HA shows them under
**"Devices that don't belong to a sub-entry"** — a UI warning, not a valid state.

## The fix

Use `AddConfigEntryEntitiesCallback` instead of `AddEntitiesCallback` and pass
`config_subentry_id` when adding entities:

```python
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

async def async_setup_entry(hass, entry, async_add_entities: AddConfigEntryEntitiesCallback):
    for subentry in entry.subentries.values():
        if subentry.subentry_type == "sensor":
            async_add_entities(
                [MyEntity(subentry)],
                config_subentry_id=subentry.subentry_id,
            )
```

## Device registry behaviour

Passing `config_subentry_id` to `async_add_entities` forwards it to both
`device_registry.async_get_or_create()` and `entity_registry.async_get_or_create()`.

HA's reference implementation (kitchen sink) uses **one device per subentry**:

```python
DeviceInfo(identifiers={(DOMAIN, subentry_id)}, name=subentry.title)
```

Do **not** share a single hub device across subentries — HA renders the device
card once per subentry it is associated with, producing duplicate device cards
in the UI.

## Editing subentries (reconfigure step)

Implement `async_step_reconfigure` on the `ConfigSubentryFlow` to allow users to
edit existing subentries. Pre-populate fields from the existing subentry:

```python
async def async_step_reconfigure(self, user_input=None):
    subentry = self._get_reconfigure_subentry()
    if user_input is not None:
        return self.async_update_and_abort(
            self._get_entry(),
            subentry,
            title=user_input["name"],
            data={...},
        )
    return self.async_show_form(
        step_id="reconfigure",
        data_schema=vol.Schema({
            vol.Required("name", default=subentry.title): str,
            ...
        }),
    )
```

Add a `reconfigure` step to `strings.json` under `config_subentries.{type}.step`.

## Sources

- [entity_platform.py — AddConfigEntryEntitiesCallback](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity_platform.py)
- [PR #128161 — Add config subentry support to entity platform](https://github.com/home-assistant/core/pull/128161)
- [PR #128157 — Add config subentry support to device registry](https://github.com/home-assistant/core/pull/128157)
