# Network Security & VLAN Segmentation

How the home network is segmented to contain a compromised IOT or camera device,
and how to audit that the isolation rules hold.

The network runs on a UniFi **Dream Machine Pro Max** (UniFi OS; Network +
Protect/NVR on the same box). Firewall rules, WLAN isolation, switch-port
isolation, and mDNS settings live on the UDM and are **not** file-managed — this
document is the source of truth for their *intent* and the audit procedure. Apply
and inspect them via the UniFi Network UI or the `unifi-network` MCP server (see
[@access-home-assistant.md](access-home-assistant.md)).

## Goals

- **IOT** devices can reach the **internet** and **Home Assistant** only — not
  the main LAN, not the Cameras VLAN, not each other.
- **Cameras** can reach **Home Assistant** and the **UniFi NVR** only — no
  internet, no lateral access, not each other.
- The isolation is **auditable**: any device breaching these rules is visible.

## VLAN / network map

| Network | Subnet | VLAN | Network ID | Notes |
|---|---|---|---|---|
| Default ("main", SSIDs `catch22`/`catch25`) | 192.168.0.0/24 | untagged | `66c254deffcde7397016bae8` | UDM = `.1`; **Home Assistant lives here** |
| IOT (SSID `iot`) | 192.168.2.0/24 | 2 | `66c245d0eb7aca2624cf9a9e` | has an ad-blocking DPI policy |
| Cameras (SSID `cameras`) | 192.168.3.0/24 | 3 | `66c32a78e23e0530de545643` | UniFi Protect cameras |
| 5G Internet | 192.168.4.0/24 | 4 | `69a69f92b0f8eea82e18ff77` | WAN failover |
| Remote-user VPN | 192.168.8.0/24 | — | `66ccac42e23e0530de571a6b` | |

**Home Assistant host:** `192.168.0.12` — wired, **DHCP-reserved**
(`use_fixedip`), MAC `c8:ff:bf:03:83:67`, on the Default network. This is the
single allow-exception target referenced by the IOT and Camera rules, so it must
stay pinned (the front-door webhook also depends on this reservation — see
[@notifications.md](notifications.md)).

