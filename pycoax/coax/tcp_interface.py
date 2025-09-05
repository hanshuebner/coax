"""
coax.tcp_interface
~~~~~~~~~~~~~~~~~~~~~
"""
import struct
import socket
import re
import threading
import time
import queue
from contextlib import contextmanager

from .exceptions import ReceiveError, InterfaceError, ReceiveTimeout
from coax.interface import normalize_frame, Interface

HOST_PORT_RE = re.compile(r'^(?P<host>[^:]+)(?::(?P<port>\d+))?$')


def split_host_port(s):
    m = HOST_PORT_RE.match(s)
    if not m:
        raise ValueError("Invalid host:port string: " + s)
    host = m.group("host")
    port = int(m.group("port")) if m.group("port") else None
    return host, port

class TcpInterface(Interface):
    """TCP server 3270 coax interface that accepts incoming connections."""

    # Protocol constants (must match client)
    TCP_PORT = 3174
    MAX_FRAME_SIZE = 4300

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

    def __init__(self, host="0.0.0.0", port=None):
        super().__init__()

        self.host = host
        self.port = port or self.TCP_PORT
        self.server_socket = None
        self.client_socket = None
        self.server_thread = None
        self.receiver_thread = None
        self.running = False
        self.connected = False
        self.connection_lock = threading.Lock()

        # Queue for response messages from the receiver thread
        self.response_queue = queue.Queue()
        self.poll_response_queue = queue.Queue()
        self.receiver_running = False
        self.receiver_lock = threading.Lock()

    def identifier(self):
        return f"{self.host}:{self.port}"

    def start_server(self):
        """Start the TCP server to accept incoming connections."""
        if self.server_socket is not None:
            return  # Already running

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.server_socket.settimeout(1.0)  # 1 second timeout for accept

        self.running = True
        self.server_thread = threading.Thread(target=self._accept_connections, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        """Stop the TCP server."""
        self.running = False

        # Stop receiver thread
        self._stop_receiver_thread()

        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None

        if self.client_socket:
            self.client_socket.close()
            self.client_socket = None

        with self.connection_lock:
            self.connected = False

    def _accept_connections(self):
        """Accept incoming connections."""
        while self.running:
            try:
                client_socket, client_address = self.server_socket.accept()
                with self.connection_lock:
                    if self.client_socket:
                        # Close existing connection
                        self.client_socket.close()
                        self._stop_receiver_thread()

                    self.client_socket = client_socket
                    self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.connected = True
                    print(f"Client connected from {client_address}")

                    # Start receiver thread for this connection
                    self._start_receiver_thread()

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
                break

    def close(self):
        """Close the interface and stop the server."""
        self.running = False
        self.stop_server()

    def _ensure_connected(self):
        """Ensure a client is connected."""
        with self.connection_lock:
            if not self.connected or self.client_socket is None:
                # Instead of raising an error, wait for reconnection
                self._wait_for_reconnection()

    def _handle_connection_loss(self):
        """Handle connection loss by marking as disconnected."""
        with self.connection_lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except:
                    pass
                self.client_socket = None
            self.connected = False
            print("Client disconnected, waiting for reconnection...")

        # Stop receiver thread when connection is lost
        self._stop_receiver_thread()

    def _wait_for_reconnection(self):
        """Wait for a client to reconnect."""
        print("Waiting for client to reconnect...")
        while True:
            with self.connection_lock:
                if self.connected or not self.running:
                    break
            time.sleep(0.1)  # Wait for reconnection
        if not self.running:
            raise InterfaceError("Interface is shutting down")
        print("Client reconnected!")

    def _start_receiver_thread(self):
        """Start the receiver thread for reading messages from the client socket."""
        with self.receiver_lock:
            if self.receiver_running:
                return  # Already running

            self.receiver_running = True
            self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.receiver_thread.start()

    def _stop_receiver_thread(self):
        """Stop the receiver thread."""
        with self.receiver_lock:
            if not self.receiver_running:
                return  # Already stopped

            self.receiver_running = False

        # Wait for receiver thread to finish
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=1.0)

    def _receiver_loop(self):
        """Background thread that continuously reads messages from the client socket."""
        while self.receiver_running:
            try:
                with self.connection_lock:
                    if not self.connected or self.client_socket is None:
                        break
                    socket_to_use = self.client_socket

                if socket_to_use is None:
                    break

                # Set a timeout for the socket to allow checking receiver_running
                socket_to_use.settimeout(0.1)

                # Read message length (2 bytes)
                length_data = bytearray(2)
                bytes_received = 0
                while bytes_received < 2 and self.receiver_running:
                    try:
                        chunk = socket_to_use.recv(2 - bytes_received)
                        if len(chunk) == 0:
                            # Connection closed
                            self._handle_connection_loss()
                            break
                        length_data[bytes_received:bytes_received + len(chunk)] = chunk
                        bytes_received += len(chunk)
                    except socket.timeout:
                        continue  # Check receiver_running and try again
                    except (socket.error, ConnectionError):
                        self._handle_connection_loss()
                        break

                if not self.receiver_running or bytes_received < 2:
                    break

                frame_len = struct.unpack("<H", length_data)[0]

                # Read response data
                response_data = bytearray(frame_len)
                bytes_received = 0
                while bytes_received < frame_len and self.receiver_running:
                    try:
                        chunk = socket_to_use.recv(frame_len - bytes_received)
                        if len(chunk) == 0:
                            # Connection closed
                            self._handle_connection_loss()
                            break
                        response_data[bytes_received:bytes_received + len(chunk)] = chunk
                        bytes_received += len(chunk)
                    except socket.timeout:
                        continue  # Check receiver_running and try again
                    except (socket.error, ConnectionError):
                        self._handle_connection_loss()
                        break

                if not self.receiver_running or bytes_received < frame_len:
                    break

                # Put the complete message on the queue
                try:
                    resp_code, data = self._unpack_response(frame_len, response_data)
                    if resp_code == self.RESP_POLL:
                        # Poll response, handle separately if needed
                        self.poll_response_queue.put(data, timeout=0.1)
                    else:
                        self.response_queue.put((resp_code, data), timeout=0.1)
                except queue.Full:
                    # Queue is full, drop the message (this shouldn't happen in normal operation)
                    print("Warning: Message queue is full, dropping message")

            except Exception as e:
                if self.receiver_running:
                    print(f"Error in receiver loop: {e}")
                    self._handle_connection_loss()
                break

    def _pack_frame(self, cmd_code, data):
        """
        Pack a command frame: [16-bit length][8-bit cmd][data]
        """
        if len(data) > self.MAX_FRAME_SIZE - 3:
            raise ValueError("Data too large for frame")

        frame_len = len(data) + 1  # +1 for cmd code
        frame = struct.pack("<HB", frame_len, cmd_code) + data
        return frame

    def _unpack_response(self, frame_len, response_data):
        """
        Unpack a response frame: [8-bit resp_code][data]
        Returns (resp_code, data)
        """
        if frame_len < 1:
            raise ValueError("Response too short")

        resp_code = response_data[0]
        data = response_data[1:]
        return resp_code, data

    def _send_command(self, cmd_code, data=b"", timeout=None):
        """
        Send a command and receive response from the message queue
        """
        self._ensure_connected()

        if cmd_code == 1 and data == b"\x05\x00":
            if self.poll_response_queue.empty():
                return self.RESP_OK, b'\x00\x00'
            else:
                return self.RESP_OK, self.poll_response_queue.get()

        # Pack and send command
        frame = self._pack_frame(cmd_code, data)
        try:
            self.client_socket.send(frame)
        except (socket.error, ConnectionError):
            raise ConnectionError("Connection lost during send")

        # Wait for response from the message queue
        try:
            if timeout is not None:
                resp_code, response_data = self.response_queue.get(timeout=timeout)
            else:
                resp_code, response_data = self.response_queue.get()
            return resp_code, response_data
        except queue.Empty:
            raise ReceiveTimeout("Timeout waiting for response")

    def _transmit_receive(self, outbound_frames, response_lengths, timeout):
        if len(response_lengths) != len(outbound_frames):
            raise ValueError('Response lengths length must equal outbound frames length')

        # Check if we need to wait for reconnection before processing any frames
        with self.connection_lock:
            if not self.connected:
                self._wait_for_reconnection()

        # Expand messages before sending.
        frames = [(address, _normalize_and_expand_frame(frame)) for (address, frame) in outbound_frames]

        responses = []
        for frame in frames:
            address, message = frame
            # Check if this is a PollAck command (FrameFormat.WORD_DATA with POLL_ACK command)
            if (len(message) == 2 and
                message[0] == 0x00 and
                message[1] == 0x11):  # POLL_ACK command word
                # PollAck is generated by the interface automatically
                responses.append(_decode_frame(b'\x00\x00')) # Always succeed
            else:
                try:
                    resp_code, data = self._send_command(self.CMD_TRANSACT, message, timeout)

                    if resp_code == self.RESP_OK:
                        responses.append(_decode_frame(data))
                    elif resp_code == self.RESP_TIMEOUT:
                        responses.append(ReceiveTimeout())
                    elif resp_code == self.RESP_ERROR:
                        responses.append(ReceiveError(f'TCP error: {data.decode("ascii", errors="replace")}'))
                    elif resp_code == self.RESP_INVALID_CMD:
                        responses.append(ReceiveError('TCP invalid command'))
                    elif resp_code == self.RESP_INVALID_LENGTH:
                        responses.append(ReceiveError('TCP invalid length'))
                    else:
                        responses.append(ReceiveError(f'TCP unknown response code: {resp_code}'))

                except socket.timeout:
                    responses.append(ReceiveTimeout())
                except (socket.error, ConnectionError) as e:
                    # Handle connection loss gracefully - mark as disconnected and wait for reconnection
                    self._handle_connection_loss()
                    # Wait for reconnection and then retry the command
                    try:
                        self._wait_for_reconnection()
                        # Retry the command after reconnection
                        resp_code, data = self._send_command(self.CMD_TRANSACT, message, timeout)
                        if resp_code == self.RESP_OK:
                            responses.append(_decode_frame(data))
                        else:
                            responses.append(ReceiveTimeout())  # Use timeout for other errors
                    except Exception:
                        # If retry fails, use timeout to keep program running
                        responses.append(ReceiveTimeout())

        return responses

    def wait_for_connection(self, timeout=None):
        """Wait for a client to connect."""
        start_time = time.time()
        while True:
            with self.connection_lock:
                if self.connected:
                    break
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError("Timeout waiting for client connection")
            time.sleep(0.1)

    def is_connected(self):
        """Check if a client is currently connected."""
        with self.connection_lock:
            return self.connected

    def get_connection_status(self):
        """Get detailed connection status."""
        with self.connection_lock:
            return {
                'connected': self.connected,
                'running': self.running,
                'host': self.host,
                'port': self.port
            }


def _normalize_and_expand_frame(frame):
    (words, repeat_count, repeat_offset) = normalize_frame(frame)
    # Uncompress the run-length encoded tail of the message
    if repeat_count > 0:
        words = words[repeat_offset:] * repeat_count

    message = b''
    for i in range(len(words)):
        message += struct.pack('<h', words[i])

    return message


def _decode_frame(message):
    assert len(message) % 2 == 0
    return struct.unpack('<%dh' % int(len(message)/2), message)


@contextmanager
def open_tcp_interface(spec=None):
    """Returns a 3270 coax TCP server interface."""
    host, port = split_host_port(spec) if spec else ("0.0.0.0", None)
    interface = TcpInterface(host, port)
    try:
        interface.start_server()
        yield interface
    finally:
        interface.close()
