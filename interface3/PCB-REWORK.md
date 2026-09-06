# PCB Rework for the Second Coax Port

Boards built from the interface3 layout before its correction have the
second port's transmit signal on a ground pin of the Pico, so port 2
can receive but never transmit.  Making such a board work needs four
signals moved by hand.

The layout in `pcb/` carries the corrected assignment.

## What is wrong

On the affected boards `~TX2` runs from the driver at U2 pin 15 to
Pico pad 13, which is a ground pin.  The driver input for the second port sits tied to ground,
so nothing the firmware does can make that port transmit.  For
comparison, the first port's `~TX1` reaches the Pico at pad 5, GP3, as
it should.

Correcting it moves the three signals that follow up by one pad, which
in turn pushes `LED_RX2` onto the pin `LED_NET` was using.  The C
firmware has no network LED, so `LED_NET` is simply given up.

## What has to change

| Signal | Affected boards | Should be | Pico pads |
|--------|-------------|-----------|-----------|
| `RX2` | GP9 | GP9 | pad 12, unchanged |
| `~TX2` | **pad 13, a ground pin** | GP10 | pad 13 → pad 14 |
| `TX2_ACTIVE` | GP10 | GP11 | pad 14 → pad 15 |
| `TX2_DELAY` | GP11 | GP12 | pad 15 → pad 16 |
| `LED_RX2` | GP12 | GP22 | pad 16 → pad 29 |
| `LED_TX2` | GP13 | GP13 | pad 17, unchanged |
| `LED_NET` | GP22 | — | pad 29, given up |

So, working along the Pico's left-hand side: separate each of the four
signals from the pad the board takes it to, and run it to the pad one
position further down; `LED_RX2` goes across to pad 29 instead.

The "should be" column is what the firmware drives — `port_pins[1]` and
`port_leds[1]` in `firmware/coax.c` and `firmware/leds.c` — and it
matches the schematic and the current layout in `pcb/`.  Check both
columns against the board in front of you before cutting anything; a
board that has already been reworked, or one built from the corrected
layout, will read as the right-hand column.

## Why it matters for capture

[In-line forwarding](./PASSIVE-CAPTURE.md) puts the interface in the
middle of a link, with one port to the controller and one to the
terminal, and both ports have to transmit.  Without this rework
`--forward 0,1` can only carry traffic one way: whatever the terminal
sends reaches the controller, and nothing goes back.

Listening — a tee or a probe on port 1 — needs only reception, and
works on an affected board without rework.

## Checking it

With a terminal on port 2 and nothing else changed, a capture should
show traffic in both directions:

```bash
tools/coax-capture --ports 1 --write port2.pcapng
```

A terminal that answers polls but never takes a screen write, or one
whose status line never updates, points at the transmit path still
being dead.
