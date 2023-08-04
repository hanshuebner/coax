#!/usr/bin/env python

import sys
import time
from coax import open_http_interface, Poll, PollAck
from coax.protocol import FrameFormat

def poll(url):
    with open_http_interface(url) as interface:
        while True:
            responses = interface._transmit_receive(outbound_frames=[(None, [FrameFormat.DATA, [1]])],
                                                    response_lengths=[2],
                                                    timeout=1)
            print(responses[0], end="")
            sys.stdout.flush()

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("missing <url> argument")
        sys.exit(1)
    url = sys.argv[1]
    print("Polling %s" % url)
    poll(url)
