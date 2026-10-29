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

### 2026-10-17: Nursery network for the eufy baby camera

The eufy baby camera and monitor in the nursery were on the `iot` SSID. Traffic Flows and the
firewall log showed both talking only to eufy's cloud: HTTPS to `care-app-eu.eufylife.com` and
UDP to three AWS relay addresses on port 32100, the ThroughTek Kalay protocol, plus LAN streaming
from the phones, which `LAN to IOT` allows. There was no gateway-visible traffic between the two
devices, and the monitor moved about 150 KB a day, which is not video. The likely reading is that
the monitor receives video over the devices' own 2.4 GHz radio and uses WiFi only for the cloud.
Neither device appeared in the AdGuard query log, which is #2.

To let the pair talk locally, a `nursery` SSID with Client Device Isolation off was created on
the IOT VLAN and both devices moved to it. That reopened a gap: an unisolated wireless client on
the IOT VLAN reaches the wired IOT devices, because switch-port isolation only blocks traffic
between isolated ports. The fix was a Nursery network (VLAN 5, `192.168.5.0/24`) in the IOT zone,
the SSID repointed at it, a logged `Block IOT Inter-Network` policy as the auditable copy of the
predefined intra-zone block, and the DNAT redirect script extended to `br5`. Creating the network
through the MCP server rejected `mdns_enabled` as read-only, so the network came up with mDNS
reflection on. After the SSID move, the monitor's flows carried a second source address,
`192.168.32.222`, on about half its relay keepalives, which looks like the monitor's own pairing
interface leaking out of its WiFi uplink; harmless, but worth knowing if it misbehaves.

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

### 2026-06-25: alerts never delivered

Every alert rule was healthy and evaluating, but the only contact point,
`grafana-default-email`, still held Grafana's placeholder address `<example@email.com>`. No
alert had ever reached an inbox, including the `IOT DNAT redirect removed` test that had been
recorded as emailed. A provisioned `email receiver` contact point was created and the default
notification policy repointed to it. `grafana-default-email` was left in place, unreferenced.

### 2026-10-01: U5G Max modem resets

