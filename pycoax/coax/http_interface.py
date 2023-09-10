"""
coax.http_interface
~~~~~~~~~~~~~~~~~~~~~
"""
import struct

from contextlib import contextmanager
import requests as requests

from .exceptions import ReceiveError, InterfaceError, ReceiveTimeout
from coax.interface import normalize_frame, Interface


class HttpInterface(Interface):
    """HTTP attached 3270 coax interface."""

    def __init__(self, url):
        if url is None:
            raise ValueError('URL is required')

        super().__init__()

        self.url = url
        self.session = requests.Session()

    def identifier(self):
        return self.url

    def close(self):
        self.session.close()

    def _transmit_receive(self, outbound_frames, response_lengths, timeout):
        if len(response_lengths) != len(outbound_frames):
            raise ValueError('Response lengths length must equal outbound frames length')

        # response_lengths are not used in the http interface.  interface3 always uses a receive
        # buffer of the maximum size and truncates it to the length of the actual frame received.

        # Expand messages before sending.
        frames = [(address, _normalize_and_expand_frame(frame)) for (address, frame) in outbound_frames]

        responses = []
        for frame in frames:
            address, message = frame
            headers = {'Accept-Encoding': None}
            if address is not None:
                headers['X-Station-Address'] = str(address)
            try:
                if timeout is not None:
                    headers['X-3270-Timeout'] = str(int(timeout * 1000))
                response = self.session.post(self.url,
                                             data=message,
                                             headers=headers)
#                print(f'status {response.status_code} headers {response.headers} body {response.content}')
                if response.status_code == 200:
                    responses.append(_decode_frame(response.content))
                elif response.status_code == 408:
                    responses.append(ReceiveTimeout())
                else:
                    responses.append(ReceiveError('HTTP status code %d: %s' % (response.status_code, str(response.content, 'ascii'))))
            except requests.exceptions.Timeout:
                responses.append(ReceiveTimeout())
            except requests.exceptions.RequestException as e:
                responses.append(InterfaceError(str(e)))

        return responses


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
def open_http_interface(url):
    """Returns a 3270 coax interface connected through HTTP."""
    yield HttpInterface(url)
