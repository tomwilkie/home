# Network

This document describes the internet connections, the queue management on each, and the Wi-Fi
layout. VLANs, firewall policies, DNS forcing and intrusion detection are in
[network-security.md](network-security.md).

The settings live on the UniFi Dream Machine Pro Max (UDM) and are not file-managed, so this
document is the source of truth for their intent. To read and change them, use the UniFi Network
UI, the `unifi-network` MCP server or the raw API, as described in
[_UniFi MCP servers_](access-home-assistant.md#unifi-mcp-servers).

## Internet connections

The UDM has two internet connections, and the following table lists them:

| WAN | Name in UniFi | Role | Path to the UDM |
|---|---|---|---|
| DSL line | `Internet 1` | Primary | The EE hub, into UDM port `eth8`. The UDM's WAN address is a `192.168.1.x` lease from the hub, so traffic is translated twice (double NAT). |
| 5G | `UniFi 5G A` | Failover only, priority 2 | The U5G Max (`192.168.4.34`) on the `5G Internet` network (VLAN 4), which carries a GRE tunnel (`gre1`) to the UDM. The SIM has unlimited data. |

- **`Internet 2` stays disabled.** It has no port assigned. See [_2026-11-11: Wi-Fi channel plan_](history.md#2026-11-11-wi-fi-channel-plan) for how it was found enabled.
- **The DSL line's modem syncs at 64.68 Mbps down and 13.17 Mbps up.** The ISP speed fields on `Internet 1` (`wan_provider_capabilities`) are set to 60 Mbps and 12 Mbps. UniFi uses them only for its usage percentages and graphs.
- **The U5G Max takes its network from the Tom's Office AP's pass-through port.** If that AP restarts, the failover connection drops with it.
- **The U5G Max's modem resets itself.** The alert that catches it is in [_U5G Max modem reset_](observability.md#u5g-max-modem-reset).

Both connections report BT (AS2856) as their provider, because EE is part of BT. To tell them
apart, look up the public address's owner: the 5G connection exits from an EE mobile range.

## Smart Queues

Smart Queues is on for both connections. It caps each connection just below the speed it can
sustain, so that the queue forms in the UDM, which shares the line fairly, rather than in the
modem's buffer. Without it, a single upload saturates the line and every other connection waits
behind it.

The following table lists the caps:

| WAN | Download cap | Upload cap | Bufferbloat grade |
|---|---|---|---|
| `Internet 1` | 45 Mbps | 11.5 Mbps | A |
| `UniFi 5G A` | 150 Mbps | 8 Mbps | C |

- **Upload is the cap that matters on both connections.** Each has an upload of about 10–13 Mbps, and unshaped uploads added 394 ms (DSL) and 858 ms (5G) of latency.
- **We accept a C on 5G.** 5G throughput varies with signal and cell load, so when the cell delivers less than the 150 Mbps cap, the queue forms in the mobile network. A 100 Mbps download cap would improve the grade, but 5G carries traffic only during a failover.
- **The DSL download cap sits just above what the line delivers unshaped.** A higher cap brings the download latency back.

The measurements are in [_2026-11-12: Smart Queues_](history.md#2026-11-12-smart-queues).

### Change a cap

To change a cap, `PUT` the fields to the WAN's network:

```sh
curl -sk -H "X-API-KEY: $UNIFI_API_KEY" -H 'Content-Type: application/json' -X PUT \
  https://192.168.0.1/proxy/network/api/s/default/rest/networkconf/NETWORK_ID \
  -d '{"wan_smartq_enabled":true,"wan_smartq_down_rate":45000,"wan_smartq_up_rate":11500}'
```

Replace `NETWORK_ID` with the WAN's `_id` from `unifi_list_networks`. The rates are in kbps. In
the UI, the setting is under **Settings** > **Internet** > the WAN > **Smart Queues**.

After a change, run the [Waveform bufferbloat test](https://www.waveform.com/tools/bufferbloat)
from a device close to an AP or wired, and keep the highest caps that still grade A or B.

## Test the 5G connection from one device

To send one device's traffic over the 5G connection without failing the whole house over, add a
temporary traffic route:

1. Create an `INTERNET` route to `UniFi 5G A` for the device's MAC with `unifi_create_traffic_route` (`matching_target: INTERNET`, one `CLIENT` target, `kill_switch_enabled: false`).
2. Wait about 15 seconds, then confirm that the device's public address has changed and is in an EE mobile range, for example with `curl https://ifconfig.co/json`.
3. Run the test.
4. Delete the route. The MCP server has no delete tool, so `DELETE` it through the raw API:

   ```sh
   curl -sk -H "X-API-KEY: $UNIFI_API_KEY" -X DELETE \
     https://192.168.0.1/proxy/network/v2/api/site/default/trafficroutes/ROUTE_ID
   ```

   Replace `ROUTE_ID` with the `id` that the create call returned. The device's public address returns to the DSL line's within about 30 seconds.

A browser test can stall on its first step just after the route is added. Reload the page and
start it again.

## Wi-Fi

### SSID placement

An SSID broadcasts only from the APs that need it, which keeps a device on the AP nearest to it
and stops it roaming to a distant one. The other WLANs broadcast from every AP:

| WLAN | AP group | Bands | Reason |
|---|---|---|---|
| `cameras` | "Ground Floor" | 5 GHz | The wireless cameras connect through the Ground Floor AP. |
| `nursery` | "Nursery and Ground Floor" | 2.4 GHz | See [_Nursery network_](network-security.md#nursery-network). |

### Channel plan

The channels are set by hand on each AP. The following table lists the plan:

| AP | 2.4 GHz | 5 GHz (80 MHz) | 6 GHz (160 MHz) |
|---|---|---|---|
| Basement | 6 | 56 | 37 |
| Garage | auto | 136 | none |
| Ground Floor | 11 | 36 | 21 |
| Nursery | 6 | 100 | auto |
| Tom's Office | 11 | 157 | none |

- **Keep 2.4 GHz off Wi-Fi channels 1 to 4.** Zigbee runs on channel 11 (2405 MHz), which sits inside Wi-Fi channel 1. Use only channels 6 and 11, which leave Zigbee clear. If the Garage AP's automatic choice lands below channel 5, set it to 6.
- **Give each AP its own 5 GHz block.** The UK's 80 MHz blocks are 36–48, 52–64, 100–112, 116–128, 132–144 and 149–161, so the APs never need to share one.
- **Keep busy APs out of the 132–144 block.** Apple devices sold in the UK don't support channel 144, so they use only the 40 MHz half of that block. The Garage AP has it because it has no 5 GHz clients.
- **Avoid the 116–128 block.** Channels 120 to 128 are weather-radar channels, where the AP can listen for up to 10 minutes after a restart before it transmits.
- **Prefer a non-radar block for the Ground Floor AP.** Channels 36 to 48 have no radar check, so the AP that serves the cameras and the living room never waits after a restart or gets forced off its channel.
- **Give each 6 GHz AP its own 160 MHz block** (1–29, 33–61 or 65–93).
- **Check a change with an RF scan** (`unifi_trigger_rf_scan`, then `unifi_get_rf_scan_results`). An AP drops its clients for the 5 to 10 minutes it scans, so scan the Nursery and Ground Floor APs when the baby camera is not in use.

The radio settings are in each device's `radio_table`. Change them with a `PUT` to
`/proxy/network/api/s/default/rest/device/<_id>` that sends the whole `radio_table`.

### Roaming

- **Leave Fast Roaming (802.11r) off on `catch22` and `catch25`.** With it on, the Apple TVs in the living room interrupted streams as they roamed between the Ground Floor and Basement APs, which they both hear weakly.
- **BSS Transition (802.11v) is on.** If the Apple TVs still stutter on Wi-Fi, turn it off next. Wiring them is the real fix.

The scans and changes were made on 2026-11-11, as recorded in
[_2026-11-11: Wi-Fi channel plan_](history.md#2026-11-11-wi-fi-channel-plan).
