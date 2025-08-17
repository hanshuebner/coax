import socket
import struct
import gc
from machine import Pin, Timer
import wifi
import coax
from leds import leds

# Protocol constants
TCP_PORT = 3278
MAX_FRAME_SIZE = 4100  # ~4KB limit
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

def send_response(client, resp_code, data):
    """
    Send a response directly to the TCP connection: [16-bit length][8-bit resp_code][data]
    """
    if len(data) > MAX_FRAME_SIZE - 3:  # -3 for length(2) + resp_code(1)
        raise ValueError("Data too large for frame")

    frame_len = len(data) + 1  # +1 for resp code
    client.send(struct.pack("<HB", frame_len, resp_code))
    if data:
        client.send(data)

def handle_transact_command(client, data):
    """
    Handle transact command - send data to coax interface
    """
    try:
        # Validate data length (must be even for coax protocol)
        if len(data) % 2 != 0:
            send_response(client, RESP_ERROR, b"Data length must be even")
            return

        # Use static buffer for transaction
        STATIC_CMD_BUFFER[:len(data)] = data

        # Perform coax transaction
        timeout = 1000  # Default timeout
        rx_data = coax.transact(STATIC_CMD_BUFFER[:len(data)], timeout=timeout)

        # Limit response size and send directly
        resp_len = min(len(rx_data), MAX_FRAME_SIZE - 3)
        response_data = rx_data[:resp_len]

        leds['ERR'].off()
        send_response(client, RESP_OK, response_data)

    except coax.Timeout:
        leds['ERR'].on()
        send_response(client, RESP_TIMEOUT, b"Transaction timeout")
    except Exception as e:
        leds['ERR'].on()
        send_response(client, RESP_ERROR, str(e).encode())

def handle_ping_command(client, data):
    """
    Handle ping command - simple echo for testing
    """
    send_response(client, RESP_OK, b"PONG")

def handle_command(client, cmd_code, data):
    """
    Route command to appropriate handler
    """
    if cmd_code == CMD_TRANSACT:
        handle_transact_command(client, data)
    elif cmd_code == CMD_PING:
        handle_ping_command(client, data)
    else:
        send_response(client, RESP_INVALID_CMD, f"Unknown command: {cmd_code}".encode())

def read_command(client):
    """
    Read a command from the client
    Returns (cmd_code, data) or None if connection closed
    """
    # Read length field (2 bytes)
    bytes_received = 0
    while bytes_received < 2:
        chunk = client.recv(2 - bytes_received)
        if len(chunk) == 0:
            print("Connection closed while reading length field")
            return None  # Connection closed
        STATIC_RECV_BUFFER[bytes_received:bytes_received + len(chunk)] = chunk
        bytes_received += len(chunk)

    frame_len = struct.unpack("<H", STATIC_RECV_BUFFER[:2])[0]

    # Validate frame length
    if frame_len > MAX_FRAME_SIZE - 2:  # -2 for length field
        print(f"Frame too large: {frame_len} bytes (max: {MAX_FRAME_SIZE - 2})")
        return None  # Frame too large

    # Read command code (1 byte)
    cmd_data = client.recv(1)
    if len(cmd_data) == 0:
        print("Connection closed while reading command code")
        return None  # Connection closed

    cmd_code = cmd_data[0]

    # Read remaining data (if any)
    data_len = frame_len - 1  # -1 for command code
    if data_len > 0:
        bytes_received = 0
        while bytes_received < data_len:
            chunk = client.recv(data_len - bytes_received)
            if len(chunk) == 0:
                print(f"Connection closed while reading data (received {bytes_received}/{data_len} bytes)")
                return None  # Connection closed
            STATIC_RECV_BUFFER[bytes_received:bytes_received + len(chunk)] = chunk
            bytes_received += len(chunk)

        data = STATIC_RECV_BUFFER[:data_len]
    else:
        data = b""

    return cmd_code, data

def handle_client(client):
    """
    Handle a single client connection
    """
    print("Client connected")

    try:
        while True:
            # Read command
            result = read_command(client)
            if result is None:
                break

            cmd_code, data = result

            leds['NET'].on()

            try:
                # Process command and send response directly
                handle_command(client, cmd_code, data)

            except Exception as e:
                print(f"Error handling command: {e}")
                send_response(client, RESP_ERROR, str(e).encode())
                raise

            leds['NET'].off()
            gc.collect()

    except Exception as e:
        print(f"Client error: {e}")

    finally:
        client.close()
        print("Client connection closed")

def blink(timer):
    """
    Blink status LED to show server is running
    """
    leds['STS'].toggle()

def serve():
    """
    Start the TCP server
    """
    listen_addr = socket.getaddrinfo('0.0.0.0', TCP_PORT)[0][-1]

    listen_socket = socket.socket()
    listen_socket.bind(listen_addr)
    listen_socket.listen(1)

    print(f'TCP server listening on port {TCP_PORT}')

    # Status LED timer
    timer = Timer()
    timer.init(freq=1, mode=Timer.PERIODIC, callback=blink)

    try:
        while True:
            try:
                client, client_addr = listen_socket.accept()
                print(f"Connection from {client_addr}")

                handle_client(client)

            except Exception as e:
                print(f'Error handling client: {e}')
                try:
                    client.close()
                except:
                    pass

    except KeyboardInterrupt:
        print("Server interrupted")

    finally:
        print("Closing server")
        timer.deinit()
        listen_socket.close()

if __name__ == "__main__":
    serve()
