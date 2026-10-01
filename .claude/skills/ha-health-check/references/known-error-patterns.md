# Known error patterns

This catalogue lists the recurring error and warning signatures in this Home Assistant instance.
Use it to interpret `ha_get_logs` results.

For each log entry, check the `name` (the logger source) and the `message` against the patterns.
On a match, apply the catalogued severity and action instead of the count-based threshold. Each
section covers one logger source, and its table lists that source's patterns.

## Apple TV (`homeassistant.components.apple_tv`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Connection lost to Apple TV` and `Connection was re-established`, cycling | Warning | The integration reconnects in a loop | Check the Apple TV's power and WiFi settings. It can be normal during Apple TV sleep. |
| `RuntimeError: loop is not the running loop` in `binary_sensor.py` | Warning | A Python 3.14 and `apple_tv` incompatibility that fires on each reconnect | An upstream bug with no local fix. Watch the Home Assistant release notes. |
| `Task was destroyed but it is pending! … binary_sensor.apple_tv` | Warning | A side effect of the loop bug | The same as the loop bug |
| `Failed to update app list` or `FetchLaunchableApplicationsEvent failed` | Warning | A Companion protocol timeout. The power state and app list are unavailable. | It usually resolves on the next reconnect. |
| `Could not fetch SystemStatus` or `FetchAttentionState failed` | Warning | The same protocol timeout | It usually resolves on the next reconnect. |

Group all Apple TV errors into one report item per device.

## Bermuda BLE (`custom_components.bermuda`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Calling process_advertisement on a metadevice … is a bug` | Warning | A Bermuda tracker bug with Everything Presence Lite devices | Check HACS for a Bermuda update. |

## Hive (`apyhiveapi`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Failed to fetch devices` | Warning | Intermittent Hive cloud connectivity | Monitor, and check the Hive service status page. |
| `Hive API request timed out` | Warning | Intermittent Hive cloud connectivity | Monitor, and check the Hive service status page. |

The hub entity usually still shows `on` during API failures. Check
`binary_sensor.*_hive_hub_status`. A Hive config entry that failed to set up is a different
fault, covered in [_Hive_](../../../../maintenance.md#hive).

## Deebot and Ecovacs (`deebot_client`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Connection lost; Reconnecting in 5 seconds …`, 50 times or more | Warning | The Ecovacs cloud MQTT connection is flapping, which is usually transient | Monitor. If it persists, re-authenticate in **Settings**, **Devices & Services**. |
| `504 Gateway Time-out` from `portal-eu.ecouser.net` | Warning | An Ecovacs cloud outage | Monitor the cloud status. |
| `Could not execute command … Timeout reached` | Info | A per-command cloud timeout during an MQTT outage | It resolves when MQTT reconnects. |

## AirGradient (`homeassistant.components.airgradient`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Error fetching AirGradient <IP> data: Timeout occurred` | Warning | The device at that address is intermittently unreachable | Reserve a DHCP address for the device's MAC, and check its WiFi signal. |

Home Assistant caches the last known values, so the entities can show valid readings while the
device is intermittently offline. To confirm, check `last_updated` on an entity such as
`sensor.*_airgradient_carbon_dioxide`.

## Z-Wave JS (`homeassistant.components.zwave_js.services`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `This service is deprecated in favor of the ping button entity` | Warning | Something calls `zwave_js.ping`, which a later Home Assistant version removes | Find the caller with `ha_search(query="zwave_js.ping")`, and replace the call with `button.press` on the `button.*_ping` entities. |

## ChimeTTS (`custom_components.chime_tts`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Unable to generate local audio filepath` | Warning | ChimeTTS cannot find or write an audio file | Check the ChimeTTS integration config, and check that the audio path is writable. |
| `expected str for dictionary value @ data['say']['fields']['chime_path']` | Info | A `services.yaml` parse issue in the installed ChimeTTS version | A HACS update is the likely fix. |

## Automations (`homeassistant.components.automation.*`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `extra keys not allowed @ data['kelvin']` | Critical | The `kelvin` parameter of `light.turn_on` was renamed `color_temp_kelvin` | Find the automation action that passes `kelvin` and rename the parameter. |
| `extra keys not allowed @ data[...]`, any key | Critical | A service schema changed, and an automation passes a removed or renamed parameter | Read the automation's traces to find the action, and fix the parameter. |

## Netatmo (`homeassistant`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `ValueError: Handler is already defined!` from `netatmo.__init__` | Info | The webhook registers twice on restart | Harmless. No action. |

Netatmo sensors that stay `unavailable` after a restart are a different fault, covered in
[_Netatmo_](../../../../maintenance.md#netatmo).

## Roomba (`homeassistant.components.sensor`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Platform roomba does not generate unique IDs. ID dock_tank_level_… already exists` | Info | Home Assistant drops a duplicate sensor ID | Cosmetic. The duplicate sensors are not created. |

## Frontend and WebRTC (`frontend.js.modern.*`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `InvalidStateError: Failed to read the 'buffered' property from 'SourceBuffer'` | Info | A WebRTC camera playback glitch on Android Chrome | Cosmetic. To cut the noise, set the `frontend` log level to WARNING in **Settings**, **System**, **Logs**. |
| `RangeError: offset is out of bounds` in `video-rtc.js` | Info | The same WebRTC glitch | The same as the `SourceBuffer` error |

These errors accumulate to counts above 100,000. Don't escalate them.

## Nabu Casa remote access (`hass_nabucasa.remote`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Can't connect to SniTun server … Try again` | Warning | A brief remote access interruption | It usually resolves without action. If it persists, check the Nabu Casa status page. |
| `Timeout error while pinging peer` | Info | One timeout during a remote connection | Harmless if infrequent |

## LinkPlay media players (`homeassistant.components.media_player`)

| Pattern | Severity | Interpretation | Action |
|---|---|---|---|
| `Updating linkplay media_player took longer than the scheduled update interval 0:00:05` | Info | A slow response from an Arylic speaker | Harmless if infrequent. If it persists, check the speaker's WiFi. |
