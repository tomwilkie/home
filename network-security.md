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

> **Hive Hub** was moved off the main network onto the **IOT VLAN** (now
> `192.168.2.125`, DHCP; wired on `Basement Switch` port 8, port isolation on).
> The Hive HA integration is **cloud-only**, so the hub only needs internet
> (IOT→External, allowed) — no HA exception required. Gotcha for legacy wired
> devices on a VLAN move: reassigning the port's VLAN does **not** drop the link,
> so the device keeps its old-subnet DHCP lease and loses its gateway. Bounce the
> switch-port link (disable/enable; it's **not** PoE, so a PoE power-cycle is a
> no-op) to force a fresh lease, then **power-cycle the hub** so it re-registers
> with its cloud. (The hub being self-powered, not PoE, also means it isn't
> rebootable from the controller.)

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

## IOT internet-destination visibility & DNS forcing

Two related goals: see *which internet hosts* each IOT device reaches, and stop
IOT devices using public DNS so their lookups are visible/controllable.

### Why Insights → Flows wasn't enough

UniFi's Insights → Flows (and the `unifi_get_traffic_flows` /
`unifi_get_traffic_flow_statistics` MCP tools) only retain **blocked** flows on
this console — even a custom ALLOW policy with `logging: true` does **not**
surface its allowed per-flow records there (`allowed_count_by_risk` is always
empty). So the top-destination data those tools return is exclusively
ad-block/DPI **blocks**, mostly from the main LAN — useless for "where is IOT
going".

### How per-flow destinations are actually captured

The working path is **UDM firewall log → remote syslog → Alloy → Loki** (see
[@observability.md](observability.md)):

1. A logged ALLOW policy **`Log IOT to Internet (ALLOW)`** (IOT→External, any,
   `logging: true`) makes the gateway emit a kernel iptables LOG line per IOT
   internet connection:
   ```
   [CUSTOM1_WAN-A-10000] DESCR="Log IOT to Internet (ALLOW)" IN=br2 OUT=eth8
   SRC=192.168.2.18 DST=8.8.8.8 PROTO=TCP SPT=... DPT=443 ...
   ```
2. Enabling the **firewall** log category in the UDM's Remote Logging exports
   those lines over the same UDP/514 syslog already feeding Loki.
3. Query in Grafana Cloud (Alloy tags these `log_type="firewall"` with the policy
   name as the `rule` label — see [@observability.md](observability.md)):
   `{log_type="firewall", rule="Log IOT to Internet (ALLOW)"} |= "SRC=192.168.2"`
   — destinations are **IPs**, not domains (reverse-resolve as needed).

> **Ordering gotcha.** The catch-all `Log IOT to Internet (ALLOW)` matches *all*
> IOT→External, so it must sit **below** the DNS BLOCK rules or it shadows them
> (first match wins; lowest `index` evaluated first). The integration-API reorder
> endpoint currently **500s** (`unifi_reorder_firewall_policies`), and direct
> `index` edits via `unifi_update_firewall_policy` are silently ignored
> ("accepted but did not apply"). Workaround: **delete and recreate** the rule
> that needs to move down — a freshly created custom rule is appended *last*
> (highest index) within its zone-pair. (That's why the ALLOW rule's policy ID
> below differs from the one originally created.)

### DNS forcing (block public resolvers)

IOT devices were found going **directly to public DNS** (8.8.8.8, 8.8.4.4,
1.1.1.1/1.0.0.1, 9.9.9.9/149.112.112.112, …) — including **DoH on 443** —
bypassing the gateway resolver entirely, so their lookups never reached CoreDNS
and couldn't be logged.

> **Plain DNS (:53) is now transparently DNAT-redirected to the local AdGuard
> resolver** (see [DNAT redirection & persistence](#dnat-redirection--persistence-dns--ntp)
> below), so hardcoded-DNS devices get *working* resolution instead of dropped
> lookups. The two BLOCK rules below remain as the fail-closed backstop for what
> DNAT can't catch (encrypted DoT/DoH, and any :53 that escapes if the redirect is
> removed).

Two BLOCK rules (IOT→External, logged, ordered **above** the ALLOW) force
everything else back onto the local resolver:

| Rule | Matches | Catches |
|---|---|---|
| `Block IOT DNS to Internet` | proto tcp_udp, dst **port group `DNS Ports` {53, 853}**, any internet host | plain DNS + DoT to *any* resolver |
| `Block IOT to Public DNS Providers` | **all ports**, dst **address group `Public DNS Resolvers`** (15 IPs) | DoH (`:443`) + anything to the known public resolvers |

