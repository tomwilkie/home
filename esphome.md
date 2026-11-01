# ESPHome devices

This document covers the custom ESPHome devices whose configs live in `esphome/`: where each
config lives, how secrets and encryption work, how to build and flash a device, and the rules
behind each config.

## Devices

The following table lists the custom devices:

| Device | Folder | Source | Hardware |
|---|---|---|---|
| Master Bedroom - Clock | `esphome/clock` | Submodule of [tomwilkie/clock](https://github.com/tomwilkie/clock) | M5Stack Dial (ESP32-S3) |
| Hallway - Doorbell | `esphome/doorbell` | Submodule of [tomwilkie/doorbell](https://github.com/tomwilkie/doorbell) | Seeed XIAO ESP32S3 and a MAX98357 amplifier in a Reolink chime case |
| Kitchen - Boiler Monitor | `esphome/boiler-monitor` | This repo | ESP32 dev board, TCS34725 colour sensor and two DS18B20 probes |

The Voice Assistants and the Everything Presence Lites also run ESPHome, but on vendor firmware.
Each has an on-device update entity, and `automation.update_esphome_devices` installs their
updates at 05:30, as described in [_Timing_](maintenance.md#timing). That automation does not
reach the custom devices, which have no update entity.

## Layout

- **The clock and the doorbell are git submodules tracking `main`.** Their repos are public, so each stands alone. To change one, commit and push inside the submodule first, then commit the new submodule commit in this repo. Renovate opens a pull request here when either repo's `main` moves past the recorded commit.
- **Clone with `git clone --recurse-submodules`,** or run `git submodule update --init` in an existing clone. Without it the two folders are empty.
- **The boiler monitor lives directly in this repo,** because it has no project of its own.
- **Each folder has its own `debug.yaml`, and the copies must stay identical.** Every config includes it as the `core` package. It supplies the diagnostic entities that the restart sweep and health checks read (Wi-Fi signal, uptime, internal temperature, free memory, online status, IP address, SSID, version and the reboot button), and it sends the device log to Loki, as described in [_ESPHome device logs_](observability.md#esphome-device-logs). Copy any change to all three folders.

## Secrets

- **Credentials live in a git-ignored `secrets.yaml` in each folder.** ESPHome reads `!secret` from the folder of the config being built. The repos are public, so a key or password must never appear in a config.
- **The key names differ per device:** `api_encryption_key` on the clock, `home_assistant_api_key` on the doorbell and `boiler_api_encryption_key` on the boiler monitor. Each file also holds `wifi_ssid` and `wifi_password`.
- **The files exist only on the machine that flashes the devices,** so keep a copy elsewhere. A lost API key means a new key, a reflash and re-authentication in Home Assistant.

## Encryption

- **The API is encrypted with a key per device.** Home Assistant's ESPHome config entry holds the same key. To change a key, set it in `secrets.yaml` and flash, then answer the re-authentication prompt under **Settings**, **Devices & services**. The prompt is a config flow with a `noise_psk` field, so `POST /api/config/config_entries/flow/FLOW_ID` with `{"noise_psk": "..."}` answers it without the UI. Find `FLOW_ID` with `hass-cli raw ws config_entries/flow/progress`.
- **OTA uploads are encrypted and need no password.** The `ota:` block carries a bare `encryption:`, which inherits the API key.
- **To move a device from password OTA to encrypted OTA, flash it twice.** The first flash keeps `password:` and adds `encryption: allow_plaintext_upload: true`, because the running firmware only understands password uploads. The second removes both. Leaving `allow_plaintext_upload` in place lets anyone on the network strip the encryption offer and downgrade an upload.
- **Don't add `web_server`.** Its `/update` endpoint accepts firmware in plaintext, which bypasses OTA encryption, and nothing uses its pages.

## Build and flash

Install ESPHome and the formatter with Homebrew:

```sh
brew install esphome yamlfmt
```

To flash a device over Wi-Fi, run the following from its folder:

```sh
esphome run DEVICE.yaml --device ADDRESS --no-logs
```

Replace `DEVICE` with the folder name and `ADDRESS` with the device's address from its
`sensor.*_ip_address` entity. Without `--device`, ESPHome finds the device by mDNS through the
gateway's reflector.

- **Nothing in Home Assistant builds or flashes these devices.** The ESPHome Device Builder add-on is not installed, because its copies of the configs went stale and installing one would have broken the device, as recorded in [_Configs moved out of the ESPHome dashboard_](history.md#2026-11-01-configs-moved-out-of-the-esphome-dashboard). Don't reinstall it to flash these devices.
- **After a flash, check two entities.** The device's online binary sensor must be `on`, and its version sensor must show the new ESPHome version and config hash.

## Config rules

- **All devices build on esp-idf,** which is ESPHome's default for the ESP32.
- **Format with `yamlfmt .` before committing.** Each folder has a `.yamlfmt` that keeps single blank lines and skips git-ignored files.
- **The clock's display uses `mipi_spi` with model `GC9A01A` and the model's default transform.** The default mirrors the x axis, which is what this panel needs. A `transform:` block with `mirror_x: false` draws the face mirrored left to right.
- **Every device config must define a time source,** because the `syslog` component in `debug.yaml` needs one for its timestamps. `debug.yaml` cannot define it: ESPHome rejects a second SNTP block with a different ID, and the clock already has one. Use `sntp` with chrony at `192.168.0.12` as the server. ESPHome's SNTP component ignores the NTP server that DHCP offers, so the address is in the config.
- **The clock uses ESPHome's default light Wi-Fi power save.** `power_save_mode: none` raised its chip temperature from about 45 °C to about 58 °C, so it stays off unless the API disconnects in [#7](https://github.com/tomwilkie/home/issues/7) return, as recorded in [_Clock API disconnects_](history.md#2026-11-01-clock-api-disconnects).
- **Boiler On needs blue above 50 and red below 30.** The burner raises the blue channel from about 44 to about 67 and leaves red near 24, while daylight from the cupboard door raises red and saturates the clear channel. Don't add `delayed_on` or `delayed_off`: the short burner cycles are real and worth seeing.

## CI

Each repo runs a workflow on push and on pull requests with the following two jobs:

- **`format`** runs `yamlfmt -lint`.
- **`build`** compiles the config with `esphome/build-action`, which uses the most recent ESPHome release at run time, and placeholder secrets.

In this repo, `.github/workflows/esphome.yml` runs only when `esphome/boiler-monitor/` or the
workflow changes.

## Known gaps

- **No ESPHome version is pinned.** CI tests the most recent release only when something is pushed, so a release that breaks a config shows up at the next push or flash.
- **The clock and doorbell repos have no Renovate,** so the action versions in their workflows stay as pinned until edited by hand.
