import sys
import micropython
import struct

HARDWARE_TYPE = "interface3"
FIRMWARE_VERSION = "v0.0"
MAX_FRAME_SIZE = 4300 # FIXME this does not belong here

# SLIP Protocol Constants
END = 0xC0      # 192 - Frame End
ESC = 0xDB      # 219 - Frame Escape
ESC_END = 0xDC  # 220 - Transposed Frame End
ESC_ESC = 0xDD  # 221 - Transposed Frame Escape

# coax interface constants

# Command codes
COMMAND_RESET = 0x01
COMMAND_TRANSMIT_RECEIVE = 0x06
COMMAND_INFO = 0xF0
COMMAND_TEST = 0xF1
COMMAND_DFU = 0xF2

# INFO subcommands
INFO_SUPPORTED_QUERIES = 0x01
INFO_HARDWARE_TYPE = 0x02
INFO_HARDWARE_REVISION = 0x03
INFO_HARDWARE_SERIAL = 0x04
INFO_FIRMWARE_VERSION = 0x05
INFO_MESSAGE_BUFFER_SIZE = 0x06
INFO_FEATURES = 0x07

# Features
FEATURE_PROTOCOL_3299 = 0x10

# TEST subcommands
TEST_SUPPORTED_TESTS = 0x01

# Response codes
RESPONSE_OK = 1
RESPONSE_ERROR = 2

# Error codes
ERROR_INVALID_MESSAGE = 1
ERROR_UNKNOWN_COMMAND = 2
ERROR_MESSAGE_TIMEOUT = 3


def unpack_message(buf: bytes):
    length, command = struct.unpack_from('>HB', buf, 0)
    return length, command, buf[3:]

def read_byte():
    """Read a single byte from stdin"""
    byte = sys.stdin.buffer.read(1)
    if len(byte) == 0:
        return None
    return byte[0]

def write_byte(b):
    """Write a single byte to stdout"""
    sys.stdout.buffer.write(bytes([b]))

def read_slip_frame():
    """Read and decode a SLIP frame from stdin"""
    frame = []
    escaped = False

    while True:
        byte = read_byte()
        if byte is None:
            return None

        if byte == END:
            if len(frame) > 0:
                return bytes(frame)
            # Empty frame, keep waiting
            continue

        if escaped:
            if byte == ESC_END:
                frame.append(END)
            elif byte == ESC_ESC:
                frame.append(ESC)
            else:
                # Protocol error, but be lenient
                frame.append(byte)
            escaped = False
        elif byte == ESC:
            escaped = True
        else:
            frame.append(byte)

def write_slip_frame(data):
    """Encode and write a SLIP frame to stdout"""
    write_byte(END)

    for byte in data:
        if byte == END:
            write_byte(ESC)
            write_byte(ESC_END)
        elif byte == ESC:
            write_byte(ESC)
            write_byte(ESC_ESC)
        else:
            write_byte(byte)

    write_byte(END)

def error_response(code, message):
    encoded_message = message.encode()

    return struct.pack('>HBB', len(encoded_message), RESPONSE_ERROR, code) + encoded_message

def cmd_reset(buf):
    return b'\x00\x03\x01\x32\x70\x00\x00'

def cmd_info(buf):
    query = buf[0]
    if query == INFO_SUPPORTED_QUERIES:
        return struct.pack(">HBBBBBB", 6,
                           RESPONSE_OK,
                           INFO_SUPPORTED_QUERIES,
                           INFO_HARDWARE_TYPE,
                           INFO_FIRMWARE_VERSION,
                           INFO_MESSAGE_BUFFER_SIZE,
                           INFO_FEATURES)
                           
    elif query == INFO_HARDWARE_TYPE:
        encoded_message = HARDWARE_TYPE.encode()

        return struct.pack('>HB', len(encoded_message),
                           RESPONSE_OK) + encoded_message

    elif query == INFO_FIRMWARE_VERSION:
        encoded_message = FIRMWARE_VERSION.encode()

        return struct.pack('>HB', len(encoded_message),
                           RESPONSE_OK) + encoded_message

    elif query == INFO_MESSAGE_BUFFER_SIZE:
        return struct.pack('>HB>L', 4,
                           RESPONSE_OK,
                           MAX_FRAME_SIZE)

    elif query == INFO_FEATURES:
        return struct.pack('>HB', 0, RESPONSE_OK)

    else:
        return error_response(ERROR_INVALID_MESSAGE, "unknown query type")

def cmd_transmit_receive(buf):
    return coax.transact(buf)

def main():
    sys.stderr.write("SLIP server starting\n")

    micropython.kbd_intr(-1)

    while True:
        frame = read_slip_frame()
        if frame is None:
            break

        length, command, buf = unpack_message(frame)

        if command == COMMAND_RESET:
            response = cmd_reset(buf)
        elif command == COMMAND_INFO:
            response = cmd_info(buf)
        elif command == COMMAND_TRANSMIT_RECEIVE:
            response = cmd_transmit_receive(buf)
        else:
            response = error_response(ERROR_UNKNOWN_COMMAND, "command not (yet) implemented")

        #sys.stderr.write("Data: {}\n".format(repr(frame)))
        write_slip_frame(response)

if __name__ == "__main__":
    main()
