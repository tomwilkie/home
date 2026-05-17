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

1. Edit `dashboards/{url-path}.yaml` in this repo
2. Diff against the live HA state to review the change:
   ```bash
   diff -u <(hass-cli -o yaml dashboard get {url-path}) dashboards/{url-path}.yaml
   ```
3. Push to HA:
   ```bash
   hass-cli dashboard set dashboards/{url-path}.yaml {url-path}
   ```
4. Commit to git

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
| Home | `home` | Per-room controls, shown conditionally based on Tom's location (room selector or auto-detected). Covers Basement, Kitchen, Living Room, Master Bedroom, Nursery, Tom's Office, Master Bathroom. Each section shows environment sensors, lights toggle, media player, and room appliances (vacuum, shutters, aircon, etc.). |
| Lighting | `lighting` | Lists all `room-light`-labelled entities per area for bulk management. |
| Climate | `climate` | Thermostat cards (house, Tom's office, master bedroom aircon), per-room temperature/humidity history, radiator temperatures, boiler status, and boiler on-time. |
| Cameras | _(default)_ | Live picture-entity feeds: front door, garage (AI Pro), garage door, G5 Turret Ultra. |

### `dashboard-settings` — Settings

Diagnostic and configuration views. Has two views:

| View | Path | Purpose |
|---|---|---|
| Debugging | _(default)_ | Low batteries, unavailable entities, stale entities (not updated in 24 h), vacuum run times, active/recently-triggered automations, adaptive lighting brightness history and on/off switches. |
| Settings | `settings` | Comfort mode schedule, weekday/weekend wakeup time inputs, bedroom clock alarm. |
