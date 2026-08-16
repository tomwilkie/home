# Wake Routines

How the morning is scheduled: one wake-time helper, its three consumers, and a
separate early-flight path for the mornings when a flight forces a much earlier
shower.

## `input_datetime.wake_up_time` — the single wake time

One helper holds "what time do I get up tomorrow". Three automations read or
write it, and they are coupled — changing it does considerably more than set an
alarm.

| Automation | Direction | Behaviour |
|---|---|---|
| `automation.reset_wake_up_time` | writes | At **17:00 daily**, sets `wake_up_time` from `input_datetime.weekday_wakeup_time` (07:00) on Sun–Thu evenings, or `input_datetime.weekend_wakeup_time` (08:00) on Fri/Sat evenings. So any manual override is self-cleaning — it survives one morning, then reverts. |
| `automation.synchronise_alarm_time` | **two-way** | Mirrors `wake_up_time` ↔ `time.master_bedroom_clock_alarm_time` (the ESPHome bedside clock). Setting either sets the other. The context guards on both branches stop the two sides ping-ponging. |
| `automation.morning_hot_water` | reads | `hive.boost_hot_water` for 1 h, at **`wake_up_time` − 1 h**. A second `state` trigger re-fires it if `wake_up_time` is *changed* to a value whose boost window has already started, so a late override still gets hot water. |
| `automation.wake_up_routine` | reads | Fires **at** `wake_up_time`: air purifier for 1 h, a 30-minute light sunrise in the master bedroom, opens the shutters, stops the white noise, and (Mon–Thu) starts every Roomba in an unoccupied area. |

> **`wake_up_time` is not just an alarm — it is the whole morning.** Because of
> the sync and the wake routine, moving it also moves the bedside alarm, opens
> the shutters and starts the vacuums. That is exactly why the early-flight
> routine below does **not** touch it.

## Early flight hot water

`automation.early_flight_hot_water` turns the hot water on an hour before an
unusually early, flight-driven shower — and **only** the hot water. The alarm,
the shutters and the vacuums stay on their normal schedule, because on a 04:00
start the rest of the routine is unwanted (and the Roombas would wake the house).

### Reading the flight from the calendar

`calendar.tom_wilkie_s_personal_calendar` receives flight events created
automatically by Gmail from booking confirmations:

```
summary:  "Flight to Stockholm (BA 770)"
start:    2026-08-17T07:05:00+01:00
location: "London LHR"
```

The `location` is the **departure** airport — `London LHR` outbound,
`Stockholm ARN` on the return leg — which is what distinguishes a flight leaving
home from one bringing you back.

> `calendar.tom_grafana_com` (work) returns events with **blank summaries**, so it
> cannot be used for this. Personal calendar only.

### Triggers

| id | Trigger | Purpose |
|---|---|---|
| `schedule` | `calendar` event start, **offset `-12:00:00`** | Fires 12 h before *every* event on the personal calendar (19:05 the previous evening for an 07:05 departure); the conditions filter it down. |
| `boost` | `time` at `input_datetime.flight_hot_water_time` | Does the actual `hive.boost_hot_water`. |
| `catchup` | `homeassistant` start | Re-runs the boost if it was missed in the last 20 min — see [the 04:00 hole](#the-0400-restart-hole). |

**Why precompute into a helper instead of boosting straight from the calendar
trigger?** A calendar `offset` is a static string and cannot track the
configurable lead time, and a `delay`/`wait_for_trigger` left running overnight
is destroyed by `automation.restart_home_assistant_at_4am_every_day`. Writing the
boost time into an `input_datetime` (with **date as well as time**, so it fires
exactly once and a stale past value can never re-fire) and firing a plain `time`
trigger on it is restart-proof.

### The filter

A single template condition — no native condition can read
`trigger.calendar_event`. It requires **all** of:

- `flight` in the summary (case-insensitive)
- `location` matching `LHR|LGW|STN|LTN|LCY` → departs from home
- a **timed** event, not all-day (`':' in start`)
- **the flight is genuinely early** (below)
- the computed boost time is still in the future

### The "early" guard

Without it a 16:00 departure would schedule a pointless boost at 12:00. The rule
is *only act when the flight forces a shower earlier than you'd normally get up*:

```
shower_time = departure − input_number.flight_lead_time
normal_wake = weekend_wakeup_time if the flight day is Sat/Sun else weekday_wakeup_time
act only if shower_time < normal_wake
```

| Departure | Shower | Normal wake | Result |
|---|---|---|---|
| 07:05 | 04:05 | 07:00 | **act** — boost at 03:05 |
| 16:00 | 13:00 | 07:00 | skip — the normal routine covers it |

> It reads the **source** helpers (`weekday_wakeup_time` / `weekend_wakeup_time`),
> not `wake_up_time`. `wake_up_time` is rewritten at 17:00 and a −12 h calendar
> trigger can land either side of that depending on departure time, so reading it
> would be racy. The weekday/weekend split mirrors `reset_wake_up_time`'s own
> logic: a Sat/Sun *morning* is the one set from `weekend_wakeup_time`.

### Lead time

`input_number.flight_lead_time` (hours, default **3.0**, on the Settings
dashboard) is departure → shower: 2 h 30 to get to Heathrow plus 30 min to shower
and dress. The boost is one hour before that:

```
boost_time = departure − (flight_lead_time + 1) hours
```

Tune it per-trip on the dashboard rather than editing the automation. A
short-haul from a nearer airport wants a smaller value.

### The 04:00 restart hole

`automation.restart_home_assistant_at_4am_every_day` bounces HA at 04:00, which
would swallow a `time` trigger firing at 04:00–04:02 (a departure around 08:00).
The `catchup` trigger re-runs the boost on HA start if `flight_hot_water_time`
fell within the previous 20 minutes.

### Notification

The schedule branch calls `script.annouce` with **`speak: false`** — a persistent
UI notification the evening before ("BA 770 departs 07:05. Hot water on at 03:05,
shower from 04:05.") with no spoken announcement over the speakers. See
[notifications.md](notifications.md) for the `speak` field.

### Gotchas

- **A hand-typed flight event needs a London airport code in its `location`**, or
  it will not be picked up. Gmail-created events get this for free.
- `automation.morning_hot_water` still boosts at 06:00 on a flight morning as
  usual. Harmless, and deliberately left alone — the house is still occupied.
- Only flights on **`calendar.tom_wilkie_s_personal_calendar`** are seen.
