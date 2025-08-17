import unittest
from unittest.mock import Mock, create_autospec, patch, call
import socket
import struct

import context

from coax.tcp_interface import TcpInterface, split_host_port, open_tcp_interface
from coax.exceptions import InterfaceError, ReceiveTimeout, ReceiveError
from coax.interface import FrameFormat


class SplitHostPortTestCase(unittest.TestCase):
    def test_host_only(self):
        # Act
        host, port = split_host_port("localhost")

        # Assert
        self.assertEqual(host, "localhost")
        self.assertIsNone(port)

    def test_host_with_port(self):
        # Act
        host, port = split_host_port("192.168.1.100:8080")

        # Assert
        self.assertEqual(host, "192.168.1.100")
        self.assertEqual(port, 8080)

    def test_host_with_default_port(self):
        # Act
        host, port = split_host_port("example.com:3278")

        # Assert
        self.assertEqual(host, "example.com")
        self.assertEqual(port, 3278)

    def test_invalid_format(self):
        # Act and assert
        with self.assertRaisesRegex(ValueError, "Invalid host:port string"):
            split_host_port("invalid:format:here")

    def test_empty_string(self):
        # Act and assert
        with self.assertRaisesRegex(ValueError, "Invalid host:port string"):
            split_host_port("")


class TcpInterfaceInitializationTestCase(unittest.TestCase):
    def test_host_required(self):
        # Act and assert
        with self.assertRaisesRegex(ValueError, "Host is required"):
            TcpInterface(None)

    def test_default_port(self):
        # Act
        interface = TcpInterface("localhost")

        # Assert
        self.assertEqual(interface.host, "localhost")
        self.assertEqual(interface.port, TcpInterface.TCP_PORT)
        self.assertIsNone(interface.socket)

    def test_custom_port(self):
        # Act
        interface = TcpInterface("localhost", 8080)

        # Assert
        self.assertEqual(interface.host, "localhost")
        self.assertEqual(interface.port, 8080)
        self.assertIsNone(interface.socket)

    def test_identifier(self):
        # Act
        interface = TcpInterface("localhost", 8080)

        # Assert
        self.assertEqual(interface.identifier(), "localhost:8080")


class TcpInterfaceConnectionTestCase(unittest.TestCase):
    def setUp(self):
        self.interface = TcpInterface("localhost", 8080)
        self.mock_socket = create_autospec(socket.socket, instance=True)
        self.interface.socket = self.mock_socket

    def test_close_with_socket(self):
        # Act
        self.interface.close()

        # Assert
        self.mock_socket.close.assert_called_once()
        self.assertIsNone(self.interface.socket)

    def test_close_without_socket(self):
        # Arrange
        self.interface.socket = None

        # Act
        self.interface.close()

        # Assert
        self.assertIsNone(self.interface.socket)

    @patch('socket.socket')
    def test_ensure_connected_creates_socket(self, mock_socket_class):
        # Arrange
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        self.interface.socket = None

        # Act
        self.interface._ensure_connected()

        # Assert
        mock_socket_class.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.connect.assert_called_once_with(("localhost", 8080))
        self.assertEqual(self.interface.socket, mock_socket)

    @patch('socket.socket')
    def test_ensure_connected_reuses_existing_socket(self, mock_socket_class):
        # Act
        self.interface._ensure_connected()

        # Assert
        mock_socket_class.assert_not_called()
        self.mock_socket.connect.assert_not_called()


