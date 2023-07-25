import re
import socket
import gc
from machine import Pin, Timer
import wifi
import coax

PORT = 80 # port to listen on for http requests

def send_response(client, status, status_string, header, body=None):
    print(status, status_string, len(body))
    client.send("HTTP/1.0 " + str(status) + " " + status_string + "\r\n")
    client.send("Connection: keep-alive\r\n")
    if body is not None and len(body) > 0:
        client.send("Content-Length: %d\r\n" % (len(body)))
    for key in header:
        client.send(key + ": " + str(header[key]) + "\r\n")
    client.send("\r\n")
    client.send(body)


HEADER_SPLIT_RE = re.compile(": *")

def handle_request(method, path, content_length, body):
    if method == 'POST' and path == '/transact':
        if content_length is None or (content_length % 1) == 1 or content_length == 0:
            return 400, "Bad request", {"Content-Type": "text/plain"}, "Invalid Content-Length header, needs to be even number of bytes"
        rx_buf = coax.transact(body)
        return 200, "OK", {"Content-Type": "application/octet-stream"}, rx_buf

    if method == 'POST' and path == '/demo':
        coax.demo()
        return 200, "OK", {"Content-Type": "text/plain"}, "DEMO EXECUTED"

    return 404, "Not found", {"Content-Type": "text/plain"}, "The requested resource was not found"


def handle_client(client):
    client_file = client.makefile('rw', 0)

    while True:
        request = client_file.readline()
        if len(request) == 0:
            # connection closed
            break

        # Read request header
        content_length = None
        connection_header = None
        body = None
        while True:
            line = client_file.readline()
            if not line or line == b'\r\n':
                break
            header, value = HEADER_SPLIT_RE.split(str(line, 'ascii')[:-2], 1)
            header = header.lower()
            if header == 'content-length':
                content_length = int(value)
            elif header == 'connection':
                connection_header = value

        # Read request body, if any
        if content_length is not None:
            body = client.read(int(content_length))

        try:
            method, path, _protocol = str(request, 'utf-8').split()
        except ValueError as e:
            print("could not parse request: ", e)
            client.close()
            break

        print(method, path, content_length)

        try:
            status, status_string, headers, body = handle_request(method, path, content_length, body)
            send_response(client, status, status_string, headers, body)

        except Exception as e:
            print("error", e)
            send_response(client, 500, "Internal server error",
                          {"Content-Type": "text/plain"},
                          str(e))

        gc.collect()
        if connection_header != 'keep-alive':
            break

    client.close()


def serve():
    listen_addr = socket.getaddrinfo('0.0.0.0', PORT)[0][-1]

    listen_socket = socket.socket()
    listen_socket.bind(listen_addr)
    listen_socket.listen(1)

    print('Listening on port', PORT)

    # Listen for connections
    try:
        while True:
            try:
                led = Pin("LED", Pin.OUT)
                timer = Timer()
                timer.init(freq=1, mode=Timer.PERIODIC, callback=wifi.blink)
                client, _client_addr = listen_socket.accept()
                timer.deinit()
                led.on()

                handle_client(client)

            except Exception as e:
                print('error handling client:', e)
                client.close()

    except KeyboardInterrupt:
        print("interrupted")

    finally:
        print("closing listening socket")
        listen_socket.close()