IOT→Gateway DNS stays allowed (ZBF predefined matrix), so devices that honour the
DHCP-handed resolver keep working; the blocks only hit *external* destinations.
Verify the blocks fire: `{log_type="firewall", rule=~"Block IOT.*"}` (or the
older content filter `{instance="udm"} |~ "DESCR=.Block IOT"`).

> **Caveats / known gaps:**
> - **DoH to providers not in the IP list** (NextDNS, other Google/Cloudflare
>   ranges) still slips through on 443 — no clean fix without SNI filtering.
> - **IPv6 DoH** isn't covered (the address group is IPv4-only; the port rule's
>   `ip_version: BOTH` does cover IPv6 plain DNS/DoT).
> - **Hardcoded-DNS devices may break.** Several IOT devices (e.g. Hive Hub
>   `.125`, Kitchen Display `.18`) just *retry* public DNS rather than fall back,
>   so they may have degraded resolution until a local resolver (gateway CoreDNS
>   / AdGuard) answers them.

### DNS query logging — AdGuard Home (live)

Full per-domain IOT visibility is now provided by **AdGuard Home**, deployed as a
**Home Assistant add-on** (`a0d7b954_adguard`, the `hassio-addons` repo) on the HA
host `192.168.0.12`:

- **Listens** on `0.0.0.0:53` (the add-on default binds `127.0.0.1`; the DNS
  `bind_hosts` was changed to `0.0.0.0` in `AdGuardHome.yaml` so it answers on the
  LAN IP). The admin UI stays on `127.0.0.1` behind HA Ingress (HA sidebar →
  AdGuard Home).
- **Upstream:** Quad9 DoH (`https://dns10.quad9.net/dns-query`), DNSSEC on.
- **Blocking:** AdGuard default blocklist (~158k rules).
- **Query log:** 90-day retention, per-client — this is the per-domain IOT
  visibility (filterable by IOT IP in the AdGuard UI). The query log is also
  **tailed into Grafana Cloud / Loki for permanent storage** (Alloy reads
  `querylog.json`; query `{job="integrations/adguard"} | json`) — see
  [@observability.md](observability.md). The AdGuard UI is capped to AdGuard's own
  retention; Loki keeps it indefinitely. `size_memory: 0` is set in
  `AdGuardHome.yaml` so AdGuard flushes each query to disk immediately (→
  near-real-time shipping) instead of buffering 1000 entries (~hourly batches).

IOT reaches it via the existing `IOT to Home Assistant (ALLOW)` policy
(IOT→`192.168.0.12`, all ports). Scope is **IOT-only** — the main LAN still uses
the UDM resolver. The :53 DNAT redirect below forces *all* IOT plain DNS to
AdGuard regardless of what resolver a device is configured with; setting the IOT
DHCP DNS server to `192.168.0.12` as well is belt-and-suspenders (recommended, so
the advertised resolver matches reality).

The UDM's CoreDNS still exports its `type:"dnsAdBlock"` entries to syslog/Loki
(`{log_type="dns"}`), but AdGuard's own query log is now the authoritative source.

## IOT NTP forcing (local time server)

IOT devices were also hammering **public NTP** (~100 flows/hour; the worst —
Prusa camera `.67`, WiiM `.10`, the two aircons — poll public servers regardless
of DHCP). A local time server plus a redirect contains this, the same way DNS is
handled.

- **chrony** runs as a HA add-on (`a0d7b954_chrony`) on `192.168.0.12:123`
  (stratum 2, synced). IOT reaches it via `IOT to Home Assistant (ALLOW)`.
- **DHCP option 42** (NTP server) for the IOT network → `192.168.0.12`. Honoured
  by well-behaved devices (e.g. Hive Hub `.125`); ignored by the hardcoded ones.
- **udp/123 DNAT redirect** (below) catches the devices that ignore DHCP.
- **`Block IOT NTP to Internet`** (udp/123, logged) — the symmetric fail-closed
  backstop, mirroring the DNS blocks. With the DNAT present it stays at ~0 hits;
  if the redirect is ever removed it contains NTP *and* feeds the drift alert.
  DHCP option 42 keeps honouring devices working even when this block is active.

> **Never *block* NTP without a working local server.** A device with no clock
> fails TLS. The block is safe only because chrony + DHCP option 42 give honouring
> devices a working source; only hardcoded-NTP devices lose time, and only during
> a *prolonged* redirect outage.

