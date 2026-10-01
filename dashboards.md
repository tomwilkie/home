# Dashboards

Dashboard YAML files live in `dashboards/`. This repo is the source of truth: edit the files
here, not the Home Assistant UI.

Each file is named `{url-path}.yaml`, after the dashboard's URL path in Home Assistant:
`dashboards/kitchen-home.yaml`, `dashboards/dashboard-home.yaml` and
`dashboards/dashboard-settings.yaml`.

## Workflow

1. Check for remote changes. If Home Assistant has changes that are not in this repo, download the live version first:

   ```bash
   diff -u dashboards/URL_PATH.yaml <(hass-cli -o yaml dashboard get URL_PATH)
   hass-cli -o yaml dashboard get URL_PATH > dashboards/URL_PATH.yaml
   ```

2. Edit `dashboards/URL_PATH.yaml`.
3. Review the outgoing change:

   ```bash
   diff -u <(hass-cli -o yaml dashboard get URL_PATH) dashboards/URL_PATH.yaml
   ```

4. Push to Home Assistant:

   ```bash
   hass-cli dashboard set dashboards/URL_PATH.yaml URL_PATH
   ```

5. For a layout change, check the render as described in [_Visual consistency_](#visual-consistency).
6. Commit.

`URL_PATH` is the dashboard's URL path, for example `kitchen-home`. To list the dashboards, run
`hass-cli dashboard list`. Installing `hass-cli` is covered in
[_Home Assistant CLI_](access-home-assistant.md#home-assistant-cli).

## `kitchen-home`: kitchen touch screen

The always-on display mounted in the kitchen shows status and quick controls for the household:

- **Environment:** kitchen temperature, CO2 and humidity (Netatmo)
- **Appliances:** vacuum control and hot water
- **Family calendar:** upcoming events with weather conditions, high temperature and UV index
- **Transport:** London Underground Weaver and Victoria line status, and bus departures from Rectory Road
- **Weather and pollen:** a clock and weather card for My Home, and grass, tree and weed pollen levels
- **Cameras:** live WebRTC feeds
- **Media:** Fully Kiosk launcher buttons for Apple Music and YouTube
- **Automations:** a "Turn Everything Off" button, and "Turn on Bedroom Aircon for 1hr" when the bedroom is above 21 °C
- **Location:** Where is Tom and Where is Rachana tiles

### Keep `background: false` on the camera cards

The `custom:webrtc-camera` cards must keep `background: false`. With `background: true` every
stream keeps decoding when it is off-screen and when the tablet's screen is off, and the setting
overrides the `intersection: 0.75` pause on each card. The permanent decoders leaked the Fully
Kiosk WebView's memory until the browser froze. With `background: false` the streams pause when
scrolled out of view, which is most of the time, because the cameras sit near the end of a long
view. `automation.restart_kitchen_display_browser` in [maintenance.md](maintenance.md) is the
backstop.

## `dashboard-home`: main home dashboard

The primary dashboard for mobile and desktop has the following views:

| View | Path | Purpose |
|---|---|---|
| Home | `home` | Per-room controls, shown according to Tom's location |
| Lighting | `lighting` | Every `room-light` entity per area, for bulk management |
| Climate | `climate` | Thermostats, per-room sensors, weather forecast, central heating history and boiler status |
| Cameras | default | Live `picture-entity` feeds: front door, garage (AI Pro), garage door and G5 Turret Ultra |

### Home view

The view is `type: sections` with `max_columns: 3`.

The header section spans the full width. It holds a `custom:mushroom-select-card` bound to
`input_select.tom_room_selector`, which lets Tom pick a room or switch to Auto or All, and tiles
for Tom, Rachana and `binary_sensor.house_occupancy`.

Each room section is visible when any of the following holds:

- The selector is set to that room's name.
- The selector is `Auto` and `sensor.tom_s_room` equals the room's area slug, for example `living_room`.
- The selector is `All`.

The rooms appear in the following order:

| Room | Slug | Notable cards |
|---|---|---|
| Basement | `basement` | Media player (`media_player.basement_home_cinema`), Lights, Auto lights, Roomba, washing machine state, tumble dryer state |
| Kitchen | `kitchen` | Vacuum (`vacuum.kitchen_vacuum`), Kitchen Display media player |
| Living Room | `living_room` | Apple TV media player, Arylic LP10 media player, Lights, Auto lights, Roomba |
| Master Bedroom | `master_bedroom` | HomePod Mini media player, Dyson fan, aircon, shutters, Lights, electric blanket |
| Nursery | `nursery` | WiiM Sound media player, Lights, Auto lights |
| Tom's Office | `toms_office` | Arylic LP10 media player, Lights, Auto lights, Roomba, aircon |
| Master Bathroom | `master_bathroom` | Velux cover |
| Rear Guest Room | `rear_guest_room` | Lights, Auto lights |

Each section heading shows badges from the area's primary sensor device: occupancy in every
room, temperature and humidity where the room has the sensor, and CO2 in the rooms with a
Netatmo module.

Adaptive lighting switches don't appear in any section. They are on the Settings dashboard.

The following rules apply to every room section:

- **Order cards the same way in every room.** The Lights and Auto lights pair is Lights first.
- **Use the Music Assistant entity for a media player** when a device has both a native entity and a Music Assistant one. `media_player.basement_home_cinema` is the exception: it is a native `apple_tv` entity with no Music Assistant equivalent. The notification players group follows the same preference, for the reason in [_Choose the entity that supports announce_](notifications.md#choose-the-entity-that-supports-announce).

### Repair a re-created Music Assistant player

Music Assistant sometimes re-creates a proxy player. The device comes back with a different
`device_id`, a vendor-derived entity ID, no area and no name override, and every card that
points at the previous entity ID breaks. The vendor-derived name comes from the speaker's own
configured name, which has no relation to the Home Assistant area: the Living Room Arylic LP10
is named "Dining Room" in the Arylic app, so its proxy returns as `media_player.dining_room`.

Fix the entity, not the dashboard. Rename the device and the entity back to the convention in
[naming-conventions.md](naming-conventions.md), and the dashboard YAML, the
`media_player.notification_players` group and the notification toggles all resolve again with no
edit. Rename the `media_player` and its companion `button.*_favorite_current_song`:

```sh
hass-cli raw ws config/device_registry/update \
  --json='{"device_id":"…","name_by_user":"Living Room - Arylic LP10 (Music Assistant)","area_id":"living_room"}'
hass-cli raw ws config/entity_registry/update \
  --json='{"entity_id":"media_player.dining_room","new_entity_id":"media_player.living_room_arylic_lp10_ma_player"}'
```

To match a proxy to its physical speaker, compare identifiers, not names. The Music Assistant
identifier (`wiim_uuid:FF31F09E-F8D9-…`) is the native integration's identifier
(`FF31F09EF8D9…`) with dashes.

Then check the announce path, because a dead group member fails silently. The following template
must render `[]`:

```jinja
{{ state_attr('media_player.notification_players','entity_id')
   | reject('in', states | map(attribute='entity_id') | list) | list }}
```

### Visual consistency

Cards that sit next to each other in a section must look like a set. When you add or restyle a
card, match its neighbours on the following:

- **Height.** Set `grid_options.rows` so that paired half-width cards (`columns: 6`) are the same height. A `tile` with a feature such as a `toggle` enforces a minimum width and does not sit at half width, so use an `entities` card or a `mushroom-template-card` instead.
- **Spacing and padding.** Match the icon inset, the icon-to-text gap and the internal padding.
- **Icon.** Match size and alignment. Two MDI glyphs of the same nominal size can have different visible widths, so matching bounding boxes does not match the visual gap.
- **Font.** The `mushroom-template-card` primary text is Roboto `14px`, weight 500, with letter-spacing `0.1px`. A plain `entities` row name is weight 400, so restyle it.

After you push a layout change, load the dashboard in Chrome at
`http://homeassistant.local:8123/dashboard-home/home` and look at the render. For pixel-level
alignment, walk the shadow roots and compare `getBoundingClientRect()` of the icon and text
against the neighbouring card. Test at a mobile or iPad column width too, where a half-width
card has much less room and a long label next to a toggle can truncate.

A card-mod selector that matches nothing fails silently: card-mod still injects its `<style>`,
nothing errors, and the card renders unchanged. Before you write a selector, list the elements
of the target shadow root to confirm the class names.

To test a conditional style whose condition is false, push a copy with the condition forced to
Home Assistant only, check the render, then push the real file again:

```sh
sed "s/state_attr(config.entity, 'bin_full')/true/g" dashboards/dashboard-home.yaml
```

### Auto lights cards

The Auto lights cards are `entities` cards on `automation.{area}_lights`, which render a toggle
switch, styled with card-mod to match the Lights `mushroom-template-card` beside them:

- **`ha-card { display: block }`, not `flex`.** With `flex` the card sizes to its content, overflows its grid column, drops padding and moves the icon out of alignment.
- **`#states { padding: 8px }`** fits the row height, with `grid_options: { columns: 6, rows: 1 }`.
- **A nested shadow pierce reaches the icon and text:** `hui-toggle-entity-row: { $: { hui-generic-entity-row: { $: ".info { … }" } } }`. It sets the icon-to-text gap, `font-weight: 500` and `letter-spacing: 0.1px`. A single-level pierce does not reach them, because they live one shadow root deeper.
- **A small negative `margin-left` on `.info`** compensates for the narrow `mdi:lightbulb-auto` glyph.

### Vacuum bin-full tiles

When `state_attr(config.entity, 'bin_full')` is true, the Roomba tile's icon turns red and gains
a red `!` badge. The reason is in [_Vacuum bin full_](notifications.md#vacuum-bin-full).

- **The tiles stay built-in `tile` cards,** so that the `vacuum-commands` feature buttons survive. A `mushroom-template-card` has templated icon colour and badge but no such buttons.
- **The icon tint is the `--tile-color` variable on `ha-card`,** and it needs `!important`, because the tile writes its own colour to an inline `style`.
- **The badge attaches to `:host` of `ha-tile-icon`.** Inside that shadow root the icon sits in `div.container`, which is `36px` square with `overflow: hidden`, so a corner badge there is clipped. The host is `48px` square with `overflow: visible`.
- **The class is `.container`, not `.shape`.** Many community snippets target `ha-tile-icon$ .shape`, which does not exist in this Home Assistant version.

### Climate view

The view is `type: sections` with `max_columns: 3` and `theme: Backend-selected`.

- **Climate Controls** spans the full width. It holds thermostat cards for the house, Tom's office and the master bedroom aircon, and a `custom:mushroom-fan-card` for the Dyson fan with percentage and oscillation controls. Every card uses `columns: 9`.
- **Weather** holds a daily `weather-forecast` card for My Home.
- **Central Heating** holds a boiler on-time tile (`sensor.kitchen_boiler_on_time`), a 24-hour boiler status history graph and a 24-hour graph of every radiator temperature sensor.
- **Room sections** follow, in the order Kitchen, Living Room, Master Bedroom, Master Bathroom, Nursery, Tom's Office, Front Guest Room, Hallway, Basement, Garage.

Each room section holds a heading card, one `entities` card and a 24-hour `history-graph` card
with `show_names: false`. The `entities` card uses
[`custom:multiple-entity-row`](https://github.com/benct/lovelace-multiple-entity-row), with one
row per measurement, and is sized to `rows: 3`, so temperature, humidity and CO2 are visible and
the remaining rows scroll.

The rows follow these conventions:

- **Every row sets `show_state: false`,** which hides the unlabelled primary state.
- **Every value carries a device label.** A single-source row repeats its entity as a named secondary, for example `name: Netatmo`, and a multi-source row lists every device.
- **Particulate readings share one row** (PM1, PM2.5, PM10).

Master Bedroom adds air quality rows from the Dyson fan, and Tom's Office adds AirGradient rows.

Front Guest Room appears only in this view. The Home view's room sections are built around
lights, occupancy and media, and the Front Guest Room has none of them and is not a selector
option. Its history graph plots only the environmental sensor, because the radiator sensor
spikes far above room temperature when the heating runs.

## `dashboard-settings`: settings

The diagnostic and configuration dashboard has the following views:

| View | Path | Purpose |
|---|---|---|
| Debugging | default | Low batteries, unavailable entities, entities not updated in 24 hours, vacuum run times, active and recently triggered automations, adaptive lighting brightness history and switches |
| Settings | `settings` | Comfort mode schedule, weekday and weekend wake-up times, the flight lead time and the bedroom clock alarm |
| Broadcast | `broadcast` | A text box (`input_text.broadcast_message`) with a send button that calls `script.broadcast`, and the Notification Players card of per-player toggles. Both are described in [notifications.md](notifications.md). |
