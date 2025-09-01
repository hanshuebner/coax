#!/usr/bin/env python3
"""
Example 15: TCP Interface Server
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This example demonstrates how to use the TCP interface as a server that
accepts incoming connections from clients.

Usage:
    python3 15_tcp_interface.py [<host>[:<port>]]

Example:
    python3 15_tcp_interface.py                    # Listen on 0.0.0.0:3174
    python3 15_tcp_interface.py localhost          # Listen on localhost:3174
    python3 15_tcp_interface.py 0.0.0.0:3278      # Listen on 0.0.0.0:3278
"""

import sys
import time
from coax import open_tcp_interface, Poll, ReadTerminalId, ReadData


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else None

    if spec:
        print(f"Starting TCP server on {spec}...")
    else:
        print("Starting TCP server on 0.0.0.0:3174...")

    try:
        with open_tcp_interface(spec) as interface:
            print(f"TCP server started on {interface.identifier()}")
            print("Waiting for client connections...")

            # Wait for a client to connect
            interface.wait_for_connection()
            print("Client connected! Ready to process commands.")

            # Keep the server running and process commands
            while interface.is_connected():
                try:
                    # Test 1: Poll the interface
                    print("\n1. Polling interface...")
                    response = interface.execute(Poll())
                    print(f"Poll response: {response}")

                    # Test 2: Read terminal ID
                    print("\n2. Reading terminal ID...")
                    response = interface.execute(ReadTerminalId())
                    print(f"Terminal ID: {response}")

                    # Test 3: Read data from address 0
                    print("\n3. Reading data from address 0...")
                    response = interface.execute(ReadData(0))
                    print(f"Data at address 0: {response}")

                    # Wait a bit before next iteration
                    time.sleep(5)

                except Exception as e:
                    print(f"Error processing command: {e}")
                    if not interface.is_connected():
                        print("Client disconnected")
                        break
                    time.sleep(1)

    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
