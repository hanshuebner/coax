import time
import unittest
from functools import partial
from queue import Queue

from coax import HttpInterface, Poll, ReceiveTimeout
from tests import http_server


class HttpIntegrationTest(unittest.TestCase):
    class HttpHandler(http_server.RequestHandler):
        def __init__(self, queue, *args, **kwargs):
            self.queue = queue
            super().__init__(*args, **kwargs)

        def transact(self, request_body) -> bytes:
            response_body = b'\x00\x00'
            self.queue.put((self, request_body, response_body))
            return response_body

    def setUp(self) -> None:
        self.queue = Queue()
        self.httpd = http_server.run(handler_class=partial(HttpIntegrationTest.HttpHandler, self.queue), port=0)
        port = self.httpd.socket.getsockname()[1]
        self.interface = HttpInterface('http://127.0.0.1:{0}/transact'.format(port))

    def tearDown(self) -> None:
        self.interface.close()
        self.httpd.server_close()

    def test_poll_is_processed(self):
        self.assertIsNone(self.interface.execute(Poll(), timeout=1))
        _, request, response = self.queue.get()
        self.assertEqual(request, b'\x05\00')
        self.assertEqual(response, b'\x00\x00')

    def test_connection_is_persistent(self):
        self.assertIsNone(self.interface.execute(Poll(), timeout=1))
        handler, _, _ = self.queue.get()
        address1 = handler.client_address
        self.assertIsNone(self.interface.execute(Poll(), timeout=1))
        handler, _, _ = self.queue.get()
        address2 = handler.client_address
        self.assertEqual(address1, address2)


class HttpTimeoutTest(unittest.TestCase):
    class HttpHandler(http_server.RequestHandler):
        def transact(self, request_body) -> bytes:
            time.sleep(1)
            return b'\x00\x00'

    def setUp(self) -> None:
        self.httpd = http_server.run(handler_class=HttpTimeoutTest.HttpHandler, port=0)
        port = self.httpd.socket.getsockname()[1]
        self.interface = HttpInterface('http://127.0.0.1:{0}/transact'.format(port))

    def tearDown(self) -> None:
        self.interface.close()
        self.httpd.server_close()

    def test_timeout_is_raised(self):
        with self.assertRaises(ReceiveTimeout):
            self.interface.execute(Poll(), timeout=0.1)


if __name__ == '__main__':
    unittest.main()
