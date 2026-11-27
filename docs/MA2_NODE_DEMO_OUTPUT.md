# Demo output into the venue's grandMA2 NODE

Written 2026-11-20 after Alexander's Q8 answer (7:45 PM ET). The first venue has a grandMA2 NODE (an MA Lighting NPU/node that speaks MA-Net, Art-Net and sACN). The fixture list, the node's IP/subnet, and its universes are still unknown (Q31–Q33).

This is a plan only. Nothing here authorises sending Art-Net or sACN to a real device. Bench tests must use a local loopback or a mock socket. Never touch grandMA2 onPC.

## Recommendation: Art-Net unicast, not sACN, for the first demo

The engine already speaks Art-Net. A unicast target already exists (`POST /api/dmx/previs/configure-unicast` and `ARTNET_IP` in settings). There is no sACN (E1.31) sender — `protocol: sacn` appears only as a comment on the rig schema.

**For the first demo, send Art-Net, unicast, to the node's IP.** That uses code we already have, avoids flooding the venue network with Art-Net broadcast (the current settings default is `255.255.255.255`, which is the wrong default in a club), and is a protocol the MA2 node can receive once Art-Net input is enabled.

sACN would be nicer later (multicast, a priority field so a console can win), but it is not implemented. It is added as backlog item #14: a loopback/mock-tested sACN sender and a remembered unicast/sACN target in the UI, with no real-network sends in tests.

## Universe and subnet mapping

Art-Net addresses a universe as Net (0–127), Sub-Net (0–15), and Universe (0–15). That 15-bit port-address must match what the node is set to output as DMX.

sACN uses a single universe number (1–63999). If we later add sACN, map our 1-based show universe onto that number directly, and write the node's corresponding Art-Net port-address next to it in the patch notes so the two views cannot drift.

Until Q32 is answered (node IP, subnet, universes), do not guess a live destination. Document the mapping in the rig once we have it: show universe N → Art-Net Net/Sub-Net/Universe → the node's DMX port.

A July assessment noted that Net/Sub-Net may be declared but not always packed into the Art-Net header. Before the demo, confirm a captured loopback frame has the net/sub-net bytes we intend.

## Unicast versus broadcast

| Mode | When to use |
|------|-------------|
| **Unicast to the node's IP (recommended)** | The demo. One node, known IP, no need to spray the LAN. |
| Limited broadcast `255.255.255.255` or Art-Net 2.255.255.255 | Only on an isolated bench NIC, never on the venue network. The current settings default is broadcast; do not leave that on at the venue. |
| Multicast sACN | Later, if we ship sACN and the venue already uses it. |

Set the target with `configure-unicast` (or `ARTNET_IP=<node-ip>` in the env the owner fills in). Do not put the real IP in committed code or logs.

## Node-side setup (grandMA2 NODE / NPU)

These are the usual steps on an MA Lighting node. Exact menu names vary by firmware; use the node's web UI or the console's network view.

1. Put the node on the same subnet as the laptop that will send (Q32).
2. Enable **Art-Net input** on the port(s) that should drive the rig (or sACN input if we have later switched protocol).
3. Map the incoming Art-Net universe (Net/Sub-Net/Universe) to the node's DMX output ports.
4. If a grandMA2 console or onPC is also on the network: in the console, **Setup → Network Protocols** (or the current equivalent) must not also output Art-Net/sACN onto the same universe, unless you have deliberately set a merge (below).
5. Leave MA-Net as the console's private language if the console is used for something else; our system will not speak MA-Net.

## Avoiding a fight with the console's own output

Two sources writing the same universe will flicker or latch at whichever packet arrived last.

Preferred for this first demo (Alexander is running it himself, Q7):

- **Our system is the only source** on the universes we use. The console/onPC does not output those universes, or is not connected to that node for DMX. Ask Q33.

If the console must stay live:

- Give our system a **dedicated universe** the console is not outputting, and patch the node's DMX ports to that universe only, or
- Use the node's **HTP/LTP merge** only if the firmware offers it for Art-Net/sACN input versus MA-Net/console input, and agree which source wins. HTP (highest takes precedence) is the usual lighting merge; LTP is last-takes-precedence and is a poor default when two controllers are both streaming.

Never rely on "it'll be fine" with onPC also transmitting. Do not start, stop, or reconfigure grandMA2 onPC from this team.

## Bench-test plan (no real hardware)

1. Point Art-Net at `127.0.0.1` or use a mock UDP socket. Never send to a NIC that could reach a node, and never to `255.255.255.255` on a shared LAN.
2. Capture frames and assert: Art-Net header, version 14, the intended net/sub-net/universe, 512-slot packets, a steady frame rate, unicast destination when configured.
3. A blackout and a grand-master-at-zero still produce dark packets (G2 stage).
4. If sACN is added, the same tests apply on loopback/multicast-to-localhost or a mock socket, including the priority field.
5. Do not open grandMA2 onPC, and do not address a real node, even "just to see."

## Gap in the current code

- **Already present:** Art-Net sender; unicast target API and settings; broadcast mode (default today, `ARTNET_IP=255.255.255.255`).
- **Missing, small and safe to add later:** an sACN (E1.31) sender; a remembered demo destination (protocol + unicast IP + universe) in the operator UI, defaulting to unicast rather than LAN broadcast; a check that Art-Net net/sub-net are packed correctly.
- Those are backlog **#14** (sACN sender and a remembered unicast/sACN demo target). Tests must use loopback or a mock socket only.
