# History

This file records how the rules in the other documents came about: incidents, outage timelines,
test-run results and superseded designs. `CLAUDE.md` does not import it, so it stays out of
context unless you read it on purpose. The other documents state the current design. If this
file and another document disagree, the other document wins.

Entries are dated records, grouped by area, oldest first within each area.

## Network security

### VLAN moves

The back-garden camera moved off the main network onto the Cameras VLAN (`192.168.3.211`) so
that the camera containment rules apply to it.

The Hive Hub moved off the main network onto the IOT VLAN (`192.168.2.125`, DHCP, wired on
`Basement Switch` port 8, port isolation on). The Hive integration is cloud-only, so the hub
needs only internet access and no Home Assistant exception. During the move, reassigning the
port's VLAN did not drop the link, so the hub kept its old-subnet lease and lost its gateway.
Bouncing the switch-port link forced a fresh lease, and a manual power-cycle made the hub
register with its cloud again.

### Containment blocks dropped return traffic

UniFi created `Block IOT to LAN` and `Block Cameras to LAN` with `connection_state_type: ALL`.
That dropped the `ESTABLISHED` and `RELATED` returns of LAN-initiated flows and silently broke
Internal to IOT for every main-LAN host except Home Assistant, which survived because its allow
sat above the block at index 10000. AirPrint to the HP printer on the IOT VLAN failed while Home
Assistant worked. The LAN client's SYN reached the device and the device answered, but the reply
was dropped and the flow hung in `SYN_RECV`. Setting both blocks to `CUSTOM` with `NEW` and
`INVALID` fixed it with containment intact.

### Public DNS and the first DNS blocks

IOT devices were found going directly to public DNS (8.8.8.8, 8.8.4.4, 1.1.1.1, 1.0.0.1,
9.9.9.9, 149.112.112.112 and others), including DoH on port 443, bypassing the gateway resolver,
so their lookups did not reach CoreDNS and could not be logged. Two BLOCK rules were added above
the ALLOW. Several devices, including the Hive Hub (`.125`) and the Kitchen Display (`.18`),
retried public DNS rather than falling back, and had degraded resolution until the DNAT redirect
gave them a local answer.

At that time UniFi's Insights Flows, and the `unifi_get_traffic_flows` tools, returned only
blocked flows on this console, even for a custom ALLOW with logging, so the logged ALLOW and the
syslog pipeline to Loki were built to capture per-flow destinations.

### Public NTP

IOT devices were sending about 100 flows an hour to public NTP. The worst were the Prusa camera
(`.67`), the WiiM (`.10`) and the two aircons, which poll public servers whatever DHCP says.
chrony, DHCP option 42, the udp port 123 redirect and `Block IOT NTP to Internet` followed. The
redirect was verified by the WiiM and the Prusa camera appearing in chrony.

### DNAT redirect

An earlier note, based on Scott Helme's same-subnet Pi-hole example, said the redirect needed
MASQUERADE. It does not, because the target is on a different subnet.

The drift alert was tested by removing the DNAT: the alert fired, then resolved on restore.

The catch-all ALLOW has been deleted and re-created twice to put it last again, when the NTP
block and then the No-Internet block were added. Its earlier policy IDs were
`6a3502dc2753ee32cc1f2955` and `6a3676352753ee32cc2398b6`.

### Per-device block: the OON design that did not enforce

The per-device block was first built as a MAC-based client group (`IOT - No Internet`) and an
OON policy with `secure.internet.mode: TURN_OFF_INTERNET`. It was configured correctly, with
every MAC and the clients tagged into the group, and it did not enforce. OON-generated rules are
predefined, so the block landed at index 30001, after the custom catch-all ALLOW at index 10005,
which matched every packet first. The schedule was not the cause: the rules were
`schedule: null`. The OON policy and the client group were deleted and replaced with the custom
client-MAC rule.

The WAN drop was verified for the original 12 devices: no hits in
`{log_type="firewall", rule="Log IOT to Internet (ALLOW)"}`, active drops in
`{log_type="firewall", rule="Block IOT No-Internet Devices"}`, and the aircons and Norman
shutters still responsive.

At the time, `unifi_create_firewall_policy` failed with `redact_sensitive_fields() got an
unexpected keyword argument 'include_sensitive'`, so the rule was created through the raw v2
API.

### 2026-09-19: AirGradient removed from the block

Tom's Office - AirGradient (`.177`, `34:b7:da:9f:7e:10`) was in the original block list, because
its Home Assistant path is the local API. It was removed to restore its internet access.

### 2026-10-01: Checks made during the docs clean-up

- `unifi_create_firewall_policy` and `unifi_delete_firewall_policy` worked on `unifi-network-mcp` 0.20.9, tested with a disabled throwaway policy. The preview accepted a `CLIENT` MAC source. The reorder tool was not retested.
- `unifi_get_traffic_flows` returned allowed and blocked flows for the IOT network, including allowed local flows with no policy attached.
- The IOT network's DHCP DNS server and NTP server were both `192.168.0.12`.
- The port 53 and port 123 blocks had no hits in seven days, and Traffic Flows showed IOT DNS flows to public resolvers marked `local` and allowed, which is the redirect at work.

