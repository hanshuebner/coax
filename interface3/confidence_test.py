#!/usr/bin/env python3
"""
Confidence test for interface3 serial protocol.

Connects to the adapter and sends RESET and INFO commands,
displaying the decoded responses.
"""

import sys
import struct
import argparse
from serial import Serial
from sliplib import SlipWrapper

# SLIP Protocol Constants
END = 0xC0
ESC = 0xDB
ESC_END = 0xDC
ESC_ESC = 0xDD

# Command codes
COMMAND_RESET = 0x01
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
        return True


def main():
    parser = argparse.ArgumentParser(description="Confidence test for interface3 serial protocol")
    parser.add_argument("port", help="Serial port name (e.g., /dev/ttyUSB0 or COM3)")
    parser.add_argument("-t", "--timeout", type=float, default=5, help="Serial timeout in seconds (default: 5)")
    args = parser.parse_args()

    try:
        success = run_confidence_test(args.port, args.timeout)
        sys.exit(0 if success else 1)
    except TimeoutError as e:
        print(f"\nTimeout: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
