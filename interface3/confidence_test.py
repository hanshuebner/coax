#!/usr/bin/env python3
"""
Confidence test for interface3 serial protocol.

Connects to the adapter and sends RESET and INFO commands,
displaying the decoded responses. Then continuously polls
the terminal keyboard.
"""

import sys
import struct
import argparse
import time
from serial import Serial
from sliplib import SlipWrapper

# SLIP Protocol Constants
END = 0xC0
ESC = 0xDB
ESC_END = 0xDC
ESC_ESC = 0xDD

# Command codes
COMMAND_RESET = 0x01
COMMAND_TRANSMIT_RECEIVE = 0x06
COMMAND_INFO = 0xF0

# INFO subcommands
INFO_SUPPORTED_QUERIES = 0x01
INFO_HARDWARE_TYPE = 0x02
INFO_HARDWARE_REVISION = 0x03
INFO_HARDWARE_SERIAL = 0x04
INFO_FIRMWARE_VERSION = 0x05
INFO_MESSAGE_BUFFER_SIZE = 0x06
INFO_FEATURES = 0x07

# Response codes
RESPONSE_OK = 0x01
RESPONSE_ERROR = 0x02

INFO_NAMES = {
    INFO_SUPPORTED_QUERIES: "Supported Queries",
    INFO_HARDWARE_TYPE: "Hardware Type",
    INFO_HARDWARE_REVISION: "Hardware Revision",
    INFO_HARDWARE_SERIAL: "Hardware Serial",
    INFO_FIRMWARE_VERSION: "Firmware Version",
    INFO_MESSAGE_BUFFER_SIZE: "Message Buffer Size",
    INFO_FEATURES: "Features",
}

# Coax protocol constants
COAX_COMMAND_POLL = 0x01
COAX_COMMAND_POLL_ACK = 0x11


def pack_command_word(command):
    """Pack a coax command into a 10-bit command word."""
    return (command << 2) | 0x1


def is_keystroke_response(value):
    """Check if the response word is a keystroke response."""
    return ((value & 0x2) == 0x2) and ((value & 0x1) == 0)


def is_tt_ar(words):
    """Check if response is TT/AR (no response from terminal)."""
    return len(words) == 1 and words[0] == 0


class SlipSerial(SlipWrapper):
    """sliplib wrapper for pySerial."""

    def send_bytes(self, packet):
        self.stream.write(packet)
        self.stream.flush()

    def recv_bytes(self):
        if self.stream.closed:
            return b''
        count = self.stream.in_waiting
        if count:
            return self.stream.read(count)
        byte = self.stream.read(1)
        if byte == b'':
            raise TimeoutError("Serial read timeout")
        return byte


def write_message(slip_serial, message):
    """Write a message with length prefix and footer."""
    packet = struct.pack('>H', len(message)) + message + struct.pack('>H', 0)
    slip_serial.send_msg(packet)


def read_message(slip_serial):
    """Read a message and strip length prefix and footer."""
    message = slip_serial.recv_msg()
    if len(message) < 4:
        raise ValueError(f"Invalid response message: {message.hex()}")
    length = struct.unpack('>H', message[:2])[0]
    if length != len(message) - 4:
        raise ValueError(f"Response message length mismatch: expected {length}, got {len(message) - 4}")
    return message[2:-2]


def decode_reset_response(response):
    """Decode RESET response."""
    if response[0] != RESPONSE_OK:
        error_code = response[1] if len(response) > 1 else 0
        error_msg = response[2:].decode('ascii', errors='replace') if len(response) > 2 else ''
        return False, f"Error {error_code}: {error_msg}"

    if response[1:] == b'\x32\x70':
        return True, "Non-legacy firmware (interface3 compatible)"
    elif len(response) == 4:
        major, minor, patch = struct.unpack('BBB', response[1:])
        return True, f"Legacy firmware v{major}.{minor}.{patch}"
    else:
        return True, f"Unknown response format: {response[1:].hex()}"


def decode_info_response(query, response):
    """Decode INFO response."""
    if response[0] != RESPONSE_OK:
        error_code = response[1] if len(response) > 1 else 0
        error_msg = response[2:].decode('ascii', errors='replace') if len(response) > 2 else ''
        return False, f"Error {error_code}: {error_msg}"

    payload = response[1:]

    if query == INFO_SUPPORTED_QUERIES:
        query_names = [INFO_NAMES.get(q, f"0x{q:02x}") for q in payload]
        return True, ", ".join(query_names)
    elif query in (INFO_HARDWARE_TYPE, INFO_FIRMWARE_VERSION):
        return True, payload.decode('ascii', errors='replace')
    elif query == INFO_MESSAGE_BUFFER_SIZE:
        if len(payload) >= 4:
            size = struct.unpack('>I', payload[:4])[0]
            return True, f"{size} bytes"
        return True, f"Raw: {payload.hex()}"
    elif query == INFO_FEATURES:
        if len(payload) == 0:
            return True, "None"
        features = [f"0x{f:02x}" for f in payload]
        return True, ", ".join(features)
    else:
        return True, f"Raw: {payload.hex()}"