## DNAT redirection & persistence (DNS + NTP)

Hardcoded-resolver/-NTP IOT devices are transparently redirected at the gateway to
the HA-host services. Three `nat PREROUTING` rules on the UDM (interface `br2` =
IOT), inserted **above** UniFi's `UBIOS_PREROUTING_JUMP`:

```
iptables -t nat -I PREROUTING -i br2 -p udp --dport 123 ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # NTP  -> chrony
iptables -t nat -I PREROUTING -i br2 -p udp --dport 53  ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # DNS  -> AdGuard
iptables -t nat -I PREROUTING -i br2 -p tcp --dport 53  ! -d 192.168.0.12 -j DNAT --to-destination 192.168.0.12  # DNS  -> AdGuard
```

- **No SNAT/MASQUERADE** (unlike Scott Helme's same-subnet Pi-hole example): the
  target `192.168.0.12` is on a *different* subnet, so chrony/AdGuard replies route
  back through the UDM and conntrack reverses the DNAT. `rp_filter` is loose
  (`2`), so the return path isn't dropped. Keeping the real source IP also
  preserves per-device visibility in chrony/AdGuard logs.
- **conntrack gotcha:** a freshly-inserted PREROUTING rule is bypassed by live UDP
  flows already in conntrack; after (re)inserting, flush them
  (`conntrack -D -p udp --dport 53` etc.) so devices re-evaluate. The apply script
  does this automatically for ports it changes.
- DNAT runs in `nat PREROUTING`, *before* the ZBF forward chains, so a redirected
  packet's destination is `192.168.0.12` by the time the blocks are evaluated — it
  matches `IOT to Home Assistant (ALLOW)`, not the `:53`/`:123` blocks. The blocks
  therefore only fire when the DNAT is **absent**.

### Persistence (UDM boot)

The UDM (UniFi OS 5.1.19, **iptables-legacy**) clears custom iptables on reboot.
Persistence is **boot-only** via systemd:

| Path | Purpose |
|---|---|
| `/persistent/iot-redirect/apply.sh` | idempotent (re)insert of the 3 DNAT rules + conntrack flush. `/persistent` survives reboot **and** firmware upgrade. |
| `/persistent/iot-redirect/install.sh` | writes + enables the unit. **Re-run after a firmware upgrade** (which wipes `/etc`). |
| `/etc/systemd/system/iot-redirect.service` | `oneshot`, `After=network-online.target udapi-server.service`, `ExecStartPre=/bin/sleep 30` (lets udapi build its ruleset first). |

> **Manual re-apply** (e.g. if a controller *provision* flushes the rules — not
> auto-recovered under boot-only): `ssh root@192.168.0.1 '/persistent/iot-redirect/apply.sh'`.
> **Do not** use `systemctl start` — the unit is `RemainAfterExit` so it's a no-op
> once active; use `systemctl restart iot-redirect` or run `apply.sh` directly.

### Drift detection (Grafana alert)

A Grafana tripwire fires if the DNAT redirect is ever removed (reboot before the
boot service runs, or a provision flush): the `:53`/`:123` blocks start logging,
which a recording rule turns into a metric and an alert watches. See
[@observability.md](observability.md) (`iot_dnat_block_hits:count5m` recording
rule + `IOT DNAT redirect removed` alert). Remediation in the alert: re-run
`apply.sh`.

## Per-device internet control (client groups + OON)

The DNS/NTP forcing above governs *how* IOT devices resolve and sync time, but
every IOT device is still allowed out to the internet generally (the blanket
IOT→External ALLOW). Some IOT devices are **local-only integrations** that never
legitimately need the internet, so their WAN access can be cut entirely for
containment — a compromised local-only device then can't exfiltrate or phone home.

UniFi offers two grouping primitives, feeding two different engines:

| Primitive | Keyed by | Engine | Expresses |
|---|---|---|---|
| Firewall **address-group** | IP/CIDR | Zone-Based Firewall policies | full L3/L4 allow/block, per-port, logged (the containment model above) |
| **Client group** | **MAC** | **OON policy** | internet on/off + schedule, app block, QoS, VPN route |

For a simple per-device internet kill-switch the **MAC-based client group + OON
policy** path is used (not an IP address-group + ZBF rule), because:

- **MAC is stable** — no IP address-group to maintain, and **no DHCP reservation
  needed** (none of the IOT devices are reserved; an IP-based group would drift).
- OON's `secure.internet_access_enabled: false` (stored as
  `secure.internet.mode: "TURN_OFF_INTERNET"`) is UniFi's native internet block.
