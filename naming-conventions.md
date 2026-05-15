# Home Assistant Naming Conventions

## Areas

### Area IDs

Area IDs are slugified from the display name using these rules:

- Spaces → underscores (`_`)
- Apostrophes → **dropped** (not replaced with `_`)
- Everything lowercase

Examples:

| Display Name | area_id |
|---|---|
| Basement | `basement` |
| Tom's Office | `toms_office` |
| Nursery | `nursery` |
| Front Guest Room | `front_guest_room` |

> **Note:** HA auto-generates area IDs differently (apostrophes become `_s_`). When creating a new area whose name contains an apostrophe, create it first with a plain name (e.g. "Toms Office") to get the correct slug, then update the display name to the correct value (e.g. "Tom's Office").

---

## Devices

### Naming format

```
{Area Display Name} - {Device Specific Name}
```

- The area display name comes first, exactly as written (including apostrophes)
- A ` - ` separator (space-dash-space) separates area from device
- The device-specific name identifies the device within the area

Examples:

| Area | Device | Full Name |
|---|---|---|
| Kitchen | Netatmo | `Kitchen - Netatmo` |
| Tom's Office | Roomba | `Tom's Office - Roomba` |
| Nursery | Motion Sensor | `Nursery - Motion Sensor` |
| Master Bedroom | Lamp Tom's | `Master Bedroom - Lamp Tom's` |
| Front Guest Room | Nest Protect | `Front Guest Room - Nest Protect` |

### Scope

- Devices **with** an assigned area must follow this convention, regardless of type (including networking gear, infrastructure devices, etc.)
- Devices **without** an area (system/infrastructure devices such as HA Core, HACS, networking gear) are excluded

---

## Entities

### Entity ID format

```
{domain}.{area_id}_{device_slug}_{measurement}
```

- `domain` — the HA domain (e.g. `sensor`, `binary_sensor`, `light`, `switch`)
- `area_id` — the area's slug (see Area IDs above)
- `device_slug` — a short identifier for the device within the area
- `measurement` — what the entity measures or controls (e.g. `temperature`, `pressure`, `occupancy`)

Examples:

| Entity ID | Area | Device | Measurement |
|---|---|---|---|
| `sensor.kitchen_netatmo_pressure` | `kitchen` | netatmo | pressure |
| `sensor.toms_office_motion_sensor_temperature` | `toms_office` | motion_sensor | temperature |
| `binary_sensor.nursery_motion_sensor_occupancy` | `nursery` | motion_sensor | occupancy |
| `light.front_guest_room_lamp_desk` | `front_guest_room` | lamp | desk |

### Key rules

- Entity IDs must start with `{domain}.{area_id}_` — the area_id prefix is mandatory
- Apostrophes in area display names are **dropped** in the area_id slug, so they do not appear in entity IDs (e.g. `toms_office_...` not `tom_s_office_...`)
- Entities on devices without an area assignment are excluded from this convention
- `device_tracker.*` entities from network-scanning integrations (e.g. UniFi, etc.) follow a conditional rule: if the entity's device has an area assigned in HA, rename it per this convention; if the device has no area (bare network client with no HA counterpart), leave it as-is.

### Display names (friendly names)

Entity display names should be concise and reflect only what the entity measures or controls — they must **not** include the area or device name as a prefix.

- **Correct:** `Temperature`, `Battery Level`, `Smoke Status`, `Motion detection`
- **Incorrect:** `Nursery Motion Sensor Temperature`, `Nest Protect (Baby's Room) Smoke Status`

**Why this matters:** Integrations and HA itself sometimes auto-generate display names by prepending the device name (e.g. `{Device Name} {measurement}`). After a device rename, these baked-in names become stale and misleading.

**How to fix stale display names after renaming:**

