# Wake routines

This document covers how the morning is scheduled: one wake-time helper, the automations that
read and write it, Kiran's nursery sleep routine, the evening hot water for Kiran's bath, and a
separate path for mornings when a flight forces a much earlier shower.

## The wake time

`input_datetime.wake_up_time` holds the time to get up tomorrow. The following automations read
or write it:

| Automation | Direction | Behaviour |
|---|---|---|
| `automation.reset_wake_up_time` | Writes | At 17:00 daily, sets `wake_up_time` from `input_datetime.weekday_wakeup_time` (07:00) on Sunday to Thursday evenings, or `input_datetime.weekend_wakeup_time` (08:00) on Friday and Saturday evenings. A manual override therefore lasts one morning. |
| `automation.synchronise_alarm_time` | Both | Mirrors `wake_up_time` and `time.master_bedroom_clock_alarm_time`, the ESPHome bedside clock. Setting either sets the other, and context guards on both branches stop a loop. |
| `automation.morning_hot_water` | Reads | Calls `hive.boost_hot_water` at `wake_up_time` minus one hour. |
| `automation.wake_up_routine` | Reads | At `wake_up_time`: runs the air purifier for one hour, runs a 30-minute light sunrise in the master bedroom, opens the shutters, and from Monday to Thursday starts every Roomba in an unoccupied area. |

`wake_up_time` is the whole morning, not an alarm. Moving it moves the bedside alarm, opens the
shutters and starts the vacuums, which is why the early-flight routine does not touch it.

## Morning hot water

