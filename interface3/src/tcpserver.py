import asyncio
import socket
import struct
import gc
from machine import Pin
import wifi
import coax
from leds import leds

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

async def handle_transact_command(writer, data):
    """
    Handle transact command - send data to coax interface
    """
    try:
        # Validate data length (must be even for coax protocol)
        if len(data) % 2 != 0:
            await send_response(writer, RESP_ERROR, b"Data length must be even")
            return

        # Perform coax transaction
        timeout = 1000  # Default timeout
        rx_data = coax.transact(data, timeout=timeout)

        # Limit response size and send directly
        resp_len = min(len(rx_data), MAX_FRAME_SIZE - 3)
        response_data = rx_data[:resp_len]

        leds['ERR'].off()
        await send_response(writer, RESP_OK, response_data)

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

async def handle_client(reader, writer):
    """
    Handle a single client connection
    """
    print("Client connected")

    try:
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
        print(f"Client error: {e}")

    finally:
        reader.close()
        writer.close()
        await reader.wait_close()
        await writer.wait_close()
        print("Client connection closed")

async def serve_incoming_connections():
    server = asyncio.start_server(handle_client, '0.0.0.0', TCP_PORT)
    asyncio.create_task(server)
    while True:
        leds['STS'].toggle()
        await asyncio.sleep_ms(1000)

def serve():
    """
    Start the TCP server
    """
    loop = asyncio.get_event_loop()
    loop.create_task(serve_incoming_connections())
    try:
        loop.run_forever()
    except Exception as e:
        print('Error serving clients: ', e)
    except KeyboardInterrupt:
        print('Server terminated in response to Ctrl-C')
