import asyncio
import socket
import struct
import gc
from machine import Pin
import coax
from leds import leds
import config

# Protocol constants
TCP_PORT = 3278
MAX_FRAME_SIZE = 4300  # ~4KB limit
STATIC_CMD_BUFFER = bytearray(MAX_FRAME_SIZE)
STATIC_RECV_BUFFER = bytearray(MAX_FRAME_SIZE)

# Command codes
CMD_TRANSACT = 0x01
CMD_PING = 0x02

# Response codes
RESP_OK = 0x00
RESP_ERROR = 0x01
RESP_TIMEOUT = 0x02
RESP_INVALID_CMD = 0x03
RESP_INVALID_LENGTH = 0x04
RESP_POLL = 0x05

# Manchester encoded commands for poll snooping
POLL_COMMAND_DATA     = b'\x05\x00'
POLL_ACK_COMMAND_DATA = b'E\x00'

# Predefined responses
EMPTY_RESPONSE_DATA   = b'\x00\x00'

loop = asyncio.get_event_loop()

async def send_response(writer, resp_code, data):
    """
    Send a response directly to the TCP connection: [16-bit length][8-bit resp_code][data]
    """
    if len(data) > MAX_FRAME_SIZE - 3:  # -3 for length(2) + resp_code(1)
        raise ValueError("Data too large for frame")

    frame_len = len(data) + 1  # +1 for resp code
    writer.write(struct.pack("<HB", frame_len, resp_code))
    if data:
        writer.write(data)
    writer.drain()

last_command = None
last_response = None

async def handle_transact_command(writer, command):
    """
    Handle transact command - send command to coax interface and receive response
    """
    global last_command, last_response

    if command == POLL_COMMAND_DATA or command == POLL_ACK_COMMAND_DATA:
        print('unexpected poll command received over TCP, responding empty')
        await send_response(writer, RESP_OK, EMPTY_RESPONSE_DATA)
        return

    try:
        # Validate data length (must be even for coax protocol)
        if len(command) % 2 != 0:
            await send_response(writer, RESP_ERROR, b"Command length must be even")
            return

        # Perform coax transaction
        response = coax.transact(command)
        if command != last_command or response != last_response:
            print('> ', command, ' < ', response)
            last_command = command
            last_response = response

        # Limit response size
        response_len = min(len(response), MAX_FRAME_SIZE - 3)

        leds['ERR'].off()
        await send_response(writer, RESP_OK, response[:response_len])

    except coax.Timeout:
        leds['ERR'].on()
        await send_response(writer, RESP_TIMEOUT, b"Transaction timeout")
    except BaseException as e:
        leds['ERR'].on()
        await send_response(writer, RESP_ERROR, str(e).encode())

async def handle_ping_command(writer, data):
    """
    Handle ping command - simple echo for testing
    """
    await send_response(writer, RESP_OK, b"PONG")

async def handle_command(writer, cmd_code, data):
    """
    Route command to appropriate handler
    """
    if cmd_code == CMD_TRANSACT:
        await handle_transact_command(writer, data)
    elif cmd_code == CMD_PING:
        await handle_ping_command(writer, data)
    else:
        await send_response(writer, RESP_INVALID_CMD, f"Unknown command: {cmd_code}".encode())

async def read_command(reader):
    """
    Read a command from the client
    Returns (cmd_code, data) or None if connection closed
    """
    len_buf = await reader.readexactly(2)
    frame_len = struct.unpack("<H", len_buf)[0]

    # Validate frame length
    if frame_len > MAX_FRAME_SIZE - 2:  # -2 for length field
        print(f"Frame too large: {frame_len} bytes (max: {MAX_FRAME_SIZE - 2})")
        return None  # Frame too large

    # Read command code (1 byte)
    cmd_data = await reader.readexactly(1)

    cmd_code = cmd_data[0]

    # Read remaining data (if any)
    data = await reader.readexactly(frame_len - 1) # -1 for command code

    return cmd_code, data

async def handle_oec_connection(reader, writer):
    """
    Handle a single OEC connection
    """
    keyboard_poller = None
    try:
        keyboard_poller = loop.create_task(poll_keyboard(writer))
        while True:
            # Read command
            result = await read_command(reader)
            if result is None:
                break

            cmd_code, data = result

            leds['NET'].on()

            try:
                # Process command and send response directly
                await handle_command(writer, cmd_code, data)

            except Exception as e:
                print(f"Error handling command: {e}")
                await send_response(writer, RESP_ERROR, str(e).encode())
                raise

            leds['NET'].off()
            gc.collect()

    except Exception as e:
        print(f"OEC error: {e}")

    finally:
        keyboard_poller.cancel()
        reader.close()
        writer.close()
        await reader.wait_closed()
        await writer.wait_closed()


async def connect_to_server():
    host, _, port = config.connect_to.partition(':')
    port = int(port or 3174)

    while True:
        leds['STS'].on()
        try:
            print(f'trying to connect to {host}:{port}')
            reader, writer = await asyncio.open_connection(host, port)
            await handle_oec_connection(reader, writer)
            await asyncio.sleep_ms(1000)
            leds['STS'].off()
            await asyncio.sleep_ms(1000)
        except Exception as e:
            print(f"Cannot connect to {host}:{port}: {e}")
            await asyncio.sleep_ms(1000)

async def poll_keyboard(writer):
    while True:
        try:
            response = coax.transact(POLL_COMMAND_DATA)
            if response != EMPTY_RESPONSE_DATA:
                ack_response = coax.transact(POLL_ACK_COMMAND_DATA)
                if ack_response != EMPTY_RESPONSE_DATA:
                    print('unexpected response to poll ack', ack_response)
                await send_response(writer, RESP_POLL, response)
        except coax.Timeout:
            print("Timeout waiting for terminal response on coax interface")
        await asyncio.sleep_ms(3)

def serve():
    """
    Start the TCP connector
    """

    loop.create_task(connect_to_server())

    try:
        loop.run_forever()
    except Exception as e:
        print('Error serving clients: ', e)
    except KeyboardInterrupt:
        print('Server terminated in response to Ctrl-C')