The U5G Max's cellular modem (a Sierra Wireless EM9291) hangs and reboots itself, typically on
weekday mornings, and keeps no crash dump. The `U5G Max modem reset` alert in
[observability.md](observability.md#u5g-max-modem-reset) counts the resets. The state of the
investigation on 2026-10-01 was as follows:

- **Onset.** No modem resets from 2026-07-02 to 2026-08-04. The first was on 2026-08-05, four days after the U5G upgraded from 7.4.1 to 7.5.3, which left the modem firmware (`SWIX65C_02.17.08.00`) unchanged. There were 75 resets from then to 2026-09-25.
- **Pattern.** 36 of the 75 fell between 08:00 and 10:00, nearly all on weekdays (Fri 23, Thu 19, Sat 4, Sun 1). Load-balanced, the rate was 1.49 a day, with a reset on 61% of weekdays. As backup only, from 2026-09-20, it fell to 0.42 a day and 22% of weekdays, but four of the five resets as backup came with the link idle.
- **Ruled out.** Signal (SINR 12 to 17 dB, transmit power about 15 dBm), heat (43 °C), PoE (the U5G is not powered by the AP's passthrough port) and cell switching (about 260 a day, peaking at 13:00 to 16:00, not in the morning).
- **Change.** On 2026-10-01 the U5G went to Early Access 8.0.2 by manual firmware URL, which updated the modem to `SWIX65C_03.04.10.01`. After the update, SINR on the same n78 cell reads 0 to 3.5 dB, with RSRP and RSRQ unchanged, which may be a reporting change. A 30-ping test over `wwan0` showed no loss and a 42 ms average.
- **Plan.** Keep the U5G as backup for a week. If no resets occur, return it to load balancing for at least two weeks, the condition that produced most resets. Compare the 07:52 speed test over `gre1` (`unpoller_device_speedtest_download{port="if!gre1"}`, 314 Mbps before the upgrade) to tell a SINR reporting change from a real loss. If the radio is worse or the resets continue, roll back to 7.5.3, which is cached on the UDM.

### 2026-10-29: eBPF profiling ruled out

The first attempt at continuous profiles of Home Assistant Core used Alloy's `pyroscope.ebpf`,
targeted at the `homeassistant` container. The HAOS kernel (6.18.52-haos) has BPF syscalls,
perf events, kprobes and uprobes, but neither BTF nor the BPF JIT. Three errors followed in
turn:

- **Kernel symbols.** `unable to read kallsyms addresses`. With `perf_event_paranoid` at 2, the kernel hides addresses without `CAP_SYSLOG`. Adding the capability fixed it.
- **Locked memory.** `failed to set temporary rlimit`. Setting `ulimits: memlock: -1` in the compose file fixed it.
- **Syscall tracepoints.** `open /sys/kernel/tracing/events/syscalls/sys_enter_bpf/id: no such file or directory`. The kernel is built without `CONFIG_FTRACE_SYSCALLS`, and HAOS offers no way to change the kernel.

The change was rolled back, including the extra capabilities (`SYS_ADMIN`, `BPF`, `PERFMON`,
`SYSLOG`). The same day, the `ha-pyroscope` integration replaced it, profiling from inside the
process and pushing through Alloy, as described in
[_Home Assistant profiles_](observability.md#home-assistant-profiles).

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

### 2026-10-04: Living Room lights stayed on all morning

The lights came on at 07:04, inside the night window. From 07:53 the Apple TV reported `playing`
(NOW, Sky Sports F1), the presence sensor held `on` and motion kept firing, so the occupancy
group never went `off` and the turn-off never ran. The window closed at about 08:05 with nothing
watching it, and the lights stayed on until they were turned off by hand at 11:05. The
`daylight` trigger was added to the blueprint as the counterpart of `darkness_fell`.

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

The cause is in the integration, confirmed against the 2026.8.3 source and present in 2026.9.3:

1. `NetatmoDataHandler.async_setup()` fetches the account topology once.
2. The fetch swallows `pyatmo.ApiError` and logs it at `DEBUG`, so a failure does not raise.
3. `async_dispatch()` creates entities by iterating `account.homes`. If the fetch failed, that is empty, and no entities are dispatched.
4. `async_dispatch()` is called only from `async_setup()`, so polling cannot repair it.

The only visible sign was a different call a few seconds later, which logged at `ERROR`:
`Error during webhook registration - 503 - Service Unavailable`. A 503 with code 27 is Netatmo's
backend being unhealthy, not a quota. The fix belongs upstream: `async_setup()` needs to raise
`ConfigEntryNotReady` when the topology fetch fails.

- **2026.9.3 logs the first fetch error at `INFO`** (`Error while fetching %s data`) with a matching recovery line, which makes the failure visible.
- **[core#181448](https://github.com/home-assistant/core/issues/181448) does not apply.** 2026.9.0 drops every entity when a Netatmo `Home` device is disabled. This instance has no `Home` device. Check again before an upgrade if that changes.

### 2026-09-20: Hive outage

The house had no hot water or heating for six hours. The 04:00 restart hit a five-second read
timeout to `sso.hivehome.com` during Hive's setup, and the entry landed in `SETUP_ERROR` until a
manual reload at 09:59. `automation.morning_hot_water` fired at 07:00 and failed in 2 ms:

```
07:00:01 ERROR [automation.morning_hot_water] Morning Hot Water: Error executing
script. Service not found for call_service at pos 1: Action hive.boost_hot_water not found
```

The following upstream defects combined:

1. **`getLoginInfo` returns `None` on a timeout.** `requests.ReadTimeout` subclasses `OSError`, which the library catches and logs, and `async_init` then raises `AttributeError`. [Pyhive #145](https://github.com/Pyhass/Pyhive/pull/145) fixes it but was unreleased, and core pinned `pyhive-integration==1.0.9`. With #145 released, the crash becomes `HiveUnknownConfiguration`, which is still uncaught and still not retried.
2. **Core catches an exception that cannot be raised.** `async_setup_entry` handles `HiveReauthRequired` and a server-side `HTTPException` class, so every other failure becomes `SETUP_ERROR`. This is [core#182752](https://github.com/home-assistant/core/issues/182752).
3. **Every startup forces a fresh sign-in.** In [Pyhive #123](https://github.com/Pyhass/Pyhive/issues/123), `tokenCreated` defaults to `datetime.min`, so stored tokens read as expired, and a restart calls the sign-in endpoint with a five-second timeout.

While the watchdog was being tested, a reload of the loaded entry wedged it in `FAILED_UNLOAD`,
and a plain reload from the UI wedged it again that evening. `async_unload_entry` unloads the
full platform list, this house has no Hive lights, unloading `light` raises, and the entry lands
in `FAILED_UNLOAD` ([core#182753](https://github.com/home-assistant/core/issues/182753)).
[core#176594](https://github.com/home-assistant/core/pull/176594) makes the unload failure
non-fatal from 2026.10. The first version of the watchdog had no `continue_on_error` on the
reload, so it failed silently every 15 minutes for six hours. `fan.master_bedroom_dyson_fan` was
seen with `restored: true` while its `dyson_local` entry was loaded, which is why every watched
entity must be a stub.

`automation.morning_hot_water` gained its `hive_recovered` and `ha_start` catch-up triggers the
same day.

## Naming

### July 2026: redundant name overrides

A sweep found 54 overrides where `name` equalled `original_name`. All were cleared, which
restored the composed names.

The Hive device was renamed from `Hallway - Thermostat` to `Hallway - Hive`, which changed
`climate.hallway_thermostat` from `Hallway - Thermostat Thermostat` to
`Hallway - Hive Thermostat`.

### 2026-07-18: Kitchen Deebot moved to Matter

The Ecovacs cloud integration broke on a server-side auth error (`1013`, "Please update to the
latest version"), a global outage awaiting upstream
[DeebotUniverse/client.py#1706](https://github.com/DeebotUniverse/client.py/pull/1706). The
Kitchen Deebot X9 Pro Omni was moved to a local Matter connection. The Matter entity was renamed
to take back `vacuum.kitchen_vacuum`, so the dashboards, `input_datetime.kitchen_vacuum_last_run`
and the vacuum automations needed no edits. The `history_stats` sensor
`sensor.kitchen_vacuum_cleaning_time` was deleted with the Ecovacs entry and was re-created
through the config flow, which produced a mangled entity ID until it was renamed.

### 2026-08-22: UniFi tracker cleanup

A sweep removed 382 UniFi trackers, taking the entity registry from 633 to 251 entries: 355 with
private MACs, 23 ghosts from the camera ports and 4 aged-out clients. The pre-sweep registry is
backed up at `/config/core.entity_registry.bak-privatemac` on the Home Assistant host. The same
day, 12 trackers with doubled names got a name override and were renamed area-first with a
`_unifi` suffix.

### 2026-10-28: Hive names compose

The `tomwilkie/ha-hive` fork was a legacy integration with `has_entity_name: false`, so it
built each `friendly_name` itself. The v0.1.4 battery sensor arrived as `Thermostat Battery
Level`, and a bare `Battery Level` override stripped the device name instead of composing it.
v0.1.5 set `has_entity_name` on every entity and gave each a bare name: `None` for the climate
entity, `Hot water` for the water heater, `Battery level` and `Boost` for the sensors. After the
upgrade the `Battery Level` and `Boost` overrides were cleared, and the device went back from
`Hallway - Hive` to `Hallway - Thermostat`, because the stutter that forced the July rename was
gone. `climate.hallway_thermostat` now displays as `Hallway - Thermostat` and
`water_heater.hallway_thermostat` as `Hallway - Thermostat Hot water`.

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

### 2026-10-12: onward flight overwrote the early boost

Two flights sat on the calendar for the same morning: "Flight to Paris (DL 8307)" from London
LHR at 06:15, and "Flight to San Francisco (DL 8726)" from Paris CDG at 09:20. At 18:15 the
`schedule` trigger ran for the Paris flight, passed the filter and set
`input_datetime.flight_hot_water_time` to 02:15. At 21:20 it ran for the San Francisco flight,
also passed the filter and overwrote the helper with 05:20. Because `script.annouce` uses the
slugified title as the `notification_id`, the second notification replaced the first, so only
the San Francisco flight was visible. The 02:15 boost never ran, and Tom boosted the water by
hand at 02:45.

### 2026-10-17: heartbeat moved to the nursery sleep routine

The heartbeat track had played from `automation.turn_bedroom_lights_on_before_sunset` at 20:00
or sunset and stopped in `automation.wake_up_routine`'s "Fade out the white noise" branch, first
on the master bedroom HomePod and, after the HomePod moved to the Nursery, on the nursery one.
Those steps were removed, and `automation.nursery_sleep_routine` took them over, keyed on
`input_boolean.kiran_asleep` so that bedtime no longer followed sunset or the parents' wake
time. The same change took `light.nursery_rocket_lamp` out of the Nursery adaptive lighting
instance and set `select.nursery_hue_go_power_on_behavior` to `previous`.

Two faults combined:

- The airport check was `regex_search(...) is not none`. Home Assistant's `regex_search` returns
  `True` or `False`, never `None`, so the comparison was always true and the check had never
  excluded anything. A live render confirmed it: `'Paris CDG' | regex_search('LHR|LGW|STN|LTN|LCY')`
  gives `False`, and `False is not none` gives `True`.
- The automation kept one helper and wrote it on every passing run. The `schedule` trigger
  fires 12 hours before each event, so the later flight's run always came last.

The fix dropped `is not none`, added an earliest-wins condition and put the event summary in
the notification title. The rules are in
[_Filter_](wake-routines.md#filter) and [_Notification_](wake-routines.md#notification).