class TcpInterfaceFramePackingTestCase(unittest.TestCase):
    def setUp(self):
        self.interface = TcpInterface("localhost")

    def test_pack_frame(self):
        # Act
        frame = self.interface._pack_frame(0x01, b"test data")

        # Assert
        expected = struct.pack("<HB", 10, 0x01) + b"test data"
        self.assertEqual(frame, expected)

    def test_pack_frame_empty_data(self):
        # Act
        frame = self.interface._pack_frame(0x02, b"")

        # Assert
        expected = struct.pack("<HB", 1, 0x02)
        self.assertEqual(frame, expected)

    def test_pack_frame_too_large(self):
        # Arrange
        large_data = b"x" * (self.interface.MAX_FRAME_SIZE - 2)

        # Act and assert
        with self.assertRaisesRegex(ValueError, "Data too large for frame"):
            self.interface._pack_frame(0x01, large_data)

    def test_unpack_response(self):
        # Arrange
        response_data = b"\x00test response"
        frame_len = len(response_data)

        # Act
        resp_code, data = self.interface._unpack_response(frame_len, response_data)

        # Assert
        self.assertEqual(resp_code, 0x00)
        self.assertEqual(data, b"test response")

    def test_unpack_response_empty_data(self):
        # Arrange
        response_data = b"\x01"
        frame_len = len(response_data)

        # Act
        resp_code, data = self.interface._unpack_response(frame_len, response_data)

        # Assert
        self.assertEqual(resp_code, 0x01)
        self.assertEqual(data, b"")

    def test_unpack_response_too_short(self):
        # Act and assert
        with self.assertRaisesRegex(ValueError, "Response too short"):
            self.interface._unpack_response(0, b"")


class TcpInterfaceSendCommandTestCase(unittest.TestCase):
    def setUp(self):
        self.interface = TcpInterface("localhost")
        self.mock_socket = create_autospec(socket.socket, instance=True)
        self.interface.socket = self.mock_socket

    def test_send_command_success(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 5),  # Length: 5 bytes
            b"\x00test"  # Response: OK + data
        ]

        # Act
        resp_code, data = self.interface._send_command(0x01, b"test data")

        # Assert
        self.assertEqual(resp_code, 0x00)
        self.assertEqual(data, b"test")
        self.mock_socket.send.assert_called_once()
        self.assertEqual(self.mock_socket.settimeout.call_count, 0)

    def test_send_command_with_timeout(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 1),  # Length: 1 byte
            b"\x00"  # Response: OK
        ]

        # Act
        resp_code, data = self.interface._send_command(0x01, b"test", timeout=1.5)

        # Assert
        self.assertEqual(resp_code, 0x00)
        self.assertEqual(data, b"")
        self.mock_socket.settimeout.assert_called_once_with(1.5)

    def test_send_command_connection_closed_during_length_read(self):
        # Arrange
        self.mock_socket.recv.return_value = b""

        # Act and assert
        with self.assertRaisesRegex(ConnectionError, "Connection closed"):
            self.interface._send_command(0x01, b"test")

    def test_send_command_connection_closed_during_data_read(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 5),  # Length: 5 bytes
            b"\x00",  # Partial response
            b""  # Connection closed
        ]

        # Act and assert
        with self.assertRaisesRegex(ConnectionError, "Connection closed"):
            self.interface._send_command(0x01, b"test")

    def test_send_command_socket_timeout(self):
        # Arrange
        self.mock_socket.recv.side_effect = socket.timeout

        # Act and assert
        with self.assertRaises(socket.timeout):
            self.interface._send_command(0x01, b"test", timeout=1.0)

    def test_send_command_socket_error(self):
        # Arrange
        self.mock_socket.recv.side_effect = socket.error("Network error")

        # Act and assert
        with self.assertRaises(socket.error):
            self.interface._send_command(0x01, b"test")


