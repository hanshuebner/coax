# Interface3 - Raspberry Pi Pico W based 3270 Terminal Adapter with WiFi

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
3. **TCP Server**: A TCP client is provided that allows the exchange
   of 3270 protocol frames through WiFi using a custom binary
   protocol.  The [oec](https://github.com/hanshuebner/oec) terminal
   controller can act as the server to bridge between a 3270
   terminal and a tn3270 host.

## How It Works

### Hardware Layer
The interface uses a Raspberry Pi Pico with custom PCB that provides:
- Two Coax interfaces with proper signal conditioning
- Two additional serial interfaces with TTL levels on a pin header
- LED indicators to display the operating state of the interface
- Momentary button that resets the Raspberry Pi Pico
- USB B socket for power supply and an optional serial connection

### Software Layer

The interface3 software provides implements the line level manchester
encoded protocol in a
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
   - `jq` for JSON processing (used by config-wifi.sh)

### Installation Steps

1. **Flash MicroPython Firmware**:

   A prebuilt MicroPython image for the Raspberry Pi Pico W (RP2040
   version) can be downloaded from
   [my web site](https://vaxbusters.org/micropython-v1.26.0-rpi-pico-w.uf2).
   Connect the Rasperry Pi Pico W to your workstation using its Micro USB
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

3. **Upload MicroPython Firmware to Pico**:
   ```bash
   # Use the provided upload script
   ./upload-and-run.sh
   ```

   This script will:
   - Reset the device
   - Copy all Python files from `src/` to the Pico
   - Start the main application
  
   You will see the output of the MicroPython firmware.  It may try to connect
   to a previously configured WiFi network.  You can interrupt the Firmware
   using Ctrl-C to get to the Python repl or exit the connection using Ctrl-X.

5. **Configure WiFi**:
   ```bash
   # Use the provided WiFi configuration script
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
  
   Again, you'll be looking at the diagnostic output of the firmware
   at the end of this process.  When it connects to the WiFi network
   successfully, it will print the IP address assigned to it by the
   DHCP server.  It will then connect to the configured server.

### Configuration

The device stores configuration in a `config.json` file with the following structure:
```json
{
  "wifi": {
    "ssid": "your_network_name",
    "password": "your_network_password"
  },
  "connect_to": "your-oec-server.example.com"
}
```

## LED Indicators

The interface provides several LED indicators:
- **NET**: Network activity (blinks during HTTP requests)
- **STS**: Status indicator (blinks at 1Hz when running)
- **ERR**: Error indicator (lights when transactions timeout)
- **TX1-4/RX1-4**: Individual channel transmit/receive indicators
- **PICO**: Raspberry Pi Pico onboard LED

## Integration with oec

Interface3 is designed to work with oec (3174 emulation software)
written by Andrew Kay. oec can be found at
[github.com/hanshuebner/oec](https://github.com/hanshuebner/oec).

## TCP Protocol

The TCP based protocol is described in a [separate file](./TCP_PROTOCOL.md).

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


