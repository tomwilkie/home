# Known Error Patterns

Catalogue of recurring error and warning signatures seen in this HA instance. Use this to interpret `ha_get_logs` results.

## How to use

For each log entry, check the `name` (logger source) and `message` against the patterns below. If a match is found, apply the catalogued severity and action instead of the default count-based threshold.

---

## Apple TV (`homeassistant.components.apple_tv`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Connection lost to Apple TV` + `Connection was re-established` cycling | Warning | Integration reconnecting in a loop | Check ATV power/WiFi settings; may be normal during ATV sleep |
| `RuntimeError: loop is not the running loop` in `binary_sensor.py` | Warning | Python 3.14 + apple_tv incompatibility; fires on each reconnect | Upstream HA bug — monitor HA release notes; no local fix |
| `Task was destroyed but it is pending! … binary_sensor.apple_tv` | Warning | Side-effect of the loop-not-running bug above | Same as above — suppress once identified |
| `Failed to update app list` / `FetchLaunchableApplicationsEvent failed` | Warning | Companion protocol timeout; power_state and app list unavailable | Usually resolves on next reconnect |
| `Could not fetch SystemStatus` / `FetchAttentionState failed` | Warning | Same protocol timeout | Same as above |

Group all Apple TV errors into a single report item per device.

---

## Bermuda BLE (`custom_components.bermuda`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Calling process_advertisement on a metadevice … is a bug` | Warning | Bermuda BLE tracker bug with Everything Presence Lite devices | Check HACS for Bermuda update |

---

## Hive (`apyhiveapi`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Failed to fetch devices` | Warning | Intermittent Hive cloud connectivity | Monitor; check Hive service status page |
| `Hive API request timed out` | Warning | Same as above | Same |

Hub entity usually still shows `on` even during API failures. Check `binary_sensor.*_hive_hub_status`.

---

## Deebot / Ecovacs (`deebot_client`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Connection lost; Reconnecting in 5 seconds …` (×50+) | Warning | Ecovacs cloud MQTT flapping — usually transient | Monitor; if persistent, re-authenticate in Settings → Devices & Services |
| `504 Gateway Time-out` from `portal-eu.ecouser.net` | Warning | Ecovacs cloud outage | Monitor cloud status |
| `Could not execute command … Timeout reached` | Info | Per-command cloud timeout during MQTT outage | Resolves when MQTT reconnects |

---

## AirGradient (`homeassistant.components.airgradient`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Error fetching AirGradient <IP> data: Timeout occurred` | Warning | Device at that IP is intermittently unreachable | Assign static DHCP reservation for the device's MAC; check WiFi signal |

Note: HA caches last-known values — entities may still show valid readings even when the device is intermittently offline. Confirm by checking `last_updated` on a key entity like `sensor.*_airgradient_carbon_dioxide`.

---

## Z-Wave JS (`homeassistant.components.zwave_js.services`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `This service is deprecated in favor of the ping button entity` | Warning | Something is calling `zwave_js.ping`; will break in a future HA version | Find the caller with `ha_deep_search(query="zwave_js.ping")`; replace with `button.press` targeting `button.*_ping` entities |

---

## ChimeTTS (`custom_components.chime_tts`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Unable to generate local audio filepath` | Warning | ChimeTTS can't find/write an audio file | Check ChimeTTS integration config; ensure audio path is writable |
| `expected str for dictionary value @ data['say']['fields']['chime_path']` | Info | services.yaml parse issue in ChimeTTS version | HACS update likely resolves it |

---

## Automations (`homeassistant.components.automation.*`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `extra keys not allowed @ data['kelvin']` | Critical | `light.turn_on` `kelvin` param renamed `color_temp_kelvin` in HA 2023.x | Find automation action passing `kelvin` and rename to `color_temp_kelvin` |
| `extra keys not allowed @ data[...]` (any key) | Critical | Service schema changed; automation passing a removed/renamed parameter | Get automation traces to identify the bad action; fix the parameter |

---

## Netatmo (`homeassistant`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `ValueError: Handler is already defined!` from `netatmo.__init__` | Info | Webhook registered twice on HA restart | Harmless; no action needed |

---

## Roomba / iRobot (`homeassistant.components.sensor`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Platform roomba does not generate unique IDs. ID dock_tank_level_… already exists` | Info | Duplicate sensor ID silently dropped | Cosmetic; those sensors just won't exist |

---

## Frontend / WebRTC (`frontend.js.modern.*`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `InvalidStateError: Failed to read the 'buffered' property from 'SourceBuffer'` | Info | WebRTC camera playback glitch on Android Chrome | Cosmetic; raise frontend log level to reduce noise: Settings → System → Logs → set `frontend` to WARNING |
| `RangeError: offset is out of bounds` in `video-rtc.js` | Info | Same WebRTC bug | Same |

These errors typically accumulate to 100k+ counts. Do not escalate.

---

## Nabu Casa / Remote Access (`hass_nabucasa.remote`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Can't connect to SniTun server … Try again` | Warning | Brief remote access interruption | Usually self-resolves; check nabu.casa status if persistent |
| `Timeout error while pinging peer` | Info | Single timeout during remote connection | Harmless if infrequent |

---

## LinkPlay media players (`homeassistant.components.media_player`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Updating linkplay media_player took longer than the scheduled update interval 0:00:05` | Info | Slow response from a LinkPlay speaker (Arylic) | Harmless if infrequent; check speaker WiFi if persistent |
