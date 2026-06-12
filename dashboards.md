# Dashboards

Dashboard YAML files live in `dashboards/`. This repo is the **source of truth** — all edits must be made to files here, never via the HA UI.

## File naming

Files are named `{url-path}.yaml`, matching the dashboard's URL path in HA:

| File | HA URL path |
|---|---|
| `dashboards/kitchen-home.yaml` | `kitchen-home` |
| `dashboards/dashboard-home.yaml` | `dashboard-home` |
| `dashboards/dashboard-settings.yaml` | `dashboard-settings` |

## Workflow

1. **Check for remote changes** before editing — if HA has changes not in this repo, pull them first:
   ```bash
   diff -u dashboards/{url-path}.yaml <(hass-cli -o yaml dashboard get {url-path})
   ```
   If there are differences, download the live version before proceeding:
   ```bash
   hass-cli -o yaml dashboard get {url-path} > dashboards/{url-path}.yaml
   ```
2. Edit `dashboards/{url-path}.yaml` in this repo
3. Diff to review your outgoing change:
   ```bash
   diff -u <(hass-cli -o yaml dashboard get {url-path}) dashboards/{url-path}.yaml
   ```
4. Push to HA:
   ```bash
   hass-cli dashboard set dashboards/{url-path}.yaml {url-path}
   ```
5. Commit to git

## Initial download (bootstrap only)

To capture a dashboard from HA for the first time:
```bash
hass-cli -o yaml dashboard get {url-path} > dashboards/{url-path}.yaml
```

---

## Dashboard inventory

### `kitchen-home` — Kitchen Touch Screen

The always-on display mounted in the kitchen. Shows at-a-glance status and quick controls for kitchen and household use:

- **Environment**: Kitchen temperature, CO2, and humidity (Netatmo)
- **Appliances**: Vacuum control, hot water (hallway thermostat)
- **Family calendar**: Upcoming events with weather integration (conditions, high temp, UV index)
- **Transport**: London Underground Weaver and Victoria line status; bus departures from Rectory Road
- **Weather & pollen**: Clock/weather card for My Home; grass, tree, and weed pollen levels
- **Cameras**: Live WebRTC feeds (3 cameras)
- **Media**: Fully Kiosk launcher buttons for Apple Music and YouTube
- **Automations**: "Turn Everything Off" button; "Turn on Bedroom Aircon for 1hr" (conditional on temp > 21°C)
- **Location**: Where is Tom / Where is Rachana tiles

### `dashboard-home` — Main Home Dashboard

The primary dashboard used on mobile and desktop. Has four views:

