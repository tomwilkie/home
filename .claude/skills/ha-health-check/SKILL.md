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

Perform a structured read-only health audit of the live Home Assistant instance. Report findings as a prioritised punch list. Do not apply fixes — offer to fix after reporting.

## Batch 1 — run all four in parallel

1. `ha_get_system_health(include="repairs")` — supervisor status, DB size, HA version, active repairs
2. `ha_get_logs(source="system", level="ERROR", limit=50)` — all errors since last restart
3. `ha_search_entities(state_filter="unavailable", limit=100, result_fields=["entity_id","friendly_name","domain"])` — currently unavailable entities
4. `ha_search_entities(domain_filter="sensor", query="battery", limit=100, result_fields=["entity_id","friendly_name","state"])` — all battery sensors

## Batch 2 — after Batch 1, run as needed

Run these only if Batch 1 reveals issues that warrant further investigation:

- `ha_get_logs(source="system", level="WARNING", limit=30)` — always run; reveals integration connectivity patterns not visible in error log
- `ha_get_automation_traces(automation_id=<id>, limit=3)` — for any automation whose name appears in the error log with an execution error

## Thresholds

| Category | Critical | Warning | Info |
|---|---|---|---|
| Battery % | < 20% | 20–50% | 51–70% |
| Battery (smoke detector) | < 50% | 50–80% | > 80% |
| Unavailable entities | Any | — | — |
| Error log: same-source count | > 100 | 5–100 | < 5 |
| Recorder DB size | > 6 GB | 3–6 GB | < 3 GB |
| Automation execution | error state | — | — |

Smoke detectors (`nest_protect`) have a higher battery threshold because they are safety devices.

## Known false positives — do not escalate

Consult `references/known-error-patterns.md` for the full catalogue. Key patterns to silently downgrade to Info:

- **WebRTC / frontend JS errors** (`frontend.js.modern.*`, `SourceBuffer`, count in the hundreds of thousands) — cosmetic Android Chrome bug
- **Netatmo `Handler is already defined!`** — harmless, fires on every HA restart
- **Roomba `does not generate unique IDs`** — cosmetic, those sensors just won't exist

## Cross-referencing error patterns

After collecting Batch 1 and Batch 2 results, check each error/warning source against `references/known-error-patterns.md`. For each match:
- Apply the catalogued severity (overrides the count-based threshold if lower)
- Use the catalogued action as the suggested fix

## Report format

Output a single punch list grouped by severity. Each item:

```
**[CRITICAL|WARNING|INFO]** `entity_or_integration`
Symptom: <one sentence>
Action: <concise suggested fix> — offer to implement if appropriate
```

End with a one-line summary: total counts per severity, e.g.:
`2 critical · 5 warning · 3 info`

## What not to do

- Do not SSH — all checks use MCP tools only
- Do not modify any configuration during the audit
- Do not report the same underlying issue twice (e.g. if Apple TV reconnects cause both ERROR and WARNING entries, group them into one item)
- Do not report integration-level issues as individual entity issues (e.g. if an entire integration is offline, report the integration — not each of its unavailable entities separately)