`automation.morning_hot_water` boosts for one hour, starting one hour before `wake_up_time`. On
Saturdays the boost lasts 1 hour 30 minutes from the same start time, because the cleaner uses
the hot water on Friday and a one-hour boost left too little for Kiran's Saturday evening bath.
The duration is a template in the action's `data` (`now().isoweekday() == 6`), so the automation
has one `hive.boost_hot_water` step. The bath itself is covered by
[_Evening hot water_](#evening-hot-water).

### Catch-up triggers

The boost is a one-shot service call at one instant, so anything that swallows that instant
loses the boost. The automation calls a Hive service, and when the Hive config entry fails to
set up, that service is not registered. Home Assistant retries a Hive setup that fails on a
transient error, as described in [_Hive_](maintenance.md#hive).

Every trigger is gated on the same window (`wake - 1 h <= now < wake`), so a late recovery
cannot boost for a shower that has already happened:

| Trigger | ID | Covers |
|---|---|---|
| `time` at `wake_up_time` minus one hour | `scheduled` | The normal path |
| `state` on `wake_up_time` | `wake_changed` | A late override into a window that has already started |
| `state` on `water_heater.hallway_thermostat` from `unavailable` | `hive_recovered` | Hive was down at the scheduled instant, and the retried setup brings it back |
| `homeassistant` start | `ha_start` | A restart inside the window |

Two guards make the retries safe:

- **`binary_sensor.basement_hotwater_boost` must be `off`.** This stops a catch-up boosting twice when the scheduled run succeeded and Hive only blipped. It is the reliable indicator of a boost: `water_heater.hallway_thermostat` stays `off` during a boost and `sensor.basement_hotwater_mode` does not change.
- **The water heater must not be `unavailable` or `unknown`.** The automation skips rather than raises, and `hive_recovered` retries after Home Assistant sets the entry up.

`automation.trigger` with `skip_condition: false` is a dry run only outside the boost window.
Inside the window, with the boost sensor `off`, the conditions pass and a real boost starts.
Check `wake_up_time` first, because a manual override moves the window.

## Evening hot water

`automation.evening_hot_water` boosts the hot water from 18:00 to 19:00 every evening, for
Kiran's bath. It copies the morning boost's guards and its `hive_recovered` and `ha_start`
catch-up triggers, as described in [_Catch-up triggers_](#catch-up-triggers), with the window
fixed at 18:00 to 19:00 by a native `condition: time`. The boost length is the time left until
19:00, so a late catch-up still ends on time.

It boosts only if the house was occupied at some point in the last 24 hours, so an empty house
is not heated for a bath. `sensor.house_occupancy_last_24h` is a `history_stats` helper that
counts the hours `binary_sensor.house_occupancy` was `on` over the last 24 hours, and the
condition is that it is above `0`. It reads the recorder, so the 04:00 restart does not reset it
the way it resets a state condition with `for: 24h`.

## Nursery sleep routine

Kiran sleeps in the Nursery from 19:00 to 07:00. `input_boolean.kiran_asleep` is the sleep
state, and the following helpers and automations read or write it:

| Entity | Behaviour |
|---|---|
| `schedule.kiran_sleep` | On from 19:00 to 07:00 every day. |
| `automation.kiran_sleep_schedule` | Copies the schedule's `off` to `on` and `on` to `off` edges onto the boolean. |
| `automation.nursery_sleep_routine` | Runs the bedtime branch when the boolean turns on and the wake branch when it turns off, and turns the Hue Go off at 21:00. |

The boolean, not the schedule, drives the routine, so a nap or an early night is a manual toggle.
Both helpers are on the Settings view of the Settings dashboard.

The bedtime branch does the following, in order:

1. Turns off `automation.nursery_lights`, so motion cannot switch the lamps on overnight.
2. Turns on `switch.nursery_adaptive_lighting_sleep_mode`, then turns on `light.nursery_hue_go`, which adaptive lighting intercepts and sets to its sleep brightness and colour.
3. Turns off `light.nursery_rocket_lamp`.
4. Plays `library://track/129` ("Baby Sleep Heartbeat") on `media_player.nursery_homepod_mini_ma_player`, sets volume 0.48 and `repeat: one`.

The wake branch stops the track, sets `repeat_set: off`, turns sleep mode off and turns
`automation.nursery_lights` back on. Between 05:00 and 09:00 it turns both lamps on for the
morning, and the blueprint's `daylight` trigger turns them off at sunrise plus one hour. At any
other time it is the end of a nap, and it turns both lamps off.

At 21:00 the routine turns `light.nursery_hue_go` off, so the sleep-level night light lasts only
the first two hours of the night.

- **Set the volume after `music_assistant.play_media`, on the Music Assistant proxy entity.** Music Assistant applies its own stored player volume about a second into playback, so a `media_player.volume_set` before the play call, or on the native `apple_tv` entity, is overwritten with no error. The step sits after the play call with a three-second delay.
- **Don't announce to this speaker.** Its notifications toggle stays off, so house announcements never play in the nursery. Never announce through its native `apple_tv` entity either: a replace-mode announcement takes the HomePod's AirPlay output away from Music Assistant, which keeps reporting `playing` into a silent room. Only a fresh `music_assistant.play_media` rebuilds the session. See [_Choose the entity that supports announce_](notifications.md#choose-the-entity-that-supports-announce).
- **The rocket lamp is not in the Nursery adaptive lighting instance.** It is an on/off plug, and sleep mode would switch it on.

- **Set the volume after `music_assistant.play_media`, on the Music Assistant proxy entity.** Music Assistant applies its own stored player volume about a second into playback, so a `media_player.volume_set` before the play call, or on the native `apple_tv` entity, is overwritten with no error. The step sits after the play call with a three-second delay.
- **Don't announce to this speaker through its native `apple_tv` entity.** A replace-mode announcement takes the HomePod's AirPlay output away from Music Assistant, which keeps reporting `playing` into a silent room. Only a fresh `music_assistant.play_media` rebuilds the session. The notification players group therefore uses the proxy, as described in [_Choose the entity that supports announce_](notifications.md#choose-the-entity-that-supports-announce).

## Early flight hot water

`automation.early_flight_hot_water` turns the hot water on an hour before an early,
flight-driven shower, and does nothing else. The alarm, the shutters and the vacuums stay on
their schedule, because on a 04:00 start the rest of the routine is unwanted.

### Flight events

`calendar.tom_wilkie_s_personal_calendar` receives flight events that Gmail creates from booking
confirmations:

```
summary:  "Flight to Stockholm (BA 770)"
start:    2026-08-17T07:05:00+01:00
location: "London LHR"
```

The `location` is the departure airport, which separates a flight that leaves home from one that
returns. A flight event typed by hand needs a London airport code in its `location`.
`calendar.tom_grafana_com` returns events with blank summaries, so only the personal calendar
works.

### Triggers

| ID | Trigger | Purpose |
|---|---|---|
| `schedule` | `calendar` event start with offset `-12:00:00` | Fires 12 hours before every event on the calendar. The filter narrows it to early flights, and the branch writes the boost time to `input_datetime.flight_hot_water_time`. |
| `boost` | `time` at `input_datetime.flight_hot_water_time` | Calls `hive.boost_hot_water` |
| `catchup` | `homeassistant` start | Runs the boost if `flight_hot_water_time` fell in the previous 20 minutes, which covers a boost time inside the 04:00 restart |

The automation writes the boost time to a helper rather than boosting from the calendar trigger
for two reasons. A calendar `offset` is a static string and cannot follow the configurable lead
time. A `delay` or `wait_for_trigger` left running overnight does not survive the 04:00 restart.
The helper holds a date and a time, so it fires once and a stale value cannot fire again.

### Filter

No native condition reads `trigger.calendar_event`, so the filter is one template condition. It
requires all of the following:

- `flight` in the summary, case-insensitive
- A `location` that matches `LHR|LGW|STN|LTN|LCY`
- A timed event, not an all-day one (`':' in start`)
- A shower time earlier than the normal wake time
- A computed boost time in the future

A second template condition makes the earliest flight win: the branch writes the helper only
when the stored boost time has passed or the new boost time is earlier. The `schedule` trigger
fires 12 hours before each event, so on a day with two flights the later flight's run comes
last and would otherwise overwrite the earlier boost with a later one.

Use the result of `regex_search` as the boolean it is. In Home Assistant the filter returns
`True` or `False`, never a match object, so `regex_search(...) is not none` is always true and
the airport check disappears. That is how an onward flight from Paris CDG replaced a 06:15
Heathrow departure's boost, as recorded in
[_2026-10-12: onward flight overwrote the early boost_](history.md#2026-10-12-onward-flight-overwrote-the-early-boost).

The automation acts only when the flight forces a shower earlier than the normal wake time, so
that an afternoon departure does not schedule a midday boost:

```
shower_time = departure - input_number.flight_lead_time
normal_wake = weekend_wakeup_time if the flight day is Saturday or Sunday, else weekday_wakeup_time
boost_time  = shower_time - 1 hour
act only if shower_time < normal_wake
```

A 07:05 departure gives a 04:05 shower and a 03:05 boost. A 16:00 departure gives a 13:00
shower, which the normal routine covers.

The condition reads the source helpers, not `wake_up_time`. `wake_up_time` is rewritten at 17:00,
and a trigger 12 hours before departure can land either side of that.

### Lead time

`input_number.flight_lead_time`, in hours with a default of 3.0, is the time from shower to
departure: 2 hours 30 minutes to reach Heathrow and 30 minutes to shower and dress. Tune it per
trip on the Settings dashboard rather than in the automation.

### Notification

The `schedule` branch calls `script.annouce` with `speak: false`, which leaves a persistent
notification the evening before ("Flight to Stockholm (BA 770) departs 07:05. Hot water on at
03:05, shower from 04:05.") and says nothing over the speakers. The title carries the event
summary, because `script.annouce` slugifies the title into the `notification_id`, and a fixed
title would let a second flight on the same day replace the first flight's notification.

`automation.morning_hot_water` still boosts at its usual time on a flight morning. That is
deliberate, because the house is still occupied.