class TcpInterfaceTransmitReceiveTestCase(unittest.TestCase):
    def setUp(self):
        self.interface = TcpInterface("localhost")
        self.mock_socket = create_autospec(socket.socket, instance=True)
        self.interface.socket = self.mock_socket

    def test_transmit_receive_success(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 3),  # Length: 3 bytes
            b"\x00\x00\x00"  # Response: OK + 2 bytes of data
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0], (0,))
        self.mock_socket.send.assert_called_once()

    def test_transmit_receive_timeout_response(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 1),  # Length: 1 byte
            b"\x02"  # Response: TIMEOUT
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveTimeout)

    def test_transmit_receive_error_response(self):
        # Arrange
        error_msg = b"Test error message"
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", len(error_msg) + 1),  # Length
            b"\x01" + error_msg  # Response: ERROR + message
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveError)
        self.assertIn("Test error message", str(responses[0]))

    def test_transmit_receive_invalid_command_response(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 1),  # Length: 1 byte
            b"\x03"  # Response: INVALID_CMD
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveError)
        self.assertIn("TCP invalid command", str(responses[0]))

    def test_transmit_receive_invalid_length_response(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 1),  # Length: 1 byte
            b"\x04"  # Response: INVALID_LENGTH
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveError)
        self.assertIn("TCP invalid length", str(responses[0]))

    def test_transmit_receive_unknown_response_code(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 1),  # Length: 1 byte
            b"\x99"  # Response: Unknown code
        ]

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveError)
        self.assertIn("TCP unknown response code: 153", str(responses[0]))

    def test_transmit_receive_socket_timeout(self):
        # Arrange
        self.mock_socket.recv.side_effect = socket.timeout

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            1.0
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], ReceiveTimeout)

    def test_transmit_receive_socket_error(self):
        # Arrange
        self.mock_socket.recv.side_effect = socket.error("Network error")

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], InterfaceError)
        self.assertIn("Network error", str(responses[0]))

    def test_transmit_receive_connection_error(self):
        # Arrange
        self.mock_socket.recv.side_effect = ConnectionError("Connection lost")

        # Act
        responses = self.interface._transmit_receive(
            [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
            [1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 1)
        self.assertIsInstance(responses[0], InterfaceError)
        self.assertIn("Connection lost", str(responses[0]))

    def test_transmit_receive_multiple_frames(self):
        # Arrange
        self.mock_socket.recv.side_effect = [
            struct.pack("<H", 3),  # Length: 3 bytes
            b"\x00\x00\x00",  # Response: OK + 2 bytes of data
            struct.pack("<H", 3),  # Length: 3 bytes
            b"\x00\x01\x00"  # Response: OK + 2 bytes of data
        ]

        # Act
        responses = self.interface._transmit_receive(
            [
                (None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000])),
                (None, (FrameFormat.WORD_DATA, 0b1111111111, [0x00, 0xff]))
            ],
            [1, 1],
            None
        )

        # Assert
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0], (0,))
        self.assertEqual(responses[1], (1,))
        self.assertEqual(self.mock_socket.send.call_count, 2)

    def test_transmit_receive_response_lengths_mismatch(self):
        # Act and assert
        with self.assertRaisesRegex(ValueError, "Response lengths length must equal outbound frames length"):
            self.interface._transmit_receive(
                [(None, (FrameFormat.WORDS, [0b1111111111, 0b0000000000]))],
                [1, 2],
                None
            )


class TcpInterfaceContextManagerTestCase(unittest.TestCase):
    @patch('coax.tcp_interface.TcpInterface')
    def test_open_tcp_interface_context_manager(self, mock_tcp_interface_class):
        # Arrange
        mock_interface = create_autospec(TcpInterface, instance=True)
        mock_tcp_interface_class.return_value = mock_interface

        # Act
        with open_tcp_interface("localhost:8080") as interface:
            pass

        # Assert
        mock_tcp_interface_class.assert_called_once_with("localhost", 8080)
        mock_interface.close.assert_called_once()

    @patch('coax.tcp_interface.TcpInterface')
    def test_open_tcp_interface_with_exception(self, mock_tcp_interface_class):
        # Arrange
        mock_interface = create_autospec(TcpInterface, instance=True)
        mock_tcp_interface_class.return_value = mock_interface

        # Act and assert
        with self.assertRaises(ValueError):
            with open_tcp_interface("localhost:8080") as interface:
                raise ValueError("Test exception")

        # Assert
        mock_interface.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
