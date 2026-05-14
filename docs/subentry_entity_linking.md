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

The device registry stores a **one-to-many** mapping of
`config_entry_id → {config_subentry_id, ...}`, so a single hub device (identified
by `(DOMAIN, entry.entry_id)`) accumulates subentry associations as sensors are
added. The device is not duplicated — it is shared across all subentries.

## Sources

- [entity_platform.py — AddConfigEntryEntitiesCallback](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity_platform.py)
- [PR #128161 — Add config subentry support to entity platform](https://github.com/home-assistant/core/pull/128161)
- [PR #128157 — Add config subentry support to device registry](https://github.com/home-assistant/core/pull/128157)
