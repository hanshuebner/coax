# Passive Capture

Normally the interface records the traffic it exchanges with a terminal
itself.  In passive capture it instead listens to a coax link between
some other controller and a terminal — a real 3174, say — and records
what passes over it.  This is the only way to see traffic the interface
does not take part in.

This is new and has not been tried on real hardware yet.  The
[what to send back](#what-to-send-back) section says what would help
most.

## What you need

- An interface3 board with firmware built from the `capture` branch.
- For forwarding, a board whose second coax port can transmit.  Boards
  built from the earlier layout cannot; see
  [PCB-REWORK.md](./PCB-REWORK.md).  Listening works without that.
- A coax link between a controller and a terminal that is working, so
  there is something to listen to.
- `tools/coax-capture` on the host, and Python 3.  Nothing else.
- A way to connect the interface to the link, which is the part that
  needs thought — see below.

Either board will do for forwarding, which gives up the transaction
programs on any chip.  For listening without forwarding, a Pico 2
(RP2350) has a spare PIO block and keeps working as a controller
meanwhile, where a Pico or Pico W gives that up for as long as the
capture runs.  Everything returns to normal when the capture stops.

## Connecting to the link

The interface has to see the signal without disturbing it.  There are
three ways, and the first is the one to try.

### Option A — in line, forwarding between two ports

Break the link and put the interface in the middle: the controller on
one coax port, the terminal on the other.

```
   controller <--coax--> port 1 [ interface ] port 2 <--coax--> terminal
                                     |
                                  capture
```

Each half of the link now ends at a port that terminates it properly,
which is what the other two options cannot offer.  What arrives on
either port is put straight back out on the other, bit by bit, sampled
at the system clock: a frame crosses the interface in a few tens of
nanoseconds, so both ends see each other much as they would over a
plain cable.  Only one direction runs at a time, held off by the
transmitter that is already driving the other port, so nothing loops
back on itself.

The traffic of both ends appears on both wires, so a single listener
records the whole conversation.  `--forward` starts it for you.

```bash
tools/coax-capture --forward 0,1 --write link.pcapng
```

This is the ordinary firmware, switched over at run time; there is no
separate build.  While forwarding runs the interface cannot act as a
controller, since the copying takes the instruction memory that
transactions need.

**Forwarding carries the link, so it stays up when a capture ends.**
Stopping the capture leaves the terminal session alone, and you can
capture again later without interrupting it.  Take it down, and give
the interface back its controller role, with:

```bash
tools/coax-capture --forward off
```

Two things follow from the interface being part of the link:

- The link only works while the interface is powered and forwarding.
  After a power cycle it comes up as a controller again, and the link
  stays dead until forwarding is started once more.
- Unplugging the interface breaks the link, as pulling out any other
  piece of cable would.  Join the two cables to restore it.

Two things may need adjusting, and both are one flag:

- **Polarity.** If neither end sees anything, add `--invert`, which
  flips the copy on its way out.
- **Line release.** A port stops transmitting once the line it follows
  has been quiet for 1000 ns.  That has to be long enough to ride over
  the code violations inside a frame and short enough to leave the far
  end its turn to answer.  `--quiet-ns` changes it; frames arriving cut
  short suggest raising it, and responses going missing suggest
  lowering it.

### Option B — bridge a coax port onto the link

Put a BNC tee in the link and connect coax port 1 or 2 to the stub.

This is the quick way, and it may well work, but be aware of what it
does electrically.  Each coax port is transformer coupled and
terminates the line.  Bridging it onto a live link puts a second
termination across a 93 Ω cable, so everyone's signal amplitude drops.
The interface's receiver is sensitive enough that it will probably
still decode; the question is whether the *terminal* still does.

So: **check the terminal after connecting the tee.**  If the screen
goes wrong, the keyboard locks, or the controller reports the terminal
as absent, the tap is disturbing the link and you want option A or C.
Keep the stub as short as you can.

### Option C — a probe on the TTL header

Ports 3 and 4 have no transformer and no termination.  Their receive
signals arrive straight from the expansion header J3 at the Pico's
GPIO pins, so you can feed them from a probe circuit of your own that
loads the line lightly.

J3 carries port 3 on the odd pins and port 4 on the even ones:

| Pin | Signal | Pin | Signal |
|----:|--------|----:|--------|
| 1 | TX3_ACTIVE | 2 | TX4_ACTIVE |
| 3 | TX3_DELAY | 4 | TX4_DELAY |
| 5 | **RX3** | 6 | **RX4** |
| 7 | TX3 | 8 | TX4 |
| 9 | GND | 10 | GND |
| 11 | +3V3 | 12 | +3V3 |

Feed your probe's output into pin 5 (port 3, GPIO 14) or pin 6 (port 4,
GPIO 18), with ground on pin 9 or 10; 3.3 V for the probe is on pin 11
or 12.

What the probe has to deliver: a 3.3 V logic copy of the Manchester
signal, clean edges, no more than a few tens of nanoseconds of skew
between the two edge directions, and a high impedance across the coax
so the link is left alone.  A high impedance divider into a fast
comparator is the usual shape.

**Polarity is a coin toss until you try it.**  If the capture stays
empty with a probe that is otherwise working, invert its output and try
again.

### What will not work

Connecting the interface in place of the terminal.  There is then no
terminal for the controller to talk to, and nothing to listen to.

## Running the capture

Ports are numbered from 0, as everywhere else in the tool: `--tap 0` is
the port labelled 1 on the board.

