# Pointing the show at a node (Art-Net or sACN, unicast)

Out of the box the backend sends Art-Net to `ARTNET_IP`, whose default is the
limited broadcast address `255.255.255.255`. For a demo into a venue's node
(for example a grandMA2 NODE, which accepts both Art-Net and sACN), send
straight to the node's IP instead. The choice is remembered across restarts.

## Recommended: Art-Net unicast

```bash
curl -X PUT http://localhost:8000/api/dmx/output-target \
  -H "Authorization: Bearer $ILS_TOKEN" -H "Content-Type: application/json" \
  -d '{"protocol": "artnet", "ip_address": "192.168.1.50", "net": 0, "subnet": 0, "universe": 0}'
```

`net` (0-127), `subnet` (0-15) and `universe` (0-15) are packed into the
15-bit Art-Net Port-Address: `net << 8 | subnet << 4 | universe`. The response
shows the result as `active.port_address`; set the node's port to the same
Net / Sub-Net / Universe.

## sACN (E1.31) unicast

```bash
curl -X PUT http://localhost:8000/api/dmx/output-target \
  -H "Authorization: Bearer $ILS_TOKEN" -H "Content-Type: application/json" \
  -d '{"protocol": "sacn", "ip_address": "192.168.1.50", "universe": 1, "priority": 100}'
```

Sent to UDP port 5568. `universe` is 1-63999 and `priority` 0-200 (default
100; the higher priority wins at the receiver, so stay at or below the house
console's if it should be able to take over). `source_name` (up to 63
characters) is what the node shows as the sender.

Multicast is only used when asked for: `{"protocol": "sacn", "multicast": true,
"universe": 1}` sends each universe to its group `239.255.<high>.<low>`.

## What to know

- `GET /api/dmx/output-target` returns the remembered `target` and the `active`
  output (protocol, destination, port, universe).
- `universe` is where the engine's **first** universe (0) lands. A rig patched
  on engine universes 0 and 1 with sACN `universe: 5` goes out on 5 and 6; with
  Art-Net it goes out on consecutive Port-Addresses from the one above.
- Broadcast addresses (`255.255.255.255`, anything ending `.255`) are refused
  unless the request also sets `"allow_broadcast": true`. A unicast target
  never turns broadcast on.
- The target is stored in `output_target.json` beside the database and is
  applied at startup before the first frame is sent. Once one is remembered it
  takes precedence over `ARTNET_IP`; delete the file to go back to the
  environment setting.
- The sACN sender identity (CID) is created once per install in `sacn_cid`
  beside the database and never changes with the target.
- Both protocols leave through the same output thread and universe store, so
  blackout, the grand master, the demo-rig output hold and blackout-on-stop
  behave identically whichever is chosen.
- `PUT /api/dmx/config` and the `/api/dmx/previs/configure-*` endpoints only
  change the Art-Net settings for the running session; they do not change the
  protocol and are not remembered.
- `GET /api/dmx/transmit-status` reports `protocol`, `target_ip`, `port` and
  whether frames are actually leaving.
