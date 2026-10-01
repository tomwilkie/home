# Repository purpose

This repo holds config and guidance for my Home Assistant setup. Most of the live Home Assistant
configuration (automations, scripts, helpers) lives in the running instance, and you reach it
through the MCP server rather than through files here. The dashboards, the lighting blueprint,
the Grafana Alloy config, and the Grafana dashboards and alerts are the exceptions: this repo is
their source of truth.

Each of the following documents covers one area:

- @access-home-assistant.md covers the ways to talk to Home Assistant, UniFi and Grafana.
- @lighting-automation.md covers how the lighting automation is configured.
- @naming-conventions.md covers how to name automations, devices and entities. Consult it before you create or rename an entity, helper, automation or device.
- @notifications.md covers the announce scripts and the front door, washing machine, tumble dryer and vacuum notifications.
- @wake-routines.md covers the wake-time helper and its consumers (bedside alarm, morning hot water, wake up routine), and the calendar-driven early-flight hot water routine.
- @maintenance.md covers the label-driven scheduled restarts of devices that degrade with uptime, and the integration watchdogs that reload a config entry that has wedged (Hive, Netatmo).
- @dashboards.md covers the GitOps workflow for dashboards and the purpose of each dashboard.
- @observability.md covers how Grafana Alloy ships metrics and logs to Grafana Cloud.
- @network-security.md covers how the UniFi gateway isolates the IOT and Camera VLANs, and how to audit the isolation.

`history.md` holds incident narratives, outage timelines, test-run results and superseded
designs. It is deliberately not imported here. Read it only when you need to know how a rule
came about.

# Documentation style

Before you edit any Markdown document in this repo, load the `docs-style` skill and follow it.
The following rules are specific to this repo and win where they disagree with the skill:

- **State the current design as rules, each with a short reason.** Put the story of how a rule
  was discovered in `history.md` under a dated entry, and keep one or two sentences of "why" in
  the main document.
- **Rewrite in place when a decision changes.** Don't append a correction that contradicts
  earlier text, don't keep "this used to say" notes, and delete checklist items when they are
  done.
- **Don't write explicit counts of devices, entities or group members.** A count such as "the
  six presence sensors" is out of date as soon as the fleet changes. Name the group, or list the
  members where the list itself is the record.
- **Say each thing in one document** and link to it from the others.

# Git workflow

**Commit directly to `master`. Don't create branches or pull requests.**

This is a single-maintainer repo of documentation and config, with no CI and no review step, so a
branch adds a merge round trip and buys nothing. When asked to commit, commit on `master` and
push. Don't run `git checkout -b`, don't open a pull request, and don't ask which branch.

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
- Jinja template calls to the `device_id(...)` function, which resolve at render time.

# PII and secrets policy

This is a public repo. Before you commit anything, check it against these rules.

## Allowed

You can commit the following:

- First names of household members (Tom, Rachana)
- MAC addresses, private IP addresses (192.168.x.x, 10.x.x.x), Zigbee IEEE addresses
- Local hostnames, for example `homeassistant.local`
- Internal Home Assistant device IDs and entity IDs, even those derived from hardware identifiers
- MQTT credentials for the local broker if they are already embedded in documentation examples

## Never commit

Don't commit any of the following:

- The home street address or postcode in any form: in entity IDs, display names, headings or prose. Use `home` or `My Home` instead, for example `weather.home` and `zone.home`.
- Public IP addresses or external URLs that could identify the home network or expose services
- API keys, long-lived access tokens, bearer tokens, or any credential that grants access to an external service (Grafana Cloud, GitHub, cloud integrations)
- Webhook IDs that are live and secret. Placeholder values such as `<your-webhook-id>` are fine.
- Full surnames of non-household third parties