1. If the entity has a user-set custom name (`name` field in entity registry is not null) that references the old device/area name — **clear it** with `ha_set_entity(entity_id, name="")` so it reverts to the integration default.
2. If the integration's own `original_name` embeds the old device name (e.g. `"Nest Protect (Baby's Room) Smoke Status"`) — **set a custom override** with `ha_set_entity(entity_id, name="Smoke Status")` to strip the prefix.

> **Note:** After renaming a device or entity ID, always check entity display names for each device and fix any that still reference the old name.

---

## Automations

### Entity ID format

Automation entity IDs are slugified from the alias (display name) using the same rules as area IDs:

- Lowercase, spaces → underscores
- Apostrophes → **dropped** (not `_s_`)
- ` - ` separators → `_`
- Special characters (parentheses, etc.) → dropped

```
automation.{slugified_alias}
```

Examples:

| Alias | entity_id |
|---|---|
| "Basement Lights" | `automation.basement_lights` |
| "Tom's Office Lights" | `automation.toms_office_lights` |
| "Nursery Lights" | `automation.nursery_lights` |
| "Living Room - Manual" | `automation.living_room_manual` |
| "Notify on Tumble Drier finished" | `automation.notify_on_tumble_drier_finished` |

> **Note:** HA auto-generates automation entity IDs from the alias when first created, using its own slugification (which maps apostrophes to `_s_`). When renaming an automation's alias after creation, the entity_id is **not** automatically updated — use `ha_rename_entity` to fix it manually.

---

## Zigbee2MQTT sync

Device names in zigbee2mqtt (friendly names) must be kept in sync with the HA device names. This section documents how to do that.

### Prerequisites

`mosquitto` CLI tools must be installed (`brew install mosquitto`). MQTT broker:

- Host: `homeassistant.local`, port `1883`
- Credentials: `homeconnect` / `homeconnect`

### Step 1 — get z2m device list

Pull the current z2m devices and their friendly names:

```bash
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.type != "Coordinator") | [.ieee_address, .friendly_name] | @tsv'
```

### Step 2 — get HA MQTT device names

SSH into HA and extract the IEEE address → display name mapping for all MQTT devices:

```bash
ssh root@homeassistant.local -C \
  "jq -r '.data.devices[] | select(.identifiers[][] == \"mqtt\") | [(.identifiers[] | select(.[0]==\"mqtt\") | .[1] | ltrimstr(\"zigbee2mqtt_\")), .name_by_user // .name] | @tsv' \
  /config/.storage/core.device_registry"
```

The identifier format for z2m devices in HA is `zigbee2mqtt_<ieee_address>`, so stripping the prefix gives the IEEE address for matching.

### Step 3 — rename z2m devices to match HA

Use the `zigbee2mqtt/bridge/request/device/rename` topic. The `homeassistant_rename: false` flag prevents z2m from also trying to rename the HA device (which is already correct).

Run renames in parallel using a shell function:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/rename' \
    -m "{\"from\": \"$1\", \"to\": \"$2\", \"homeassistant_rename\": false}" \
    && echo "ok: $2" || echo "FAIL: $2"
}

pub "0x001788010ea0b4e4" "Living Room - Tom's Lamp" &
pub "0xaabbccddeeff0011" "Kitchen - Radiator" &
# ... one line per device
wait
```

> **Note:** Avoid naming the shell function `rename` — it conflicts with the zsh builtin and the mosquitto_pub call will silently not run.

### Step 4 — clear stale descriptions

z2m devices have a user-settable `description` field that can hold stale names from before a rename. After renaming, check for and clear any non-empty descriptions:

```bash
# List devices with non-empty descriptions
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.description != null and .description != "") | [.friendly_name, .description] | @tsv'
```

Clear descriptions in parallel using `zigbee2mqtt/bridge/request/device/options`:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/options' \
    -m "{\"id\": \"$1\", \"options\": {\"description\": \"\"}}" \
    && echo "ok: $1" || echo "FAIL: $1"
}

pub "Living Room - Lamp Rear" &
pub "Kitchen - Radiator" &
# ... one line per device with a stale description
wait
```