| View | Path | Purpose |
|---|---|---|
| Home | `home` | Per-room controls, shown conditionally based on Tom's location (room selector or auto-detected). Covers Basement, Kitchen, Living Room, Master Bedroom, Nursery, Tom's Office, Master Bathroom, Rear Guest Room. Each section shows environment sensors, lights toggle, media player, and room appliances (vacuum, shutters, aircon, etc.). |
| Lighting | `lighting` | Lists all `room-light`-labelled entities per area for bulk management. |
| Climate | `climate` | Thermostat controls, per-room sensor cards, weather forecast, central heating history, and boiler status. See [Climate view layout](#climate-view-layout) below. |
| Cameras | _(default)_ | Live picture-entity feeds: front door, garage (AI Pro), garage door, G5 Turret Ultra. |

#### Home view layout

`type: sections`, `max_columns: 3`

**Section 1 — Header / selector** (`column_span: 3`, full width)
- `custom:mushroom-select-card` bound to `input_select.tom_room_selector` — lets Tom manually pick a room or switch to Auto/All mode
- `sensor.tom_s_iphone_area` tile (Tom's current room, display-name format)
- `sensor.rachanas_iphone_area` tile + `person.rachana_shanbhogue` tile
- `binary_sensor.house_occupancy` tile

**Sections 2–9 — Rooms**

Each room section has a `visibility` block with an `or` condition:
1. Selector is set to that room's name (manual override)
2. Selector is `Auto` **and** `sensor.tom_s_room` equals the room's area slug (e.g. `living_room`)
3. Selector is `All`

`sensor.tom_s_room` returns the area slug (e.g. `living_room`, `toms_office`) — all Auto-mode conditions use this entity consistently.

Rooms in order, with their area slugs and notable cards:

| Room | Slug | Notable cards |
|---|---|---|
| Basement | `basement` | Media player (`media_player.basement_home_cinema`), Auto Lights toggle, Lights toggle, Roomba, Washing Machine state, Tumble Dryer state |
| Kitchen | `kitchen` | Roomba, Kitchen Display media player |
| Living Room | `living_room` | Apple TV media player, Arylic LP10 media player (Music Assistant), Auto Lights toggle, Lights toggle, Roomba |
| Master Bedroom | `master_bedroom` | HomePod Mini media player (Music Assistant), Dyson fan tile, Aircon tile, Shutters cover, Lights toggle, Electric Blanket |
| Nursery | `nursery` | WiiM Sound media player (Music Assistant), Lights toggle, Auto Lights toggle |
| Tom's Office | `toms_office` | Arylic LP10 media player (Music Assistant), Lights toggle, Auto Lights toggle, Roomba, Aircon tile |
| Master Bathroom | `master_bathroom` | Velux cover |
| Rear Guest Room | `rear_guest_room` | Lights toggle, Auto Lights toggle |

Each section heading card shows environment sensor badges sourced from the area's primary sensor device:
- **Temperature** and **Humidity**: all rooms except Rear Guest Room (no sensor)
- **CO2**: rooms with a Netatmo CO2 sensor — Kitchen, Master Bedroom, Nursery, Tom's Office
- **Occupancy**: all rooms
- Master Bathroom shows Temperature and Occupancy only (no humidity sensor)

**Media player rule**: when both a native integration entity and a Music Assistant entity exist for the same device, always use the Music Assistant entity. Exception: `media_player.basement_home_cinema` is Apple TV native (`platform: apple_tv`) with no Music Assistant equivalent — use the native entity.

**What does not appear in any section**: adaptive lighting switches (`switch.adaptive_lighting_*`). These are managed from the Settings dashboard only.

---

#### Climate view layout

`type: sections`, `max_columns: 3`, `theme: Backend-selected`

**Section 1 — Climate Controls** (`column_span: 3`, full width)
Three thermostat cards (house, Tom's office, master bedroom aircon) plus a `custom:mushroom-fan-card` for the Dyson fan in the master bedroom (with percentage and oscillation controls). All cards use `columns: 9` so they fill the section evenly.

**Section 2 — Weather** (`column_span: 1`)
Daily weather forecast for My Home (`weather-forecast` card, `forecast_type: daily`).

**Section 3 — Central Heating** (`column_span: 2`)
- Boiler on-time tile (`sensor.kitchen_boiler_on_time`)
- Boiler status history graph (boiler on/off binary + two temperature sensors, 24 h, no legend)
- Radiator temperatures history graph (all 13 radiator sensors, 24 h, no legend)

**Sections 4–12 — Rooms** (`column_span: 1`, 3 per row)

Rooms in order: Kitchen, Living Room, Master Bedroom, Master Bathroom, Nursery, Tom's Office, Hallway, Basement, Garage.

Each room section contains:
- A heading card with a room icon
- A single `entities` card using [`custom:multiple-entity-row`](https://github.com/benct/lovelace-multiple-entity-row) — one row per measurement type (Temperature, Humidity, CO2, etc.)
- A `history-graph` card (24 h, `show_names: false`)

The entities card is sized to `rows: 3` so only the first three rows (temperature, humidity, CO2) are visible without scrolling; additional rows (particulates, VOC, NOx, etc.) are accessible by scrolling.

**`custom:multiple-entity-row` conventions:**
- Every row uses `show_state: false` so the unlabelled primary state is hidden
- Even single-source rows repeat the entity as a named secondary (e.g. `name: Netatmo`) so every value has a device label visible in the UI
- Multi-source rows list all devices as named secondaries (e.g. Netatmo, Multisensor, AirGradient)
- Particulate readings (PM1, PM2.5, PM10) are grouped into a single "Particulates" row

Master Bedroom also includes air quality rows from the Dyson fan (HCHO, PM2.5, PM10, VOC Index, Nitrogen Dioxide Index) below the standard sensors.

Tom's Office includes additional AirGradient rows: Particulates (PM1/PM2.5/PM10), VOC Index, and NOx Index.

---

### `dashboard-settings` — Settings

Diagnostic and configuration views. Has three views:

| View | Path | Purpose |
|---|---|---|
| Debugging | _(default)_ | Low batteries, unavailable entities, stale entities (not updated in 24 h), vacuum run times, active/recently-triggered automations, adaptive lighting brightness history and on/off switches. |
| Settings | `settings` | Comfort mode schedule, weekday/weekend wakeup time inputs, bedroom clock alarm. |
| Broadcast | `broadcast` | Text box (`input_text.broadcast_message`) with embedded send button (paper-buttons-row) for broadcasting a spoken message via `script.broadcast`, which calls `script.annouce` with `important: true` and `persistent: false`, then clears the box. Also a Notification Players card with the per-player `input_boolean.*_notifications` toggles that control which speakers announcements play on. |
