# Zigbee2MQTT sync

After you rename a Home Assistant device, rename the device in zigbee2mqtt (z2m) to match. The
z2m friendly name must equal the Home Assistant device name.

The steps need the `mosquitto` CLI tools (`brew install mosquitto`). The MQTT broker is
`homeassistant.local` on port `1883`, with the credentials `homeconnect` / `homeconnect`.

## 1. List the z2m devices

The following command prints each z2m device's IEEE address and friendly name:

```bash
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.type != "Coordinator") | [.ieee_address, .friendly_name] | @tsv'
```

## 2. List the Home Assistant device names

Home Assistant identifies a z2m device as `zigbee2mqtt_<ieee_address>`. The following command
strips the prefix and prints each IEEE address with its display name:

```bash
ssh root@homeassistant.local -C \
  "jq -r '.data.devices[] | select(.identifiers[][] == \"mqtt\") | [(.identifiers[] | select(.[0]==\"mqtt\") | .[1] | ltrimstr(\"zigbee2mqtt_\")), .name_by_user // .name] | @tsv' \
  /config/.storage/core.device_registry"
```

## 3. Rename the z2m devices

Publish to `zigbee2mqtt/bridge/request/device/rename` with `homeassistant_rename: false`, which
stops z2m renaming the Home Assistant device as well. Run the renames in parallel:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/rename' \
    -m "{\"from\": \"$1\", \"to\": \"$2\", \"homeassistant_rename\": false}" \
    && echo "ok: $2" || echo "FAIL: $2"
}

pub "0x001788010ea0b4e4" "Living Room - Tom's Lamp" &
# ... one line per device
wait
```

Don't name the shell function `rename`. It conflicts with the zsh builtin, and the
`mosquitto_pub` call does not run.

## 4. Clear stale descriptions

A z2m device has a `description` field that can hold a name from before a rename. The following
command lists the devices with a description:

```bash
/opt/homebrew/bin/mosquitto_sub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
  -t 'zigbee2mqtt/bridge/devices' -C 1 -W 10 \
  | jq -r '.[] | select(.description != null and .description != "") | [.friendly_name, .description] | @tsv'
```

To clear one, publish to `zigbee2mqtt/bridge/request/device/options`:

```bash
pub() {
  /opt/homebrew/bin/mosquitto_pub -h homeassistant.local -p 1883 -u homeconnect -P homeconnect \
    -t 'zigbee2mqtt/bridge/request/device/options' \
    -m "{\"id\": \"$1\", \"options\": {\"description\": \"\"}}" \
    && echo "ok: $1" || echo "FAIL: $1"
}

pub "Living Room - Lamp Rear" &
# ... one line per device
wait
```
