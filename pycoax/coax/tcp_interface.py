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
    """TCP client 3270 coax interface for individual connections."""

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

    def __init__(self, client_socket):
        super().__init__()

        self.client_socket = client_socket
        self.client_address = client_socket.getpeername()
        self.receiver_thread = None
        self.connected = True
        # Queue for response messages from the receiver thread
        self.response_queue = queue.Queue()
        self.poll_response_queue = queue.Queue()
        self.receiver_running = False

        # Start the receiver thread for this connection
        self._start_receiver_thread()

    def identifier(self):
        return f"{self.client_address[0]}:{self.client_address[1]}"

    def close(self):
        """Close the interface and stop the receiver thread."""
        self.connected = False
        self._stop_receiver_thread()

        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None

    def _ensure_connected(self):
        """Ensure a client is connected."""
        if not self.connected or self.client_socket is None:
            raise InterfaceError("Client connection lost")

    def _handle_connection_loss(self):
        """Handle connection loss by marking as disconnected."""
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
            self.client_socket = None
        self.connected = False
        print(f"Client {self.client_address} disconnected")

        # Stop receiver thread when connection is lost
        self._stop_receiver_thread()

    def _start_receiver_thread(self):
        """Start the receiver thread for reading messages from the client socket."""
        if self.receiver_running:
            return  # Already running

        self.receiver_running = True
        self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
        self.receiver_thread.start()

    def _stop_receiver_thread(self):
        """Stop the receiver thread."""
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
                    import time
                    unpack_start = time.perf_counter()
                    resp_code, data = self._unpack_response(frame_len, response_data)
                    unpack_time = time.perf_counter()
                    unpack_duration = (unpack_time - unpack_start) * 1000

                    queue_put_start = time.perf_counter()
                    if resp_code == self.RESP_POLL:
                        # Poll response, handle separately if needed
                        self.poll_response_queue.put(data, timeout=0.1)
                    else:
                        self.response_queue.put((resp_code, data), timeout=0.1)
                    queue_put_time = time.perf_counter()
                    queue_put_duration = (queue_put_time - queue_put_start) * 1000

                    if unpack_duration > 1.0 or queue_put_duration > 1.0:
                        print(f"TCP receiver: unpack={unpack_duration:.2f}ms, queue_put={queue_put_duration:.2f}ms, frame_len={frame_len}")
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
            import time
            send_start = time.perf_counter()
            bytes_sent = self.client_socket.send(frame)
            send_time = time.perf_counter()
            send_duration = (send_time - send_start) * 1000
            if send_duration > 1.0:  # Log if send takes more than 1ms
                print(f"TCP send took {send_duration:.2f}ms, bytes={bytes_sent}, frame_len={len(frame)}, cmd={cmd_code}, data_len={len(data)}")
        except (socket.error, ConnectionError):
            raise ConnectionError("Connection lost during send")

        # Wait for response from the message queue
        try:
            import time
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
        if not self.connected:
            raise InterfaceError("Client connection lost")

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
                    # Handle connection loss gracefully
                    self._handle_connection_loss()
                    responses.append(ReceiveTimeout())

        return responses

    def is_connected(self):
        """Check if a client is currently connected."""
        return self.connected

    def get_connection_status(self):
        """Get detailed connection status."""
        return {
            'connected': self.connected,
            'client_address': self.client_address
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
def open_tcp_interface(client_socket):
    """Returns a 3270 coax TCP client interface for a specific connection."""
    interface = TcpInterface(client_socket)
    try:
        yield interface
    finally:
        interface.close()
