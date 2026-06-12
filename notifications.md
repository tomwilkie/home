# Notifications

## Announce Scripts

### `script.annouce`

Delivers a message to the house. Accepts `title`, `message`, and optional `important` and `persistent` fields. Actions:
1. Temporarily lowers Tom's office speaker volume if it is playing
2. Speaks the message via ChimeTTS to all notification players (time-gated: 06:00–23:00, or always if `important: true`)
3. Creates a persistent notification in the HA UI, unless `persistent: false` (default `true`) — `notification_id` is derived from `title | slugify` so it can be addressed for later dismissal

### `script.broadcast`

Backs the Broadcast view on the Settings dashboard. Guards against an empty `input_text.broadcast_message`, calls `script.annouce` with the box's contents (`title: Broadcast`, `important: true`, `persistent: false`), then clears the box.

### `script.cancel_announce`

Dismisses a persistent notification previously created by `script.annouce`. Accepts a `title` field and calls `persistent_notification.dismiss` using the same `title | slugify` convention. Automations call this script on their dismiss trigger rather than calling the service directly.

---

## Pattern

Each appliance uses the same structure: an `input_select` state helper decouples device events from notification. One automation manages all state transitions; a second reacts to state changes and delivers or dismisses alerts. All state automations run in `restart` mode — a new trigger interrupts any in-progress run, so late-arriving events are never queued or dropped.

---

## Tumble Dryer Automation

---

### Helper: Tumble Dryer State

| Field | Value |
|---|---|
| Entity ID | `input_select.tumble_dryer_state` |
| Type | `input_select` |
| Options | `idle`, `active`, `finished` |
| Initial | `idle` |

Tracks the current phase of a drying cycle.

---

### Automation: Tumble Dryer State (`automation.tumble_dryer_state`)

Manages all transitions of the `tumble_dryer_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `start` | `sensor.dryer_bsh_common_status_operationstate` | Operation state → `Run` |
| `finished` | `event.dryer_laundrycare_dryer_event_dryingprocessfinished` | `event_type` attribute → `Present` |
| `door_open` | `event.dryer_laundrycare_common_event_dooropen` | `event_type` attribute → `Present` |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`start` trigger** — only if current state is `idle`:
- Sets state → `active`

**`finished` trigger** — only if current state is `active`:
- Sets state → `finished`

**`door_open` trigger** — only if current state is `finished`:
- Sets state → `idle`

> The state guards also prevent the anti-wrinkle tumble (a second Run→Finished cycle after the main drying completes) from re-triggering the notification.

---

### Automation: Tumble Dryer Notification (`automation.notify_on_tumble_drier_finished`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `tumble_dryer_state` transitions `active` → `finished` | Announce via `script.annouce` (title: "Tumble Drier") |
| `dismiss` | `tumble_dryer_state` leaves `finished` (door opened → `idle`) | Dismiss notification via `script.cancel_announce` |

The `from` guard on the `create` trigger prevents spurious fires on HA restart or unknown state initialisation. The `dismiss` trigger fires on the same `door_open` transition that resets the state helper to `idle`, so the persistent notification is cleared automatically when the user retrieves the laundry.

---

## Front Door Automation

---

### Helper: Front Door State

| Field | Value |
|---|---|
| Entity ID | `input_select.front_door_state` |
| Type | `input_select` |
| Options | `Absent`, `Someone at the Door` |
| Initial | `Absent` |

Tracks whether someone is currently at the front door.

---

### Automation: Front Door State (`automation.front_door_state`)

Manages all transitions of the `front_door_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `knocking` | `binary_sensor.front_door_vibration_vibration` | Vibration detected (`off` → `on`) |
| `webhook` | Webhook `<your-webhook-id>` | GET request received |
| `door_open` | `binary_sensor.front_door_contact_contact` | Door opens (state → `on`) |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`door_open` trigger** — only if current state is `Someone at the Door`:
- Sets state → `Absent`

**`knocking` trigger** — only if current state is `Absent` AND `front_door_contact_contact` has been `off` for ≥ 1 minute (door was closed, not just opened):
- Sets state → `Someone at the Door`

**`webhook` trigger** — only if current state is `Absent`:
- Sets state → `Someone at the Door`

#### Auto-reset

After the choose block, if the state is now `Someone at the Door` (i.e. one of the above branches fired), the automation waits **2 minutes** then resets to `Absent`. The door-open trigger can fire earlier to reset sooner.

Runs in `restart` mode — if the door opens during the 2-minute wait, the reset fires immediately rather than waiting for the current run to finish.

---

### Automation: Front Door Notification (`automation.front_door_notification`)

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

## Washing Machine Automation

---

### Helper: Washing Machine State

| Field | Value |
|---|---|
| Entity ID | `input_select.washing_machine_state` |
| Type | `input_select` |
| Options | `idle`, `running`, `finished` |
| Initial | `idle` |

Tracks the current phase of a wash cycle.

---

### Automation: Washing Machine State (`automation.washing_machine_state`)

Manages all transitions of the `washing_machine_state` helper. Triggered by two sources:

| Trigger ID | Source | Event |
|---|---|---|
| `power_change` | `sensor.basement_washing_machine_smart_switch_power` | Any power reading change |
| `door_open` | `binary_sensor.0x00158d008c7104b7_contact` | Door opens (state → `on`) |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`power_change` trigger, power > 1W** — only if current state is `idle`:
- Sets state → `running`

**`power_change` trigger, power ≤ 1W** — only if current state is `running`:
- Waits 10 minutes, then sets state → `finished`

**`door_open` trigger** — only if current state is `finished`:
- Sets state → `idle`

Runs in `restart` mode — power fluctuations during the 10-minute wait restart the clock. The machine must sustain low power for a full uninterrupted 10 minutes before the state advances to `finished`.

---

### Automation: Washing Machine Notification (`automation.notify_on_washing_machine_has_finished`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `washing_machine_state` transitions `running` → `finished` | Announce via `script.annouce` (title: "Washing Machine") |
| `dismiss` | `washing_machine_state` leaves `finished` (door opened → `idle`) | Dismiss notification via `script.cancel_announce` |

