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
| Basement | `basement` | Media player (`media_player.basement_home_cinema`), Lights, Auto lights, Roomba, Washing Machine state, Tumble Dryer state |
| Kitchen | `kitchen` | Roomba, Kitchen Display media player |
| Living Room | `living_room` | Apple TV media player, Arylic LP10 media player (Music Assistant), Lights, Auto lights, Roomba |
| Master Bedroom | `master_bedroom` | HomePod Mini media player (Music Assistant), Dyson fan tile, Aircon tile, Shutters cover, Lights, Electric Blanket |
| Nursery | `nursery` | WiiM Sound media player (Music Assistant), Lights, Auto lights |
| Tom's Office | `toms_office` | Arylic LP10 media player (Music Assistant), Lights, Auto lights, Roomba, Aircon tile |
| Master Bathroom | `master_bathroom` | Velux cover |
| Rear Guest Room | `rear_guest_room` | Lights, Auto lights |

Each section heading card shows environment sensor badges sourced from the area's primary sensor device:
- **Temperature** and **Humidity**: all rooms except Rear Guest Room (no sensor)
- **CO2**: rooms with a Netatmo CO2 sensor — Kitchen, Master Bedroom, Nursery, Tom's Office
- **Occupancy**: all rooms
- Master Bathroom shows Temperature and Occupancy only (no humidity sensor)

**Media player rule**: when both a native integration entity and a Music Assistant entity exist for the same device, always use the Music Assistant entity. Exception: `media_player.basement_home_cinema` is Apple TV native (`platform: apple_tv`) with no Music Assistant equivalent — use the native entity. This rule applies to dashboard cards only; the notification players group is the opposite — it uses the **native** entity for each speaker (see [@notifications.md](notifications.md)).

**What does not appear in any section**: adaptive lighting switches (`switch.adaptive_lighting_*`). These are managed from the Settings dashboard only.

#### Visual consistency & verification

Cards that sit alongside each other in a section must look like a set. When adding or restyling a panel, match it to its neighbours on:

- **Height** — set `grid_options.rows` so paired half-width cards (`columns: 6`) are the same height. A `tile` with a feature (e.g. a `toggle`) enforces a minimum width and will **not** sit at half-width, so it can't be paired — use an `entities` card or a `mushroom-template-card` instead.
- **Spacing & padding** — icon inset, icon-to-text gap, and internal card padding.
- **Icon** — size and alignment. Beware that two MDI glyphs of the same nominal size can have different *visible* widths (e.g. `mdi:lightbulb-auto` draws a narrow bulb plus a small "A", leaving empty space inside its box), so matching bounding boxes is not the same as matching the visual gap.
- **Font** — size, weight, and letter-spacing of the label. The mushroom-template-card primary text is **weight 500, letter-spacing 0.1px** (Roboto 14px); a plain `entities` row name is weight 400 — restyle it to match.

**Consistent ordering**: keep the same card order within every room section. The Lights / Auto lights pair is always **Lights first, then Auto lights**.

**Verify layout changes in the browser — don't trust the YAML alone.** After pushing, load the dashboard in Chrome (`http://homeassistant.local:8123/dashboard-home/home`) and look at the actual render. For pixel-level alignment, inspect the live DOM rather than eyeballing: recursively traverse shadow roots and compare `getBoundingClientRect()` of the icon/text against the neighbouring card you're matching (HA buries card content several shadow roots deep — e.g. an `entities` toggle row is `hui-entities-card → #states → hui-toggle-entity-row → hui-generic-entity-row → state-badge`/`.info`). Also test at a realistic mobile/iPad column width: a half-width card has far less room than on desktop, and a long label (with a toggle eating ~40px) can truncate.

**Auto lights panels** (Basement, Living Room, Nursery, Tom's Office, Rear Guest Room) are the worked example of the above: an `entities` card on `automation.{area}_lights` (which renders a visible toggle switch), styled with `card-mod` to match the adjacent Lights `mushroom-template-card`. Key points learnt:

- `ha-card { display: block }` — **not** `flex`. `display: flex` makes the card size to its content and overflow its sections-grid column, which silently drops padding and pins the icon out of alignment.
- `#states { padding: 8px }` for the row-height fit; `grid_options: { columns: 6, rows: 1 }`.
- A **nested** shadow pierce reaches the icon/text — `hui-toggle-entity-row: { $: { hui-generic-entity-row: { $: ".info { … }" } } }` — to set the icon-to-text gap, `font-weight: 500` and `letter-spacing: 0.1px`. A single-level `hui-toggle-entity-row$ …` pierce does **not** reach them (they live one shadow root deeper, in `hui-generic-entity-row`).
- A small **negative** `margin-left` on `.info` compensates for the narrow `mdi:lightbulb-auto` glyph so its visual gap matches the plain `mdi:lightbulb` beside it.

**Vacuum bin-full styling** (Basement, Living Room, Tom's Office Roomba tiles) is the second card-mod worked example. When `state_attr(config.entity, 'bin_full')` is true the tile icon turns red and gains a small red `!` badge, so a Roomba that can't clean is obvious at a glance (see [@notifications.md](notifications.md) for why a full bin silently aborts a run). Key points learnt:

- These stay **built-in `tile` cards**, not `mushroom-template-card`s, so the `vacuum-commands` feature buttons (start/pause, return home) survive. Mushroom's templated `icon_color`/`badge_icon` would have cost those buttons.
- The tile's icon tint is the **`--tile-color`** CSS variable, set on `ha-card`. It needs `!important` — the tile card writes its own computed colour to an inline `style` attribute, which otherwise wins.
- The badge attaches to **`:host` of `ha-tile-icon`**, *not* to an inner element. Inside that shadow root the icon lives in `div.container`, which is only 36×36 and has **`overflow: hidden`**, so a corner badge placed there is clipped. The host is 48×48 with `overflow: visible`, giving room for the badge at `top: 0; right: 0`.
- ⚠️ **There is no `.shape` element.** Many community card-mod snippets target `ha-tile-icon$ .shape`; in this HA version the class is `.container`. A wrong selector fails **completely silently** — card-mod still injects its `<style>` into the shadow root, so nothing errors and the tile just renders unchanged. This is exactly why the icon-colour half of the change appeared to work while the badge was missing.
- Verify by piercing the shadow root rather than eyeballing: `deepQueryAll(...)` to the `hui-tile-card` whose `_config.entity` matches, then read `ha-tile-icon.shadowRoot` — list its elements to confirm the real class names before writing a selector against them.

> **Testing a conditional style whose condition is currently false:** push a copy with the condition forced (`sed "s/state_attr(config.entity, 'bin_full')/true/g"`) to HA only, verify visually, then re-push the real file from the repo. This exercises the true card-mod path (JS-injected CSS does not) while never committing the forced condition.

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
