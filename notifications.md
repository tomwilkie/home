# Announce Scripts

## `script.annouce`

Delivers a message to the house. Accepts `title`, `message`, and optional `important` fields. Actions:
1. Temporarily lowers Tom's office speaker volume if it is playing
2. Speaks the message via ChimeTTS to all notification players (time-gated: 06:00–23:00, or always if `important: true`)
3. Creates a persistent notification in the HA UI — `notification_id` is derived from `title | slugify` so it can be addressed for later dismissal

## `script.cancel_announce`

Dismisses a persistent notification previously created by `script.annouce`. Accepts a `title` field and calls `persistent_notification.dismiss` using the same `title | slugify` convention. Automations call this script on their dismiss trigger rather than calling the service directly.

---

# Tumble Dryer Automation

## Overview

The tumble dryer system uses a **state helper** to decouple device events from notification. A single automation manages all state transitions; a second automation reacts to state changes and delivers the alert.

---

## Helper: Tumble Dryer State

| Field | Value |
|---|---|
| Entity ID | `input_select.tumble_dryer_state` |
| Type | `input_select` |
| Options | `idle`, `active`, `finished` |
| Initial | `idle` |

Tracks the current phase of a drying cycle. All other automations read or react to this value rather than directly wiring triggers to notifications.

---

## Automation: Tumble Dryer State (`automation.tumble_dryer_state`)

Manages all transitions of the `tumble_dryer_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `start` | `sensor.dryer_bsh_common_status_operationstate` | Operation state → `Run` |
| `finished` | `event.dryer_laundrycare_dryer_event_dryingprocessfinished` | `event_type` attribute → `Present` |
| `door_open` | `event.dryer_laundrycare_common_event_dooropen` | `event_type` attribute → `Present` |

### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`start` trigger** — only if current state is `idle`:
- Sets state → `active`

**`finished` trigger** — only if current state is `active`:
- Sets state → `finished`

**`door_open` trigger** — only if current state is `finished`:
- Sets state → `idle`

The automation runs in `restart` mode — if a new trigger fires while a previous run is still executing, the current run is interrupted and the automation restarts immediately. This ensures a `door_open` event is never queued or dropped if it arrives mid-run.

### Anti-wrinkle guard edge case

After the main drying cycle completes, the dryer runs a short anti-wrinkle tumble (~60 sec). This causes a second `Run → Finished` sequence and fires the `dryingprocessfinished` event again. The state guards prevent any corruption:
- The second `Run` does not flip `finished → active` because the `start` branch requires state = `idle`.
- The second `dryingprocessfinished` event is a no-op because the `finished` branch requires state = `active`.

---

## Automation: Tumble Dryer Notification (`automation.notify_on_tumble_drier_finished`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `tumble_dryer_state` transitions `active` → `finished` | Announce via `script.annouce` (title: "Tumble Drier") |
| `dismiss` | `tumble_dryer_state` leaves `finished` (door opened → `idle`) | Dismiss notification via `script.cancel_announce` |

The `from` guard on the `create` trigger prevents spurious fires on HA restart or unknown state initialisation. The `dismiss` trigger fires on the same `door_open` transition that resets the state helper to `idle`, so the persistent notification is cleared automatically when the user retrieves the laundry.

---

## Flow diagram

```
Dryer starts (Run) ───────────────────────────────────────────────────┐
                                                                       ▼
Drying complete (dryingprocessfinished) ──► Tumble Dryer State ──► input_select.tumble_dryer_state
                                               automation                      │
Door opens ───────────────────────────────► (state guards)            idle → active → finished → idle
                                                                               │
                                                                       active → finished
                                                                               │
                                                                               ▼
                                                               Tumble Dryer Notification automation
                                                               (announce via script.annouce)
```

---

# Front Door Automation

## Overview

The front door system uses a **state helper** to decouple detection from notification. A single automation manages all state transitions; a second automation reacts to state changes and delivers alerts.

---

## Helper: Front Door State

| Field | Value |
|---|---|
| Entity ID | `input_select.front_door_state` |
| Type | `input_select` |
| Options | `Absent`, `Someone at the Door` |
| Initial | `Absent` |

Tracks whether someone is currently at the front door. All other automations read or react to this value rather than directly wiring triggers to notifications.

---

## Automation: Front Door State (`automation.front_door_state`)

Manages all transitions of the `front_door_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `knocking` | `binary_sensor.front_door_vibration_vibration` | Vibration detected (`off` → `on`) |
| `webhook` | Webhook `<your-webhook-id>` | GET request received |
| `door_open` | `binary_sensor.front_door_contact_contact` | Door opens (state → `on`) |

### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`door_open` trigger** — only if current state is `Someone at the Door`:
- Sets state → `Absent`

**`knocking` trigger** — only if current state is `Absent` AND `front_door_contact_contact` has been `off` for ≥ 1 minute (door was closed, not just opened):
- Sets state → `Someone at the Door`

**`webhook` trigger** — only if current state is `Absent`:
- Sets state → `Someone at the Door`

### Auto-reset

After the choose block, if the state is now `Someone at the Door` (i.e. one of the above branches fired), the automation waits **2 minutes** then resets to `Absent`. The door-open trigger can fire earlier to reset sooner.

The automation runs in `restart` mode — if a new trigger fires while the automation is in the 2-minute wait (e.g. door opens), the current run is interrupted and the automation restarts immediately from the top. This ensures the door-open reset is never delayed by an in-progress wait.

---

## Automation: Front Door Notification (`automation.front_door_notification`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `front_door_state` transitions `Absent` → `Someone at the Door` | Announce + push notify (see below) |
| `dismiss` | `front_door_state` leaves `Someone at the Door` | Dismiss notification via `script.cancel_announce` |

**`create` branch actions:**
1. If Tom's Office media player is playing, temporarily lower volume to 10%
2. In parallel:
   - Announce "Someone is at the front door." via `script.annouce`
   - If Tom is in his office (`sensor.tom_s_iphone_area` = `Tom's Office`): take a snapshot from the front door camera and send a push notification to Tom's iPhone with the image and a "Tell them I'm coming!" action button
3. Restore the media player volume

The `dismiss` trigger fires when the state helper resets to `Absent` — either via the door opening (immediate) or the 2-minute auto-reset — clearing the persistent notification automatically.

---

## Flow diagram

```
Vibration detected ──┐
                      ├──► Front Door State automation ──► input_select.front_door_state
Webhook received ─────┤         (state guards + 2-min auto-reset)          │
                      │                                                     │
Door opens ───────────┘                                              Absent → Someone at the Door
                                                                            │
                                                                            ▼
                                                              Front Door Notification automation
                                                              (announce + push notify)
```
