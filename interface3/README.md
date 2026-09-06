# Interface3 - Raspberry Pi Pico W based 3270 Terminal Adapter

Interface3 is an alternative hardware solution to connect a 3270 coax
terminal to host systems through the oec terminal controller software
written by Andrew Kay.  It consists of a Raspberry Pi Pico-based
hardware interface and MicroPython software that implements the coax
protocol used by 3270 terminals in CUT mode.

## Overview

Interface3 enables communication with IBM 3270 terminals by:

1. **Hardware Interface**: A custom PCB with a Raspberry Pi Pico and
   up to four serial coax interfaces that implement the physical layer
   connection to 3270 terminals.
2. **Protocol Implementation**: The Manchester-encoded coax protocol
   is implemented using PIO blocks of the RP2040 microcontroller.
3. **Connection Modes**: Two connection modes are supported:
   - **Serial Mode**: Direct USB serial connection to a host running
     oec/pycoax, compatible with interface2.  Requires Andrew Kay's
     original [oec](https://github.com/lowobservable/oec).
   - **WiFi Mode**: TCP client that connects to an oec server over
     WiFi using a custom binary protocol.  Requires the modified
     [oec-tcp](https://github.com/hanshuebner/oec-tcp).

## How It Works

### Hardware Layer
The interface uses a Raspberry Pi Pico with custom PCB that provides:
- Two Coax interfaces with proper signal conditioning
- Two additional serial interfaces with TTL levels on a pin header
- LED indicators to display the operating state of the interface
- Momentary button that resets the Raspberry Pi Pico
- USB B socket for power supply and serial connection

### Software Layer

The interface3 software implements the line level Manchester-encoded
protocol in a
[PIO](https://www.raspberrypi.com/news/what-is-pio/) block.  This
offloads the handling of the real-time protocol requirements from the
main ARM CPU and allows the rest of the interface software to be
implemented in MicroPython.  Data between MicroPython and the PIO
blocks is exchanged through DMA, allowing the MicroPython part to
operate only on full frames.

## Installation

### Prerequisites

1. **MicroPython with DMA Extensions**: You need a MicroPython release
   1.26.0 or later to get support for the DMA transfer library
   required by the firmware.

2. **Hardware**: The interface3 PCB with Raspberry Pi Pico installed

3. **Development Tools**:
   - `mpremote` for communicating with the Pico
   - `jq` for JSON processing (used by config-wifi.sh, WiFi mode only)

### Common Installation Steps

1. **Flash MicroPython Firmware**:

   A prebuilt MicroPython image for the Raspberry Pi Pico W (RP2040
   version) can be downloaded from
   [my web site](https://vaxbusters.org/micropython-v1.26.0-rpi-pico-w.uf2).
   Connect the Raspberry Pi Pico W to your workstation using its Micro USB
   port while holding the small white "BOOTSEL" button, then copy the
   image to the USB drive that automatically appears (mounted as
   `/Volumes/RPI-RP2/` on Macs).

2. **Install mpremote**

   You can either install mpremote from your system's package repository
   or using pip.  When using pip, using a virtual environment is
   recommended:

   ```bash
   python -m venv .venv
   . .venv/bin/activate
   pip install mpremote
   ```

3. **Upload and install the firmware** using the install script:

   ```bash
   ./install.sh serial   # For serial mode
   ./install.sh wifi     # For WiFi mode
   ```

   The install script will upload all required files and configure
   the device for the selected mode.

### Serial Mode Setup

After running `./install.sh serial`, the device is ready to use.
Connect to the interface using oec (see Usage section below).

### WiFi Mode Setup

After running `./install.sh wifi`, configure WiFi credentials:

```bash
./config-wifi.sh
```

This interactive script will:
- Prompt for WiFi network name and password
- Prompt for the hostname of the oec server
- Create a `config.json` file on the device
- Reset the device to apply the configuration

For testing, you can use my oec server running at netzhansa.com.
It is located in Germany, however, so the latency may be quite
high.  If you run oec on a port other than 3174, you can enter it
after the hostname, colon separated (host:port).

The device stores configuration in a `config.json` file:
```json
{
  "wifi": {
    "ssid": "your_network_name",
    "password": "your_network_password"
  },
  "connect_to": "your-oec-server.example.com"
}
```

## Usage

### Serial Mode

Serial mode requires Andrew Kay's original oec repository:
https://github.com/lowobservable/oec

Run oec with the serial port:

```bash
python -m oec /dev/tty.usbmodem* tn3270 your-host.example.com:23
```

Replace `/dev/tty.usbmodem*` with the actual device path (e.g.,
`/dev/tty.usbmodem1124101` on macOS, `/dev/ttyACM0` on Linux, or
`COM3` on Windows).

The interface presents five serial ports: one per coax port, followed
by the capture port.  Name the port you want explicitly rather than
relying on a glob.

#### Accessing the Python REPL

During startup, the firmware provides a 5-second window to access the
MicroPython REPL for debugging or configuration.  To access the REPL:

1. **Connect to the USB serial port** before or immediately after
   resetting the device.  Use a terminal program or mpremote:
   ```bash
   mpremote connect /dev/tty.usbmodem* repl
   ```

2. **Watch for the startup blink pattern** - the STS LED blinks slowly
   (250ms on, 250ms off) during this 5-second window.

3. **Press Ctrl-C** during this window to interrupt startup and enter
   the REPL.

**Important**: You must connect to the serial port *before* the
startup window expires.  Once the firmware enters protocol mode, the
serial port is used exclusively for SLIP-encoded communication and
keyboard interrupt is disabled.

### WiFi Mode

WiFi mode requires a modified version of oec that acts as a TCP server:
https://github.com/hanshuebner/oec-tcp

Start the oec-tcp server:

```bash
python -m oec --server :3174 tn3270 your-host.example.com:23
```

This starts oec listening on port 3174 for incoming connections from
interface3 devices.  When the interface connects to WiFi successfully,
it will automatically connect to the configured server.

See the [TCP Protocol documentation](./TCP_PROTOCOL.md) for details on
the network protocol.

### Capturing Coax Traffic

The interface can record the coax traffic it exchanges with attached
terminals and hand it to Wireshark.  Capture happens in the firmware,
so both directions of every transaction are recorded as they appear on
the wire, with microsecond timestamps.

Records leave the device on a fifth USB serial port named `Coax
Capture`, which the four command ports are unaffected by.  Write a
capture file with:

```bash
tools/coax-capture --write coax.pcapng
```

To capture from the Wireshark GUI, install the capture plugin and the
dissector once:

```bash
tools/install-wireshark.sh
```

Idle polls are left out unless `--idle-polls` is given, since a
terminal is polled continuously.  See the [capture
documentation](./CAPTURE.md) for the record format, the filtering
options and the pcapng layout.

The interface can also record a link between some other controller and
a terminal, either sitting in the middle of it and forwarding between
two ports, or listening on one:

```bash
tools/coax-capture --forward 0,1 --write link.pcapng
tools/coax-capture --tap 0 --write tap.pcapng
```

See [Passive Capture](./PASSIVE-CAPTURE.md) for how to connect the
interface to a link and what to expect.  Forwarding needs a second coax
port that can transmit; boards built from the earlier layout need the
rework described in [PCB Rework](./PCB-REWORK.md).

## LED Indicators

The interface provides several LED indicators:
- **NET**: Network activity (WiFi mode only)
- **STS**: Status indicator
- **ERR**: Error indicator
- **TX1-4/RX1-4**: Individual channel transmit/receive indicators
- **PICO**: Raspberry Pi Pico onboard LED

### Serial Mode LED Patterns

| LED | Pattern | Description |
|-----|---------|-------------|
| STS | Slow blink (250ms on/off) | **Startup window** - Press Ctrl-C to access REPL |
| STS | Fast blink (100ms on, 200ms off) | **Waiting for connection** - Ready for host to connect |
| STS | Once per second (100ms on, 900ms off) | **Connected** - Normal operation |
| ERR | Continuous fast blink (250ms on/off) | **Fatal error** - Unhandled exception occurred |

### WiFi Mode LED Patterns

| LED | Pattern | Description |
|-----|---------|-------------|
| NET | Fast blink (8Hz) | **Connecting to WiFi** - Attempting to join network |
| NET | Brief on, then off | **WiFi connected** - Successfully joined network |
| NET | On during activity | **Network activity** - Processing commands from server |
| STS | Solid on | **Connecting to server** - Attempting TCP connection |
| STS | Blink (1s on, 1s off) | **Reconnecting** - Connection lost, retrying |
| ERR | Solid on | **WiFi failed** - Could not connect to WiFi network |
| ERR | Solid on | **Coax timeout** - Terminal not responding (clears on success) |

## Quick Reference

| Mode | oec Repository | Command |
|------|----------------|---------|
| Serial | [lowobservable/oec](https://github.com/lowobservable/oec) | `python -m oec /dev/ttyUSB0 tn3270 host:port` |
| WiFi | [hanshuebner/oec-tcp](https://github.com/hanshuebner/oec-tcp) | `python -m oec --server :3174 tn3270 host:port` |

## License

Copyright (c) 2025, Hans Hübner

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
