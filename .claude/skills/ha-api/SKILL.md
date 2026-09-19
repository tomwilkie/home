---
name: ha-api
description: >
  Use the scripts/ha-api helper to call the Home Assistant REST API directly.

  TRIGGER THIS SKILL WHEN:
  - An MCP tool does not exist for the needed operation (e.g. creating a new integration config entry such as a new adaptive lighting instance)
  - You need to drive a multi-step HA config entry flow (start flow → submit steps → confirm)
  - You need to call an HA REST API endpoint not exposed by any mcp__claude_ai_ha-mcp__* tool
---

# ha-api

A thin wrapper around `curl` that reads the HA URL and token from `HASS_SERVER` / `HASS_TOKEN` — the same environment variables as `hass-cli` (see [access-home-assistant.md](../../../access-home-assistant.md)).

**Always prefer MCP tools (`mcp__claude_ai_ha-mcp__*`) when one exists.** Reach for `scripts/ha-api` only when no MCP tool covers the operation.

## Usage

```
scripts/ha-api <path> [extra curl flags...]
```

- `<path>` — the API path, starting with `/` (e.g. `/api/states`)
- Extra flags are forwarded to `curl` verbatim (`-X POST`, `-d '{...}'`, etc.)
- Output is raw JSON from HA; pipe through `jq` for readability

## Common patterns

### GET a resource
```bash
scripts/ha-api /api/states/light.master_bedroom_lamp_toms | jq
```

### POST with a body
```bash
scripts/ha-api /api/services/light/turn_on \
  -X POST \
  -d '{"entity_id": "light.master_bedroom_lamp_toms"}'
```

---

## Config entry flows (multi-step)

Creating a new integration instance (e.g. a new Adaptive Lighting instance) requires a stateful three-step flow. The flow ID returned by step 1 must be threaded through subsequent steps.

### Step 1 — start the flow
```bash
scripts/ha-api /api/config/config_entries/flow \
  -X POST \
  -d '{"handler": "adaptive_lighting"}'
# → {"flow_id": "<flow_id>", "step_id": "menu", ...}
```

### Step 2 — navigate menus / submit form fields
```bash
scripts/ha-api /api/config/config_entries/flow/<flow_id> \
  -X POST \
  -d '{"action": "new"}'
# → next step form, e.g. step_id: "user" asking for a name

scripts/ha-api /api/config/config_entries/flow/<flow_id> \
  -X POST \
  -d '{"name": "Master Bedroom"}'
# → {"type": "create_entry", "result": {"entry_id": "<entry_id>", ...}}
```

### Step 3 — configure options (lights, settings)
```bash
# Start an options flow for the newly created entry
scripts/ha-api /api/config/config_entries/options/flow \
  -X POST \
  -d '{"handler": "<entry_id>"}'
# → {"flow_id": "<options_flow_id>", "step_id": "init", ...}

# Submit options
scripts/ha-api /api/config/config_entries/options/flow/<options_flow_id> \
  -X POST \
  -d '{
    "lights": ["light.master_bedroom_lamp_toms", "light.master_bedroom_lamp_rachanas"],
    "min_brightness": 50,
    ...
  }'
# → {"type": "create_entry", ...}
```

## Notes

- Credentials come from the **shell environment** only, never from files in this repo. `HOMEASSISTANT_URL` / `HOMEASSISTANT_TOKEN` are accepted as a fallback.
- The MCP connector's OAuth sign-in cannot be reused here — this needs an HA long-lived access token.