def transmit_receive(slip_serial, command_word, response_length=1, timeout_ms=100):
    """Send a coax command via TRANSMIT_RECEIVE and return response words."""
    # Build message: command + repeat_info + words + response_length + timeout
    message = bytes([COMMAND_TRANSMIT_RECEIVE])
    message += struct.pack('>H', 0)  # repeat_info: no repeat
    message += struct.pack('<H', command_word)  # word in little-endian
    message += struct.pack('>H', response_length)
    message += struct.pack('>H', timeout_ms)

    write_message(slip_serial, message)
    response = read_message(slip_serial)

    if response[0] != RESPONSE_OK:
        error_code = response[1] if len(response) > 1 else 0
        return None, error_code

    # Unpack response words (little-endian pairs)
    words = []
    payload = response[1:]
    for i in range(0, len(payload), 2):
        if i + 1 < len(payload):
            word = payload[i] | (payload[i + 1] << 8)
            words.append(word)
    return words, None


def poll_keyboard(slip_serial, timeout_ms=100):
    """Poll the terminal keyboard. Returns (scan_code, error) tuple."""
    command_word = pack_command_word(COAX_COMMAND_POLL)
    words, error = transmit_receive(slip_serial, command_word, response_length=1, timeout_ms=timeout_ms)

    if error is not None:
        return None, error

    if words is None or len(words) == 0:
        return None, "No response"

    if is_tt_ar(words):
        return None, None  # No key pressed

    if is_keystroke_response(words[0]):
        scan_code = (words[0] >> 2) & 0xff
        return scan_code, None

    return None, f"Unknown response: 0x{words[0]:04x}"


def send_poll_ack(slip_serial, timeout_ms=100):
    """Send POLL_ACK to acknowledge a keystroke."""
    command_word = pack_command_word(COAX_COMMAND_POLL_ACK)
    transmit_receive(slip_serial, command_word, response_length=1, timeout_ms=timeout_ms)


def run_confidence_test(port, timeout=5):
    """Run the confidence test on the specified serial port."""
    print(f"Opening serial port {port} at 115200 baud...")

    with Serial(port, 115200, timeout=timeout) as serial:
        serial.reset_input_buffer()
        serial.reset_output_buffer()

        slip_serial = SlipSerial(serial)

        # Send RESET command
        print("\n--- RESET Command ---")
        write_message(slip_serial, bytes([COMMAND_RESET]))
        response = read_message(slip_serial)
        print(f"  Raw response: {response.hex(' ')}")
        success, decoded = decode_reset_response(response)
        status = "OK" if success else "FAILED"
        print(f"  Status: {status}")
        print(f"  Result: {decoded}")

        if not success:
            print("\nRESET failed, aborting further tests.")
            return False

        # Send INFO commands
        print("\n--- INFO Commands ---")

        # First get supported queries
        write_message(slip_serial, bytes([COMMAND_INFO, INFO_SUPPORTED_QUERIES]))
        response = read_message(slip_serial)
        print(f"\n  {INFO_NAMES[INFO_SUPPORTED_QUERIES]}:")
        print(f"    Raw: {response.hex(' ')}")
        success, decoded = decode_info_response(INFO_SUPPORTED_QUERIES, response)
        print(f"    Result: {decoded}")

        if success and response[0] == RESPONSE_OK:
            supported = list(response[1:])
        else:
            # Query common ones anyway
            supported = [INFO_HARDWARE_TYPE, INFO_FIRMWARE_VERSION, INFO_MESSAGE_BUFFER_SIZE, INFO_FEATURES]

        # Query each supported info type (except SUPPORTED_QUERIES which we already did)
        for query in supported:
            if query == INFO_SUPPORTED_QUERIES:
                continue

            query_name = INFO_NAMES.get(query, f"Query 0x{query:02x}")
            write_message(slip_serial, bytes([COMMAND_INFO, query]))
            response = read_message(slip_serial)
            print(f"\n  {query_name}:")
            print(f"    Raw: {response.hex(' ')}")
            success, decoded = decode_info_response(query, response)
            print(f"    Result: {decoded}")

        print("\n--- Confidence Test Complete ---")

        # Keyboard polling loop
        print("\n--- Keyboard Polling (press Ctrl+C to exit) ---")
        print("Polling terminal keyboard at 100ms intervals...")

        while True:
            scan_code, error = poll_keyboard(slip_serial, timeout_ms=100)

            if error is not None:
                if error == 102:  # ReceiveTimeout - normal when no key pressed
                    pass
                else:
                    print(f"\rPoll error: {error}                    ", end="", flush=True)
            elif scan_code is not None:
                print(f"\nKey pressed! Scan code: 0x{scan_code:02X} ({scan_code})")
                send_poll_ack(slip_serial, timeout_ms=100)

            time.sleep(0.1)

        return True


def main():
    parser = argparse.ArgumentParser(description="Confidence test for interface3 serial protocol")
    parser.add_argument("port", help="Serial port name (e.g., /dev/ttyUSB0 or COM3)")
    parser.add_argument("-t", "--timeout", type=float, default=5, help="Serial timeout in seconds (default: 5)")
    args = parser.parse_args()

    try:
        success = run_confidence_test(args.port, args.timeout)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nKeyboard polling stopped.")
        sys.exit(0)
    except TimeoutError as e:
        print(f"\nTimeout: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
