---
name: ha-health-check
description: >
  Audit the live Home Assistant instance for health issues, broken devices, and
  failing automations.

  TRIGGER THIS SKILL WHEN:
  - User runs /ha-health-check
  - User asks to check, audit, or analyse the health of Home Assistant
  - User asks about broken devices, unhealthy sensors, or flapping entities
  - User asks what's wrong with their Home Assistant setup
  - User asks for a health report or diagnostic sweep
---

# ha-health-check

Run a structured, read-only health audit of the live Home Assistant instance, and report the
findings as a prioritised punch list. Don't apply fixes during the audit. Offer to fix after
you report.

## Rules

- **Use MCP tools only.** Don't use SSH.
- **Don't modify any configuration** during the audit.
- **Report each underlying issue once.** If Apple TV reconnects cause both ERROR and WARNING entries, group them into one item.
- **Report an offline integration as one item,** not as each of its unavailable entities.

## Collect

Run the following calls in parallel:

1. `ha_get_system_health(include="repairs")` returns the supervisor status, database size, Home Assistant version and active repairs.
2. `ha_get_logs(source="system", level="ERROR", limit=50)` returns the errors since the last restart.
3. `ha_search(state_filter="unavailable", limit=100, result_fields=["entity_id","friendly_name","domain"])` returns the unavailable entities.
4. `ha_search(query="battery", domain_filter="sensor", limit=100, result_fields=["entity_id","friendly_name","state"])` returns the battery sensors.

Then run the following:

- `ha_get_logs(source="system", level="WARNING", limit=30)`, every time. Warnings show integration connectivity patterns that the error log does not.
- `ha_get_automation_traces(automation_id="AUTOMATION_ENTITY_ID", limit=3)`, for each automation that the error log names with an execution error.

## Thresholds

Classify each finding with the following thresholds:

| Category | Critical | Warning | Info |
|---|---|---|---|
| Battery | below 20% | 20–50% | 51–70% |
| Battery (smoke detector) | below 50% | 50–80% | above 80% |
| Unavailable entities | any | none | none |
| Error log, count from one source | above 100 | 5–100 | below 5 |
| Recorder database size | above 6 GB | 3–6 GB | below 3 GB |
| Automation execution | error state | none | none |

Smoke detectors (`nest_protect`) have a higher battery threshold because they are safety
devices.

## Known error patterns

Check every error and warning source against
[`references/known-error-patterns.md`](references/known-error-patterns.md). For each match:

- Apply the catalogued severity. It overrides the count-based threshold.
- Use the catalogued action as the suggested fix.

The following patterns are the common false positives. Report them as Info:

- **WebRTC and frontend JavaScript errors** (`frontend.js.modern.*`, `SourceBuffer`, counts in the hundreds of thousands) are a cosmetic Android Chrome bug.
- **Netatmo `Handler is already defined!`** fires on every Home Assistant restart and is harmless.
- **Roomba `does not generate unique IDs`** is cosmetic. The duplicate sensors are not created.

## Report

Output one punch list grouped by severity. Each item has the following form:

```
**[CRITICAL|WARNING|INFO]** `entity_or_integration`
Symptom: <one sentence>
Action: <concise suggested fix>, with an offer to implement it where that fits
```

End with a one-line summary of the counts per severity, for example
`2 critical · 5 warning · 3 info`.
