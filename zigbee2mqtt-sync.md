# Zigbee2MQTT Sync

Device names in zigbee2mqtt (friendly names) must be kept in sync with the HA device names after any rename.

## Prerequisites

`mosquitto` CLI tools must be installed (`brew install mosquitto`). MQTT broker:

- Host: `homeassistant.local`, port `1883`
- Credentials: `homeconnect` / `homeconnect`

## Step 1 — get z2m device list

Pull the current z2m devices and their friendly names:

```bash
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.type != "Coordinator") | [.ieee_address, .friendly_name] | @tsv'
```

## Step 2 — get HA MQTT device names

SSH into HA and extract the IEEE address → display name mapping for all MQTT devices:

```bash
ssh root@homeassistant.local -C \
  "jq -r '.data.devices[] | select(.identifiers[][] == \"mqtt\") | [(.identifiers[] | select(.[0]==\"mqtt\") | .[1] | ltrimstr(\"zigbee2mqtt_\")), .name_by_user // .name] | @tsv' \
  /config/.storage/core.device_registry"
```

The identifier format for z2m devices in HA is `zigbee2mqtt_<ieee_address>`, so stripping the prefix gives the IEEE address for matching.

## Step 3 — rename z2m devices to match HA

Use the `zigbee2mqtt/bridge/request/device/rename` topic. The `homeassistant_rename: false` flag prevents z2m from also trying to rename the HA device (which is already correct).

Run renames in parallel using a shell function:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/rename' \
    -m "{\"from\": \"$1\", \"to\": \"$2\", \"homeassistant_rename\": false}" \
    && echo "ok: $2" || echo "FAIL: $2"
}

pub "0x001788010ea0b4e4" "Living Room - Tom's Lamp" &
pub "0xaabbccddeeff0011" "Kitchen - Radiator" &
# ... one line per device
wait
```

> **Note:** Avoid naming the shell function `rename` — it conflicts with the zsh builtin and the mosquitto_pub call will silently not run.

## Step 4 — clear stale descriptions

z2m devices have a user-settable `description` field that can hold stale names from before a rename. After renaming, check for and clear any non-empty descriptions:

```bash
# List devices with non-empty descriptions
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.description != null and .description != "") | [.friendly_name, .description] | @tsv'
```

Clear descriptions in parallel using `zigbee2mqtt/bridge/request/device/options`:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/options' \
    -m "{\"id\": \"$1\", \"options\": {\"description\": \"\"}}" \
    && echo "ok: $1" || echo "FAIL: $1"
}

pub "Living Room - Lamp Rear" &
pub "Kitchen - Radiator" &
# ... one line per device with a stale description
wait
```
