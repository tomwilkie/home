---
name: rename-entities
description: >
  Rename devices and entities in a Home Assistant area to comply with naming-conventions.md.

  TRIGGER THIS SKILL WHEN:
  - User runs /rename-entities (optional <Area Display Name> or <Device Name>)
  - User asks to rename, fix, or standardise entity IDs for a specific device or area.
---

# rename-entities

Rename the devices and entities in a Home Assistant area so that they comply with
[naming-conventions.md](../../../naming-conventions.md).

Usage: `/rename-entities [AREA_DISPLAY_NAME | DEVICE_NAME]`

Don't use SSH at any point. Renames go through the `mcp__claude_ai_ha-mcp__*` tools. The one
step that touches files is the dashboard fix, which edits the YAML in this repo and pushes it
with `hass-cli`.

## Main agent

Choose the path from what the user asked for:

- **A device:** list devices with `ha_get_device` and match the name, which gives the `device_id` and the `area_id`. Spawn a per-device subagent, then a reference-fix subagent.
- **An area:** follow [_Rename an area_](#rename-an-area).
- **Neither:** call `ha_list_floors_areas` to list the areas, then rename each area in turn.

## Rename an area

1. If you have a display name, derive the `area_id` slug by the rules in `naming-conventions.md`.
2. Call `ha_get_device(area_id="AREA_ID", detail_level="summary")` to list the devices. Page with `offset` while `has_more` is true.
3. Spawn one per-device subagent for each device, in parallel. Pass each one the device name, `device_id`, area display name and `area_id`. Don't look up entities in the main agent.
4. Collect the rename map that each subagent returns: a list of `{old_entity_id, new_entity_id}` pairs.
5. If any rename happened, spawn one reference-fix subagent with the full rename map.
6. Print a summary table of every device you checked and every change made.

## Per-device subagent

Each subagent receives the device name, `device_id`, area display name and `area_id`. Use the
default model, not Haiku. The subagent does the following:

1. Calls `ToolSearch` with the query `select:mcp__claude_ai_ha-mcp__ha_get_device,mcp__claude_ai_ha-mcp__ha_set_entity` to load the tool schemas. It uses only these MCP tools: no shell commands, no `hass-cli` and no file writes.
2. Checks that the device name follows the convention.
3. Calls `ha_get_device(device_id="DEVICE_ID")` to list the entities.
4. Checks each entity:
   - **Entity ID:** if it does not start with `{domain}.{area_id}_`, rename it with `ha_set_entity(entity_id, new_entity_id=...)`. Don't search for or fix references at this point.
   - **Display name:** if it embeds the area or device name, fix it as `naming-conventions.md` describes.
5. Returns the list of renames, for example `[{old: "sensor.foo", new: "sensor.toms_office_bar"}]`, and reports what already complied.

A `device_tracker` entity follows a conditional rule, because network-scanning integrations
(UniFi, iRobot, ESPHome) create a tracker for every client they see:

- If the device has an area, rename the tracker by the convention.
- If the device has no area, leave the tracker as it is.

## Reference-fix subagent

The reference-fix subagent runs once per area, after every per-device subagent has finished,
and only if a rename happened. It receives the full rename map.

For each renamed entity:

1. Call `ha_search(query="OLD_ENTITY_ID", search_types=["automation","script","scene","helper","dashboard"])` with the exact old entity ID.
2. Verify each match. The search matches substrings, so a short ID can match an unrelated one: `nas_` matches `rachanas_`.
3. Update each real reference to the new entity ID, using the following sections.
4. Check the adaptive lighting `lights` lists, which no search covers, as [_Audit `lights` after a light rename_](../../../lighting-automation.md#audit-lights-after-a-light-rename) describes.

Report a summary of the references updated.

### Dashboards

The dashboards are file-managed, and this repo is their source of truth. Don't edit them with
`ha_config_set_dashboard`. For each dashboard, follow [_Workflow_](../../../dashboards.md#workflow):
pull any remote changes, replace the old entity ID in `dashboards/*.yaml`, review the diff and
push with `hass-cli`.

Search the YAML for the old entity ID string rather than relying on a card search, which can
miss a reference inside a template or a condition. References appear in the following places:

- `entity` fields on tile, button and other cards
- `tap_action.target.entity_id` and `tap_action.perform_action` data
- `filter.include[].area` on `auto-entities` cards
- Jinja templates inside `icon_color`, `primary` and `secondary` strings, for example `area_entities('area_id')`
- `visibility` conditions that compare against sensor states that return area IDs
- Entity lists inside `entities` cards, as plain strings or `{entity: ...}` objects
- `badges` arrays on heading cards
- `footer.entity` on `entities` cards

### Automations

Use the search to find the automations. Don't guess. Then call `ha_config_get_automation` on
each match and check the following:

- `trigger`: state triggers on the entity, or `event_data.entity_id`
- `condition`: state or template conditions that reference the entity
- `action`: service calls that target the entity, for example `automation.turn_on` or `light.turn_on` with `area_id`
- Blueprint `input` fields, for example `area_id: "old_area_id"`

An automation that mirrors an entity is the one that manual inspection misses, because it
observes the renamed device without controlling it. "Synchronise Alarm Time", triggered by the
bedside clock's alarm time, is an example.

### Group helpers

Call `ha_get_integration(domain="group")` to list every group config entry, and check every
group whose domain matches the renamed entity's domain. Light groups, cover groups and media
player groups can all hold a stale ID. The following groups are the common ones:

- `binary_sensor.{area_id}_occupancy`, the room occupancy group
- `binary_sensor.house_occupancy_raw`, which aggregates the room occupancy groups
- `media_player.notification_players`, the notification speakers

Read a group's members from the `entity_id` attribute of `ha_get_state(GROUP_ENTITY_ID)`. To
update a group, pass its `entry_id` as the `helper_id`:

```
ha_config_set_helper(helper_type="group", helper_id="ENTRY_ID", config={"entities": [...]})
```

### Rename outside the area flow

To rename one ID by hand, such as an area ID or an automation ID, use the following order:

1. Find every reference: dashboards, automations and group helpers.
2. Rename the ID. Use `ha_set_entity(entity_id, new_entity_id=...)` for an entity or automation. Delete and re-create an area.
3. Update every reference straight away: dashboards through the repo YAML, automations with `ha_config_set_automation`, and group helpers with `ha_config_set_helper`.

## Integration quirks

- **Z-Wave (`zwave_js`)** puts the device name into `original_name`, for example `Tom's Office Spotlight: Electric Consumption [W]`. Set a bare override with `ha_set_entity(entity_id, name="Electric Consumption [W]")`.
- **ESPHome with hardware-suffix IDs,** for example `binary_sensor.everything_presence_lite_ee60e8_occupancy`: every entity except the tracker needs a rename. One device can have more than 70 entities, which a subagent handles.
- **ESPHome sub-devices share entities with the parent.** For a Bluetooth proxy sub-device, such as "Everything Presence Lite (Bluetooth)", `ha_get_device` returns the parent's entity list. If those entities already carry the `{area_id}_{parent_slug}_` prefix, treat the sub-device as compliant and leave it alone.
- **Nest Protect** generates IDs as `{domain}.nest_protect_{area_id}_{measurement}_N`. Rename them to `{domain}.{area_id}_nest_protect_{measurement}`.
- **UniFi networking gear** (access points, switches) has entity IDs such as `sensor.u5g_max_clients` and `sensor.link_speed_37`, which need a rename. Only `device_tracker` entities are exempt.
- **Music Assistant virtual devices** often have a null `original_name`, so the display name falls back to the full device name. Set a concise custom name.