## Observability

### Unpoller discovery vanished

The unpoller keep rule was `/addon_[a-z0-9]+_unpoller`. After the Supervisor renamed the
container prefix from `addon` to `app`, it matched nothing and
`up{job="integrations/unpoller"}` disappeared, with no error, no `up == 0` and nothing in the
Alloy log. It went unnoticed for months: a check on 2026-09-30 found no unpoller series in 120
days. The same rename leaked `app_<repo>_` into every Docker `service_name`. The fix and the
`Exporter down` alert followed.

### Temperature dashboard axis

Device self-heat sensors read 26 to 57 °C against 22 to 28 °C rooms and compressed the y-axis.
Master Bedroom stretched to 42.8 °C for the clock's board temperature.
`basement_washing_machine_door_temperature` is the one self-heat sensor without the `device_`
prefix, hence the `door_temperature` exclusion.

### AdGuard query log batching

At the default `size_memory: 1000`, AdGuard flushed the query log about hourly, so Loki received
it in hourly batches. `size_memory: 0` gives about 24,000 to 36,000 small appends a day.

## Notifications

### 2026-08-17 and 2026-08-22: appliance helpers reset by `initial`

Both appliance helpers carried `initial: idle`, so the nightly restart reset any cycle in flight
and the "finished" notification was lost: `washing_machine_state` went `running` to `idle` at
04:00:31 on 2026-08-17, and `tumble_dryer_state` went `active` to `idle` mid-cycle at 04:00:15
on 2026-08-22.

### 2026-08-19: HomePod announcement killed the sleep sound

The notification players group originally held native entities. A tumble-dryer announcement was
delivered to `media_player.master_bedroom_homepod_mini`, the native `apple_tv` entity for the
speaker that Music Assistant was streaming the sleep sound to. An `apple_tv` HomePod does not
advertise `MEDIA_ANNOUNCE`, so ChimeTTS replaced playback: the announcement took the AirPlay
output and the HomePod did not return to Music Assistant's stream. Music Assistant is
fire-and-forget on its `cliraop` process, so it did not notice. Its process stayed alive, its
queue kept advancing, the dashboard read `playing`, and `pause` and `play` could not recover a
session that was never torn down.

The group moved to the Music Assistant proxies. That left three toggles behind
(`kitchen_display`, `living_room_arylic_lp10`, `master_bedroom_homepod_mini`), because the
proxies' toggles carry the `_ma_player` suffix. They were deleted.

### Doorbell webhook stopped delivering

The Protect "Ring" rule originally pointed at the external Nabu Casa URL, which sent every ring
out to the internet and back. That path stopped delivering: no webhook reached Home Assistant
for more than seven days, consistent with the 2026 UniFi Alarm Manager and Protect 7.x
transition. The native `doorbell` trigger was added as the primary path, and the rule was
pointed at the LAN address.

### 2026-09-20: `notify_on_automation_failure` was dead code

With no `system_log:` block, `system_log_event` was never fired, so the automation had not
triggered since 2026-08-16. The Hive hot-water failure that morning produced no notification,
and the first sign was a cold shower. `fire_event: true` was added, with `script.annouce` and
`automation.notify_on_automation_failure` added to the exclusion list. Both exclusions were
verified by firing synthetic events from those loggers and confirming that `last_triggered` did
not move.

## Dashboards

### Kitchen display memory leak

The three `custom:webrtc-camera` cards were set to `background: true`. Three permanent H.264
decoders and three peer connections leaked the Fully Kiosk WebView at about 600 MB a day:
`sensor.kitchen_display_free_memory` fell from 2634 MB to 876 MB over three days without
recovering, and the browser froze after a few hours.

### Music Assistant proxies re-created

Seen twice. In June 2026 the Living Room proxy came back as
`living_room_arylic_lp10_music_assistant`. In September 2026 both Arylic LP10 proxies were
re-created as `media_player.dining_room` and `media_player.toms_office`.

## Lighting

### 2026-09-20: Tom's Office adaptive lighting was dead

The instance's `lights` held four pre-rename IDs: `light.elgato_key_light`, `light.nano_dimmer`,
`light.tom_s_office_light_3d_printers` and `light.tom_s_office_desk_lamp`. It had adapted
nothing since the rename. It surfaced when a `min_brightness` change was rejected with
`entity_missing`. Submitting a single known-good light through `ha_set_integration` returned the
same error, which showed that the tool does not pass `lights`. It was repaired in the UI the
same day, and all six instances were swept: none of 18 lights was missing.

`min_brightness` was raised from 10 to 25 on the same day.

### 2026-09-20: Living Room lights did not come on

`use_sun` was a condition only. Occupancy had been `on` since 15:24, the window opened at 18:03,
and `last_triggered` still read 07:36 with every stored trace `failed_conditions`. The
`darkness_fell` trigger was added to the blueprint, which fixed the three `use_sun: true` rooms
(Living Room, Nursery, Rear Guest Room) at once. Basement and Tom's Office render the trigger
`enabled: false`.