> **back-garden camera** was moved off the main network onto the **Cameras VLAN**
> (now `192.168.3.211`) so the camera-containment rules apply to it. After a
> subnet move an adopted Protect camera may briefly show offline until the NVR
> re-discovers it (reboot / power-cycle its PoE port if it doesn't recover).

> **Why HA needs an explicit exception:** HA is on the *main* network, not on
> IOT. So this is **not** the per-network "Network Isolation" checkbox (which
> would also cut IOT off from HA). It requires explicit firewall policies that
> block IOT→main while allowing IOT→`192.168.0.12`.

## Firewall policies (Zone-Based Firewall)

Zone-Based Firewall is used because it separates the **Gateway** zone (DHCP/DNS
to the UDM) from the **Internal** zone, so "block IOT→Internal" does not also
break DHCP/DNS — unlike a flat `block 192.168.0.0/16` rule.

**Zone model.** IOT and Cameras each have a **dedicated zone** (so the policy is
default-DENY for a new device, not reliant on enumerating blocks); the main
network and HA stay in **Internal**:

| Zone | Zone ID | Member network |
|---|---|---|
| Internal | `6a3114d4631d350c25c14067` | Default / main (incl. HA `.12`) |
| IOT | `6a3115f9631d350c25c14179` | IOT (192.168.2.0/24) |
| Cameras | `6a31160b631d350c25c141a3` | Cameras (192.168.3.0/24) |

With dedicated zones the UniFi **predefined** matrix already gives us: IOT→Internal
BLOCK, IOT→External (internet) ALLOW, IOT/Cameras→Gateway (DHCP/DNS/NVR) ALLOW,
Cameras→Internal BLOCK — **and** Internal→IOT / Internal→Cameras BLOCK (which
would stop HA controlling devices / pulling streams). The custom policies below
add the HA exceptions, restore trusted inbound, block camera internet, and add
**logging** for the audit. Within each zone-pair, ALLOWs sit above the BLOCK.

| Action | From | To | Logged | Purpose |
|---|---|---|---|---|
| ALLOW | IOT | HA `192.168.0.12` | — | device-initiated: MQTT, Voice/Wyoming, webhooks |
| BLOCK | IOT | Internal (rest of main LAN) | ✓ | containment |
| ALLOW | Internal (any) | IOT | — | HA/LAN initiates to IOT (ESPHome, Cast, push); stateful, IOT can't initiate back |
| ALLOW | Cameras | HA `192.168.0.12` | — | camera-initiated to HA (if any) |
| BLOCK | Cameras | Internal (rest of main LAN) | ✓ | containment |
| BLOCK | Cameras | External (internet) | ✓ | Protect updates cameras via the NVR |
| ALLOW | HA `192.168.0.12` only | Cameras | — | HA may pull camera streams directly (RTSP) |

- IOT→Internet and IOT/Cameras→Gateway (DHCP/DNS, and Camera↔NVR) are allowed by
  the ZBF predefined matrix — no custom rule needed.

> **Logging is enabled on the BLOCK policies.** UniFi Traffic Flows only records
> traffic that *matches a policy* — ordinary allowed inter-VLAN traffic is not
> logged. Logging the block rules is what makes the audit below meaningful.

## Same-VLAN (device-to-device) isolation

L3 firewall policies do **not** stop two devices on the *same* VLAN talking to
each other — that traffic is L2-switched and never reaches the gateway. To meet
"not each other":

- **Wireless** IOT/camera devices → **Client Device Isolation** (`l2_isolation`)
  on the `iot` (`66c24e06eb7aca2624cf9fb5`) and `cameras`
  (`66c32aafe23e0530de545688`) WLANs.
- **Wired** IOT (e.g. Norman Hub) and wired PoE cameras → **switch-port
  isolation** (port profile) on the UniFi switch.

> **Tradeoff:** L2 isolation breaks peer-to-peer features on that VLAN (e.g.
> multi-room audio grouping, local device-to-device discovery). Accepted here in
> exchange for containment.

## Cross-VLAN discovery (mDNS)

Because HA is on a different VLAN from IOT, multicast discovery
(HomeKit / Cast / ESPHome / Matter) needs the **mDNS reflector** enabled (global
Multicast DNS + per-network mDNS), with the firewall permitting it. Without it,
already-added devices keep working but **auto-discovery of new devices breaks**.
The reflector runs at the gateway, so it keeps working despite the IOT→Internal
block. This was **already enabled** (`mdns_enabled: true` on the IOT network) —
left as-is.

## Auditing the isolation

Repeatable, no UI needed, via the `unifi-network` MCP `unifi_get_traffic_flows`
tool. Query by source network and inspect `direction: "local"` flows:

```
# IOT — any blocked lateral attempts (containment working), and any allowed
# local destination that is NOT 192.168.0.12 (HA) = a rule gap / breach
unifi_get_traffic_flows(source_network_id="66c245d0eb7aca2624cf9a9e",
                        direction="local", within_hours=168)

# Cameras — allowed local dest must be only HA (.12) or the NVR/gateway;
# any allowed internet flow = a breach
unifi_get_traffic_flows(source_network_id="66c32a78e23e0530de545643",
                        within_hours=168)
```

- A healthy result shows the BLOCK policies logging blocked attempts to non-HA
  hosts (and, for cameras, blocked internet), and **no** allowed local flow to
  any destination other than HA / NVR.
- `unifi_get_traffic_flow_statistics` gives a top-talkers / top-blocked overview.
- Reminder: only policy-matched traffic appears, so the audit's coverage depends
  on the block rules having **logging enabled**.

## Status

- [x] `UNIFI_API_KEY` configured on the `unifi-network` MCP server.
- [x] Zone-Based Firewall enabled; dedicated `IOT` + `Cameras` zones created,
      networks assigned.
- [x] IOT firewall policies created (HA exception + logged block + trusted inbound).
- [x] Cameras firewall policies created (HA exception + logged blocks incl. internet).
- [x] `l2_isolation` enabled on `iot` + `cameras` WLANs.
- [x] **Switch-port isolation for wired devices** (`isolation: true` confirmed):
      - Norman Hub (IOT) — `USW Pro Max 16 PoE` port 5.
      - Garage Door camera, G5 Turret Ultra (Cameras) — `Garage Switch` port 5.
      - Garage camera, AI Pro (Cameras) — `Garage Switch` port 7.
      Port isolation is per-switch, so it does not block same-VLAN traffic between
      devices on *different* switches (inherent L2 limit; minor residual for
      trusted cams). The back-garden cam on `Basement Switch` port 3 is **not**
      isolated — optional to add.
- [x] mDNS reflector already enabled (`mdns_enabled: true`), left as-is.
- [x] Functional verification: camera entities `recording`, IOT Voice satellites
      connected after the change.
- [ ] Ongoing audit (re-run the traffic-flow queries above periodically).

### Live policy IDs (created via MCP)

| Name | Policy ID |
|---|---|
| IOT to Home Assistant (ALLOW) | `6a311707631d350c25c14233` |
| Block IOT to LAN (BLOCK, logged) | `6a311721631d350c25c1423c` |
| LAN to IOT (ALLOW) | `6a311704631d350c25c14230` |
| Cameras to Home Assistant (ALLOW) | `6a31170a631d350c25c14239` |
| Block Cameras to LAN (BLOCK, logged) | `6a311724631d350c25c1423f` |
| Block Cameras to Internet (BLOCK, logged) | `6a311725631d350c25c14242` |
| Home Assistant to Cameras (ALLOW) | `6a311709631d350c25c14236` |
