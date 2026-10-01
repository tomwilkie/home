---
name: ha-api
description: >
  Use the scripts/ha-api helper to call the Home Assistant REST API directly.

  TRIGGER THIS SKILL WHEN:
  - An MCP tool does not exist for the needed operation (for example, creating a new integration config entry such as a new adaptive lighting instance)
  - You need to drive a multi-step Home Assistant config entry flow (start flow, submit steps, confirm)
  - You need to call a Home Assistant REST API endpoint not exposed by any mcp__claude_ai_ha-mcp__* tool
---

# ha-api

`scripts/ha-api` is a thin wrapper around `curl` for the Home Assistant REST API.

Prefer an MCP tool (`mcp__claude_ai_ha-mcp__*`) when one covers the operation. Use
`scripts/ha-api` only when none does.

## Usage

```
scripts/ha-api API_PATH [CURL_FLAGS...]
```

- `API_PATH` is the API path, starting with `/`, for example `/api/states`.
- `CURL_FLAGS` are passed to `curl` unchanged, for example `-X POST` and `-d '{...}'`.
- The output is raw JSON. Pipe it through `jq` to read it.

The script reads the URL and token from `HASS_SERVER` and `HASS_TOKEN`, the same environment
variables as `hass-cli` (see [_Home Assistant CLI_](../../../access-home-assistant.md#home-assistant-cli)),
and accepts `HOMEASSISTANT_URL` and `HOMEASSISTANT_TOKEN` as a fallback. The token is a
long-lived access token: the MCP connector's OAuth sign-in cannot be used here. Keep the
credentials in the shell environment, not in files in this repo.

To read a resource, pass the path:

```bash
scripts/ha-api /api/states/light.master_bedroom_lamp_toms | jq
```

To send a body, add the `curl` flags:

```bash
scripts/ha-api /api/services/light/turn_on \
  -X POST \
  -d '{"entity_id": "light.master_bedroom_lamp_toms"}'
```

## Config entry flows

Creating an integration instance, such as an Adaptive Lighting instance, takes a stateful flow.
Each response returns the ID or the next step that the following request needs.

1. Start the flow. The response carries the `flow_id` and the first `step_id`:

   ```bash
   scripts/ha-api /api/config/config_entries/flow \
     -X POST \
     -d '{"handler": "adaptive_lighting"}'
   # {"flow_id": "FLOW_ID", "step_id": "menu", ...}
   ```

2. Answer each menu or form until the response has `"type": "create_entry"`, which carries the `entry_id`:

   ```bash
   scripts/ha-api /api/config/config_entries/flow/FLOW_ID \
     -X POST \
     -d '{"action": "new"}'
   # the next step, for example step_id "user", which asks for a name

   scripts/ha-api /api/config/config_entries/flow/FLOW_ID \
     -X POST \
     -d '{"name": "Master Bedroom"}'
   # {"type": "create_entry", "result": {"entry_id": "ENTRY_ID", ...}}
   ```

3. Start an options flow for the entry, then submit the options:

   ```bash
   scripts/ha-api /api/config/config_entries/options/flow \
     -X POST \
     -d '{"handler": "ENTRY_ID"}'
   # {"flow_id": "OPTIONS_FLOW_ID", "step_id": "init", ...}

   scripts/ha-api /api/config/config_entries/options/flow/OPTIONS_FLOW_ID \
     -X POST \
     -d '{
       "lights": ["light.master_bedroom_lamp_toms", "light.master_bedroom_lamp_rachanas"],
       "min_brightness": 25,
       ...
     }'
   # {"type": "create_entry", ...}
   ```

`FLOW_ID`, `ENTRY_ID` and `OPTIONS_FLOW_ID` are the values from the preceding responses. The
standard Adaptive Lighting options are in
[_Adaptive lighting_](../../../lighting-automation.md#adaptive-lighting).
