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
- **Don't use the integration's options form**, which opens from **Configure** on an entry. It replaces the
  entry's stored data with only the scan interval and calendars, which deletes the API key and
  the registration number, and every sensor goes `unavailable`. To change either setting, delete
  the entry and add it again with the new values in the setup form, then redo the steps in
  _Add a car_ after the first.
- **Every car is in the Garage area, and its device is named `Garage - <REG>`**, following
  [naming-conventions.md](naming-conventions.md). The entity names then compose as
  `Garage - <REG> Tax Due Date`.
- **Entity IDs are `{domain}.garage_<reg>_{measurement}`**, for example
  `sensor.garage_<reg>_taxduedate`, with `<reg>` in lower case. The integration creates them as
  `dvla_<reg>_*`, so rename them after you add a car. They contain the registration number, so a
  dashboard or automation that references them can't be committed as it stands.
- **A new car has no MOT record.** Until its first MOT, `sensor.garage_<reg>_motstatus` reads
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

Then finish the car:

1. Assign the car's device to the Garage area, and name it `Garage - <REG>`.
2. Rename each of its entities from `{domain}.dvla_<reg>_*` to `{domain}.garage_<reg>_*`.
3. Create its two helpers, as described in [_Reminders_](#reminders).

Each car added uses about 30 lookups a month at the 24-hour interval. Before you add one,
check that the total stays under the API key's limit, or ask the DVLA for a higher one.

## Reminders

Each car's device has two template sensor helpers, **Days until tax due** and **Days until MOT
expires**, with device class `duration` and unit `d`. Their state template is the following, with
the car's `taxduedate` or `motexpirydate` sensor as `SOURCE`:

```jinja
{{ ((states('SOURCE') | as_datetime).date() - now().date()).days }}
```

They exist because Home Assistant exports only numeric states to Prometheus, and the DVLA date
sensors are text. The Grafana alert in
[_Vehicle tax or MOT due_](observability.md#vehicle-tax-or-mot-due) emails when either is under
30 days.

- **Create both helpers when you add a car,** in the template helper's setup form with the car's device selected, after you rename the car's entities so that `SOURCE` is the `garage_` ID. The entity name then composes with the device name, and the helper's entity ID gets the area prefix. The alert's pattern picks the entity up with no change.
- **A helper's template names its source sensor by entity ID,** so renaming a car's entities means updating the `state` of both helpers.
- **Delete both helpers when you remove a car.** A helper whose source sensor is gone goes `unavailable` and drops out of Prometheus, so it doesn't alert, but it clutters the entity list.

