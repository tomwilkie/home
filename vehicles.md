# Vehicles

The [DVLA Vehicle Enquiry Service](https://github.com/jampez77/DVLA-Vehicle-Enquiry-Service)
integration (domain `dvla`, installed from HACS) puts each car's tax and MOT status into Home
Assistant and adds the tax and MOT dates to the personal calendar.

Registration numbers are personal data, so this document doesn't list them, and they must not
appear in any committed file. See the [PII and secrets policy](CLAUDE.md#pii-and-secrets-policy).

## Rules

- **Each car has its own config entry.** The integration takes one registration number per
  entry, and every entry carries the same API key.
- **Enter the registration number without spaces**, for example `AB12CDE`. The DVLA returns the
  plate without a space, and the integration compares the two. With a space, the
  `registrationnumber` sensor reads `unknown` and the `taxstatus` binary sensor reads `off` even
  for a taxed car.
- **Set the scan interval to `86400` seconds (24 hours) on every entry.** The API key is
  registered for 300 lookups a month, and each entry makes one lookup per interval plus one at
  each Home Assistant restart. A 6-hour interval uses about 120 lookups a month per car.
- **Entity IDs follow the plate**: `sensor.dvla_<reg>_taxstatus`, `sensor.dvla_<reg>_motexpirydate`
  and so on, with `<reg>` in lower case. They contain the registration number, so a dashboard
  or automation that references them can't be committed as it stands.
- **A new car has no MOT record.** Until its first MOT, `sensor.dvla_<reg>_motstatus` reads
  `No details held by DVLA` and the `motstatus` binary sensor reads `off`. That is expected.

## Add a car

The setup form asks for the API key, so the quickest way to add a car is to copy the existing
entry's data into a new config flow. The following commands do that without printing the key.
Replace `REG` with the registration number, without spaces:

```sh
ENTRY=$(ssh root@homeassistant.local -C "jq -c '[.data.entries[] | select(.domain==\"dvla\")][0].data' /config/.storage/core.config_entries")
FLOW=$(./scripts/ha-api /api/config/config_entries/flow -X POST -d '{"handler":"dvla"}' | jq -r .flow_id)
./scripts/ha-api /api/config/config_entries/flow/$FLOW -X POST \
  -d "$(jq -c --arg r REG '.reg_number=$r' <<<"$ENTRY")" | jq '{type, title, errors}'
```

Each car added uses about 30 lookups a month at the 24-hour interval. Before you add one,
check that the total stays under the API key's limit, or ask the DVLA for a higher one.

## Change the scan interval or calendars

The options flow holds `scan_interval` and `calendars`. To change them on every entry at once,
run the options flow for each `dvla` entry through `scripts/ha-api`, passing both fields.
