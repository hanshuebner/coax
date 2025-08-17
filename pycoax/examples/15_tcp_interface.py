#!/usr/bin/env python3
"""
Example 15: TCP Interface
~~~~~~~~~~~~~~~~~~~~~~~~~

This example demonstrates how to use the TCP interface to connect to
Interface 3 over TCP/IP network.

Usage:
    python3 15_tcp_interface.py <host>[:<port>]

Example:
    python3 15_tcp_interface.py 192.168.1.100
    python3 15_tcp_interface.py 192.168.1.100:3278
"""

import sys
from coax import open_tcp_interface, Poll, ReadTerminalId, ReadData


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec = sys.argv[1]

    print(f"Connecting to {spec}...")

    try:
        with open_tcp_interface(spec) as interface:
            print(f"Connected to {interface.identifier()}")

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

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
