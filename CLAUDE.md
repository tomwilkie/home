# Repository purpose

This repo holds config and guidance for my Home Assistant setup. Most of the live Home Assistant
configuration (automations, scripts, helpers) lives in the running instance, and you reach it
through the MCP server rather than through files here. The dashboards, the lighting blueprint,
the Grafana Alloy config, and the Grafana dashboards and alerts are the exceptions: this repo is
their source of truth.

# Documents

@access-home-assistant.md is loaded with this file. It covers how to reach Home Assistant (the
`ha_*` MCP tools, `hass-cli`, the REST API via `scripts/ha-api`, SSH to the host and the
`.storage` registries), the UniFi gateway (the `unifi-network` and `unifi-protect` MCP plugins,
`scripts/unifi-ssh`) and Grafana Cloud (`gcx`), with each tool's quirks.

None of the following documents is loaded for you. Each is the rules for one area, and you must
read it with the Read tool before you touch that area: the rules are not derivable from the
live config, and most of them exist because something broke without them. When a task spans
areas, read every matching document. The table says what each one covers and when to read it.

| Document | What it covers | Read it when |
|---|---|---|
| [naming-conventions.md](naming-conventions.md) | Area, device, entity, automation and label naming: `{Area} - {Device}` device names, area-first entity IDs, bare entity names so that `friendly_name` composes, when a `name` override is wrong (and the UniFi tracker case where it is right), reusing a deleted entity ID, what to update after a rename (dashboards, automations, groups, config-entry options, zigbee2mqtt). | You create, rename or relabel any entity, helper, automation, device, area or label, or you see a `friendly_name` that looks wrong. |
| [lighting-automation.md](lighting-automation.md) | The occupancy-group plus `motion_lights` blueprint plus `room-light` label plus adaptive-lighting pattern that every room follows. The standard adaptive-lighting settings. Which rooms are exceptions and why. How to edit and deploy the blueprint, with and without SSH. The blueprint's triggers, the sun-window edge cases and the known gaps. | Lights come on or go off at the wrong time, a room's lighting needs changing, a light is added, renamed or removed, or the blueprint is edited. |
| [heating.md](heating.md) | `climate.house_thermostat`, a `generic_thermostat` in `configuration.yaml`; the template `switch.heating_relay` that drives the Hive thermostat's setpoint; `automation.set_thermostat_state`, which picks the preset from presence and the comfort schedule, and why it acts on transitions only. | The heating is on or off when it should not be, a setpoint or schedule changes, or the Hive thermostat is involved. |
| [wake-routines.md](wake-routines.md) | `input_datetime.wake_up_time` and everything that reads or writes it: the 17:00 reset, the bedside-clock mirror, `automation.morning_hot_water` and its catch-up triggers, `automation.wake_up_routine`. The nursery sleep routine (`input_boolean.kiran_asleep`, the heartbeat track). `automation.evening_hot_water` for Kiran's bath. The calendar-driven `automation.early_flight_hot_water`. | Anything about mornings: the alarm, hot water, shutters, the vacuums starting, or a flight. Also Kiran's bedtime, naps, bath-time hot water and the heartbeat track. Also read it for a hot-water outage, together with maintenance.md. |
| [notifications.md](notifications.md) | `script.annouce` and `script.cancel_announce`, which callers speak and which stay silent, the `media_player.notification_players` group and its per-player toggles, why the speech step is split by `MEDIA_ANNOUNCE` support, the Kitchen Display watchdog. The `input_select` state-machine pattern for the tumble dryer, front door and washing machine, and the vacuum bin-full alert. | A notification was missed, duplicated or spoken when it should not have been, a speaker is added or swapped, an appliance or doorbell automation changes, or you add a new announcement. |
| [maintenance.md](maintenance.md) | The label-driven 04:30 restart sweep (`restart-daily`, `restart-weekly`, `restart-monthly` on devices, not entities), the 04:00 to 06:00 timing of the other maintenance automations, and how to verify the sweep. The Netatmo watchdog: why it exists and how to test it. Why Hive needs no watchdog on the `tomwilkie/ha-hive` fork. Cleaning up UniFi ghost trackers from the camera ports. | A device or integration is `unavailable`, something is wrong "every morning", a device needs a scheduled restart, an integration keeps failing after the nightly restart, any automation runs between 04:00 and 06:00, or junk `device_tracker.unifi_default_*` entities pile up. |
| [dashboards.md](dashboards.md) | The `hass-cli` pull, edit, push workflow for the three dashboards in `dashboards/`; what each view holds; the card-mod recipes for the Auto lights cards and the bin-full tiles; how to repair a re-created Music Assistant player and how to remove one; the `background: false` rule on the kitchen camera cards; how to check a render. | You edit any dashboard YAML, a card looks wrong or is missing, or a dashboard references an entity that no longer exists. |
| [observability.md](observability.md) | Grafana Alloy on the HAOS host: why it runs without AppArmor, the metric scrape jobs, the log pipelines (Docker, journal, UniFi syslog with its `log_type` split, AdGuard query log), continuous profiles of Alloy and of Home Assistant Core (the `ha-pyroscope` integration pushing through Alloy's receiver, and why eBPF profiling cannot run on HAOS), how to query Home Assistant's own logs in Loki, deployment with `make`, the file-managed Grafana dashboards and their workflow, the Grafana alert rules (exporter down, U5G modem reset, DNAT tripwire) and the contact point that delivers them. | You need logs older than four hours, a metric or dashboard is missing or wrong, an alert fired or failed to arrive, the Alloy config or a Grafana dashboard or alert changes, or an add-on container is renamed. |
| [network-security.md](network-security.md) | The VLANs and the Home Assistant reservation; what breaks when a device moves VLAN; the Zone-Based Firewall policies that isolate IOT and Cameras while allowing Home Assistant; same-VLAN isolation on WLANs and switch ports; the mDNS reflector; DNS and NTP forcing through DHCP, an iptables DNAT redirect and backstop blocks; the per-device internet block by MAC; how to audit it all. | A device cannot be reached or discovered, a device moves VLAN or joins the IOT or Cameras network, a firewall or DNS change is needed, the DNAT tripwire alert fires, or you audit the isolation. |
| [zigbee2mqtt-sync.md](zigbee2mqtt-sync.md) | How to make zigbee2mqtt friendly names match Home Assistant device names with the `mosquitto` CLI. | You rename a Zigbee device. |
| [history.md](history.md) | Incident narratives, outage timelines, root-cause analyses, test-run results, measurements and superseded designs, under dated entries per area. | You need to know how a rule came about, you are investigating an incident that looks like an earlier one, or you are recording an investigation, a measurement or a "status as of". |

The project skills in `.claude/skills/` are `ha-api` (call the REST API through
`scripts/ha-api`), `ha-health-check` (audit the live instance) and `rename-entities` (bring an
area's names into line with naming-conventions.md).

# Documentation style

Before you edit any Markdown document in this repo, load the `docs-style` skill and follow it.
The following rules are specific to this repo and win where they disagree with the skill:

- **State the current design as rules, each with a short reason.** Put the story of how a rule
  was discovered in `history.md` under a dated entry, and keep one or two sentences of "why" in
  the main document.
- **Dated status goes in `history.md`.** An investigation in progress, a measurement, a plan or
  a "status as of" belongs there under a dated entry, even while it is live. The main document
  keeps the rule or alert it motivated and a link to the entry.
- **Rewrite in place when a decision changes.** Don't append a correction that contradicts
  earlier text, don't keep "this used to say" notes, and delete checklist items when they are
  done.
- **Don't write explicit counts of devices, entities or group members.** A count such as "the
  six presence sensors" is out of date as soon as the fleet changes. Name the group, or list the
  members where the list itself is the record.
- **Say each thing in one document** and link to it from the others.
- **Keep the index in this file current.** When you add a document, add a row with what it
  covers and when to read it. When a document gains or loses a topic, update its row.

# Git workflow

**Commit directly to `master`. Don't create branches or pull requests.**

This is a single-maintainer repo of documentation and config, with no CI and no review step, so a
branch adds a merge round trip and buys nothing. When asked to commit, commit on `master` and
push. Don't run `git checkout -b`, don't open a pull request, and don't ask which branch. The one
exception is Renovate, which opens pull requests for dependency updates such as the Alloy image,
because the release notes in the PR are worth reading before the update is deployed (see
[_Upgrading Alloy_](observability.md#upgrading-alloy)). Merge those on GitHub rather than
redoing them by hand.

**Before you start any work, bring `master` up to date with upstream.** Run `git fetch`, and if
`master` is behind `origin/master`, run `git pull --rebase` before you read or edit anything, so
that you work from the current documents rather than stale ones. If the working tree has
uncommitted changes, or the rebase conflicts, stop and ask rather than stashing or discarding
anything.

Commit messages follow `<area>: <lowercase summary>` (for example `lighting:`, `naming:`,
`notifications:`, `maintenance:`), with a body explaining why when the change is not
self-evident.

Before every commit, check the change against the [PII and secrets policy](#pii-and-secrets-policy).
This repo is public.

# Entity IDs, not device IDs

Reference entities by `entity_id`, not `device_id`, in automations, dashboards, scripts and
scenes. An integration regenerates device IDs whenever it re-creates a device, while entity IDs
survive. A Music Assistant update re-created the WiiM speaker and silently broke every
automation that targeted its device ID.

When you edit an automation or dashboard that still contains a hardcoded `device_id`, convert it
to the corresponding `entity_id`. Prefer native conditions and actions (`condition: state`,
`climate.set_hvac_mode`) over `condition: device` and device actions, which embed device IDs.

The following exceptions are permitted:

- Zigbee2MQTT autodiscovered **device triggers** for buttons and remotes (`trigger: device` with `domain: mqtt`), because a button press has no entity to trigger on.
- Services that only accept device targets, for example `fully_kiosk.load_url` and `fully_kiosk.start_application`.
- Jinja template calls to the `device_id(...)` and `config_entry_id(...)` functions, which resolve at render time. Pass `config_entry_id('<entity>')` as the `entry_id` of `homeassistant.reload_config_entry`, because reloading by target stops working in 2027.4.

# PII and secrets policy

This is a public repo. Before you commit anything, check it against these rules.

## Allowed

You can commit the following:

- First names of household members (Tom, Rachana)
- MAC addresses, private IP addresses (192.168.x.x, 10.x.x.x), Zigbee IEEE addresses
- Local hostnames, for example `homeassistant.local`
- Internal Home Assistant device IDs and entity IDs, even those derived from hardware identifiers

## Never commit

Don't commit any of the following:

- The home street address or postcode in any form: in entity IDs, display names, headings or prose. Use `home` or `My Home` instead, for example `weather.home` and `zone.home`. The UniFi site name is the street address, so don't echo UniFi site settings into files or commit messages.
- Public IP addresses or external URLs that could identify the home network or expose services
- API keys, long-lived access tokens, bearer tokens, or any credential that grants access to an external service (Grafana Cloud, GitHub, cloud integrations)
- Passwords for the local MQTT broker. Documentation reads them from 1Password, as in [zigbee2mqtt-sync.md](zigbee2mqtt-sync.md).
- Webhook IDs that are live and secret. Placeholder values such as `<your-webhook-id>` are fine.
- Full surnames of non-household third parties
