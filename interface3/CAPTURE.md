# Coax Capture

The interface can capture the coax traffic it exchanges with attached
terminals and hand it to Wireshark in pcap form.  Capture happens in
the firmware, at the point where a transaction is performed, so both
the outbound frame (controller to terminal) and the inbound frame
(terminal to controller) are recorded as they appear on the wire, with
microsecond timestamps taken by the device itself.

## Overview

A fifth USB CDC interface, `Coax Capture`, carries capture records to
the host and capture control commands to the device.  The four command
ports keep working exactly as before; a host that never opens the
capture port pays nothing for the feature.

On the host, `tools/coax-capture` reads that port and writes a pcapng
file.  It also works as a Wireshark extcap plugin, so the interface
appears in Wireshark's list of capture sources and can be started from
the GUI.  `tools/coax.lua` dissects the captured frames into commands,
data bytes and poll responses.

```
   terminal <--coax--> firmware --+--> CDC 0..3  command/response (oec)
                                  |
                                  +--> CDC 4     capture records
                                                     |
                                              coax-capture (extcap)
                                                     |
                                                 pcapng --> Wireshark
                                                              + coax.lua
```

## Capture point

`cmd_transmit_receive()` in `firmware/command.c` has both halves of a
transaction in the same representation: 10-bit coax words held in
16-bit little-endian containers.  `coax_transact()` reports the time
transmission started and the time reception finished, so each of the
two frames gets its own timestamp.

Transmit timestamps are exact.  Receive timestamps are taken when the
end-of-frame marker is noticed by the polling loop in
`coax_transact()`, which runs every 100 µs, so they are accurate to
within that interval.

## Flow control

Capture never delays a transaction.  Records are SLIP-encoded into a
16 KB ring buffer as they are produced, and the main loop moves
whatever fits into the CDC FIFO.  A record that does not fit into the
ring is dropped and counted; once space is available again, a `DROP`
record reports the cumulative count, which the capture tool writes
into the pcapng interface statistics as `isb_ifdrop`.  A capture host
that stops reading therefore loses records but never affects coax
timing.

Capture stops and the ring is reset when the capture port is closed.

## Listening

`TAP` gives a port over to listening, so the interface records a link
it does not drive.  Frames then carry the `INFERRED` flag, and their
direction is decided by the first word: a command word means the frame
is going to the terminal, anything else that it is coming back.  The
idle poll filter still applies, by pairing a `POLL` frame with a
`0x0000` frame arriving within 2 ms of it.

The listening decoder is the receive program without the handshake that
keeps it out of the interface's own transmission, and it runs from a
free-running DMA ring rather than one transaction at a time.  On a chip
with a spare PIO block it runs alongside normal operation; where the
transmit and receive programs already fill every block, it takes the
receive program's place and transactions are refused until the tap
stops.

`FORWARD` puts the interface in the middle of a link instead, with one
port to each end.  The line arriving on either port is copied back out
on the other bit by bit, sampled at the system clock, so a frame
crosses in tens of nanoseconds; the transmitter already driving one
port holds the opposite direction off, so the pair runs one way at a
time.  Both ends' traffic appears on both wires, so a tap on either
port records the whole conversation.  Forwarding gives up the
transaction programs for as long as it runs, and carries the link it
sits in, so it outlives a capture: `STOP` and closing the capture port
leave it running, and it stops when `FORWARD` says so.

See [PASSIVE-CAPTURE.md](./PASSIVE-CAPTURE.md) for how to connect and
run either of them.

## Filtering

A terminal is polled continuously, and unfiltered those polls bury
everything else.  The capture control command selects what is
recorded:

| Option | Default | Effect |
|--------|---------|--------|
| port mask | all ports | Ports to capture |
| idle polls | off | A single-word outbound frame answered by `0x0000` |
| timeouts | on | Records a zero-word inbound frame flagged `TIMEOUT` |
| snap words | 0 (unlimited) | Truncate frames to this many words |

Suppressed idle polls are counted per port and reported by the
`STATUS` command, so the capture never silently understates traffic.

Truncated frames carry the full length in the record, which the
capture tool writes as the pcap `orig_len`, so Wireshark shows them as
properly truncated packets.

## Record format

Records travel over the capture CDC as SLIP frames (RFC 1055 framing,
as used by the command ports).  Every record starts with a 13-byte
prefix:

| Offset | Size | Field |
|-------:|-----:|-------|
| 0 | 1 | Record type |
| 1 | 8 | Timestamp, microseconds since device boot |
| 9 | 2 | Length of the body present in this record |
| 11 | 2 | Length the body would have had untruncated |

| Type | Name | Body |
|------|------|------|
| 1 | `FRAME` | A coax frame, in the link-layer format below |
| 2 | `META` | Device identification, sent when capture starts |
| 3 | `DROP` | Cumulative count of dropped records |
| 4 | `STATUS` | Capture state and per-port counters |

Everything in the prefix and in the `META`, `DROP` and `STATUS` bodies
is little-endian.  The `FRAME` body is big-endian, because it is
written to the pcap file verbatim and is meant to be usable as a
registered link-layer type.

### FRAME body — the link-layer format

| Offset | Size | Field |
|-------:|-----:|-------|
| 0 | 1 | Format version, currently 1 |
| 1 | 1 | Coax port, 0 to 3 |
| 2 | 1 | Flags |
| 3 | 1 | 3299 multiplexer address, `0xff` when not addressed |
| 4 | 2 | Number of words present |
| 6 | 2×n | The words, each a 10-bit coax word right-aligned in 16 bits |