- It blocks **WAN only** — LAN→HA (`192.168.0.12`) is untouched, and the DNS
  (AdGuard) / NTP (chrony) DNAT redirects to `.12` are LAN-local, so blocked
  devices keep working time + resolution. Coexists with the ZBF rules (a per-MAC
  WAN block layered on top of the IOT→External ALLOW).

### `IOT - No Internet` group

A client group **`IOT - No Internet`** (id `6a36c6732753ee32cc248cc4`) holds the
MACs of IOT devices verified to have a **local** HA path (so HA control survives
the block); an OON policy **`IOT - No Internet`** (id `6a36c6932753ee32cc248d20`,
`target_type: GROUPS` → that group) turns their internet off.

| Device | IP | MAC | Local path |
|---|---|---|---|
| Master Bedroom - Norman Hub | .225 | `80:5e:4f:9d:da:a3` | norman_shutters |
| Master Bedroom - Clock | .42 | `c0:4e:30:13:33:d8` | esphome |
| Hallway - Doorbell | .49 | `d8:3b:da:45:62:b8` | esphome |
| Tom's Office - AirGradient | .177 | `34:b7:da:9f:7e:10` | airgradient (local API) |
| Master Bedroom - Dyson Fan | .19 | `44:6f:f8:42:ba:f7` | dyson_local |
| Nursery - VELUX Gateway | .196 | `70:ee:50:6a:51:2d` | homekit_controller |
| Tom's Office - Aircon | .24 | `10:68:38:47:dc:b5` | daikin (local) |
| Master Bedroom - Aircon | .27 | `10:68:38:47:4c:7f` | daikin (local) |
| Living Room - Arylic LP10 | .237 | `00:22:6c:23:38:56` | linkplay |
| Tom's Office - Arylic LP10 | .245 | `00:22:6c:67:19:56` | linkplay |
| Nursery - WiiM Sound | .10 | `40:fd:f3:66:ac:e4` | wiim |
| Basement - Dryer | .68 | `94:27:70:e6:c1:3d` | mqtt / hcpy (local bridge) |

> **Notes / gotchas:**
> - **Daikin / Dyson / VELUX / Norman** are local integrations; the block kills
>   only the vendor *cloud app* (Onecta, MyDyson, VELUX Active), not HA control.
> - **Dryer is local** despite being a Home Connect appliance — it's bridged by a
>   local **hcpy → MQTT** add-on (HA device `integration_type: mqtt`, identifier
>   `["mqtt","dryer"]`), which reads the appliance directly over the LAN. So the
>   block does **not** break the "Tumble Drier finished" notification (that would
>   only be true if it used the cloud `home_connect` integration). The washing
>   machine is unaffected regardless (local Zigbee power sensor).
> - **Streamers (Arylic ×2, WiiM)** keep working *via Music Assistant* — MA fetches
>   the stream on the HA server and serves it to the player over the LAN, and
>   ChimeTTS announcements are LAN-served. Only *direct* native streaming (Spotify
>   Connect straight to the device, the vendor app, on-device internet radio) stops.
> - **Deliberately excluded** (kept on the internet so they can pull firmware):
>   the 4 Everything Presence Lites and the 2 Voice Assistants. Cloud-dependent
>   devices (Nest Protect, Hive, Deebot, Netatmo, Kitchen Display kiosk, Prusa
>   cameras, alarm module) are out of scope by design.

**Editing membership:** update the client group's `members` only
(`unifi_update_client_group`); the OON policy needs no change. **OON create
gotcha:** `qos.mode` must be a valid enum (`LIMIT`/`PRIORITIZE`/…) even when
`qos.enabled: false` — `"OFF"` and a null mode are both rejected by the backend
(the MCP `confirm:false` preview does *not* catch this; only the real create does).

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
      - Hive Hub (IOT) — `Basement Switch` port 8.
      - Garage Door camera, G5 Turret Ultra (Cameras) — `Garage Switch` port 5.
      - Garage camera, AI Pro (Cameras) — `Garage Switch` port 7.
      - Back-garden camera, G5 Turret Ultra (Cameras) — `Basement Switch` port 3.
      Port isolation is per-switch, so it does not block same-VLAN traffic between
      devices on *different* switches (inherent L2 limit; minor residual for
      trusted cams).
- [x] mDNS reflector already enabled (`mdns_enabled: true`), left as-is.
- [x] Functional verification: camera entities `recording`, IOT Voice satellites
      connected after the change.