## Maintenance

### 2026-08-02: commissioning run of the restart sweep

Triggered by hand on a Sunday, so only the daily block ran.

- All seven iterations fired exactly 20 seconds apart (15:53:20 to 15:55:21 UTC).
- The weekly and monthly blocks skipped (`now_weekday: "sun"`).
- Hallway - Doorbell went from 77.8 days of uptime to 23 seconds.
- Living Room Arylic blipped `unavailable` to `idle`.
- All three `assist_satellite` entities returned to `idle`, and the Voice PEs came back at `volume_level: 1.0`.
- The Nursery WiiM press failed, and `continue_on_error: true` let the sweep finish.

Devices had been reaching more than 75 days of uptime. The Kitchen - Boiler Monitor was at 77
days. Two of the three Voice PE restart buttons shipped `disabled_by: integration` and were
enabled. `automation.restart_audio_streamers`, which restarted the two Arylic LP10s at 09:00
from a hardcoded list, was deleted and absorbed into the sweep.

### Nursery WiiM restart

On `linkplay`, the WiiM's restart button failed every time with
`LinkPlayRequestException: Didn't receive expected OK from https://192.168.2.10`. The speaker
(`project: WiiM_Sound`, firmware `Linkplay.5.2.813247`) answers `unknown command` to the
`reboot` httpapi command. Upstream:
[Velleman/python-linkplay#121](https://github.com/Velleman/python-linkplay/issues/121), open
since 2025-08-02, where commenters found `StartRebootTime:1`.

The speaker was for a while adopted by both `linkplay` and `wiim`, giving one device two native
`media_player` entities plus the Music Assistant proxy. The `linkplay` entry was removed. `wiim`
adds `NEXT_TRACK`, `PREVIOUS_TRACK` and `SEEK` and loses only `SELECT_SOUND_MODE`.

### Netatmo outages

Every outage began at 03:00 UTC, the 04:00 BST restart, and every recovery coincided with a
later restart or a manual reload. The long-term statistics gaps were identical across the base
station, the outdoor module and the three indoor modules, which ruled out radio, battery and
WiFi.

| Outage start (UTC) | Recovered | Duration |
|---|---|---|
| 2026-09-05 03:00 | 09-05 20:00 | 16 h |
| 2026-09-07 03:00 | 09-08 03:00 | 23 h |
| 2026-09-09 03:00 | 09-11 03:00 | 47 h |
| 2026-09-12 03:00 | 09-19 05:12 | 169 h |

There were no gaps between 2026-06-21, the start of the 90-day statistics window, and
2026-09-05. The onset is consistent with the move to 2026.8.x, where `UNAVAILABLE_AFTER_ERRORS`
and the publisher `available` flag first appear in the coordinator, but the upgrade date was not
confirmed. During a stranded window the log carried `not ready yet` lines for `roomba`,
`norman_shutters` and `music_assistant` and none for `netatmo`, and `config_entry_setup`
finished in about four seconds.

### 2026-09-20: Hive outage

The house had no hot water or heating for six hours. The 04:00 restart hit a five-second read
timeout to `sso.hivehome.com` during Hive's setup, and the entry landed in `SETUP_ERROR` until a
manual reload at 09:59. `automation.morning_hot_water` fired at 07:00 and failed in 2 ms:

```
07:00:01 ERROR [automation.morning_hot_water] Morning Hot Water: Error executing
script. Service not found for call_service at pos 1: Action hive.boost_hot_water not found
```

While the watchdog was being tested, a reload of the loaded entry wedged it in `FAILED_UNLOAD`,
and a plain reload from the UI wedged it again that evening. The first version of the watchdog
had no `continue_on_error` on the reload, so it failed silently every 15 minutes for six hours.
`fan.master_bedroom_dyson_fan` was seen with `restored: true` while its `dyson_local` entry was
loaded, which is why every watched entity must be a stub.

`automation.morning_hot_water` gained its `hive_recovered` and `ha_start` catch-up triggers the
same day.

## Naming

### July 2026: redundant name overrides

A sweep found 54 overrides where `name` equalled `original_name`. All were cleared, which
restored the composed names.

The Hive device was renamed from `Hallway - Thermostat` to `Hallway - Hive`, which changed
`climate.hallway_thermostat` from `Hallway - Thermostat Thermostat` to
`Hallway - Hive Thermostat`.

## Wake routines

### Sleep sound volume

For months the automation set 0.36 on `media_player.master_bedroom_homepod_mini` before the play
call. Music Assistant reset it to 0.60 about 0.7 seconds later, so the heartbeat played at 0.60
every night. 0.48 was chosen by ear on 2026-09-04.

### 2026-09-19: boost indicator

`binary_sensor.basement_hotwater_boost` went `on` at 07:00:12 and `off` at 08:00:57, bracketing
the one-hour boost, while `water_heater.hallway_thermostat` stayed `off` and
`sensor.basement_hotwater_mode` did not move.

### 2026-09-30: accidental boost during a test

`automation.trigger` with `skip_condition: false` started a real boost, because the wake time
had been moved to 07:45 and the test ran inside the window.
