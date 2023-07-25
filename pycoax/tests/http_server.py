import http.server
import socketserver
import struct
import _thread as thread
from threading import Event

from coax.protocol import is_data_word, Command


class RequestHandler(http.server.BaseHTTPRequestHandler):
    def respond(self, status, body, headers=None):
        if headers is None:
            headers = {}
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'text/plain'
        self.send_response(status)
        for header in headers:
            self.send_header(header, headers[header])
        self.end_headers()
        if isinstance(body, (bytes, bytearray)):
            self.wfile.write(body)
        else:
            self.wfile.write(bytes(str(body), 'ascii'))

    def transact(self, request_body) -> bytes:
        print(_format_frame(request_body))
        first_word = struct.unpack("<h", request_body[:2])[0]
        if not is_data_word(first_word):
            command = _command_name(first_word)
            if command == 'READ_TERMINAL_ID':
                return struct.pack("<h", 0b00000100_00)
        return b'\x00\x00'

    def handle_one_request(self) -> None:
        try:
            super().handle_one_request()
        except ConnectionResetError:
            pass
        except BrokenPipeError:
            pass

    def do_POST(self):
        if self.path != '/transact':
            return self.respond(404, 'Not found')

        content_length = int(self.headers.get('Content-Length', -1))
        if content_length == -1:
            return self.respond(400, 'Missing Content-Length header')

        if content_length % 2 != 0 or content_length < 2:
            return self.respond(400, 'Invalid content length (%d)' % content_length)

        # Read the request body
        request_body = self.rfile.read(content_length)

        # Create the response
        response_body = self.transact(request_body)

        self.respond(200, response_body, headers={
            'Content-Type': 'application/octet-stream',
            'Content-Length': str(len(response_body)),
            'Connection': 'keep-alive',
        })

    def method_not_allowed(self):
        self.respond(405, 'Method Not Allowed')

    do_GET = method_not_allowed
    do_PUT = method_not_allowed
    do_DELETE = method_not_allowed
    do_HEAD = method_not_allowed

    def log_request(self, code='-', size='-'):
        pass

valid_command_values = set(item.value for item in Command)

def _command_name(word):
    assert not is_data_word(word)
    value = word >> 2
    if value in valid_command_values:
        return Command(value).name
    elif value & 0x0f in valid_command_values:
        return Command(value & 0x0f).name

def _format_word(word):
    value = word >> 2
    if is_data_word(word):
        return "{0:02x}".format(value)
    else:
        if value in valid_command_values:
            return Command(value).name
        elif value & 0x0f in valid_command_values:
            return Command(value & 0x0f).name
        else:
            return "UNKNOWN COMMAND 0x{0:02x} (flags {1:02b})".format(value, word & 0x03)

def _format_frame(frame):
    words = struct.unpack("<{0}h".format(len(frame)//2), frame)
    return ' '.join([_format_word(word) for word in words])


def run(server_class=socketserver.ThreadingTCPServer, handler_class=RequestHandler, port=8771):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.allow_reuse_address = True
    httpd.protocol_version = "HTTP/1.1"
    thread.start_new_thread(httpd.serve_forever, ())
    return httpd

if __name__ == '__main__':
    httpd = run()
    Event().wait()
