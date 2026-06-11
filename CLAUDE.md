# Repository Purpose

This repo contains config and guidance for my Home Assistant setup.
The live Home Assistant configuration (automations, scripts, helpers, dashboards) lives in the running HA instance and is accessed via the MCP server, not via files in this repo.

- Refer to @access-home-assistant.md for various methods to talk to home assistant.
- Refer to @lighting-automation.md for information on how the lighting automation should be configured.
- Refer to @naming-conventions.md for information on how to name automations, devices, entities etc. Always consult @naming-conventions.md before creating or renaming entities, helpers, automations, or devices.
- Refer to @notifications.md for information on how e.g. the front door, washing machine and tumble dryer notifications are configured.
- Refer to @dashboards.md for the GitOps workflow for managing dashboards and the purpose of each dashboard.
- Refer to @observability.md for how metrics and logs are shipped to Grafana Cloud via Grafana Alloy.

# Entity IDs, not Device IDs

Always reference entities by `entity_id` — never by `device_id` — in automations, dashboards, scripts, and scenes. Device IDs are regenerated whenever an integration re-creates a device (e.g. a Music Assistant update once re-created the WiiM speaker, silently breaking every automation that targeted its device ID), while entity IDs survive. When editing any automation or dashboard that still contains a hardcoded `device_id`, convert it to the corresponding `entity_id` while you're there. Prefer native conditions/actions (`condition: state`, `climate.set_hvac_mode`, etc.) over `condition: device` / device actions, which embed device IDs.

Permitted exceptions:
- Zigbee2MQTT autodiscovered **device triggers** for buttons/remotes (`trigger: device` with `domain: mqtt`) — button presses have no entity to trigger on.
- Services that only accept device targets (e.g. `fully_kiosk.load_url`, `fully_kiosk.start_application`).
- Jinja template calls to the `device_id(...)` function — these resolve dynamically and are fine.

# PII and Secrets Policy

This is a public repo. Before committing anything, check it against these rules.

## Allowed
- First names of household members (Tom, Rachana)
- MAC addresses, private IP addresses (192.168.x.x, 10.x.x.x), Zigbee IEEE addresses
- Local hostnames (e.g. `homeassistant.local`)
- Internal HA device IDs and entity IDs (even those derived from hardware identifiers)
- MQTT credentials for the local broker if they are already embedded in documentation examples

## Never commit
- The home street address or postcode in any form — in entity IDs, display names, headings, or prose. Use `home` or `My Home` instead (e.g. `weather.home`, `zone.home`).
- Public IP addresses or external URLs that could identify the home network or expose services
- API keys, long-lived access tokens, bearer tokens, or any credential that grants access to an external service (Grafana Cloud, GitHub, cloud integrations, etc.)
- Webhook IDs that are live and secret (placeholder values like `<your-webhook-id>` are fine)
- Full surnames of non-household third parties

