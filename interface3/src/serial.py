import sys
import micropython
import struct
import coax
import uselect
import machine
from machine import Timer, WDT
from leds import leds
from time import sleep
from debug import dprint, debug

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

poll = uselect.poll()
poll.register(sys.stdin, uselect.POLLIN)

def sync():
    dprint("synchronizing")
    while poll.poll(0):
        b = sys.stdin.buffer.read(1)
        dprint("discard {}".format(b.hex(' ')))
    dprint("done synchronizing")

def unpack_message(buf: bytes):
    length, command = struct.unpack_from('>HB', buf, 0)
    return length, command, buf[3:-2]  # exclude 2-byte footer

def read_byte():
    """Read a single byte from stdin"""
    byte = sys.stdin.buffer.read(1)
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
    payload_len = 2 + len(encoded_message)  # 2 for RESPONSE_ERROR + error code
    return struct.pack('>HBB', payload_len, RESPONSE_ERROR, code) + encoded_message + b'\x00\x00'

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
                           INFO_FEATURES) + b'\x00\x00'

    elif query == INFO_HARDWARE_TYPE:
        encoded_message = HARDWARE_TYPE.encode()
        payload_len = 1 + len(encoded_message)  # 1 for RESPONSE_OK
        return struct.pack('>HB', payload_len,
                           RESPONSE_OK) + encoded_message + b'\x00\x00'

    elif query == INFO_FIRMWARE_VERSION:
        encoded_message = FIRMWARE_VERSION.encode()
        payload_len = 1 + len(encoded_message)  # 1 for RESPONSE_OK
        return struct.pack('>HB', payload_len,
                           RESPONSE_OK) + encoded_message + b'\x00\x00'

    elif query == INFO_MESSAGE_BUFFER_SIZE:
        return struct.pack('>HBI', 5,
                           RESPONSE_OK,
                           MAX_FRAME_SIZE) + b'\x00\x00'

    elif query == INFO_FEATURES:
        return struct.pack('>HB', 1, RESPONSE_OK) + b'\x00\x00'

    else:
        return error_response(ERROR_INVALID_MESSAGE, "unknown query type")

def cmd_transmit_receive(buf):
    # Parse message format:
    # repeat_info (2 bytes BE) + words (N*2 bytes LE) + response_length (2 bytes BE) + timeout_ms (2 bytes BE)
    repeat_info = struct.unpack('>H', buf[0:2])[0]
    timeout_ms = struct.unpack('>H', buf[-2:])[0]

    # Extract coax words (everything between repeat_info and response_length/timeout)
    coax_words = buf[2:-4]

    dprint("repeat_info={} timeout_ms={} coax_words={}".format(repeat_info, timeout_ms, coax_words.hex(' ')))

    # Use timeout from message, with minimum of 200ms (1ms from pycoax is too short)
    timeout = max(timeout_ms, 200)

    try:
        rx_data = coax.transact(coax_words, timeout=timeout)
    except coax.Timeout:
        return error_response(102, "")  # ReceiveTimeout

    # Format: length (2 bytes) + RESPONSE_OK (1 byte) + coax data + footer (2 bytes)
    payload_len = 1 + len(rx_data)  # 1 for RESPONSE_OK
    return struct.pack('>HB', payload_len, RESPONSE_OK) + rx_data + b'\x00\x00'

timer_period = 200
status_timer = Timer()

def status_led_off(_):
    leds['STS'].off()
    status_timer.init(period=timer_period, mode=Timer.ONE_SHOT, callback=status_led_on)

def status_led_on(_):
    leds['STS'].on()
    status_timer.init(period=100, mode=Timer.ONE_SHOT, callback=status_led_off)

def serve():
    global timer_period
    micropython.kbd_intr(-1)
    sync()
    leds['STS'].off()
    wdt = None
    status_led_on(None)

    while True:
        frame = read_slip_frame()

        dprint("Data: {}".format(frame.hex(' ')))

        length, command, buf = unpack_message(frame)

        if command == COMMAND_RESET:
            dprint("COMMAND_RESET")
            timer_period = 900
            wdt = WDT(timeout = 5000)
            response = cmd_reset(buf)
        elif command == COMMAND_INFO:
            dprint("COMMAND_INFO")
            response = cmd_info(buf)
        elif command == COMMAND_TRANSMIT_RECEIVE:
            dprint("COMMAND_TRANSMIT_RECEIVE")
            response = cmd_transmit_receive(buf)
        else:
            dprint("COMMAND_TRANSMIT_RECEIVE")
            response = error_response(ERROR_UNKNOWN_COMMAND, "command not (yet) implemented")

        dprint("Response: {}".format(response.hex(' ')))
        write_slip_frame(response)

        if wdt != None:
            wdt.feed()

def main():
    # give the operator some time to press ctrl-c
    for _ in range(10):
        leds['STS'].on()
        sleep(0.25)
        leds['STS'].off()
        sleep(0.25)

    dprint('Starting serial protocol')
    try:
        serve()
    except Exception as e:
        micropython.kbd_intr(3)                             # reset keyboard interrupt to ctrl-c
        import traceback
        debug = True
        dprint("EXCEPTION:", repr(e))
        dprint(traceback.format_exc())
        while True:
            leds['ERR'].on()
            sleep(0.25)
            leds['ERR'].off()
            sleep(0.25)
