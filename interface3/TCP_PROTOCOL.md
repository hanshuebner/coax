# Interface 3 TCP Protocol

This document describes the simplified TCP-based protocol for communication between the OEC client and Interface 3 server.

## Protocol Overview

The protocol uses frame-based communication over TCP with the following structure:

```
[16-bit length][8-bit command/response code][data]
```

- **Length**: 16-bit little-endian integer indicating the total frame length (including command/response code)
- **Command/Response Code**: 8-bit code identifying the operation
- **Data**: Variable-length payload (limited to 2KB total frame size)

## Frame Format

### Command Frame
```
[16-bit length][8-bit cmd_code][data]
```

### Response Frame
```
[16-bit length][8-bit resp_code][data]
```

## Command Codes

| Code | Name | Description |
|------|------|-------------|
| 0x01 | CMD_TRANSACT | Send data to coax interface and receive response |
| 0x02 | CMD_PING | Simple ping/echo for testing |

## Response Codes

| Code | Name | Description |
|------|------|-------------|
| 0x00 | RESP_OK | Command executed successfully |
| 0x01 | RESP_ERROR | General error occurred |
| 0x02 | RESP_TIMEOUT | Transaction timed out |
| 0x03 | RESP_INVALID_CMD | Unknown command code |
| 0x04 | RESP_INVALID_LENGTH | Frame length invalid |

## Communication Flow

1. Client connects to server (default port 3278)
2. Client sends command frame
3. Server processes command and sends response frame
4. Repeat steps 2-3 for additional commands
5. Client disconnects when done

## Implementation Details

### Server (Interface 3)
- File: `src/tcp.py`
- Uses static buffers to minimize memory allocation
- Maximum frame size: 2KB
- Supports multiple commands per connection
- LED indicators for network activity and errors
- Direct TCP read/write without intermediate buffers

### Client (OEC)
- Example implementation: `test_tcp_client.py`
- Demonstrates how to pack/unpack frames
- Shows proper error handling

## Usage Examples

### Starting the Server
```python
# On Interface 3
import tcp
tcp.serve()
```

### Client Connection
```python
import socket
import struct

# Connect to server
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('192.168.1.100', 3278))

# Send ping command
frame = struct.pack("<HB", 1, 0x03)  # length=1, cmd=PING
sock.send(frame)

# Read response
length_data = sock.recv(2)
frame_len = struct.unpack("<H", length_data)[0]
response = sock.recv(frame_len)
resp_code, data = struct.unpack("<B", response[0]), response[1:]

sock.close()
```

## Protocol Constraints

- Maximum frame size: 2048 bytes
- Data for CMD_TRANSACT must have even length (coax requirement)
- Server uses static buffers to avoid memory fragmentation
- Connection is maintained for multiple commands
- No authentication or encryption (for simplicity)

## Error Handling

- Invalid frame lengths are rejected
- Unknown commands return RESP_INVALID_CMD
- Coax timeouts return RESP_TIMEOUT
- Network errors close the connection
- All errors include descriptive messages

## Testing

Use the provided test client to verify the protocol:

```bash
python3 test_tcp_client.py <interface3_ip>
```

This will test all available commands and demonstrate proper frame handling.
