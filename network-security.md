# Network security and VLAN segmentation

This document describes how the home network is segmented to contain a compromised IOT or
camera device, and how to audit that the isolation holds.

The network runs on a UniFi Dream Machine Pro Max (UDM), with UniFi Network and UniFi Protect on
the same box. Firewall rules, WLAN isolation, switch-port isolation and multicast DNS (mDNS)
settings live on the UDM and are not file-managed, so this document is the source of truth for
their intent. To apply and inspect them, use the UniFi Network UI or the `unifi-network` MCP
server described in [_UniFi MCP servers_](access-home-assistant.md#unifi-mcp-servers).

## Goals

- **IOT devices reach the internet and Home Assistant only.** They don't reach the main LAN, the Cameras VLAN or each other. IOT devices with a local-only integration don't reach the internet either.
- **Cameras reach Home Assistant and the UniFi network video recorder (NVR) only.** They have no internet access and no lateral access, including to each other.
- **The isolation is auditable.** A device that breaches these rules is visible.

## Network map

The following table lists the networks:

| Network | Subnet | VLAN | Network ID | Notes |
|---|---|---|---|---|
| Default (main, SSIDs `catch22` and `catch25`) | 192.168.0.0/24 | untagged | `66c254deffcde7397016bae8` | The UDM is `.1`. Home Assistant lives here. |
| IOT (SSID `iot`) | 192.168.2.0/24 | 2 | `66c245d0eb7aca2624cf9a9e` | Has an ad-blocking DPI policy |
| Cameras (SSID `cameras`) | 192.168.3.0/24 | 3 | `66c32a78e23e0530de545643` | UniFi Protect cameras |
| 5G Internet | 192.168.4.0/24 | 4 | `69a69f92b0f8eea82e18ff77` | WAN failover |
| Remote-user VPN | 192.168.8.0/24 | none | `66ccac42e23e0530de571a6b` | |

The Home Assistant host is `192.168.0.12`, wired, on the Default network, with MAC
`c8:ff:bf:03:83:67`. Its address is a DHCP reservation and must stay pinned: it is the single
allow-exception target of the IOT and Camera rules, the target of the DNS and NTP redirects, and
the target of the front-door webhook in [notifications.md](notifications.md).

Home Assistant is on the main network, not on IOT, so the per-network **Network Isolation**
checkbox is the wrong tool: it would also cut IOT off from Home Assistant. The design needs
explicit firewall policies that block IOT to the main network and allow IOT to `192.168.0.12`.

### Move a device to another VLAN

- **A Protect camera can show offline after a subnet move** until the NVR rediscovers it. If it doesn't recover, reboot it or power-cycle its PoE port.
- **Reassigning a wired port's VLAN does not drop the link**, so the device keeps its old DHCP lease and loses its gateway. To force a fresh lease, disable and re-enable the switch port. A PoE power-cycle does nothing for a self-powered device.
- **A cloud-registered device needs a power-cycle after the move.** The Hive Hub is self-powered, so the controller cannot reboot it, and it only re-registers with its cloud after it is power-cycled by hand.

## Firewall policies

The design uses the Zone-Based Firewall (ZBF) because it separates the Gateway zone (DHCP and DNS
on the UDM) from the Internal zone. Blocking IOT to Internal therefore does not break DHCP or
DNS, which a flat `block 192.168.0.0/16` rule would.

IOT and Cameras each have a dedicated zone, so a device that joins either network is denied by
default rather than by an enumerated block. The main network and Home Assistant stay in
Internal:

| Zone | Zone ID | Member network |
|---|---|---|
| Internal | `6a3114d4631d350c25c14067` | Default, including Home Assistant |
| External | `6a3114d4631d350c25c14068` | Internet |
| IOT | `6a3115f9631d350c25c14179` | IOT |
| Cameras | `6a31160b631d350c25c141a3` | Cameras |

With dedicated zones, the UniFi predefined matrix allows IOT to External and allows IOT and
Cameras to Gateway (DHCP, DNS and the NVR). It blocks IOT and Cameras to Internal, and it also
blocks Internal to IOT and Internal to Cameras, which would stop Home Assistant controlling
devices and pulling streams. The following custom policies add the Home Assistant exceptions,
restore trusted inbound traffic, block camera internet access, and add logging for the audit.
Within each zone pair they are listed in evaluation order:

| Zone pair | Policy | Action | Logged | Policy ID | Purpose |
|---|---|---|---|---|---|
| IOT to Internal | `IOT to Home Assistant` | ALLOW to `192.168.0.12` | no | `6a311707631d350c25c14233` | Device-initiated traffic: MQTT, Wyoming voice, webhooks, DNS, NTP |
| IOT to Internal | `Block IOT to LAN` | BLOCK, `NEW` and `INVALID` states | yes | `6a311721631d350c25c1423c` | Containment |
| Internal to IOT | `LAN to IOT` | ALLOW | no | `6a311704631d350c25c14230` | The LAN initiates to IOT (ESPHome, Cast, printing) |
| Cameras to Internal | `Cameras to Home Assistant` | ALLOW to `192.168.0.12` | no | `6a31170a631d350c25c14239` | Camera-initiated traffic to Home Assistant |
| Cameras to Internal | `Block Cameras to LAN` | BLOCK, `NEW` and `INVALID` states | yes | `6a311724631d350c25c1423f` | Containment |
| Cameras to External | `Block Cameras to Internet` | BLOCK | yes | `6a311725631d350c25c14242` | Protect updates cameras through the NVR |
| Internal to Cameras | `Home Assistant to Cameras` | ALLOW from `192.168.0.12` | no | `6a311709631d350c25c14236` | Home Assistant pulls camera streams (RTSP) |
| IOT to External | `Block IOT DNS to Internet` | BLOCK tcp and udp, port group `DNS Ports` | yes | `6a3502392753ee32cc1f26e8` | Plain DNS and DNS over TLS to any resolver |
| IOT to External | `Block IOT to Public DNS Providers` | BLOCK all ports, address group `Public DNS Resolvers` | yes | `6a35023a2753ee32cc1f26eb` | DNS over HTTPS and anything else to the known public resolvers |
| IOT to External | `Block IOT NTP to Internet` | BLOCK udp, port group `NTP Ports` | yes | `6a36760b2753ee32cc2397f4` | Public NTP |
| IOT to External | `Block IOT No-Internet Devices` | BLOCK, source matched on client MAC | yes | `6a37a57e2753ee32cc2733cc` | [Per-device internet block](#per-device-internet-block) |
| IOT to External | `Log IOT to Internet (ALLOW)` | ALLOW | yes | `6a37a5b62753ee32cc273453` | Logs every IOT internet connection |

The policies reference the following firewall groups:

| Group | Type | Group ID | Members |
|---|---|---|---|
| `Public DNS Resolvers` | address group | `6a3502122753ee32cc1f2645` | 8.8.8.8, 8.8.4.4, 1.1.1.1, 1.0.0.1, 9.9.9.9, 149.112.112.112, 208.67.222.222, 208.67.220.220, 94.140.14.14, 94.140.15.15, 4.2.2.1, 4.2.2.2, 4.4.4.4, 64.6.64.6, 64.6.65.6 |
| `DNS Ports` | port group | `6a3502132753ee32cc1f2648` | 53, 853 |
| `NTP Ports` | port group | `6a3675fb2753ee32cc2397cb` | 123 |

### Log every BLOCK policy

Keep `logging: true` on the BLOCK policies. The gateway only emits a firewall log line for a
policy with logging enabled, and the [audit](#audit-the-isolation), the Loki pipeline and the
[drift alert](#drift-detection) all depend on those lines.

### Containment blocks match new connections only

`Block IOT to LAN` and `Block Cameras to LAN` must use `connection_state_type: CUSTOM` with
`connection_states: ["NEW","INVALID"]`, not `ALL`.

A containment block exists to stop a device initiating into the LAN. UniFi creates the block
with `ALL`, which also drops the `ESTABLISHED` and `RELATED` return traffic of connections that
a LAN device started. That breaks Internal to IOT for every main-LAN host except Home Assistant,
which survives only because its own allow sits above the block. The symptom is that AirPrint,
Cast or an ESPHome web UI fails from any device other than Home Assistant.

To tell a forward drop from a return drop, read the UDM's connection tracker with
`ssh root@192.168.0.1 "conntrack -L -d IOT_IP"`. A flow stuck in `SYN_RECV` with a high
reply-packet count is the return being blocked.

### Rule ordering

Within a zone pair the first matching rule wins, and the lowest `index` is evaluated first. ZBF
evaluates the whole custom band (index 10000 to 29999) before the predefined band (30000 and
later).

In the IOT to External pair, the blocks must stay above `Log IOT to Internet (ALLOW)`. The ALLOW
matches all IOT internet traffic, so any rule placed after it never matches.

A created custom rule lands last in its zone pair. To place a rule above the ALLOW, create the
rule, then delete and re-create the ALLOW so that the ALLOW lands last again. Re-creating the
ALLOW changes its policy ID, so update the policy table afterwards. The reorder tool did not
work when these rules were built, as described in
[_Firewall tools_](access-home-assistant.md#firewall-tools).

## Same-VLAN isolation

Firewall policies do not stop two devices on the same VLAN talking to each other, because that
traffic is switched at layer 2 and does not reach the gateway. Two settings cover it:

- **Wireless devices:** Client Device Isolation (`l2_isolation`) on the `iot` WLAN (`66c24e06eb7aca2624cf9fb5`) and the `cameras` WLAN (`66c32aafe23e0530de545688`).
- **Wired devices:** switch-port isolation (`isolation: true` in the port override) on the following ports:

| Device | VLAN | Switch | Port |
|---|---|---|---|
| Norman Hub | IOT | `USW Pro Max 16 PoE` | 5 |
| Hive Hub | IOT | `Basement Switch` | 8 |
| Garage Door camera (G5 Turret Ultra) | Cameras | `Garage Switch` | 5 |
| Garage camera (AI Pro) | Cameras | `Garage Switch` | 7 |
| Back-garden camera (G5 Turret Ultra) | Cameras | `Basement Switch` | 3 |

Isolation breaks peer-to-peer features on that VLAN, such as multi-room audio grouping and local
device-to-device discovery. We accept that in exchange for containment. Port isolation works per
switch, so it does not block same-VLAN traffic between devices on different switches.

## Cross-VLAN discovery

Home Assistant is on a different VLAN from IOT, so multicast discovery (HomeKit, Cast, ESPHome,
Matter) needs the mDNS reflector: global Multicast DNS plus `mdns_enabled: true` on the IOT
network. Without it, devices that are already added keep working, and discovery of added devices
breaks. The reflector runs on the gateway, so the IOT to Internal block does not affect it.

## DNS and NTP forcing

IOT devices resolve names and sync time against services on the Home Assistant host, whatever
resolver or time server they are configured with. Every lookup is then visible per device, and a
device that ignores DHCP still gets working DNS and time.

A packet meets the following layers in order:

1. **DHCP.** The IOT network hands out `192.168.0.12` as its DNS server and as its NTP server (option 42). Devices that honour DHCP go straight to the local services.
2. **Destination NAT (DNAT) redirect.** The gateway rewrites plain DNS (port 53) and NTP (udp port 123) from IOT to any other address so that it goes to `192.168.0.12`. This catches devices with a hardcoded resolver or time server.
3. **Local services.** AdGuard Home answers DNS and chrony answers NTP. IOT reaches both through `IOT to Home Assistant`.
4. **BLOCK policies.** The three DNS and NTP blocks are the fail-closed backstop for what the redirect cannot catch, and for everything if the redirect is removed.

Don't block NTP without a working local time server. A device with no clock fails TLS.

### AdGuard Home

AdGuard Home runs as the Home Assistant add-on `a0d7b954_adguard` and is the resolver for IOT
only. The main LAN uses the UDM resolver.

- **Listener:** `0.0.0.0:53`. The add-on default binds `127.0.0.1`, so `bind_hosts` under `dns` in `AdGuardHome.yaml` is changed. The admin UI stays on `127.0.0.1` behind Home Assistant Ingress.
- **Upstream:** Quad9 DNS over HTTPS (`https://dns10.quad9.net/dns-query`), with DNSSEC on.
- **Blocking:** the AdGuard default blocklist.
- **Query log:** 90 days, per client, filterable by IOT address in the AdGuard UI. Alloy also ships it to Loki, as described in [_AdGuard Home query log_](observability.md#adguard-home-query-log).

### chrony

chrony runs as the Home Assistant add-on `a0d7b954_chrony` on `192.168.0.12:123`, at stratum 2.

### Blocks

`Block IOT DNS to Internet` and `Block IOT NTP to Internet` stay at about zero hits while the
redirect is in place, because a redirected packet's destination is already `192.168.0.12` when
the firewall evaluates it. `Block IOT to Public DNS Providers` catches DNS over HTTPS (DoH) on
port 443 to the listed resolvers, which the redirect cannot rewrite.

To check that the blocks fire, query `{log_type="firewall", rule=~"Block IOT.*"}` in Loki.

Two gaps remain:

- **DoH to a provider outside the address group** passes on port 443. Closing it needs filtering on the TLS server name.
- **IPv6 DoH is not covered**, because the address group is IPv4 only. The port rules have `ip_version: BOTH`, so they do cover IPv6 plain DNS and DNS over TLS.

### DNAT redirect

Three `nat PREROUTING` rules on the UDM, on interface `br2` (IOT), sit above UniFi's
`UBIOS_PREROUTING_JUMP`:

```
iptables -t nat -I PREROUTING -i br2 -p udp --dport 123 ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # NTP -> chrony
iptables -t nat -I PREROUTING -i br2 -p udp --dport 53  ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # DNS -> AdGuard
iptables -t nat -I PREROUTING -i br2 -p tcp --dport 53  ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # DNS -> AdGuard
```

- **No source NAT is needed.** The target is on a different subnet, so replies route back through the UDM and the connection tracker reverses the DNAT. `rp_filter` is loose (`2`), so the return path is not dropped. Keeping the real source address preserves per-device visibility in the chrony and AdGuard logs.
- **Flush the connection tracker after inserting a rule.** Live UDP flows bypass a freshly inserted PREROUTING rule until they expire. `apply.sh` runs `conntrack -D -p udp --dport PORT` for the ports it changes.
- **The redirect runs before the firewall.** DNAT happens in `nat PREROUTING`, ahead of the ZBF forward chains, so a redirected packet matches `IOT to Home Assistant` and not the port 53 and port 123 blocks.

### Persistence

The UDM (UniFi OS 5.1.19, which uses iptables-legacy) clears custom iptables rules on reboot.
The following files restore them at boot:

| Path | Purpose |
|---|---|
| `/persistent/iot-redirect/apply.sh` | Inserts the three DNAT rules if they are missing, then flushes the connection tracker. `/persistent` survives reboot and firmware upgrade. |
| `/persistent/iot-redirect/install.sh` | Writes and enables the systemd unit. Run it again after a firmware upgrade, which wipes `/etc`. |
| `/etc/systemd/system/iot-redirect.service` | A `oneshot` unit that runs `apply.sh` after `network-online.target` and `udapi-server.service`, with a 30-second sleep so that udapi builds its ruleset first. |

To re-apply the rules by hand, run `ssh root@192.168.0.1 '/persistent/iot-redirect/apply.sh'`
or `systemctl restart iot-redirect`. Don't use `systemctl start`: the unit is `RemainAfterExit`,
so `start` does nothing after the first run.

### Drift detection

A Grafana alert fires if the redirect is removed. Without the redirect, the port 53 and port 123
blocks start logging, a recording rule turns those lines into a metric, and the alert watches
the metric. The rules are in
[_IOT DNAT redirect tripwire_](observability.md#iot-dnat-redirect-tripwire). The remediation is
to run `apply.sh`.

## IOT internet destinations

`Log IOT to Internet (ALLOW)` logs every IOT internet connection, so the gateway emits one
kernel firewall log line per connection. With the **firewall** category enabled in the UDM's
remote logging, those lines reach Loki over the syslog pipeline described in
[_UniFi firewall and DNS logs_](observability.md#unifi-firewall-and-dns-logs).

To list a device's destinations, query:

```
{log_type="firewall", rule="Log IOT to Internet (ALLOW)"} |= "SRC=192.168.2.67"
```

The destinations are IP addresses, not domains. For the domains a device looks up, use the
AdGuard query log.

## Per-device internet block

Some IOT devices have a local-only Home Assistant integration and no need for the internet.
`Block IOT No-Internet Devices` cuts their WAN access, so a compromised device cannot exfiltrate
or phone home. The rule blocks WAN only: traffic to Home Assistant is untouched, and the DNS and
NTP redirects are LAN-local, so a blocked device keeps working time and resolution.

The rule is a custom ZBF policy that matches the source on client MAC
(`matching_target: CLIENT`, `matching_target_type: SPECIFIC`). A MAC is stable, so the rule
needs no address group and no DHCP reservations. A custom rule is required because an
Object-Oriented Network (OON) policy generates predefined rules, which sit in the predefined band
and can never outrank the custom catch-all ALLOW.

The rule's `source.client_macs` lists the following devices, each verified to have a local Home
Assistant path. The addresses are DHCP leases, not reservations:

| Device | IP | MAC | Local path |
|---|---|---|---|
| Master Bedroom - Norman Hub | .225 | `80:5e:4f:9d:da:a3` | norman_shutters |
| Master Bedroom - Clock | .42 | `c0:4e:30:13:33:d8` | esphome |
| Hallway - Doorbell | .49 | `d8:3b:da:45:62:b8` | esphome |
| Master Bedroom - Dyson Fan | .19 | `44:6f:f8:42:ba:f7` | dyson_local |
| Nursery - VELUX Gateway | .196 | `70:ee:50:6a:51:2d` | homekit_controller |
| Tom's Office - Aircon | .24 | `10:68:38:47:dc:b5` | daikin (local) |
| Master Bedroom - Aircon | .27 | `10:68:38:47:4c:7f` | daikin (local) |
| Living Room - Arylic LP10 | .237 | `00:22:6c:23:38:56` | linkplay |
| Tom's Office - Arylic LP10 | .245 | `00:22:6c:67:19:56` | linkplay |
| Nursery - WiiM Sound | .10 | `40:fd:f3:66:ac:e4` | wiim |
| Basement - Dryer | .68 | `94:27:70:e6:c1:3d` | mqtt (hcpy local bridge) |

The block has the following effects:

- **Daikin, Dyson, VELUX and Norman** lose only the vendor cloud app (Onecta, MyDyson, VELUX Active), not Home Assistant control.
- **The dryer stays local** although it is a Home Connect appliance. The hcpy add-on bridges it to MQTT over the LAN, so the "Tumble Drier finished" notification still works.
- **The streamers keep working through Music Assistant**, which fetches the stream on the Home Assistant server and serves it over the LAN. Direct streaming on the device stops: Spotify Connect, the vendor app and on-device internet radio.

The following devices are deliberately left out of the rule:

- **The Everything Presence Lites and the Voice Assistants**, so that they can pull firmware.
- **Tom's Office - AirGradient**, which has a local API but keeps its internet access.
- **Cloud-dependent devices:** Nest Protect, Hive, Deebot, Netatmo, the Kitchen Display, the Prusa cameras and the alarm module.

To change membership, edit the rule's `source.client_macs` in the UniFi UI (**Firewall**,
**Policies**, **Block IOT No-Internet Devices**) or through the firewall tools. Then flush the
connection tracker for the affected address with `ssh root@192.168.0.1 conntrack -D -s IOT_IP`,
so that live flows are re-evaluated.

## Audit the isolation

To audit without the UI, query Traffic Flows by source network through the `unifi-network` MCP
server:

```
unifi_get_traffic_flows(source_network_id="66c245d0eb7aca2624cf9a9e", within_hours=168)   # IOT
unifi_get_traffic_flows(source_network_id="66c32a78e23e0530de545643", within_hours=168)   # Cameras
```

Each flow carries an `action` (`allowed` or `blocked`), a `direction` and the policies it
matched. A healthy result has the following properties:

- **IOT:** the only allowed `local` destinations are `192.168.0.12` and the IOT gateway address `192.168.2.1`. An allowed `local` DNS or NTP flow to a public address is the DNAT redirect at work. Any other allowed local destination is a rule gap.
- **Cameras:** the only allowed local destinations are `192.168.0.12` and the gateway, which hosts the NVR. Any allowed internet flow is a breach.
- **Both:** blocked flows to other LAN hosts show the containment policies doing their job.

`unifi_get_traffic_flow_statistics` gives a top-talkers and top-blocked overview. Loki keeps the
firewall log lines of every logged policy for 30 days.

## Known gaps

- **Persistence is boot-only.** A controller provision can flush the DNAT rules, and nothing restores them until the next reboot or a manual `apply.sh`. The drift alert reports it. If it recurs, add a self-healing timer.
- **The audit is manual.** Run the Traffic Flows queries periodically.