```bash
tools/coax-capture --forward 0,1 --write link.pcapng   # in line
tools/coax-capture --tap 0 --write tap.pcapng          # tee or probe
```

Watch it live instead:

```bash
tools/coax-capture --tap 0 --write - | wireshark -k -i -
```

Or from the Wireshark GUI, after `tools/install-wireshark.sh`: pick the
coax interface, open its options, and set **Listen on coax port**.

Useful additions:

| Option | Effect |
|--------|--------|
| `--idle-polls` | Record the polls a terminal answers with nothing, which are left out by default |
| `--duration 60` | Stop after a minute |
| `--snap-words 64` | Cut long frames short, to keep a long run small |
| `--forward off` | Stop forwarding and hand the ports back to the controller |
| `--invert` | Flip the forwarded copy, when the far end sees nothing |
| `--quiet-ns 1500` | Hold a forwarded line longer before releasing it |

Start the capture, then do something at the terminal — type into a
field, press Enter, change screens — so there is traffic beyond
polling.

## Reading what you get

Load the file with the dissector (`tools/install-wireshark.sh` puts it
where Wireshark finds it) and you should see the same shapes as an
ordinary capture:

```
coax0 > POLL
coax0 < keystroke 0x24
coax0 > LOAD_ADDRESS_COUNTER_HI, 1 byte
coax0 < TT/AR
coax0 > WRITE_DATA, 1023 bytes
coax0 < TT/AR
```

Frames from a listened link are marked **direction inferred**, and the
packet detail says so.  The interface cannot know which end of the
cable a frame came from, so it decides from the first word: only a
controller sends command words, so a frame that starts with one is
going to the terminal, and anything else is coming back from it.  That
rule holds for CUT terminals.  Filter on `coax.inferred == 1` to see
which frames were guessed at.

### Timestamps are imprecise

Read the times as "roughly when this happened", not as measurements.

Decoded words go into a buffer as they arrive, and the firmware stamps
a frame when its main loop empties that buffer — which is after the
frame has been received, by however long the loop happens to take that
time round.  In a quiet listening session that is a few tens of
microseconds.  While the interface is busy with something else, such as
a transaction on another port, it is as long as that takes, up to
several milliseconds for a full screen write.  Frames read out in the
same pass end up within a few microseconds of each other however far
apart they were on the wire, which makes the gap between a poll and its
answer look far smaller than it was.

What stays true: frames appear in the order they happened, and timing
measured over a whole poll cycle or a screen update is sound.  What
does not: the gap between any two adjacent frames, and anything that
depends on microsecond accuracy — turnaround times, inter-word timing,
response latency.  An ordinary capture, where the firmware stamps the
transmission and reception of each transaction itself, is the one to
use for those.

## Limits to be aware of

- **Timestamps are imprecise**, as described
  [above](#timestamps-are-imprecise).
- **Direction is inferred**, as described above.
- **The interface cannot act as a controller at the same time.**
  Transactions on a listened port are refused; while forwarding, and on
  a Pico or Pico W while listening, transactions on every port are
  refused.
- **Idle polls are dropped by default.**  A poll answered by `0x0000`
  is left out unless `--idle-polls` is given.  The count of what was
  dropped shows up in Wireshark under *Statistics → Capture File
  Properties*.
- **Frames longer than 8192 words** are reported with a receive error
  flag rather than in full.
- The 3299 multiplexer address is not decoded.

## Troubleshooting

| What you see | What it usually means |
|---|---|
| No packets at all, and `--list` finds the device | The probe or tee is not delivering a signal, or its polarity is inverted. Try the other polarity first. |
| `no coax capture port found` | The capture port is the fifth serial device the interface presents; name it with `--port`. |
| A few frames, then nothing | The tap disturbed the link and the controller dropped the terminal. Check the terminal, and move to option B. |
| Nothing but `POLL` and `TT/AR` | That is what an idle link looks like. Type at the terminal while capturing. |
| Frames marked with a receive error | Signal quality: reflections from a long stub, a slow comparator, or a marginal probe. |
| Only one direction ever appears | One end's signal is much weaker at the tap point than the other's. Move the tap closer to the middle of the link. |
| Wireshark shows raw bytes, not `COAX` | The dissector is not installed; run `tools/install-wireshark.sh` and restart Wireshark. |
| Forwarding, and the terminal never comes up | Try `--invert` first. If that changes nothing, the far ends are not seeing clean edges; a scope on the outgoing port settles it. |
| Forwarding, and frames arrive cut short | The line is released mid frame; raise `--quiet-ns`. |
| Forwarding, and commands appear but answers do not | The line is held too long for the terminal to get its turn; lower `--quiet-ns`. |

The device also counts what it could not deliver.  After a run, drops
appear per port in *Statistics → Capture File Properties*; anything
other than zero means the host was not reading fast enough, not that
the link was faulty.

## What to send back

Even a failed attempt is useful.  Please include:

1. The `.pcapng` file, however short.
2. Which board (Pico, Pico W, Pico 2, Pico 2 W) and which ports you
   used.
3. How you connected — in line, tee, or probe, and for a probe, its
   circuit.
4. Whether the terminal kept working normally while you were connected.
5. Anything `coax-capture` printed to the terminal.

If nothing decoded at all, a scope trace of the signal arriving at the
Pico pin is worth more than anything else, since it settles the
polarity and signal quality questions in one go.