- [x] IOT internet-destination logging live (`Log IOT to Internet (ALLOW)` →
      UDM firewall syslog → Loki; verified per-flow `SRC=/DST=` lines arriving).
- [x] DNS forcing live: IOT→public-DNS blocked (53/853 to any + known resolver
      IPs incl. DoH/443); verified `Block IOT to Public DNS Providers` firing.
- [x] **AdGuard Home as the IOT resolver** — deployed as a HA add-on on
      `192.168.0.12:53` (Quad9 DoH upstream, 90-day per-client query log,
      ad-block). Scope IOT-only. See [DNS query logging — AdGuard Home](#dns-query-logging--adguard-home-live).
- [x] **DNAT-redirect IOT plain DNS (:53) → AdGuard** (`tcp+udp`, `br2`→`.12`).
      Hardcoded-DNS devices (Hive Hub `.125`, Kitchen Display `.18`) now resolve.
      **No MASQUERADE needed** (cross-subnet target; conntrack reverses; rp_filter
      loose) — corrects the earlier Scott-Helme-based note. DoT/DoH still can't be
      transparently redirected, so the `Block IOT to Public DNS Providers` (DoH
      :443) and `Block IOT DNS to Internet` (DoT :853) rules stay.
- [x] **Local NTP**: chrony HA add-on on `.12:123` + DHCP option 42 → `.12` +
      **udp/123 DNAT redirect** + symmetric **`Block IOT NTP to Internet`**.
      Verified the hardcoded devices (WiiM `.10`, Prusa `.67`) now hit chrony.
- [x] **DNAT persistence** (boot-only): `/persistent/iot-redirect/` + enabled
      `iot-redirect.service` on the UDM. Re-apply via `apply.sh` / `systemctl
      restart`; re-run `install.sh` after firmware upgrades.
- [x] **Drift alert**: Grafana `IOT DNAT redirect removed` (on the
      `iot_dnat_block_hits:count5m` recording rule). Tested by removing the DNAT —
      alert fired, then resolved on restore. See [@observability.md](observability.md).
- [x] **`IOT - No Internet` group**: MAC-based client group
      (`6a36c6732753ee32cc248cc4`, 12 local-only devices) + OON internet-block
      policy (`6a36c6932753ee32cc248d20`). Verified LAN→HA intact post-block
      (aircons, Norman shutters still responsive). See
      [Per-device internet control](#per-device-internet-control-client-groups--oon).
- [ ] Confirm WAN actually dropped for the 12 devices once flows/Loki catch up
      (`{log_type="firewall", rule="Log IOT to Internet (ALLOW)"}` should no longer
      show their SRC IPs; or `unifi_get_traffic_flows` shows them blocked).
- [ ] Watch for IOT devices broken by the DNS block (Hive Hub, Kitchen Display).
- [ ] Persistence is boot-only — a controller *provision* can flush the DNAT until
      the next reboot/manual re-apply. Revisit a self-healing timer if it recurs.
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
| Block IOT DNS to Internet (BLOCK, logged) | `6a3502392753ee32cc1f26e8` |
| Block IOT to Public DNS Providers (BLOCK, logged) | `6a35023a2753ee32cc1f26eb` |
| Block IOT NTP to Internet (BLOCK, logged) | `6a36760b2753ee32cc2397f4` |
| Log IOT to Internet (ALLOW, logged) | `6a3676352753ee32cc2398b6` |

> Within the IOT→External zone-pair these must stay ordered **blocks first, ALLOW
> last** (see the ordering gotcha above). Current `index`: DNS block `10001`,
> public-DNS block `10002`, NTP block `10004`, ALLOW `10005`. The ALLOW was
> deleted+recreated to re-append it last when the NTP block was added, so its
> policy ID changed (was `6a3502dc2753ee32cc1f2955`).

### Firewall groups (created via MCP)

| Name | Type | Group ID | Members |
|---|---|---|---|
| Public DNS Resolvers | address-group | `6a3502122753ee32cc1f2645` | 8.8.8.8, 8.8.4.4, 1.1.1.1, 1.0.0.1, 9.9.9.9, 149.112.112.112, 208.67.222.222, 208.67.220.220, 94.140.14.14, 94.140.15.15, 4.2.2.1, 4.2.2.2, 4.4.4.4, 64.6.64.6, 64.6.65.6 |
| DNS Ports | port-group | `6a3502132753ee32cc1f2648` | 53, 853 |
| NTP Ports | port-group | `6a3675fb2753ee32cc2397cb` | 123 |