| Flag | Value | Meaning |
|------|-------|---------|
| `FROM_TERMINAL` | 0x01 | Terminal to controller; clear means controller to terminal |
| `TRUNCATED` | 0x02 | Frame was cut to the configured snap length |
| `TIMEOUT` | 0x04 | No response arrived; the frame carries no words |
| `RX_ERROR` | 0x08 | Reception failed |
| `INFERRED` | 0x10 | Direction was inferred rather than known |

The words are stored raw, exactly as they appear on the wire: bit 0
distinguishes command words from data words, bit 1 carries the data
word parity bit, and an all-zero word is a transmission turnaround.
Decoding is left to the dissector.

### META body

| Size | Field |
|-----:|-------|
| 1 | Meta format version, currently 1 |
| 1 | Number of coax ports |
| 2 | Largest frame the device can handle, in words |
| 1+n | Hardware type, length-prefixed |
| 1+n | Firmware version, length-prefixed |

### DROP body

| Size | Field |
|-----:|-------|
| 4 | Records dropped since capture started |
| 4×4 | Records dropped, per port |

### STATUS body

| Size | Field |
|-----:|-------|
| 1 | Capturing |
| 1 | Port mask |
| 1 | Options |
| 2 | Snap length in words |
| 4 | Records dropped |
| 4×4 | Frames captured, per port |
| 4×4 | Idle polls suppressed, per port |
| 4×4 | Records dropped, per port |
| 1 | Port being listened to, `0xff` when none |
| 1 | First forwarded port, `0xff` when not forwarding |
| 1 | Second forwarded port, `0xff` when not forwarding |
| 2 | Quiet period in nanoseconds, 0 when not forwarding |

## Control commands

Control commands are SLIP frames sent to the capture CDC.  All fields
are little-endian.

| Code | Name | Arguments | Reply |
|------|------|-----------|-------|
| 0x01 | `START` | port mask (1), options (1), snap words (2) | `META` |
| 0x02 | `STOP` | — | — |
| 0x03 | `STATUS` | — | `STATUS` |
| 0x04 | `TAP` | port (1), enable (1) | `STATUS` |
| 0x05 | `FORWARD` | port a (1), port b (1), enable (1), flags (1), quiet ns (2) | `STATUS` |

| Option | Value | Meaning |
|--------|-------|---------|
| `IDLE_POLLS` | 0x01 | Record polls answered by `0x0000` |
| `TIMEOUTS` | 0x02 | Record transactions that timed out |

`FORWARD` flag bit 0 inverts the copy on its way out, for a line whose
receiver and driver do not share a polarity.  A quiet period of zero
takes the default of 1000 ns.

## File format

The capture tool writes pcapng, using link type `LINKTYPE_USER0` (147)
and one interface per coax port, named `coax0` to `coax3`.  This makes
the port available as `frame.interface_name` without a dissector, lets
each packet carry its direction in `epb_flags`, and lets the drop
counter be reported in interface statistics blocks.  Section header
options record the hardware type and firmware version from the `META`
record.

Timestamps have microsecond resolution.  The device counts from boot,
so the tool anchors the first record it sees to the host clock and
offsets the rest.  A timestamp that moves backwards means the device
was reset; the tool re-anchors and notes it in a comment.

## Usage

`tools/coax-capture` needs nothing beyond Python 3.  It finds the
capture port itself, or takes one with `--port`:

```bash
tools/coax-capture --list
tools/coax-capture --write coax.pcapng
tools/coax-capture --port /dev/tty.usbmodem1124109 --write coax.pcapng
```

Useful options:

| Option | Effect |
|--------|--------|
| `--ports 0,2` | Capture only these coax ports |
| `--tap 0` | Listen to a line the interface does not drive |
| `--forward 0,1` | Sit in the middle of a link and record what passes |
| `--idle-polls` | Include polls answered by `0x0000` |
| `--no-timeouts` | Leave out transactions that timed out |
| `--snap-words 64` | Truncate frames to 64 words |
| `--duration 30` | Stop after 30 seconds |

Watch live:

```bash
tools/coax-capture --write - | wireshark -k -i -
```

From the Wireshark GUI, install the capture plugin and the dissector
once, then pick the coax interface from the capture list:

```bash
tools/install-wireshark.sh
```

`--self-test` writes a synthetic capture without a device attached,
which is a quick way to check the dissector:

```bash
tools/coax-capture --self-test -w /tmp/coax.pcapng
tshark -r /tmp/coax.pcapng -X lua_script:tools/coax.lua
```

The capture port is the fifth serial device the interface presents.
It is named `Coax Capture` in the USB descriptors, which is how it is
recognised on Linux; on macOS it is the highest numbered
`/dev/cu.usbmodem*` of the interface.

## Dissector

`tools/coax.lua` decodes the captured frames: command words and their
names, data words with their parity bit, transmission turnarounds, and
poll responses read in the light of the command they answer, including
keystroke scan codes and power-on-reset.  Responses link back to their
request through `coax.request_in` and `coax.response_in`.

A long write is split into several frames, with the command word in the
first of them; the frames that follow are shown as a continuation of
that command and link to it through `coax.command_in`.

Filter fields include `coax.port`, `coax.direction`, `coax.command`,
`coax.continues`, `coax.data`, `coax.payload`, `coax.scan_code`,
`coax.timeout` and `coax.truncated`.  Expert information flags parity
mismatches, timeouts, receive errors and truncated frames.

The flag fields are present in every frame, so compare them rather than
testing for their presence: `coax.timeout == 0` selects the
transactions a terminal answered.

The 3270 character encoding is left undecoded; data bytes appear as
hex in their own byte view.
